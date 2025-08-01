# src/doc_investigator_strategy_pattern/logging_config.py

"""
Logging configuration for the Document Investigator application.

This module sets up the Loguru logger with handlers for both console
output and file-based logging. It establishes a standardized, structured
log format to ensure consistency and readability across the entire application.
"""

# ----------
# Imports
# ----------
import os
import sys
from pathlib import Path
from typing import NoReturn
from loguru import logger

from .config import Config

# ----------
# Coding
# ----------

def setup_logging(config: Config) -> None:
    """
    Configures the application-wide Loguru logger.
    Retention policy is to keep as maximum youngest 5 log files.

    Removes default Loguru handler and setup 2 new ones:
    -  A console handler (stderr) for real-time, colorized output during
        development and interactive sessions. It's configured to show logs
        from the INFO level and above.
    -  A file handler that writes logs to 'logs/app.log'. This file log
        is more verbose (DEBUG level), includes comprehensive details
        (like module and function name), and has built-in rotation and
        retention policies for production use.

    This setup should be called once at the very beginning of the application's
    entry point.
    """

    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)

    # --- retention policy ---
    # logic runs *before* new logger is added,
    # check ensures directory state before creating new file
    try:
        # get all log files, sort them by modification time (newest first)
        log_files = sorted(
            [os.path.join(log_dir, f) for f in os.listdir(log_dir) if f.startswith("app_session_") and f.endswith(".log")],
            key=os.path.getmtime,
            reverse=True
        )
        
        # having config.MAX_LOG_FILES=5 or more, the 5th newest is at index 4,
        # any file from index 5 onwards is older and will be deleted                     
        files_to_delete = log_files[config.MAX_LOG_FILES - 1:]
        if files_to_delete:
            logger.info(f"Log Retention: Found {len(log_files)} logs. Max is {config.MAX_LOG_FILES}. Cleaning up oldest ones.")
            for f in files_to_delete:
                os.remove(f)
                logger.info(f"Log Retention: Removed old log file '{os.path.basename(f)}'.")
                
    except Exception as e:
        # don't want log cleanup to crash app, so just print a warning.
        logger.warning("[WARNING] Could not perform log file cleanup...", exc_info=e)
        pass
    
    # --- loguru configuration ---
    log_format = (
        "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}:{function}:{line}</cyan> - <level>{message}</level>"
    )

    # remove default handler to avoid duplicate outputs
    logger.remove()

    # colorful console log handler
    logger.add(
        sys.stderr,
        level = "INFO",
        format = log_format,
        colorize = True,
        enqueue = True,      # to be thread-safe
        backtrace = True,
        diagnose = False     # False in production for security
    )

    # file log handler
    log_file_path = log_dir / "app_session_{time:YYYY-MM-DD_HH-mm-ss}.log"
    logger.add(
        log_file_path,
        level = "DEBUG",
        format = log_format,
        rotation = "10 MB",  # rotate log file when it reaches 10 MB
        retention = 5,       # keep max 5 log files
        compression = "zip", # compress old log files
        enqueue = True,      # make logging thread-safe
        serialize = False,   # True for JSON-structured logs
        diagnose = False     # make tracebacks pickleable; 'True' not working in Python native traceback
    )

    logger.info("Logger has been initialized successfully with retention policy of 5 files.")
    logger.debug("This is a debug message, only visible in the log file.")


def unexpected_shutdown_handler(exc_type, exc_value, exc_traceback) -> NoReturn:
    """
    Custom exception hook to ensure all uncaught exceptions are logged.
    Final safety task to capture any errors that would otherwise cause
    app crash silently.
    """
    if issubclass(exc_type, (KeyboardInterrupt, SystemExit)):
        # Don't log standard exit signals as critical errors
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return

    logger.critical("An uncaught exception occurred. Application will now shut down.",
                    exc_info=(exc_type, exc_value, exc_traceback))

# Set the custom exception hook
sys.excepthook = unexpected_shutdown_handler