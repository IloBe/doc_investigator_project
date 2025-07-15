# src/doc_investigator_strategy_pattern/app.py

"""
Gradio UI module for the Document Investigator application.

Defines the AppUI class, which constructs the user interface using the
Gradio library. It manages UI components, state and event handling. It
acts as the central controller that connects user actions to the
backend services (document processing, AI and database).
"""

import gradio as gr
import os
import sqlite3
from typing import Any, List, Optional, Tuple
from loguru import logger

from .documents import InvalidFileTypeException

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

        with gr.Blocks(theme=theme, title="Document Investigator") as app:
            # --- State Management ---
            state_doc_names = gr.State(None)
            state_last_prompt = gr.State(None)
            state_last_answer = gr.State(None)

            # --- UI Layout ---
            gr.Markdown(
               """
               <div style="text-align: center;">
                   <h1><img src="https://em-content.zobj.net/source/google/387/magnifying-glass-tilted-left_1f50d.png" width="35" height="35" style="display:inline-block; vertical-align: middle;"> Document Investigation</h1>
               </div>
               """
            )

            with gr.Tabs():
                with gr.TabItem("Investigate"):
                    self._build_investigate_tab(state_doc_names, state_last_prompt, state_last_answer)
                with gr.TabItem("Analyze Evaluations"):
                    self._build_analyze_tab()
        return app


    def _build_investigate_tab(self,
        state_doc_names: gr.State,
        state_last_prompt: gr.State,
        state_last_answer: gr.State
    ) -> None:
        """Builds the main 'Investigate' tab UI components."""
        gr.Markdown(
            """
            ### How to use this tool:
            1.  **Upload** one or more documents.
            2.  **Ask a specific question** about their content.
            3.  Click **"Investigate"** to get an AI-powered answer.
            4.  **Evaluate** the answer to help improve the system.
            5.  For **"Exit"** manually close this browser tab, then use 'Ctrl+C' on CLI terminal session.

            **Supported Document Types:** `.pdf`, `.docx`, `.xlsx`, `.txt`
            """
        )
        with gr.Row():
            with gr.Column(scale = 1):
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
            with gr.Column(scale = 2):
                answer_output = gr.Markdown(
                    value = "<p style='color:grey;'>The answer will be shown here...</p>",
                    label = "LLM Answer")
                with gr.Column(visible = False) as evaluation_panel:
                    evaluation_radio = gr.Radio(
                        ["✔️ Yes, the answer is helpful and accurate.",
                         "❌ No, the answer is not helpful or inaccurate."],
                        label = "Step 3: Was this answer useful?"
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
                      prompt_input],
            outputs = [answer_output,
                       evaluation_panel,
                       state_doc_names,
                       state_last_prompt,
                       state_last_answer]
        )

        evaluation_button.click(
            fn = self._handle_evaluation,
            inputs = [state_doc_names,
                      state_last_prompt,
                      state_last_answer,
                      evaluation_radio],
            outputs = [file_uploader,
                       prompt_input,
                       answer_output,
                       evaluation_panel,
                       evaluation_radio,
                       state_doc_names,
                       state_last_prompt,
                       state_last_answer]
        )


    def _build_analyze_tab(self) -> None:
        """Builds the 'Analyze Evaluations' tab UI components."""
        gr.Markdown(
            """
            ### Analyzing Evaluation Data with Datasette
            All interactions and evaluations are stored in a local SQLite database (`doc_investigator_prod.db`).
            Datasette provides an instant, read-only web interface to explore this data for analysis.

            **Instructions:**
            1.  Open a new terminal or command prompt in this project's directory.
            2.  Click the button below to copy the command.
            3.  Paste the command into your terminal and press Enter.
            4.  Your web browser will open with the Datasette interface, ready to explore the `interactions` table.
            """
        )
        datasette_command = f"datasette {self.config.DB_FILE} --open"
        gr.Textbox(
            value = datasette_command,
            label = "Command to run Datasette",
            interactive = False,
            show_copy_button = True
        )


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
        prompt: str
    ) -> Tuple[Any, ...]:
        """
        Orchestrates the main investigation workflow.

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

            answer = self.ai_service.get_answer(full_text, prompt)

            # check if answer is real one or a pre-defined inappropriate response
            is_real_answer = answer not in [self.config.UNKNOWN_ANSWER, self.config.NOT_ALLOWED_ANSWER] and "error" not in answer.lower()

            if is_real_answer:
                logger.success("Correct answer received. Displaying to user for evaluation.")
                return gr.update(value = answer), gr.update(visible = True), doc_names, prompt, answer
            else:
                # automatic background logging for non-answers
                logger.info(f"Pre-defined answer returned: '{answer}'. Logging automatically with 'no' evaluation.")
                try:
                    self.db_manager.log_interaction(
                        document_names = doc_names,
                        prompt = prompt,
                        answer = answer,
                        evaluation = "no",
                        temperature = self.config.TEMPERATURE,
                        top_p = self.config.TOP_P
                    )
                except sqlite3.Error as e:
                    logger.error(f"Failed to auto-log non-answer to database. Error: {e}")
                    # don't raise a gr.Error here as it's a background task
                return gr.update(value = answer), gr.update(visible = False), None, None, None

        except InvalidFileTypeException as e:
            raise gr.Error(str(e))
        except Exception as e:
            logger.critical(f"An unexpected error occurred during investigation: {e}", exc_info = True)
            raise gr.Error("An unexpected system error occurred. Please check the logs and try again.")


    def _handle_evaluation(
        self, doc_names: str,
        prompt: str,
        answer: str,
        choice: Optional[str]
    ) -> Tuple[Any, ...]:
        """
        Handles user's evaluation submission, logs it, and resets the UI.
        """
        if not choice:
            gr.Warning("Please select an evaluation option ('Yes' or 'No') before submitting.")
            # return no-op updates to keep UI state as-is
            return (gr.update(), gr.update(), gr.update(),
                    gr.update(visible = True),
                    gr.update(), gr.update(), gr.update(), gr.update())

        evaluation_text = "yes" if "✔️ Yes" in choice else "no"
        logger.info(f"User submitted evaluation: '{evaluation_text}'. Logging to database.")

        try:
            self.db_manager.log_interaction(
                document_names = doc_names,
                prompt = prompt,
                answer = answer,
                evaluation = evaluation_text,
                temperature = self.config.TEMPERATURE,
                top_p = self.config.TOP_P
            )
            gr.Info("Evaluation saved! The interface has been reset for the next investigation.")
            
            # returns tuple to reset all relevant UI items and states to initial values
            return (
                None,  # file_uploader
                "",    # prompt_input
                "<p style='color:grey;'>The answer will be shown here...</p>", # answer_output
                gr.update(visible = False), # evaluation_panel
                None,  # evaluation_radio
                None,  # state_doc_names
                None,  # state_last_prompt
                None,  # state_last_answer
            )
        except sqlite3.Error as e:
            logger.error(f"Failed to save evaluation to database. Error: {e}", exc_info = True)
            gr.Error("Failed to save evaluation due to a database error. Please try again.")
            # keep panel open and state intact for user to retry
            return (gr.update(), gr.update(), gr.update(),
                    gr.update(visible = True),
                    gr.update(), gr.update(), gr.update(), gr.update())