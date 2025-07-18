#!/usr/bin/env -S python3 -i

# main.py
"""
Main entry point for the Document Investigator application.

This script initializes all core components and starts the Uvicorn server
to serve the Gradio-based user interface.
"""

# Fix for numpy warnings,
# MUST be at the absolute top of the file, before any other imports,
# ... nevertheless, is not always working during pytest run,
# why? https://github.com/numpy/numpy/issues/26414
# seems to be an issue between WSL ubuntu, MS Windows and numpy
import warnings
warnings.filterwarnings(    
    "ignore",
    message=".*does not match any known type.*",
    category=UserWarning,
    module="numpy._core.getlimits"
)

import gradio as gr
import getpass
import os
import sys
import uvicorn
from loguru import logger
from typing import TYPE_CHECKING


# Allows app to run as script from 'src' dir.
# Adds parent dir 'src' to Python path, making 'doc_investigator_strategy' package importable.
# Future toDo: distribution of a pyproject.toml file
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

try:
    from doc_investigator_strategy_pattern.app import AppUI
    from doc_investigator_strategy_pattern.config import Config
    from doc_investigator_strategy_pattern.database import DatabaseManager
    from doc_investigator_strategy_pattern.documents import DocumentProcessor
    from doc_investigator_strategy_pattern.services import GeminiService
    from doc_investigator_strategy_pattern.logging_config import setup_logging
except ImportError as e:
    print(f"FATAL: A required module could not be imported. "
          f"Please ensure you are running this script from the 'src' directory "
          f"and all dependencies are installed. Error: {e}")
    sys.exit(1)


# TYPE_CHECKING is True only during static type checking,
# preventing circular imports at runtime
if TYPE_CHECKING:
    from doc_investigator_strategy_pattern.app import AppUI
    from doc_investigator_strategy_pattern.config import Config
    from doc_investigator_strategy_pattern.database import DatabaseManager
    from doc_investigator_strategy_pattern.documents import DocumentProcessor
    from doc_investigator_strategy_pattern.services import GeminiService


def initialize_app() -> gr.Blocks:
    """
    Initializes and wires together all application components.

    This function follows the Dependency Injection pattern, creating instances
    of services and passing them to the components that depend on them.

    Returns:
        gr.Blocks: A configured Gradio application instance.

    Raises:
        SystemExit: If any critical initialization step fails.
    """

    logger.info("Starting Document Investigator application initialization...")

    try:
        config = Config()
        setup_logging(config)
    
        # which LLM in use?
        logger.info(f"Configuration loaded successfully, as LLM: {config.LLM_MODEL_NAME}")
    except Exception as e:
        logger.critical(f"Failed to load configuration. Aborting. Error: {e}", exc_info=True)
        raise SystemExit(1) from e

    # by now: only Google API Key for LLM available
    api_key = os.environ.get('GOOGLE_API_KEY')
    if not api_key:
        logger.warning("GOOGLE_API_KEY environment variable not found. Falling back to password prompt.")
        try:
            api_key = getpass.getpass('Enter your Google Gemini API Key: ')
            if not api_key:
                raise ValueError("LLM API Key cannot be empty.")
        except Exception as e:
            logger.critical(f"Could not read Google's LLM API key. Aborting. Error: {e}", exc_info=True)
            raise SystemExit(1) from e

    # app components
    try:
        db_manager = DatabaseManager(db_path=config.DB_FILE)
        logger.success("DatabaseManager initialized successfully.")

        doc_processor = DocumentProcessor(supported_extensions=config.SUPPORTED_FILE_TYPES)
        logger.success("DocumentProcessor initialized successfully.")

        ai_service = GeminiService(api_key=api_key, config=config)
        logger.success("GeminiService initialized successfully.")

    except Exception as e:
        logger.critical(f"Failed to initialize a core component. Aborting. Error: {e}", exc_info=True)
        raise SystemExit(1) from e

    # Gradio App UI, injecting dependencies
    app_ui = AppUI(
        config=config,
        db_manager=db_manager,
        doc_processor=doc_processor,
        ai_service=ai_service
    )
    logger.success("Application UI created successfully.")

    # Gradio app object required by Uvicorn
    return app_ui.app


# variable name 'app' is default Uvicorn looks for
app = initialize_app()


if __name__ == "__main__":
    # runs app directly using 'python main.py' on src dir,
    # use Gradio app's own launch method, not uvicorn run - would be a conflict
    if app:
        logger.info("Launching application with Gradio's built-in server...")
        app.launch(
            server_name="0.0.0.0",  # Makes the app accessible on the local network
            server_port=8000        # Sets the desired port
        )
    else:
        logger.critical("Application failed to initialize and will not start.")
