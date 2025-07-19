# tests/test_app.py

"""
Unit tests for the AppUI class, focusing on event handler logic.
These tests are designed to run partly in async context to mimic the Gradio environment.
"""

import pytest
import gradio as gr
import sys
from unittest.mock import MagicMock, patch

from doc_investigator_strategy_pattern.app import AppUI
from doc_investigator_strategy_pattern.documents import InvalidFileTypeException
from doc_investigator_strategy_pattern.database import InteractionLog

# get rid off warning filter to suppress DeprecationWarning from Gradio
pytestmark = [
    pytest.mark.filterwarnings("ignore:There is no current event loop:DeprecationWarning:gradio.utils")
]

@pytest.fixture
def mock_services():
    """Provides a dictionary of mock services. Remains a synchronous fixture."""
    config_mock = MagicMock()
    config_mock.LLM_MODEL_NAME = "mock-model-name"
    # default values for reset button test
    config_mock.TEMPERATURE = 0.2
    config_mock.TOP_P = 0.95
    return {
        "config": config_mock,
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
    """
    # Arrange
    mock_files = [MagicMock()]
    mock_prompt = "test prompt"
    mock_answer = "This is a real answer."
    temperature_from_ui = 0.75
    top_p_from_ui = 0.85
    mock_services["doc_processor"].process_files.return_value = "Extracted text"
    mock_services["ai_service"].get_answer.return_value = mock_answer
    mock_services["config"].LLM_MODEL_NAME = "mock-model-name"
    mock_services["config"].UNKNOWN_ANSWER = "Unknown"
    mock_services["config"].NOT_ALLOWED_ANSWER = "Not Allowed"
    mock_services["config"].MAX_CONTEXT_CHARACTERS = 800000

    # Act: Although the handler itself is synchronous, call it from an async
    # test function being a simulation of the Gradio runtime
    (answer_update, panel_update,
     _, _, _,
     temp_state_out, top_p_state_out) = app_ui._handle_investigation(
        mock_files, mock_prompt, temperature_from_ui, top_p_from_ui
    )  

    # Assert
    # service called with dynamic param values
    mock_services["doc_processor"].validate_files.assert_called_once_with(mock_files)
    mock_services["doc_processor"].process_files.assert_called_once_with(mock_files)
    mock_services["ai_service"].get_answer.assert_called_once_with(
        "Extracted text", mock_prompt, temperature_from_ui, top_p_from_ui
    )
    assert answer_update['value'] == mock_answer, "Extracted investigation text and ai service not as expected"
    assert panel_update['visible'] is True, "Investigation panel is not updated resp. its not visible"
    assert temp_state_out == temperature_from_ui, "Wrong temperature value returned for state storage"
    assert top_p_state_out == top_p_from_ui, "Wrong top-p value returned for state storage"
    mock_services["db_manager"].log_interaction.assert_not_called()

@pytest.mark.asyncio    
async def test_handle_investigation_unknown_answer_logs_correctly(app_ui, mock_services):
    """
    Tests that a non-answer is auto-logged with the new, correct schema.
    """
    # Arrange
    mock_files = [MagicMock(name="test.pdf")]
    mock_prompt = "test prompt"
    unknown_answer = "Your request is unknown..."
    mock_services["doc_processor"].process_files.return_value = "Some text from a document."
    mock_services["ai_service"].get_answer.return_value = unknown_answer
    mock_services["config"].LLM_MODEL_NAME = "mock-model-name"
    mock_services["config"].UNKNOWN_ANSWER = unknown_answer
    mock_services["config"].NOT_ALLOWED_ANSWER = "Not Allowed"
    mock_services["config"].MAX_CONTEXT_CHARACTERS = 800000
    temperature_from_ui = 0.5
    top_p_from_ui = 0.5
    
    # Act
    (answer_update, panel_update, doc_names_out,
     prompt_out, answer_out, temp_out, top_p_out) = app_ui._handle_investigation(
        mock_files, mock_prompt, temperature_from_ui, top_p_from_ui
    )

    # Assert
    assert panel_update['visible'] is False, "Investigation panel is updated"
    
    db_mock = mock_services["db_manager"]
    db_mock.log_interaction.assert_called_once() 
    
    # check the Pydantic object
    logged_object = db_mock.log_interaction.call_args.args[0]
    assert isinstance(logged_object, InteractionLog), "Instance is not an object of Pydantic InteractionLog"
    assert logged_object.output_passed == 'no', "User decision about output passed is not 'no'"
    assert logged_object.prompt == mock_prompt, "User prompt input is not as expected"
    assert logged_object.eval_reason == "no reason given", "Free user evaluation reason text is given, but shall not"
    assert logged_object.model_name == "mock-model-name", "LLM model name not as expected"
    assert logged_object.temperature == temperature_from_ui, "temperature is not as in UI"
    assert logged_object.top_p == top_p_from_ui, "top-p is not as in UI"


@pytest.mark.asyncio
async def test_handle_evaluation_persists_slider_values(app_ui, mock_services):
    """
    Tests that the evaluation handler persist the last used slider values,
    not reset them.
    """
    # Arrange
    choice = "✔️ Yes, the answer is helpful and accurate."
    reason = "A valid reason."
    # The values that were used for the query, passed from state
    last_used_temp = 0.55
    last_used_top_p = 0.65

    # Act
    result_tuple = app_ui._handle_evaluation(
        "doc.txt", "prompt", "answer", choice, reason, last_used_temp, last_used_top_p
    )

    # Assert
    # return tuple has 13 elements: last two are the sliders
    assert len(result_tuple) == 13, "return tuple does not include 13 elements"
    
    # checks that slider outputs are no-op updates
    temp_slider_update = result_tuple[-2]
    top_p_slider_update = result_tuple[-1]
    assert temp_slider_update == gr.update(), "temperature slider is no no-op update"
    assert top_p_slider_update == gr.update(), "top-p slider is no no-op update"

    # state itself is persisted
    temp_state_update = result_tuple[-4]
    top_p_state_update = result_tuple[-3]
    assert temp_state_update == gr.update(), "Wrong state of temperature"
    assert top_p_state_update == gr.update(), "Wrong state of top-p"
    
def test_reset_llm_button_functionality(app_ui):
    """
    Tests lambda function for the LLM param reset button,
    should return the default values from config file.
    """
    # Arrange
    # LLM param reset button is a lambda function,
    # so simulate what that lambda does to test its output
    reset_function = lambda: (app_ui.config.TEMPERATURE, app_ui.config.TOP_P)

    # Act
    temp_output, top_p_output = reset_function()

    # Assert
    # outputs match default values set in mock_services fixture
    assert temp_output == 0.2, "temperature output doesn't match default 0.2"
    assert top_p_output == 0.95, "top-p output doesn't match default 0.95"
    
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
    temp_from_state = 0.8
    top_p_from_state = 0.9

    # Act
    app_ui._handle_evaluation(
        "doc.txt", "prompt", "answer", choice, reason, temp_from_state, top_p_from_state
    )

    # Assert
    db_mock = mock_services["db_manager"]
    db_mock.log_interaction.assert_called_once()
    logged_object = db_mock.log_interaction.call_args.args[0]
    assert isinstance(logged_object, InteractionLog), "logged object is no InteractionLog instance"
    assert logged_object.output_passed == 'yes', "User decision about output passed is not 'yes'"
    assert logged_object.eval_reason == reason, "Free user evaluation reason text is not as expected"
    assert logged_object.document_names == 'doc.txt', "Document name is not 'doc.txt'"
    assert logged_object.model_name == 'mock-model-name', "LLM model name not as expected"
    assert logged_object.temperature == temp_from_state, "temperature value not as state"
    assert logged_object.top_p == top_p_from_state, "top-p value not as state"

@pytest.mark.asyncio
async def test_handle_evaluation_success_with_no_reason(app_ui, mock_services):
    """Tests the evaluation handler logs correctly when no reason is provided."""
    # Arrange
    choice = "❌ No, the answer is not helpful or inaccurate."
    reason = "   " # Test with empty space to ensure stripping works
    mock_services["config"].NO_REASON_GIVEN = "no reason given"
    mock_services["config"].LLM_MODEL_NAME = "mock-model-name"
    temp_from_state = 0.1
    top_p_from_state = 0.2

    # Act
    app_ui._handle_evaluation(
        "doc.txt", "prompt", "answer", choice, reason, temp_from_state, top_p_from_state
    )

    # Assert
    db_mock = mock_services["db_manager"]
    db_mock.log_interaction.assert_called_once()
    logged_object = db_mock.log_interaction.call_args.args[0]
    assert isinstance(logged_object, InteractionLog), "logged object is no InteractionLog instance"
    assert logged_object.output_passed == 'no', "User decision about output passed is not 'no'"
    assert logged_object.eval_reason == 'no reason given', "Free user evaluation reason text is given, but shall not"
    assert logged_object.temperature == temp_from_state, "temperature value not as state"
    assert logged_object.top_p == top_p_from_state, "top-p value not as state"

@patch('doc_investigator_strategy_pattern.app.analysis.generate_profile_report')
def test_handle_profile_generation_success(mock_generate_report, app_ui):
    """
    Test Case: Successful profile generation in the UI.
    Checks that the handler returns the correct HTML, state object, and enabled button.
    """
    # Arrange
    # - Create a mock ProfileReport object that our mocked analysis function will return.
    mock_profile = MagicMock()
    mock_profile.to_html.return_value = "<h1>Mock Report HTML</h1>"
    mock_generate_report.return_value = mock_profile

    # Act
    html_output, state_output, button_update = app_ui._handle_profile_generation()

    # Assert
    mock_generate_report.assert_called_once()
    assert html_output == "<h1>Mock Report HTML</h1>", "Report mock is not available"
    assert state_output is mock_profile, "Report mock profile is not as expected"
    assert button_update == gr.update(interactive=True), "Report button for creation is not interactive"

@patch('doc_investigator_strategy_pattern.app.analysis.generate_profile_report', return_value=None)
def test_handle_profile_generation_failure(mock_generate_report, app_ui):
    """
    Test Case: Failed profile generation in the UI (e.g., file not found).
    Checks that the handler returns an error message and a disabled button.
    """
    # Arrange
    # - The mock is already configured to return None by the patch decorator.

    # Act
    html_output, state_output, button_update = app_ui._handle_profile_generation()

    # Assert
    mock_generate_report.assert_called_once()
    assert "Error:" in html_output, "Failure message of profiling report creation does not include 'Error:' string"
    assert state_output is None, "Output state of creation failure is not 'None'"
    assert button_update == gr.update(interactive=False), "Report button for creation is interactive"

@patch('doc_investigator_strategy_pattern.app.os.makedirs')
@patch('doc_investigator_strategy_pattern.app.gr.Info')
def test_handle_export_html_success(mock_gr_info, mock_makedirs, app_ui):
    """
    Test Case: Successful HTML export.
    Checks that the report's to_file method is called with a correctly formatted path.
    """
    # Arrange
    mock_profile = MagicMock()
    
    # Act
    app_ui._handle_export_html(mock_profile)

    # Assert
    mock_makedirs.assert_called_once_with("reports", exist_ok=True)
    # checks report file is saved in 'reports' dir with correct format
    mock_profile.to_file.assert_called_once()
    saved_path = mock_profile.to_file.call_args.args[0]
    assert saved_path.startswith("reports/profiling_report_"), "Profiling report name structure is not correct"
    assert saved_path.endswith(".html"), "Profiling report type is not '.html'"
    # checks user receives a confirmation popup
    mock_gr_info.assert_called_once()

@patch('doc_investigator_strategy_pattern.app.gr.Warning')
def test_handle_export_html_no_report(mock_gr_warning, app_ui):
    """
    Test Case: User tries to export before a report is generated.
    Checks that a warning is shown.
    """
    # Arrange
    # - The state passed to the handler is None.

    # Act
    app_ui._handle_export_html(None)

    # Assert
    mock_gr_warning.assert_called_once_with("No report has been generated yet. Please generate the report first.")