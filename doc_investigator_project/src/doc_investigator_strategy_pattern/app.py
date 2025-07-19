# src/doc_investigator_strategy_pattern/app.py

"""
Gradio UI module for the Document Investigator application.

Defines the AppUI class, which constructs the user interface using the
Gradio library. It manages UI components, state and event handling. It
acts as the central controller that connects user actions to the
backend services (document processing, AI and database).
"""

# --- FIX: Suppress noisy dependency warnings at the very start ---
# handle warnings from third-party libs that are not critical for app's function,
# appears with old WSL ubuntu version 20.04 on Windows 10 and Python 3.10 version, see:
# https://github.com/numpy/numpy/issues/22187
import warnings
warnings.filterwarnings(
    "ignore",
    message="Signature b'\\x00\\xd0\\xcc\\xcc\\xcc\\xcc\\xcc\\xcc\\xfb\\xbf\\x00\\x00\\x00\\x00\\x00\\x00' for <class 'numpy.longdouble'> does not match any known type")
warnings.filterwarnings("ignore", message="Upgrade to ydata-sdk")
# ---

import gradio as gr
import os
import sqlite3
from datetime import datetime
from typing import Any, List, Optional, Tuple
from loguru import logger
from ydata_profiling import ProfileReport
from pydantic import ValidationError

from .documents import InvalidFileTypeException
from . import analysis
from .database import InteractionLog # Pydantic model

# if typing, avoid circular imports at runtime
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .config import Config
    from .database import DatabaseManager
    from .documents import DocumentProcessor
    from .services import GeminiService

class AppUI:
    """
    Encapsulates the Gradio UI and its event handling logic.

    Initialized with all necessary backend services and the app
    configuration, following dependency injection design pattern.
    """
    
    def __init__(self,
        config: 'Config',
        db_manager: 'DatabaseManager',
        doc_processor: 'DocumentProcessor',
        ai_service: 'GeminiService'
    ):
        """
        Initializes the AppUI class.

        Args:
            config: application configuration object
            db_manager: database manager instance
            doc_processor: document processor instance
            ai_service: AI service instance
        """
        self.config = config
        self.db_manager = db_manager
        self.doc_processor = doc_processor
        self.ai_service = ai_service

        # `_build_ui` method returns Gradio app object, stored here
        self.app: gr.Blocks = self._build_ui()

    def _build_ui(self) -> gr.Blocks:
        """
        Constructs the entire Gradio user interface using Blocks.

        Returns:
            A configured Gradio Blocks object representing the application UI.
        """
        # theme inspired by Google's modern aesthetic
        theme = gr.themes.Soft(
            primary_hue = gr.themes.colors.blue,
            secondary_hue = gr.themes.colors.sky,
            neutral_hue = gr.themes.colors.slate,
        ).set(
            body_background_fill = "#F7F7F7",
            block_background_fill = "white",
            block_border_width = "1px",
            block_shadow = "*shadow_drop_lg",
            block_radius = "12px",
            input_background_fill = "#F7F7F7",
        )
        
        with gr.Blocks(theme=theme,
                       title="Document Investigator",
                      ) as app:
            
            # --- State Management ---
            state_doc_names = gr.State(None)
            state_last_prompt = gr.State(None)
            state_last_answer = gr.State(None)
            state_temperature = gr.State(None)
            state_top_p = gr.State(None)
            state_profile_report = gr.State(None)

            # --- UI Layout ---
            # panel header
            gr.Markdown(
               """
               <div style="text-align: center;">
                   <h1><img src="https://em-content.zobj.net/source/google/387/magnifying-glass-tilted-left_1f50d.png" width="35" height="35" style="display:inline-block; vertical-align: middle;"> Document Investigation</h1>
               </div>
               """
            )
                        
            with gr.Tabs():
                with gr.TabItem("Investigate"):
                    self._build_investigate_tab(
                        state_doc_names,
                        state_last_prompt,
                        state_last_answer,
                        state_temperature,
                        state_top_p,
                    )
                with gr.TabItem("Evaluation Analysis"):
                    self._build_analyze_tab(state_profile_report)
        return app


    def _build_investigate_tab(self,
        state_doc_names: gr.State,
        state_last_prompt: gr.State,
        state_last_answer: gr.State,
        state_temperature: gr.State,
        state_top_p: gr.State,
        #state_profile_report = gr.State(None),
    ) -> None:
        """Builds the main 'Investigate' tab UI components."""
        
        # first row at the top
        with gr.Row():
            # left side for workflow description
            with gr.Column(scale=2):  # larger horizontal space
                gr.Markdown(
                    """
                    ### How to use this tool:
                    1.  **LLM parameters** temperature = 0.2 & top-p = 0.95 are defaults being more focused, not creative.
                    2.  If the LLM output result is not as expected, you can change this LLM parameters.
                    3.  **LLM output** language follows the **user prompt** language, but default is English.
                    4.  **Upload** one or more documents.
                    5.  **Ask a specific question** about their content (user prompt).
                    6.  Click **"Investigate"** to get an AI-powered answer (LLM output).
                    7.  **Evaluate** the answer to help improve the system.
                    8.  For **"Exit"** manually close this browser tab, then use 'Ctrl+C' on CLI terminal session.

                    **Supported Document Types:** `.pdf`, `.docx`, `.xlsx`, `.txt`
                    """
                )
            # right side for LLM settings    
            with gr.Column(scale=1): 
                with gr.Accordion(f"LLM Settings ({self.config.LLM_MODEL_NAME})", open=False):
                    temperature_slider = gr.Slider(
                        minimum = 0.0,
                        maximum = 1.0,
                        step = 0.05,
                        label = "Temperature",
                        value = self.config.TEMPERATURE
                    )
                    top_p_slider = gr.Slider(
                        minimum = 0.0,
                        maximum = 1.0,
                        step = 0.05,
                        label = "Top-P",
                        value = self.config.TOP_P
                    )
                    reset_llm_button = gr.Button("Reset to Defaults", variant="secondary")
        
        gr.Markdown("---") # Visual separator
                
        # second row for core business workflow
        with gr.Row():
            # left column for user inputs
            with gr.Column(scale=1):        
                file_uploader = gr.File(
                    label = "Step 1: Upload Your Documents",
                    file_count = "multiple",
                    # must be None, not starting Gradios own validation; using our configured
                    # doc type list would block our custom .upload() event handler (_handle_file_validation)
                    file_types = None
                )
                
                prompt_input = gr.Textbox(
                    label = "Step 2: Enter Your Prompt",
                    lines = 4,
                    placeholder = "e.g. 'Summarize key findings in the financial report.'")
                
                submit_btn = gr.Button("Investigate", variant="primary")
                
            # right column for LLM params and answer output
            with gr.Column(scale=2):
                # LLM result and evaluation part
                answer_output = gr.Markdown(
                    value = "<p style='color:grey;'>The answer will be shown here...</p>",
                    label = "LLM Answer")
                with gr.Column(visible = False) as evaluation_panel:
                    evaluation_radio = gr.Radio(
                        ["✔️ Yes, the answer is helpful and accurate.",
                         "❌ No, the answer is not helpful or inaccurate."],
                        label = "Step 3: Was this answer useful?"
                    )
                    eval_reason_textbox = gr.Textbox(
                        label="Optional: Explain your evaluation",
                        placeholder="Regarding your passing decision about the LLM answer: Please add your reason with max. 10 sentences. This is optional.",
                        lines=5,  # Allows for multi-line input with a scrollbar
                        interactive=True,
                        visible=True
                    )
                    evaluation_button = gr.Button("Submit Evaluation and Reset")

        # --- Event Handling ---
        file_uploader.upload(
            fn=self._handle_file_validation,
            inputs=[file_uploader],
            outputs=[file_uploader]
        )
        
        submit_btn.click(
            fn = self._handle_investigation,
            inputs = [file_uploader,
                      prompt_input,
                      temperature_slider,
                      top_p_slider],
            outputs = [answer_output,
                       evaluation_panel,
                       state_doc_names,
                       state_last_prompt,
                       state_last_answer,
                       state_temperature,
                       state_top_p]
        )

        evaluation_button.click(
            fn = self._handle_evaluation,
            inputs = [state_doc_names,
                      state_last_prompt,
                      state_last_answer,
                      evaluation_radio,
                      eval_reason_textbox,
                      state_temperature,
                      state_top_p],
            outputs = [file_uploader,
                       prompt_input,
                       answer_output,
                       evaluation_panel,
                       evaluation_radio,
                       eval_reason_textbox, 
                       state_doc_names,
                       state_last_prompt,
                       state_last_answer,
                       temperature_slider,
                       top_p_slider]
        )
        
        reset_llm_button.click(
            fn=lambda: (self.config.TEMPERATURE, self.config.TOP_P),
            inputs=None,
            outputs=[temperature_slider, top_p_slider]
        )


    def _build_analyze_tab(self, state_profile_report: gr.State) -> None:
        """
        Builds the 'Analyze Evaluations' tab UI components with sections of Datasette and data profiling,
        including customized styling.
        """
        with gr.Blocks() as analyze_tab:
            gr.Markdown(
                """
                ## Evaluation Analysis Tools
                This section provides two ways to analyze the collected evaluation data.
                """
            )
            
            with gr.Accordion(
                label='Option 1: Manual Analysis with Datasette',
                open=True,
            ):
                gr.Markdown(
                    """
                    All interactions and evaluations are stored in a local SQLite database (`doc_investigator_prod.db`).
                    Datasette provides an instant, read-only web interface to explore this data for analysis.

                    **Instructions:**
                    1.  Open a new terminal or command prompt in this project's directory.
                    2.  Click the button below to copy the command.
                    3.  Paste the command into your terminal and press Enter.
                    4.  Your web browser will open with the Datasette interface, ready to explore the `interactions` table.
                    5.  For creation of the automated data profiling report, store content as `evaluations.csv` in `data` directory.
                    """
                )
                datasette_command = f"datasette {self.config.DB_FILE} --open"
                gr.Textbox(
                    value=datasette_command,
                    label="Command to run Datasette",
                    interactive=False,
                    show_copy_button=True
                )
            
            with gr.Accordion(
                label="Option 2: Automated Data Profiling Report",
                open=False,
            ):
                gr.Markdown(
                    """
                    Generate a detailed data profile report from the `data/evaluations.csv` file.
                    You get a statistical overview of the entire dataset, including distributions,
                    correlations, missing values and potential data quality issues.

                    **Instructions:**
                    1.  Ensure you have exported your database `interactions` table to `data/evaluations.csv` via Datasette.
                    2.  Click the blue button below to generate or refresh the report. Its overview is visualised afterwards.
                    3.  After generating, you can export the report as a self-contained HTML file.
                    4.  Export of profiling report is necessary to get all interactive features of this information.
                    """
                )
                profile_button = gr.Button("Generate/Refresh Profile Report", variant="primary")
                export_html_button = gr.Button("Export to HTML", interactive=False)
                
                with gr.Group():
                    profile_output = gr.HTML(
                        "<div style='text-align:center; color:grey;'><p>Area to show the data profile report.</p></div>"
                    )
                    

           # Event handling for profiling section
            profile_button.click(
                fn=self._handle_profile_generation,
                inputs=None,
                outputs=[profile_output, state_profile_report, export_html_button]
            )

            export_html_button.click(
                fn=self._handle_export_html,
                inputs=[state_profile_report],
                outputs=None
            )
    
    
    def _handle_profile_generation(self) -> Tuple[str, Optional[ProfileReport], Any]:
        """
        Event handler to generate, display and enable the export of the data profile report.
        """
        csv_path = os.path.join("data", "evaluations.csv")
        gr.Info("Generating data profile... This may take a moment.")
        profile = analysis.generate_profile_report(csv_path=csv_path)

        if profile:
            return profile.to_html(), profile, gr.update(interactive=True)
        else:
            error_html = "<p style='color:red; text-align:center;'><b>Error:</b> Could not generate report. Please check if a none empty `data/evaluations.csv` exists.</p>"
            return error_html, None, gr.update(interactive=False)

        
    def _handle_export_html(self, profile: Optional[ProfileReport]) -> None:
        """
        Saves the generated profile report to a timestamped HTML file.
        """
        if not profile:
            gr.Warning("No report has been generated yet. Please generate the report first.")
            return

        reports_dir = "reports"
        os.makedirs(reports_dir, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"profiling_report_{timestamp}.html"
        filepath = os.path.join(reports_dir, filename)

        try:
            profile.to_file(filepath)
            logger.success(f"Successfully exported report to '{filepath}'.")
            gr.Info(f"Success! Report saved to: {filepath}")
        except Exception as e:
            logger.error(f"Failed to export report to file. Error: {e}", exc_info=True)
            gr.Error(f"Failed to save the report. Please check the logs.")    


    def _handle_file_validation(self, files: Optional[List[Any]]) -> Optional[List[Any]]:
        """
        Validates files immediately upon upload. If invalid, shows a warning
        and clears the component. This provides instant, non-blocking feedback.

        Args:
            files: List of file-like objects from Gradio uploader

        Returns:
            List of files if they are all valid or None if validation fails,
            which clears the file uploader component.
        """
        if not files:
            return None

        try:
            logger.info("Performing immediate validation on uploaded files.")
            self.doc_processor.validate_files(files)
            logger.success("Immediate file validation passed.")
            return files  # Success: Keep the valid files listed in the UI

        except InvalidFileTypeException as e:
            logger.warning(f"User uploaded an invalid file type. Error: {e}")
            supported_types = ", ".join(self.config.SUPPORTED_FILE_TYPES)
            gr.Warning(f"Invalid File Type: {e} Please upload only supported file types: {supported_types}")
            return None  # Failure: Returning None resets the file uploader


    def _handle_investigation(self,
                              files: Optional[List[Any]],
                              prompt: str,
                              temperature: float,
                              top_p: float
    ) -> Tuple[Any, ...]:
        """
        Orchestrates the main investigation workflow with dynamic LLM parameters.

        Raises:
            gr.Error: If user inputs are invalid (no files, no prompt).
        """
        if not files:
            raise gr.Error("Please upload at least one document to investigate.")
        if not prompt.strip():
            raise gr.Error("Please enter a prompt to continue.")

        logger.info(f"Starting investigation for prompt: '{prompt[:50]}...'")
        doc_names = ", ".join([os.path.basename(f.name) for f in files])

        try:
            self.doc_processor.validate_files(files)
            full_text = self.doc_processor.process_files(files)

            # truncate context if exceeds configured limit
            if len(full_text) > self.config.MAX_CONTEXT_CHARACTERS:
                logger.warning(
                    f"Context length ({len(full_text)}) exceeds limit. Truncating to {self.config.MAX_CONTEXT_CHARACTERS} characters.")
                full_text = full_text[:self.config.MAX_CONTEXT_CHARACTERS]

            answer = self.ai_service.get_answer(full_text, prompt, temperature, top_p)

            # check if answer is real one or a pre-defined inappropriate response
            is_real_answer = answer not in [self.config.UNKNOWN_ANSWER, self.config.NOT_ALLOWED_ANSWER] and "error" not in answer.lower()

            if is_real_answer:
                logger.success("Correct answer received. Displaying to user for evaluation.")
                return (gr.update(value = answer),
                        gr.update(visible = True),
                        doc_names, 
                        prompt, 
                        answer, 
                        temperature, 
                        top_p)
            else:
                # automatic background logging for non-answers
                logger.info(f"Pre-defined answer returned: '{answer}'. Logging automatically with 'no' evaluation.")
                try:
                    log_entry = InteractionLog(
                        document_names = doc_names,
                        prompt = prompt,
                        answer = answer,
                        output_passed = "no",
                        eval_reason = "no reason given",
                        model_name = self.config.LLM_MODEL_NAME,
                        temperature = temperature,   # default is: self.config.TEMPERATURE,
                        top_p = top_p   # default is: self.config.TOP_P
                    )
                    self.db_manager.log_interaction(log_entry)
                except ValidationError as e:
                    # critical developer error
                    logger.critical(f"Pydantic validation failed for auto-log. Error: {e}")
                
                except sqlite3.Error as e:
                    logger.error(f"Failed to auto-log non-answer to database. Error: {e}")
                    # don't raise a gr.Error here, it's a background task
                    
                return gr.update(value = answer), gr.update(visible = False), None, None, None, None, None

        except InvalidFileTypeException as e:
            raise gr.Error(str(e))
        except Exception as e:
            logger.critical(f"An unexpected error occurred during investigation: {e}", exc_info = True)
            raise gr.Error("An unexpected system error occurred. Please check the logs and try again.")


    def _handle_evaluation(self,
                           doc_names: str,
                           prompt: str,
                           answer: str,
                           choice: Optional[str],
                           eval_reason: str,
                           temperature: float,
                           top_p: float
    ) -> Tuple[Any, ...]:
        """
        Handles user's evaluation submission, logs it, and resets the UI.
        """
        if not choice:
            gr.Warning("Please select an evaluation passed option ('Yes' or 'No') before submitting.")
            # return no-op updates to keep UI state as-is
            return (gr.update(), gr.update(), gr.update(),
                    gr.update(visible = True),
                    gr.update(), gr.update(), gr.update(), gr.update(), gr.update())

        evaluation_text = "yes" if "✔️ Yes" in choice else "no"
        reason_text = eval_reason.strip() if eval_reason and eval_reason.strip() else self.config.NO_REASON_GIVEN
        logger.info(f"User submitted evaluation: '{evaluation_text}' with reason: '{reason_text[:50]}'. Logging to database.")

        try:
            log_entry = InteractionLog(
                document_names = doc_names,
                prompt = prompt,
                answer = answer,
                output_passed = evaluation_text,
                eval_reason = reason_text,
                model_name = self.config.LLM_MODEL_NAME,
                temperature = temperature,   # defautl is: self.config.TEMPERATURE,
                top_p = top_p                # default is: self.config.TOP_P
            )
            self.db_manager.log_interaction(log_entry)
            gr.Info("Evaluation saved! The interface has been reset for next investigation.")
            
            # returns tuple to reset all relevant UI items and states to initial values
            return (
                None,  # file_uploader
                "",    # prompt_input
                "<p style='color:grey;'>The answer will be shown here...</p>", # answer_output
                gr.update(visible = False), # evaluation_panel
                None,  # evaluation_radio
                "",    # eval reason
                None,  # state_doc_names
                None,  # state_last_prompt
                None,  # state_last_answer
                gr.update(), gr.update(),  # persist temperature and top_p state
                gr.update(), gr.update()   # persist slider UI values
            )
        
        except ValidationError as e:
            logger.error(f"Pydantic validation failed on user evaluation. Error: {e}", exc_info=True)
            gr.Error("Failed to save evaluation due to invalid data. Please check logs.")
            # keep panel open and state intact for user to retry
            return (gr.update(), gr.update(), gr.update(),
                    gr.update(visible = True),
                    gr.update(), gr.update(), gr.update(), gr.update(), gr.update(), 
                    gr.update(), gr.update(), gr.update(), gr.update())
        
        except sqlite3.Error as e:
            logger.error(f"Failed to save evaluation to database. Error: {e}", exc_info = True)
            gr.Error("Failed to save evaluation due to a database error. Please try again.")
            # keep panel open and state intact for user to retry
            return (gr.update(), gr.update(), gr.update(),
                    gr.update(visible = True),
                    gr.update(), gr.update(), gr.update(), gr.update(), gr.update(), 
                    gr.update(), gr.update(), gr.update(), gr.update())