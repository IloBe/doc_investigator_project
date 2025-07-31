#!/usr/bin/env -S python3 -i

# src/main.py
"""
Main entry point for the Document Investigator application.

This script initializes all core components
to serve the Gradio-based user interface.
"""

# ----------
# Imports
# ----------

# Fix for numpy warnings,
# MUST be at the absolute top of the file, before any other imports,
# ... nevertheless, is not always working during pytest run,
# why? https://github.com/numpy/numpy/issues/26414
# seems to be an issue between WSL ubuntu, MS Windows and numpy
import warnings
warnings.filterwarnings(    
    "ignore",
    message = ".*does not match any known type.*",
    category = UserWarning,
    module = "numpy._core.getlimits"
)

import gradio as gr
import getpass
import os
import sys
from loguru import logger
from typing import TYPE_CHECKING

# ----------
# Coding
# ----------

# Allows app to run as script from 'src' dir.
# Adds parent dir 'src' to Python path, making 'doc_investigator_strategy' package importable.
#sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

try:
    from doc_investigator_strategy_pattern.app import AppUI
    from doc_investigator_strategy_pattern.config import Config
    from doc_investigator_strategy_pattern.database import DatabaseManager
    from doc_investigator_strategy_pattern.documents import DocumentProcessor
    from doc_investigator_strategy_pattern.services import GeminiService
    from doc_investigator_strategy_pattern.logging_config import setup_logging
    from doc_investigator_strategy_pattern.state_machine import build_application
except ImportError as e:
    print(f"FATAL: A required module could not be imported. "
          f"Please ensure you are running this script from 'src' directory "
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
    Note: The Burr state machine app is not built here; it's built on-demand in the AppUI.

    Returns:
        gr.Blocks: A configured Gradio application instance.

    Raises:
        SystemExit: If any critical initialization step fails.
    """

    logger.info("Starting Document Investigator application initialisation...")

    try:
        config = Config()
        setup_logging(config)
    
        # which LLM in use?
        logger.info(f"Configuration loaded successfully, as LLM: {config.LLM_MODEL_NAME}")
    except Exception as e:
        logger.critical(f"Failed to load configuration. Aborting. Error: {e}", exc_info = True)
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
            logger.critical(f"Could not read Google's LLM API key. Aborting. Error: {e}", exc_info = True)
            raise SystemExit(1) from e

    # app components
    try:
        db_manager = DatabaseManager(db_path = config.DB_FILE)
        logger.success("DatabaseManager initialized successfully.")

        doc_processor = DocumentProcessor(supported_extensions = config.SUPPORTED_FILE_TYPES)
        logger.success("DocumentProcessor initialized successfully.")

        ai_service = GeminiService(api_key = api_key, config = config)
        logger.success("GeminiService initialized successfully.")

    except Exception as e:
        logger.critical(f"Failed to initialize a core component. Aborting. Error: {e}", exc_info = True)
        raise SystemExit(1) from e

    # Gradio App UI, injecting dependencies
    app_ui = AppUI(
        config = config,
        db_manager = db_manager,
        doc_processor = doc_processor,
        ai_service = ai_service,
    )
    logger.success("Application UI created successfully.")

    # Gradio app object required by Uvicorn
    return app_ui.app


# var name 'app' is default Uvicorn looks for,
# but skipped uvicorn, because gradio stucked in loading
app = initialize_app()

if __name__ == "__main__":
    if app:
        logger.info("Launching application with Gradio's built-in server using HTTPS...")
        # use Gradio's own launch method and passes the SSL parameters to it,
        # creates an encrypted (HTTPS/WSS) connection that will bypass firewall's web filter, so,
        # gradio didn't stuck in loading (but private certificates have to be explicitly accepted)
        app.launch(
            server_name = "127.0.0.1",
            server_port = 7861,
            ssl_keyfile = "./key.pem",
            ssl_certfile = "./cert.pem",
            # tells Gradio's internal HTTP client (used for health checks, etc.)
            # to NOT verify SSL certificates. Necessary when using
            # a self-signed certificate for localhost
            ssl_verify = False
        )
    else:
        logger.critical("Application failed to initialize and will not start.")    

