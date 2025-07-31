# src/doc_investigator_strategy_pattern/state_machine.py

"""
Defines the Burr state machine for orchestrating the document investigation workflow
and the caching mechanism for LLM prompt results.
OpenTelemetry traces are logging to Burr, visible via Burr UI as backend, that is called
with 'burr' CLI command on a second terminal in parallel to the app. The browser tab
opens automatically.

See: 
- https://blog.dagworks.io/p/9ef2488a-ff8a-4feb-b37f-1d9a781068ac
- https://blog.dagworks.io/p/burr-ui
- https://github.com/apache/burr/blob/main/examples/opentelemetry/application.py


Have in mind, when standard @action is executed, Burr passes the state to the function
as its own burr.core.state.State object, which must be handled like a dictionary,
not a Pydantic object (means no <state.attribute> implementation).
"""

# ----------
# Imports
# ----------
import os
import sqlite3
import hashlib
import json
from pydantic import BaseModel, Field
from typing import Tuple, Optional, List, Dict, Any

from burr.core import Action, State, ApplicationBuilder, default, when
from burr.core.action import action
# with our own pydantic basemodel we need a typing for our state object
from burr.integrations.pydantic import PydanticTypingSystem
from opentelemetry import trace
from loguru import logger
from pydantic import ValidationError

from .config import Config
from .database import InteractionLog, DatabaseManager
from .documents import DocumentProcessor, InvalidFileTypeException
from .services import GeminiService

# ----------
# Coding
# ----------

# Creation of pydantic model to inform about internal states and data structure
# It is used by the PydanticTypingSystem to manage the state between actions and
# for initialization, but the object passed into the action function itself is the
# dictionary-like State wrapper.
class InvestigationState(BaseModel):   
    # UI inputs
    files: Optional[List[Any]] = None
    prompt: Optional[str] = None
    llm_params: Dict[str, float] = Field(default_factory = dict)
    
    # processed data
    doc_names: str = ""
    extracted_text: str = ""
    llm_answer: str = ""
    
    # for flow control and state machine results
    is_real_answer: bool = False
    error_message: Optional[str] = None
    
    # user evaluation handling
    evaluation_choice: Optional[str] = None
    evaluation_reason: Optional[str] = None
    
    # logged data
    interaction_to_log: Optional[Dict] = None

    # fields to store actions result for conditional routing
    outcome: Optional[str] = None
    classification: Optional[str] = None
    hit: Optional[bool] = None
    cache_key: Optional[str] = None

    # required for pydantic,
    # allows arbitrary types like Gradio's file object
    class Config:
        arbitrary_types_allowed = True

@action(
    reads = [],
    writes = ["files", "prompt", "llm_params", "error_message", "outcome"]
)
def process_inputs(
    state: InvestigationState,
    doc_processor: DocumentProcessor,
    files: List[Any],
    prompt: str,
    llm_params: Dict[str, float],
) -> Tuple[dict, InvestigationState]:
    """Validates files and saves all initial inputs to the state."""
    
    # remember input values
    base_update = {"files": files, "prompt": prompt, "llm_params": llm_params}
    
    if not files:
        # update state with all inputs and error
        new_state = state.update(
            **base_update,
            error_message = "Please upload at least one document.",
            outcome = "failure"
        )
        return {}, new_state
    try:
        doc_processor.validate_files(files)
        logger.success("State machine: File validation successful.")
        # update state with all inputs and success
        new_state = state.update(
            **base_update,
            outcome = "success"
        )
        return {}, new_state
    except InvalidFileTypeException as e:
        logger.warning(f"State machine: File validation failed. Error: {e}")
        new_state = state.update(
            **base_update,
            error_message = str(e),
            outcome = "failure"
        )
        return {}, new_state

@action(
    reads = ["files", "config.MAX_CONTEXT_CHARACTERS"],
    writes = ["extracted_text", "doc_names"]
)
def process_documents(
    state: InvestigationState,
    doc_processor: DocumentProcessor,
    config: Config
) -> Tuple[dict, InvestigationState]:
    """Action to process documents and extract text."""
    full_text = doc_processor.process_files(state["files"])
    doc_names = ", ".join([os.path.basename(f.name) for f in state["files"]])
    if len(full_text) > config.MAX_CONTEXT_CHARACTERS:
        full_text = full_text[:config.MAX_CONTEXT_CHARACTERS]
        
    new_state = state.update(extracted_text = full_text, doc_names = doc_names)
    return {}, new_state

@action(
    reads = ["extracted_text", "prompt", "llm_params", "config"],
    writes = ["cache_key", "llm_answer", "hit"]
)
def check_cache(
    state: InvestigationState, db_manager: DatabaseManager, config: Config
) -> Tuple[dict, InvestigationState]:
    """Generates a cache key and checks if the answer exists in DB."""
    prompt = state["prompt"]
    llm_params = state["llm_params"]
    # stable string representation of LLM params
    params_str = json.dumps(llm_params, sort_keys = True)
    
    # sha256 cache key is a hash of all unique inputs
    key_material = (
        state["extracted_text"] + prompt + params_str + config.LLM_MODEL_NAME
    ).encode('utf-8')
    cache_key = hashlib.sha256(key_material).hexdigest()
    
    cached_answer = db_manager.get_cached_answer(cache_key)
    
    if cached_answer:
        # Cache HIT: put answer in the state and return "hit"
        new_state = state.update(llm_answer = cached_answer, cache_key = cache_key, hit = True)
        return {}, new_state
    
    # Cache MISS: save key for later and return "miss"
    new_state = state.update(cache_key = cache_key, hit = False)
    return {}, new_state

@action(
    reads = ["extracted_text", "prompt", "llm_params"],
    writes = ["llm_answer"]
)
def generate_answer(
    state: InvestigationState,
    ai_service: GeminiService
) -> Tuple[dict, InvestigationState]:
    """Action to call the AI service and get an answer."""
    answer = ai_service.get_answer(
        full_text_context = state["extracted_text"],
        user_prompt = state["prompt"],
        temperature = state["llm_params"]["temperature"],
        top_p = state["llm_params"]["top_p"],
    )
    new_state = state.update(llm_answer = answer)
    return {}, new_state

@action(
    reads = ["cache_key", "llm_answer"],
    writes = []
)
def update_cache(state: InvestigationState, db_manager: DatabaseManager) -> Tuple[dict, InvestigationState]:
    """Saves the newly generated answer to the cache if it is a 'real' one."""
    if state.get("is_real_answer"):
        db_manager.set_cached_answer(state["cache_key"], state["llm_answer"])
    return {}, state

@action(
    reads = ["llm_answer", "config"],
    writes = ["is_real_answer", "classification"]
)
def classify_answer(
    state: InvestigationState,
    config: Config
) -> Tuple[dict, InvestigationState]:
    """Action to classify the answer as real or predefined."""
    answer = state["llm_answer"]
    is_real = answer not in [config.UNKNOWN_ANSWER, config.NOT_ALLOWED_ANSWER] and "error" not in answer.lower()
    logger.info(f"State machine: Answer classified as {'real' if is_real else 'predefined'}.")
    classification_result = "real_answer" if is_real else "predefined_answer"
    new_state = state.update(is_real_answer = is_real, classification = classification_result)
    return {}, new_state

@action(
    reads = ["doc_names", "prompt", "llm_answer", "llm_params", "config"],
    writes = ["interaction_to_log"]
)
def auto_log_and_terminate(
    state: InvestigationState,
    config: Config,
    db_manager: DatabaseManager
) -> Tuple[dict, InvestigationState]:
    log_entry = InteractionLog(
        document_names = state["doc_names"],
        prompt = state["prompt"],
        answer = state["llm_answer"],
        output_passed = "no",
        eval_reason = "no reason given",
        model_name = config.LLM_MODEL_NAME,
        temperature = state["llm_params"]["temperature"],
        top_p = state["llm_params"]["top_p"],
    )
    try:
        db_manager.log_interaction(log_entry)
        new_state = state.update(interaction_to_log = log_entry.model_dump())
        return {"logged": True}, new_state
    except (ValidationError, sqlite3.Error) as e:
        logger.error(f"State machine: Failed to auto-log non-answer. Error: {e}")
        return {"logged": False, "error": str(e)}, state

@action(reads = [], writes = [])
def await_human_evaluation(state: InvestigationState) -> Tuple[dict, InvestigationState]:
    return {}, state

@action(  
    reads = ["config"],
    writes = ["interaction_to_log", "error_message", "evaluation_choice", "evaluation_reason"]
)
def process_human_evaluation(
    state: InvestigationState,
    config: Config,
    db_manager: DatabaseManager,
    # comes from 'inputs' to app.step():
    doc_names: str,
    prompt: str,
    llm_answer: str,
    llm_params: dict,
    evaluation_choice: str,  
    evaluation_reason: str,
) -> Tuple[dict, InvestigationState]:
    
    choice = evaluation_choice
    reason = evaluation_reason
    evaluation_text = "yes" if "✔️ Yes" in choice else "no"
    reason_text = reason.strip() if reason and reason.strip() else config.NO_REASON_GIVEN
    
    log_entry = InteractionLog(
        document_names = doc_names,
        prompt = prompt,
        answer = llm_answer,
        output_passed = evaluation_text,
        eval_reason = reason_text,
        model_name = config.LLM_MODEL_NAME,
        temperature = state["llm_params"]["temperature"],
        top_p = state["llm_params"]["top_p"],
    )
    try:
        db_manager.log_interaction(log_entry)
        new_state = state.update(
            interaction_to_log = log_entry.model_dump(),
            error_message = None,
            evaluation_choice = evaluation_choice,
            evaluation_reason = evaluation_reason,
        )
        return {"logged": True}, new_state
    except (ValidationError, sqlite3.Error) as e:
        new_state = state.update(error_message = "Failed to save evaluation due to database error.")
        return {"logged": False, "error": str(e)}, new_state

@action(reads = [], writes = [])
def terminal_state(state: InvestigationState) -> Tuple[dict, InvestigationState]:
    return {}, state

def build_application(
    config: Config,
    db_manager: DatabaseManager,
    doc_processor: DocumentProcessor,
    ai_service: GeminiService,
) -> "Application":
    return (
        ApplicationBuilder()
        .with_typing(PydanticTypingSystem(InvestigationState))  # informs about shape and schema of state
        .with_state(InvestigationState())                       # Pydantic model initialisation
        .with_tracker(                                          # for OpenTelemetry tracer integration:
            project = "doc-investigator",                       # all state machine actions are traced 
            params = {"storage_dir": "./.burr"}                 # as spans automatically; burr UI as backend
        )
        .with_actions(
            process_inputs = process_inputs.bind(doc_processor = doc_processor),
            process_documents = process_documents.bind(doc_processor = doc_processor, config = config),
            check_cache = check_cache.bind(db_manager = db_manager, config = config),
            generate_answer = generate_answer.bind(ai_service = ai_service),
            update_cache = update_cache.bind(db_manager = db_manager),
            classify_answer = classify_answer.bind(config = config),
            auto_log_and_terminate = auto_log_and_terminate.bind(config = config, db_manager = db_manager),
            await_human_evaluation = await_human_evaluation,
            process_human_evaluation = process_human_evaluation.bind(config = config, db_manager = db_manager),
            error = terminal_state,        # terminal failure state
            end = terminal_state,          # terminal success state
        )
        .with_transitions(
            ("process_inputs", "process_documents", when(outcome = "success")),
            ("process_inputs", "error", when(outcome = "failure")),
            ("process_documents", "check_cache"),

            # path 1: cache Miss
            ("check_cache", "generate_answer", when(hit = False)),
            ("generate_answer", "classify_answer"), # classify if it is a real result

            # path 2: cache Hit
            ("check_cache", "classify_answer", when(hit = True)),  # skip answer creation

            # classification path
            ("classify_answer", "update_cache", when(classification = "real_answer")),
            ("classify_answer", "auto_log_and_terminate", default),
            
            # after caching, await human input.
            ("update_cache", "await_human_evaluation"),
            
            # final path after classification and caching
            ("auto_log_and_terminate", "end"),
            ("await_human_evaluation", "process_human_evaluation"),
            ("process_human_evaluation", "end"),
        )
        .with_entrypoint("process_inputs")
        .build()
    )