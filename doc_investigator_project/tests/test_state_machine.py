# tests/test_state_machine.py

# ----------
# Imports
# ----------
import pytest
from unittest.mock import MagicMock, ANY

# Import the components to be tested and mocked
from doc_investigator_strategy_pattern.config import Config
from doc_investigator_strategy_pattern.state_machine import build_application, InvestigationState
from doc_investigator_strategy_pattern.documents import InvalidFileTypeException

# ----------
# Coding
# ----------

# --- Fixtures for Mocking Dependencies ---

@pytest.fixture
def mock_config():
    """Provides a mock Config object with known values for testing."""
    return Config(UNKNOWN_ANSWER = "Unknown",
                  NOT_ALLOWED_ANSWER = "Not Allowed",
                  )

@pytest.fixture
def mock_db_manager():
    """Provides a mock DatabaseManager."""
    return MagicMock()

@pytest.fixture
def mock_doc_processor():
    """Provides a mock DocumentProcessor."""
    return MagicMock()

@pytest.fixture
def mock_ai_service():
    """Provides a mock GeminiService."""
    return MagicMock()

@pytest.fixture
def mock_gradio_file():
    """Factory to create a mock Gradio file object for tests."""
    class MockFile:
        def __init__(self, name):
            self.name = f"/tmp/{name}"
    return MockFile

# --- Test Cases for State Machine Workflows ---

def test_happy_path_with_human_evaluation(
    mock_config, mock_db_manager, mock_doc_processor, mock_ai_service, mock_gradio_file
):
    """
    Tests the full workflow: valid file -> AI generates a real answer -> human evaluates positively.
    """
    # Arrange: configure mocks for "happy path"
    mock_doc_processor.process_files.return_value = "Extracted text."
    mock_db_manager.get_cached_answer.return_value = None   # mocks a cache miss
    mock_ai_service.get_answer.return_value = "This is a real answer."
    
    app = build_application(
        config = mock_config,
        db_manager = mock_db_manager,
        doc_processor = mock_doc_processor,
        ai_service = mock_ai_service
    )
    initial_inputs = {
        "files": [mock_gradio_file("test.pdf")],
        "prompt": "Summarize.",
        "llm_params": {"temperature": 0.2, "top_p": 0.95},
    }
    
    # Act: run until machine needs human input
    final_action, state, _ = app.run(halt_after = ["await_human_evaluation"], inputs = initial_inputs)

    # Assert: check state and stopped at right place
    assert final_action.name == "await_human_evaluation"
    assert app.state["llm_answer"] == "This is a real answer."

    # human evaluation
    evaluation_inputs = {
        "doc_names": app.state["doc_names"],
        "prompt": app.state["prompt"],
        "llm_answer": app.state["llm_answer"],
        "llm_params": app.state["llm_params"],
        "evaluation_choice": "✔️ Yes...",
        "evaluation_reason": "It was good."
    }
    
    # Act: flow result with evaluation
    # machine knows next action is `process_human_evaluation`.
    final_action, _, _ = app.step(inputs = evaluation_inputs)

    # Assert: check next step runs, flow finished and logged correct data
    # Note: app.step() only runs one action, second step needed to 'end'.
    assert final_action.name == "process_human_evaluation"
    final_action, _, _ = app.step()                        # 'end' action takes no inputs
    assert final_action.name == "end"
    mock_db_manager.log_interaction.assert_called_once()   # db is called
    logged_data = mock_db_manager.log_interaction.call_args[0][0]
    assert logged_data.output_passed == "yes"
    assert logged_data.eval_reason == "It was good."

def test_predefined_answer_path_auto_logs(
    mock_config, mock_db_manager, mock_doc_processor, mock_ai_service, mock_gradio_file
):
    """
    Tests that if AI returns a predefined response, it auto-logs and terminates.
    """
    # Arrange: AI returns predefined "Unknown" answer
    mock_doc_processor.process_files.return_value = "Extracted text."
    mock_db_manager.get_cached_answer.return_value = None  # mocks a cache miss
    mock_ai_service.get_answer.return_value = mock_config.UNKNOWN_ANSWER
    
    app = build_application(
        config = mock_config,
        db_manager = mock_db_manager,
        doc_processor = mock_doc_processor,
        ai_service = mock_ai_service
    )
    inputs = {
        "files": [mock_gradio_file("test.pdf")],
        "prompt": "A question",
        "llm_params": {"temperature": 0.2, "top_p": 0.95},
    }

    # Act: run completion
    final_action, state, _ = app.run(halt_after = ["end"], inputs = inputs)

    # Assert: flow end without waiting for human
    assert final_action.name == "end"
    assert app.state["llm_answer"] == mock_config.UNKNOWN_ANSWER
    mock_db_manager.log_interaction.assert_called_once()
    logged_data = mock_db_manager.log_interaction.call_args[0][0]
    assert logged_data.answer == mock_config.UNKNOWN_ANSWER
    assert logged_data.output_passed == "no"


def test_process_inputs_with_invalid_file_error_path(
    mock_config, mock_db_manager, mock_doc_processor, mock_ai_service, mock_gradio_file
):
    """
    Tests if inputs file validation fails, flow transitions directly to error state.
    """
    # Arrange: doc processor config to raise validation error
    error_message = "Unsupported file type"
    mock_doc_processor.validate_files.side_effect = InvalidFileTypeException(error_message)
    
    app = build_application(
        config = mock_config,
        db_manager = mock_db_manager,
        doc_processor = mock_doc_processor,
        ai_service = mock_ai_service
    )
    inputs = {
        "files": [mock_gradio_file("image.png")],
        "prompt": "Any prompt",
        "llm_params": {"temperature": 0.2, "top_p": 0.95},
    }

    # Act: run state machine
    final_action, state, _ = app.run(halt_after = ["error"], inputs = inputs)

    # Assert: check being in error state, no further actions
    assert final_action.name == "error"
    # error message written to state by 'process_inputs' action before machine halt
    assert app.state["error_message"] == str(InvalidFileTypeException(error_message))
    mock_doc_processor.process_files.assert_not_called()
    mock_ai_service.get_answer.assert_not_called()


def test_workflow_on_cache_miss_calls_llm_and_updates_cache(
    mock_config, mock_db_manager, mock_doc_processor, mock_ai_service, mock_gradio_file
):
    """
    Tests full workflow on a cache miss, ensuring LLM is called to create an answer
    and the cache is updated with it.
    """
    # Arrange
    mock_doc_processor.process_files.return_value = "Extracted text."
    mock_db_manager.get_cached_answer.return_value = None    # mocks a cache miss
    mock_ai_service.get_answer.return_value = "A fresh answer from the LLM."
    
    app = build_application(
        config = mock_config,
        db_manager = mock_db_manager,
        doc_processor = mock_doc_processor,
        ai_service = mock_ai_service
    )
    inputs = {
        "files": [mock_gradio_file("doc.pdf")],
        "prompt": "summarize",
        "llm_params": {"temperature": 0.5, "top_p": 0.95}
    }

    # Act
    app.run(halt_after = ["await_human_evaluation"], inputs = inputs)

    # Assert
    mock_db_manager.get_cached_answer.assert_called_once()
    mock_ai_service.get_answer.assert_called_once()
    mock_db_manager.set_cached_answer.assert_called_once_with(ANY, "A fresh answer from the LLM.")
    assert app.state["llm_answer"] == "A fresh answer from the LLM.", "LLM hasn't created a new answer"


def test_workflow_on_cache_hit_skips_llm(
    mock_config, mock_db_manager, mock_doc_processor, mock_ai_service, mock_gradio_file
):
    """
    Tests full workflow on a cache hit, ensuring the LLM is SKIPPED and no update happened.
    """
    # Arrange
    mock_doc_processor.process_files.return_value = "Extracted text."
    cached_answer = "This is a previously cached answer."
    mock_db_manager.get_cached_answer.return_value = cached_answer   # mocks a cache hit
    
    app = build_application(
        config = mock_config,
        db_manager = mock_db_manager,
        doc_processor = mock_doc_processor,
        ai_service = mock_ai_service
    )
    inputs = {
        "files": [mock_gradio_file("doc.pdf")], "prompt": "summarize",
        "llm_params": {"temperature": 0.5}
    }

    # Act
    app.run(halt_after = ["await_human_evaluation"], inputs = inputs)

    # Assert
    mock_db_manager.get_cached_answer.assert_called_once()
    mock_ai_service.get_answer.assert_not_called()
    # state machine calls `set_cached_answer` on a cache hit to update the timestamp.
    mock_db_manager.set_cached_answer.assert_called_once_with(ANY, cached_answer)
    assert app.state["llm_answer"] == cached_answer, "Cache hit, but answer is not the cached one"
