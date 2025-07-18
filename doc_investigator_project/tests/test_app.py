# tests/test_app.py

"""
Unit tests for the AppUI class, focusing on event handler logic.
These tests are designed to run in an async context to mimic the Gradio environment.
"""

import pytest
import gradio as gr
import sys
from unittest.mock import MagicMock, patch

from doc_investigator_strategy_pattern.app import AppUI
from doc_investigator_strategy_pattern.documents import InvalidFileTypeException

# get rid off warning filter to suppress DeprecationWarning from Gradio
pytestmark = [
    pytest.mark.filterwarnings("ignore:There is no current event loop:DeprecationWarning:gradio.utils")
]

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

@pytest.mark.asyncio
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
    mock_services["config"].LLM_MODEL_NAME = "mock-model-name"
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

@pytest.mark.asyncio    
async def test_handle_investigation_unknown_answer_logs_correctly(app_ui, mock_services):
    """
    Tests that a non-answer is auto-logged with the new, correct schema.
    """
    mock_files = [MagicMock(name="test.pdf")]
    mock_prompt = "test prompt"
    unknown_answer = "Your request is unknown..."
    mock_services["doc_processor"].process_files.return_value = "Some text from a document."
    mock_services["ai_service"].get_answer.return_value = unknown_answer
    mock_services["config"].LLM_MODEL_NAME = "mock-model-name"
    mock_services["config"].UNKNOWN_ANSWER = unknown_answer
    mock_services["config"].NOT_ALLOWED_ANSWER = "Not Allowed"
    mock_services["config"].MAX_CONTEXT_CHARACTERS = 800000
    mock_services["config"].TEMPERATURE = 0.2
    mock_services["config"].TOP_P = 0.95

    _, panel_update, _, _, _ = app_ui._handle_investigation(mock_files, mock_prompt)

    assert panel_update['visible'] is False
    mock_services["db_manager"].log_interaction.assert_called_once()
    
    # Assert that log_interaction was called with the correct keyword arguments
    call_kwargs = mock_services["db_manager"].log_interaction.call_args.kwargs
    assert call_kwargs['output_passed'] == 'no'
    assert call_kwargs['prompt'] == mock_prompt
    assert call_kwargs['eval_reason'] == "no reason given"
    assert call_kwargs['model_name'] == "mock-model-name"
    assert call_kwargs['temperature'] == 0.2
    assert call_kwargs['top_p'] == 0.95    

@pytest.mark.asyncio
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

@pytest.mark.asyncio
async def test_handle_evaluation_success_with_reason(app_ui, mock_services):
    """Tests the evaluation handler for a successful submission."""
    # Arrange
    choice = "✔️ Yes, the answer is helpful and accurate."
    reason = "This is a detailed reason."
    mock_services["config"].LLM_MODEL_NAME = "mock-model-name"
    mock_services["config"].TEMPERATURE = 0.2
    mock_services["config"].TOP_P = 0.95

    # Act
    result = app_ui._handle_evaluation("doc.txt", "prompt", "answer", choice, reason)

    # Assert
    mock_services["db_manager"].log_interaction.assert_called_once()
    call_kwargs = mock_services["db_manager"].log_interaction.call_args.kwargs
    assert call_kwargs['output_passed'] == 'yes'
    assert call_kwargs['eval_reason'] == reason
    assert call_kwargs['document_names'] == 'doc.txt'
    assert call_kwargs['model_name'] == 'mock-model-name'
    assert call_kwargs['temperature'] == 0.2
    assert isinstance(result, tuple)
    assert result[0] is None   # file_uploader reset
    assert result[1] == ""     # prompt_input reset

@pytest.mark.asyncio
async def test_handle_evaluation_success_with_no_reason(app_ui, mock_services):
    """Tests the evaluation handler logs correctly when no reason is provided."""
    choice = "❌ No, the answer is not helpful or inaccurate."
    reason = "   " # Test with empty space to ensure stripping works
    mock_services["config"].NO_REASON_GIVEN = "no reason given"
    mock_services["config"].LLM_MODEL_NAME = "mock-model-name"
    mock_services["config"].TEMPERATURE = 0.2
    mock_services["config"].TOP_P = 0.95

    app_ui._handle_evaluation("doc.txt", "prompt", "answer", choice, reason)

    mock_services["db_manager"].log_interaction.assert_called_once()
    call_kwargs = mock_services["db_manager"].log_interaction.call_args.kwargs
    assert call_kwargs['output_passed'] == 'no'
    assert call_kwargs['eval_reason'] == 'no reason given' # Check for default

@patch('doc_investigator_strategy_pattern.app.analysis.generate_profile_report')
def test_handle_profile_generation_success(mock_generate_report, app_ui):
    """
    Test Case: Successful profile generation in the UI.
    Checks that the handler returns the correct HTML, state object, and enabled button.
    """
    # Arrange:
    # - Create a mock ProfileReport object that our mocked analysis function will return.
    mock_profile = MagicMock()
    mock_profile.to_html.return_value = "<h1>Mock Report HTML</h1>"
    mock_generate_report.return_value = mock_profile

    # Act:
    html_output, state_output, button_update = app_ui._handle_profile_generation()

    # Assert:
    mock_generate_report.assert_called_once()
    assert html_output == "<h1>Mock Report HTML</h1>"
    assert state_output is mock_profile
    assert button_update == gr.update(interactive=True)

@patch('doc_investigator_strategy_pattern.app.analysis.generate_profile_report', return_value=None)
def test_handle_profile_generation_failure(mock_generate_report, app_ui):
    """
    Test Case: Failed profile generation in the UI (e.g., file not found).
    Checks that the handler returns an error message and a disabled button.
    """
    # Arrange:
    # - The mock is already configured to return None by the patch decorator.

    # Act:
    html_output, state_output, button_update = app_ui._handle_profile_generation()

    # Assert:
    mock_generate_report.assert_called_once()
    assert "Error:" in html_output
    assert state_output is None
    assert button_update == gr.update(interactive=False)

@patch('doc_investigator_strategy_pattern.app.os.makedirs')
@patch('doc_investigator_strategy_pattern.app.gr.Info')
def test_handle_export_html_success(mock_gr_info, mock_makedirs, app_ui):
    """
    Test Case: Successful HTML export.
    Checks that the report's to_file method is called with a correctly formatted path.
    """
    # Arrange:
    mock_profile = MagicMock()
    
    # Act:
    app_ui._handle_export_html(mock_profile)

    # Assert:
    mock_makedirs.assert_called_once_with("reports", exist_ok=True)
    # checks report file is saved in 'reports' dir with correct format
    mock_profile.to_file.assert_called_once()
    saved_path = mock_profile.to_file.call_args.args[0]
    assert saved_path.startswith("reports/profiling_report_")
    assert saved_path.endswith(".html")
    # checks user receives a confirmation popup
    mock_gr_info.assert_called_once()

@patch('doc_investigator_strategy_pattern.app.gr.Warning')
def test_handle_export_html_no_report(mock_gr_warning, app_ui):
    """
    Test Case: User tries to export before a report is generated.
    Checks that a warning is shown.
    """
    # Arrange:
    # - The state passed to the handler is None.

    # Act:
    app_ui._handle_export_html(None)

    # Assert:
    mock_gr_warning.assert_called_once_with("No report has been generated yet. Please generate the report first.")