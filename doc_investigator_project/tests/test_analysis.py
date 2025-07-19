# tests/test_analysis.py

"""
Unit tests for the analysis module.

These tests validate the logic for generating a data profiling report,
ensuring that file handling, data validation, and library interactions
are managed correctly.

Some additional coding is nessecary to make loguru and pytest's standard
logging work together:
The caplog fixture provides a handler attribute, which is the object pytest
uses to capture logs. Then use logger.add() to tell loguru to send all its
logs directly to this handler.
"""

import pytest
import pandas as pd
from loguru import logger
from unittest.mock import patch, MagicMock

from doc_investigator_strategy_pattern import analysis

@pytest.fixture
def mock_valid_csv(tmp_path):
    """Creates a valid, non-empty CSV file in a temporary directory."""
    csv_path = tmp_path / "valid_data.csv"
    csv_path.write_text("col1,col2,col3\n1,a,'dasfsfds'\n2,b,'This is an example which is very simple for testing.'")
    return str(csv_path)

@pytest.fixture
def mock_empty_csv(tmp_path):
    """Creates an empty CSV file in a temporary directory."""
    csv_path = tmp_path / "empty_data.csv"
    # empty file with headers only
    csv_path.write_text("col1,col2,col3")
    return str(csv_path)


# --- Using patch as a context manager to mock external libraries ---
@patch('doc_investigator_strategy_pattern.analysis.ProfileReport')
@patch('doc_investigator_strategy_pattern.analysis.pd.read_csv')
def test_generate_profile_report_success(mock_read_csv, mock_profile_report_class, mock_valid_csv):
    """
    Test Case: Successful report generation.
    Checks if pandas and ProfileReport are called correctly and the profile object is returned.
    """
    # Arrange
    # config: mock DataFrame that pandas will "return"
    mock_df = pd.DataFrame({'col1': [1, 2]})
    mock_read_csv.return_value = mock_df
    # config: mock ProfileReport instance that constructor will "return"
    mock_profile_instance = MagicMock()
    mock_profile_report_class.return_value = mock_profile_instance

    # Act
    result = analysis.generate_profile_report(mock_valid_csv)

    # Assert
    # verify that pandas was called reading CSV file
    mock_read_csv.assert_called_once_with(mock_valid_csv)
    # verify that ProfileReport class was initialized with mock DataFrame
    mock_profile_report_class.assert_called_once()
    assert mock_profile_report_class.call_args.args[0].equals(mock_df)
    # verify that created profile instance is returned
    assert result is mock_profile_instance


def test_generate_profile_report_file_not_found(caplog):
    """
    Test Case: Specified CSV file does not exist.
    Checks FileNotFoundError is handled gracefully and returns None.
    """
    handler_id = logger.add(caplog.handler, format="{message}")
    
    try:
        # Arrange
        non_existent_path = "path/to/non_existent_file.csv"

        # Act
        result = analysis.generate_profile_report(non_existent_path)

        # Assert
        assert result is None, ".csv file has been found"
        assert "file does not exist" in caplog.text, "FileNotFound exception message not as expected"
    finally:
        logger.remove(handler_id)


@patch('doc_investigator_strategy_pattern.analysis.pd.read_csv')
def test_generate_profile_report_empty_file(mock_read_csv, mock_empty_csv, caplog):
    """
    Test Case: CSV file is empty.
    Checks that an empty DataFrame is handeled appropriately and returns None.
    """
    handler_id = logger.add(caplog.handler, format="{message}")
    
    try:
        # Arrange
        # config: pandas returns an empty DataFrame
        mock_read_csv.return_value = pd.DataFrame()

        # Act
        result = analysis.generate_profile_report(mock_empty_csv)

        # Assert
        assert result is None, "The .csv file is not empty and a dataframe is created"
        assert "is empty" in caplog.text, "Empty dataframe exception message not as expected"
    finally:
        logger.remove(handler_id)


@patch('doc_investigator_strategy_pattern.analysis.ProfileReport',
       side_effect=Exception("Profiling Failed"))
@patch('doc_investigator_strategy_pattern.analysis.pd.read_csv')
def test_generate_profile_report_unexpected_exception(mock_read_csv, mock_profile_report_class, mock_valid_csv, caplog):
    """
    Test Case: The profiling library itself raises an unexpected error.
    Checks the caught of the exception and returning value is None.
    """
    handler_id = logger.add(caplog.handler, format="{message}")
    
    try:
        # Arrange
        mock_read_csv.return_value = pd.DataFrame({'col1': [1, 2]})

        # Act
        result = analysis.generate_profile_report(mock_valid_csv)

        # Assert
        assert result is None
        assert "unexpected error" in caplog.text.lower(), "Unexpected error message of profiling lib exception not as expected"
        assert "Profiling Failed" in caplog.text, "Profiling failure message not as expected"
    finally:
        logger.remove(handler_id)
