# src/doc_investigator_strategy_pattern/analysis.py

"""
Data analysis module for Document Investigator application.

Provides functions to perform data profiling on evaluation data,
encapsulating the logic for reading, processing and generating reports.
"""

# ----------
# Imports
# ----------
import os
import pandas as pd
from loguru import logger
from ydata_profiling import ProfileReport
from typing import Optional

# ----------
# Coding
# ----------

def generate_profile_report(csv_path: str) -> Optional[ProfileReport]:
    """
    Generates a ydata-profiling report from a CSV file.

    Reads evaluation data, creates a comprehensive data profile, and
    returns it as a self-contained HTML string. Handles errors such as
    missing files or empty data.

    Args:
        csv_path (str): full path to the input CSV file

    Returns:
        Optional[ProfileReport]: Generated ProfileReport object, or None if an
                                 error occurred.
    """
    logger.info(f"Attempting to generate data profile from '{csv_path}'...")

    try:
        if not os.path.exists(csv_path):
            raise FileNotFoundError(f"Specified file does not exist: {csv_path}")

        df = pd.read_csv(csv_path)
        if df.empty:
            logger.warning(f"CSV file '{csv_path}' is empty. No report generated.")
            return None

        logger.debug("CSV data loaded successfully. Generating ydata-profiling report...")
        profile = ProfileReport(
            df,
            title = "Document Investigator - Evaluation Data Profiling Report",
            explorative = True,
        )

        #html_report = profile.to_html()
        logger.success("Successfully generated data profile report.")
        del df
        return profile

    except FileNotFoundError as e:
        logger.error(f"Data profiling error: {e}", exc_info = True)
        return None
    
    except pd.errors.EmptyDataError as e:
        logger.error(f"CSV file '{csv_path}' is empty or corrupted: {e}.", exc_info = True)
        return None

    except Exception as e:
        logger.critical(f"An unexpected error occurred during profile generation: {e}", exc_info = True)
        return None
