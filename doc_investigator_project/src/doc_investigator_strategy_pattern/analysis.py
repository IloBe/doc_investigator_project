# src/doc_investigator_strategy_pattern/analysis.py

"""
Data analysis module for Document Investigator application.

Provides functions to perform data profiling on evaluation data,
encapsulating the logic for reading, processing and generating reports.
"""

import os
import pandas as pd
from loguru import logger
from ydata_profiling import ProfileReport
from typing import Optional

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
            return "<p style='color:orange; text-align:center;'>Source file is empty. Cannot generate profile.</p>"

        logger.debug("CSV data loaded successfully. Generating ydata-profiling report...")
        profile = ProfileReport(
            df,
            title="Document Investigator - Evaluation Profile",
            explorative=True,
        )

        #html_report = profile.to_html()
        logger.success("Successfully generated data profile report.")
        return profile

    except FileNotFoundError as e:
        logger.error(f"Data profiling error: {e}")
        return f"<p style='color:red; text-align:center;'><b>Error:</b> {e}. Please ensure the file is in the 'data' directory.</p>"
    
    except pd.errors.EmptyDataError:
        logger.error(f"CSV file '{csv_path}' is empty or corrupted.", exc_info=True)
        return "<p style='color:red; text-align:center;'><b>Error:</b> The CSV file is empty or could not be read.</p>"
    
    except Exception as e:
        logger.critical(f"An unexpected error occurred during profile generation: {e}", exc_info=True)
        return f"<p style='color:red; text-align:center;'><b>Critical Error:</b> An unexpected error occurred. Check application logs for details.</p>"