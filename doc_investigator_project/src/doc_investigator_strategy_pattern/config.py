# src/doc_investigator_strategy_pattern/config.py

"""
Configuration module for the Document Investigator application.
Defines a frozen dataclass to hold all application-wide configuration settings. 
"""

from dataclasses import dataclass, field
from typing import List

@dataclass(frozen=True)
class Config:
    """
    Encapsulates all application configuration settings.

    The 'frozen=True' argument makes instances of this class immutable,
    which is a best practice for handling configuration to prevent
    unintended changes during the application's lifecycle.
    """

    # --- Database Settings ---
    DB_FILE: str = "doc_investigator_prod.db"

    # --- LLM and AI Service Settings ---
     # Use a model name confirmed available via `genai.list_models()`
    # as checked with origin github repo helper file 'check_google_models.py'
    LLM_MODEL_NAME: str = "gemini-2.5-pro"
    TEMPERATURE: float = 0.2    # low value - more deterministic, focused 
    TOP_P: float = 0.95         # nucleus sampling parameter
    MAX_CONTEXT_CHARACTERS: int = 800000 # Corresponds to ~1M tokens for Gemini

    # --- Application Logic Settings ---
    UNKNOWN_ANSWER: str = "Your request is unknown, associated information is not available. Please try again!"
    NOT_ALLOWED_ANSWER: str = "Sorry, your task is not allowed. Please try again!"
    NO_REASON_GIVEN: str = "no reason given"

    # Whenever you need to create a new Config object,
    # call this lambda function, which will return a brand new list. 
    # This correctly isolates the state of each object. Annotation:
    # A simple list is created only once, and will throw the following error:
    # ValueError: mutable default <class 'list'> for field SUPPORTED_FILE_TYPES is not allowed:
    # use default_factory
    SUPPORTED_FILE_TYPES: List[str] = field(
        default_factory=lambda: ['.pdf', '.docx', '.txt', '.xlsx']
    )

    # --- Logging Retention Policy ---
    MAX_LOG_FILES = 5
