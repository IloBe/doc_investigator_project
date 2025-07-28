# tests/test_app.py

"""
Unit tests for the AppUI class, focusing on event handler logic.
These tests are designed to run partly in async context to mimic the Gradio environment.
These tests mock the Burr application to ensure the UI layer
interacts with the state machine correctly.
"""

# ----------
# Imports
# ----------
import pytest
import gradio as gr
import sys
from unittest.mock import MagicMock, patch

from doc_investigator_strategy_pattern.app import AppUI
from doc_investigator_strategy_pattern.documents import InvalidFileTypeException
from doc_investigator_strategy_pattern.database import InteractionLog

# ----------
# Coding
# ----------

# get rid off warning filter to suppress DeprecationWarning from Gradio
pytestmark = [
    pytest.mark.filterwarnings(
        "ignore:There is no current event loop:DeprecationWarning:gradio.utils"
    )
]

@pytest.fixture
def mock_dependencies():
    """Provides a dictionary of mock services. Remains a synchronous fixture."""
    config_mock = MagicMock()
    config_mock.LLM_MODEL_NAME = "mock-model-name"
    # default values of LLM params for reset button test
    config_mock.TEMPERATURE = 0.2
    config_mock.TOP_P = 0.95
    return {
        "config": config_mock,
        "db_manager": MagicMock(),
        "doc_processor": MagicMock(),
        "ai_service": MagicMock(),
    }

@pytest.fixture
def app_ui(mock_dependencies):
    """Provides an AppUI instance with all backend services mocked."""
    return AppUI(**mock_dependencies)

# --- 
# Tests of 'Investigation' tab (Burr-related)
# ---

# patch `build_application` here to control Burr app instance on demand
# in UI tests without calling real state machine logic
@patch('doc_investigator_strategy_pattern.app.build_application')
@pytest.mark.asyncio
async def test_handle_investigation_success(mock_build_application, app_ui):
    """
    Tests the main investigation handler, ensuring it calls Burr and updates the UI correctly.
    """
    # Arrange
    mock_burr_app = MagicMock()
    mock_build_application.return_value = mock_burr_app

    # to avoid ValueError - not enough values to unpack:
    # configure mock's `run` method to return 3-tuple like real method,
    # contents don't matter...
    mock_burr_app.run.return_value = (MagicMock(), MagicMock(), MagicMock())
    
    mock_files = [MagicMock()]
    mock_prompt = "test prompt"
    temperature_from_ui = 0.75
    top_p_from_ui = 0.85

    # UI handler reads burr app's internal state
    mock_burr_app.state = {
        "llm_answer": "This is a real answer.",
        "is_real_answer": True,
        "doc_names": "doc1.pdf",
        "prompt": mock_prompt,
        "error_message": None
    }

    # Act
    (answer_update, panel_update,
     doc_names_out, prompt_out, answer_out,
     temp_state_out, top_p_state_out) = app_ui._handle_investigation(
        mock_files, mock_prompt, temperature_from_ui, top_p_from_ui
    )

    # Assert
    # verify burr_app correctly build and run
    mock_build_application.assert_called_once_with(
        config = app_ui.config,
        db_manager = app_ui.db_manager,
        doc_processor = app_ui.doc_processor,
        ai_service = app_ui.ai_service
    )
    mock_burr_app.run.assert_called_once()
    call_inputs = mock_burr_app.run.call_args.kwargs['inputs']
    assert call_inputs['prompt'] == mock_prompt
    assert call_inputs['llm_params']['temperature'] == temperature_from_ui
    
    # verify UI components updated correctly based on mocked state
    assert answer_update['value'] == "This is a real answer.", "Extracted investigation text and ai service not as expected"
    assert panel_update['visible'] is True, "Investigation panel is not updated resp. its not visible"
    assert doc_names_out == "doc1.pdf", "Document name not as expected"
    assert prompt_out == mock_prompt, "LLM output prompt txt not as expected"
    assert answer_out == "This is a real answer.", "LLM output state result not as expected"
    assert temp_state_out == temperature_from_ui, "Wrong temperature value returned for state storage"
    assert top_p_state_out == top_p_from_ui, "Wrong top-p value returned for state storage"


@patch('doc_investigator_strategy_pattern.app.build_application')
@pytest.mark.asyncio
async def test_handle_investigation_auto_logged(mock_build_application, app_ui):
    """
    Tests the handler when Burr returns a non-answer that was auto-logged.
    """
    # Arrange
    mock_burr_app = MagicMock()
    mock_build_application.return_value = mock_burr_app

    # to avoid ValueError - not enough values to unpack:
    # configure mock's `run` method to return 3-tuple like real method,
    # contents don't matter...
    mock_burr_app.run.return_value = (MagicMock(), MagicMock(), MagicMock())
    
    mock_burr_app.state = {
        "llm_answer": "Unknown",
        "is_real_answer": False,
        "error_message": None
    }

    # Act
    (answer_update, panel_update, *other_states) = app_ui._handle_investigation(
        [MagicMock()], "prompt", 0.5, 0.5
    )

    # Assert
    assert answer_update['value'] == "Unknown", "Default answer for unknown is not there"
    assert panel_update['visible'] is False, "Evaluation analysis panel should be hidden"
    assert all(s is None for s in other_states), "Not all state variables are correctly reset to None"

    
@pytest.mark.asyncio
async def test_handle_evaluation_calls_burr_step(app_ui, mock_dependencies):
    """
    Tests that the evaluation handler calls burr_app.step() correctly.
    """
    # Arrange
    choice = "✔️ Yes..."
    reason = "A valid reason."
    # place a mock Burr app into AppUI instance to simulate
    # state after an investigation has been run and halted
    app_ui.burr_app = MagicMock()
    
    # Act
    result_tuple = app_ui._handle_evaluation(
        "doc.txt", "prompt", "answer", choice, reason, 0.5, 0.5
    )
    
    # Assert
    assert app_ui.burr_app.step.call_count == 2, "App code hasn't called step() twice, as it is expected"
    
    # inspect first call ensures inputs were correct
    first_call_inputs = app_ui.burr_app.step.call_args_list[0].kwargs['inputs']
    assert first_call_inputs['evaluation_choice'] == choice, "Evaluation choice buttons are not set"
    assert first_call_inputs['evaluation_reason'] == reason , "Evaluation reason txt window component not there"
    
    # UI reset
    assert result_tuple[0] is None, "file_uploader window component is not cleared"
    assert result_tuple[1] == "", "User prompt_input window component is not cleared"
    assert result_tuple[3]['visible'] is False, "Evaluation analysis panel 'evaluation_panel' is not hidden"
    
    # sliders receive a "no-op" update
    UpdateObjectType = type(gr.update())
    assert isinstance(result_tuple[9], UpdateObjectType), "temperature slider reset not updated correctly, no-op"
    assert isinstance(result_tuple[10], UpdateObjectType), "top-p slider reset not updated correctly, no-op"

# ---
# Tests of 'Evaluation Analysis' tab (not Burr related)
# ---
    
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
    # outputs match default values set in mock_dependencies fixture
    assert temp_output == 0.2, "temperature output doesn't match default 0.2"
    assert top_p_output == 0.95, "top-p output doesn't match default 0.95"
    
@pytest.mark.asyncio
async def test_handle_file_validation_failure(app_ui, mock_dependencies):
    """
    Tests that the file validation handler catches an exception and returns None.
    """
    # Arrange
    mock_files = [MagicMock()]
    mock_dependencies["doc_processor"].validate_files.side_effect = InvalidFileTypeException("Bad file")
    
    # Act
    # We patch 'gradio.Warning' to prevent it from trying to render in a non-UI context
    with patch('gradio.Warning') as mock_gr_warning:
        result = app_ui._handle_file_validation(mock_files)

    # Assert
    assert result is None, "The handler should return None to clear the Gradio component."
    mock_gr_warning.assert_called_once(), "gr.Warning should have been called to inform the user."


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