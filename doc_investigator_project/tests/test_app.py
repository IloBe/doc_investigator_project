# tests/test_app.py

"""
Unit tests for the AppUI class, focusing on event handler logic.
These tests are designed to run in an async context to mimic the Gradio environment.
"""

import pytest
import gradio as gr
import sys
import os
from unittest.mock import MagicMock, patch

from doc_investigator_strategy_pattern.app import AppUI
from doc_investigator_strategy_pattern.documents import InvalidFileTypeException

# using pytest-asyncio's 'asyncio' marker for explicit async tests
pytestmark = pytest.mark.asyncio

@pytest.fixture
def mock_services():
    """Provides a dictionary of mock services. Remains a synchronous fixture."""
    return {
        "config": MagicMock(),
        "db_manager": MagicMock(),
        "doc_processor": MagicMock(),
        "ai_service": MagicMock()
    }

@pytest.fixture
def app_ui(mock_services):
    """Provides an AppUI instance with all backend services mocked."""
    return AppUI(**mock_services)

async def test_handle_investigation_success(app_ui, mock_services):
    """
    Tests the main investigation workflow on a successful path.
    This test is now async.
    """
    # Arrange
    mock_files = [MagicMock()]
    mock_prompt = "test prompt"
    mock_answer = "This is a real answer."
    mock_services["doc_processor"].process_files.return_value = "Extracted text"
    mock_services["ai_service"].get_answer.return_value = mock_answer
    mock_services["config"].UNKNOWN_ANSWER = "Unknown"
    mock_services["config"].NOT_ALLOWED_ANSWER = "Not Allowed"
    mock_services["config"].MAX_CONTEXT_CHARACTERS = 800000

    # Act: Although the handler itself is synchronous, call it from an async
    # test function being a simulation of the Gradio runtime
    answer_update, panel_update, _, _, _ = app_ui._handle_investigation(mock_files, mock_prompt)  

    # Assert
    mock_services["doc_processor"].validate_files.assert_called_once_with(mock_files)
    mock_services["doc_processor"].process_files.assert_called_once_with(mock_files)
    mock_services["ai_service"].get_answer.assert_called_once_with("Extracted text", mock_prompt)
    assert answer_update['value'] == mock_answer
    assert panel_update['visible'] is True
    mock_services["db_manager"].log_interaction.assert_not_called()

async def test_handle_investigation_unknown_answer(app_ui, mock_services):
    """
    Tests the workflow for an 'unknown' answer, which should be auto-logged.
    """
    # Arrange
    mock_files = [MagicMock(name = "test.pdf")]
    mock_prompt = "test prompt"
    unknown_answer = "Your request is unknown..."
    mock_services["ai_service"].get_answer.return_value = unknown_answer
    mock_services["config"].UNKNOWN_ANSWER = unknown_answer
    mock_services["config"].NOT_ALLOWED_ANSWER = "Not Allowed"
    mock_services["config"].MAX_CONTEXT_CHARACTERS = 800000
    mock_services["config"].TEMPERATURE = 0.2
    mock_services["config"].TOP_P = 0.95

    # Act
    answer_update, panel_update, _, _, _ = app_ui._handle_investigation(mock_files, mock_prompt)

    # Assert
    assert answer_update['value'] == unknown_answer
    assert panel_update['visible'] is False
    mock_services["db_manager"].log_interaction.assert_called_once()
    call_kwargs = mock_services["db_manager"].log_interaction.call_args.kwargs
    assert call_kwargs['evaluation'] == 'no'
    assert call_kwargs['prompt'] == mock_prompt

async def test_handle_file_validation_failure(app_ui, mock_services):
    """
    Tests that the file validation handler catches an exception and returns None.
    """
    # Arrange
    mock_files = [MagicMock()]
    mock_services["doc_processor"].validate_files.side_effect = InvalidFileTypeException("Bad file")
    
    # Act
    # We patch 'gradio.Warning' to prevent it from trying to render in a non-UI context
    with patch('gradio.Warning') as mock_gr_warning:
        result = app_ui._handle_file_validation(mock_files)

    # Assert
    assert result is None, "The handler should return None to clear the Gradio component."
    mock_gr_warning.assert_called_once(), "gr.Warning should have been called to inform the user."

async def test_handle_evaluation_success(app_ui, mock_services):
    """Tests the evaluation handler for a successful submission."""
    # Arrange
    choice = "✔️ Yes, the answer is helpful and accurate."
    mock_services["config"].TEMPERATURE = 0.2
    mock_services["config"].TOP_P = 0.95

    # Act
    result = app_ui._handle_evaluation("doc.txt", "prompt", "answer", choice)

    # Assert
    mock_services["db_manager"].log_interaction.assert_called_once()
    call_kwargs = mock_services["db_manager"].log_interaction.call_args.kwargs
    assert call_kwargs['evaluation'] == 'yes'
    assert call_kwargs['document_names'] == 'doc.txt'
    assert isinstance(result, tuple)
    assert result[0] is None   # file_uploader reset
    assert result[1] == ""     # prompt_input reset

