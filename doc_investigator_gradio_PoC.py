"""
A small gradio app for document investigation with error handling, typing and logging.
This version includes a UI reset after evaluation and an analysis tab.
"""

# --- Imports ---
import os
import getpass
import sqlite3
import abc
from datetime import datetime
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any, Type, Tuple

import gradio as gr
import fitz  # PyMuPDF for pdf handling
import docx
import openpyxl
import google.generativeai as genai


# --- Config ---
@dataclass(frozen=True)
class Config:
    """Encapsulates all application configuration settings."""
    DB_FILE: str = "doc_investigator_prod.db"
    UNKNOWN_ANSWER: str = "Your request is unknown, associated information is not available. Please try again!"
    MAX_CONTEXT_CHARACTERS: int = 80000
    # Use a model name confirmed available via `genai.list_models()`
    # as checked with helper file 'check_google_models.py' of this directory
    LLM_MODEL_NAME: str = "gemini-2.5-pro"
    # Whenever you need to create a new Config object,
    # call this lambda function, which will return a brand new list." 
    # This correctly isolates the state of each object. Annotation:
    # A simple list is created only once, and will throw the following error:
    # ValueError: mutable default <class 'list'> for field SUPPORTED_FILE_TYPES is not allowed:
    # use default_factory
    SUPPORTED_FILE_TYPES: List[str] = field(default_factory=lambda: ['.pdf', '.docx', '.txt', '.xlsx'])


# --- DB layer ---
class DatabaseManager:
    """Manages all interactions with the SQLite database."""
    
    def __init__(self, db_path: str):
        """
        Initializes the DatabaseManager.

        Args:
            db_path (str): The file path for the SQLite database.
        """
        self.db_path = db_path
        self._setup_database()

    def _setup_database(self) -> None:
        """Initializes the database and creates the interactions table if not present."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS interactions (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp TEXT NOT NULL,
                        prompt TEXT,
                        answer TEXT,
                        evaluation TEXT
                    )
                """)
                conn.commit()
            print(f"Database '{self.db_path}' is ready.")
        except sqlite3.Error as e:
            print(f"FATAL: Database setup failed: {e}")
            raise

    def log_interaction(self, prompt: str, answer: str, evaluation: str) -> None:
        """
        Logs a user interaction to the database.

        Args:
            prompt (str): The user's input prompt.
            answer (str): The LLM's generated answer.
            evaluation (str): The user's evaluation of the answer.
        
        Raises:
            sqlite3.Error: If there is an issue with the database transaction.
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT INTO interactions (timestamp, prompt, answer, evaluation) VALUES (?, ?, ?, ?)",
                    (datetime.now().isoformat(), prompt, answer, evaluation)
                )
                conn.commit()
        except sqlite3.Error as e:
            print(f"ERROR: Could not log interaction to database: {e}")
            raise  # Re-raise to be handled by the caller UI layer


# --- Doc layer (strategy design pattern) ---
class DocumentLoaderStrategy(abc.ABC):
    """Abstract base class for a document loading strategy."""
    @abc.abstractmethod
    def load(self, file_path: str) -> str:
        """Loads a file and returns its text content."""
        pass

class PDFLoaderStrategy(DocumentLoaderStrategy):
    """Strategy for loading text from PDF files."""
    def load(self, file_path: str) -> str:
        try:
            text = ""
            with fitz.open(file_path) as doc:
                for page in doc:
                    text += page.get_text()
            return text
        except (FileNotFoundError, fitz.fitz.PyMuPDFError) as e:
            print(f"Error loading PDF {file_path}: {e}")
            return f"[Error processing PDF: {os.path.basename(file_path)}]"

class DocxLoaderStrategy(DocumentLoaderStrategy):
    """Strategy for loading text from DOCX files."""
    def load(self, file_path: str) -> str:
        try:
            doc = docx.Document(file_path)
            return "\n".join([para.text for para in doc.paragraphs])
        except (FileNotFoundError, Exception) as e: # python-docx can have various errors
            print(f"Error loading DOCX {file_path}: {e}")
            return f"[Error processing DOCX: {os.path.basename(file_path)}]"

class TextLoaderStrategy(DocumentLoaderStrategy):
    """Strategy for loading text from TXT files."""
    def load(self, file_path: str) -> str:
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                return f.read()
        except (FileNotFoundError, IOError) as e:
            print(f"Error loading TXT {file_path}: {e}")
            return f"[Error processing TXT: {os.path.basename(file_path)}]"

class ExcelLoaderStrategy(DocumentLoaderStrategy):
    """Strategy for loading text from Excel files."""
    def load(self, file_path: str) -> str:
        try:
            workbook = openpyxl.load_workbook(file_path)
            content = []
            for sheet_name in workbook.sheetnames:
                content.append(f"--- Sheet: {sheet_name} ---")
                sheet = workbook[sheet_name]
                for row in sheet.iter_rows():
                    row_text = "\t".join([str(cell.value) if cell.value is not None else "" for cell in row])
                    content.append(row_text)
            return "\n".join(content)
        except (FileNotFoundError, Exception) as e:
            print(f"Error loading XLSX {file_path}: {e}")
            return f"[Error processing XLSX: {os.path.basename(file_path)}]"

class DocumentProcessor:
    """Context class that uses a strategy to process documents."""
    def __init__(self):
        self._strategies: Dict[str, DocumentLoaderStrategy] = {
            '.pdf': PDFLoaderStrategy(),
            '.docx': DocxLoaderStrategy(),
            '.txt': TextLoaderStrategy(),
            '.xlsx': ExcelLoaderStrategy(),
            '.xls': ExcelLoaderStrategy()
        }

    def process_files(self, files: List[Any]) -> str:
        """
        Extracts text from a list of Gradio file objects.

        Args:
            files (List[Any]): A list of file objects from Gradio.

        Returns:
            str: The combined text content of all files.
        """
        all_texts = []
        for file in files:
            file_path = file.name
            _, file_extension = os.path.splitext(file_path)
            strategy = self._strategies.get(file_extension.lower(), TextLoaderStrategy())
            text = strategy.load(file_path)
            all_texts.append(f"--- CONTENT FROM {os.path.basename(file_path)} ---\n{text}")
        return "\n\n".join(all_texts)


# --- AI Gemini LLM layer ---
class GeminiService:
    """Handles all communication with the Google Gemini API."""
    def __init__(self, api_key: str, config: Config):
        self.config = config
        try:
            genai.configure(api_key=api_key)
            self.model = genai.GenerativeModel(config.LLM_MODEL_NAME)
        except Exception as e:
            print(f"FATAL: Failed to configure Gemini API: {e}")
            raise

    def get_answer(self, full_text_context: str, user_prompt: str) -> str:
        """
        Generates an answer based on context and a prompt.

        Args:
            full_text_context (str): The context extracted from documents.
            user_prompt (str): The user's question.

        Returns:
            str: The generated answer from the LLM or an error message.
        """
        if not user_prompt:
            return "Please enter a prompt to continue."

        prompt_template = f"""
        You are a meticulous assistant. Your task is to answer the user's question based *ONLY* on the provided context.
        Do not use any external knowledge or make up information.
        If the information to answer the question is not in the context, you MUST respond with the exact phrase: '{self.config.UNKNOWN_ANSWER}'

        CONTEXT:
        ---
        {full_text_context}
        ---

        USER'S QUESTION:
        {user_prompt}

        ANSWER:
        """
        try:
            response = self.model.generate_content(prompt_template)
            if not response.parts:
                return "The model did not generate a response, possibly due to safety settings."
            return response.text.strip()
        except Exception as e:
            print(f"ERROR: Gemini API call failed: {e}")
            return "An error occurred while communicating with the AI model. Please check the logs."


# --- Gradio App ---
class AppUI:
    """Encapsulates the Gradio UI and its event handling logic."""
    def __init__(self, config: Config, db_manager: DatabaseManager, doc_processor: DocumentProcessor, ai_service: GeminiService):
        self.config = config
        self.db_manager = db_manager
        self.doc_processor = doc_processor
        self.ai_service = ai_service
        self.app = self._build_ui()

    def _build_ui(self) -> gr.Blocks:
        """Constructs the entire Gradio user interface."""
        theme = gr.themes.Soft(
            primary_hue=gr.themes.colors.blue,
            secondary_hue=gr.themes.colors.sky,
            neutral_hue=gr.themes.colors.slate,
        ).set(
            body_background_fill="#F7F7F7",
            block_background_fill="white",
            block_border_width="1px",
            block_shadow="*shadow_drop_lg",
            block_radius="12px",
            input_background_fill="#F7F7F7",
        )

        with gr.Blocks(theme=theme, title="Document Investigation") as app:
            # State management
            state_full_text = gr.State(None)
            state_last_prompt = gr.State(None)
            state_last_answer = gr.State(None)
            
            # UI components
            # header and instructions
            # added tabs for investigation and analysis
            gr.Markdown(
                """
                <div style="text-align: center;">
                    <h1><img src="https://em-content.zobj.net/source/google/387/magnifying-glass-tilted-left_1f50d.png" width="35" height="35" style="display:inline-block; vertical-align: middle;"> Document Investigation</h1>
                </div>
                """
            )
            
            with gr.Tabs():
                with gr.TabItem("Investigate"):
                    gr.Markdown(
                        """
                        ### How to use this tool:
                        1.  **Upload** one or more documents.
                        2.  **Ask a specific question** about the content of your documents.
                        3.  Click **"Investigate"** to get an answer from the AI.
                        4.  **Evaluate** the answer to help improve the system.
            
                        **Supported Document Types:**
                        - 📄 PDF (.pdf)
                        - 📝 Word (.docx)
                        - 📊 Excel (.xlsx)
                        - 🗒️ Text (.txt)
                        """
                    )

                    with gr.Row():
                        with gr.Column(scale=1):
                            file_uploader = gr.File(
                                label="Step 1: Upload Your Documents",
                                file_count="multiple",
                                file_types=self.config.SUPPORTED_FILE_TYPES,
                            )
                            prompt_input = gr.Textbox(label="Step 2: Enter Your Prompt", lines=3)
                            submit_btn = gr.Button("Investigate", variant="primary")
                        with gr.Column(scale=2):
                            answer_output = gr.Markdown(
                                label="LLM Answer", value="Your answer will appear here...")
                            with gr.Column(visible=False) as evaluation_panel:
                                evaluation_radio = gr.Radio(
                                    ["✔️ Yes, the answer is helpful and accurate.", "❌ No, the answer is not helpful or inaccurate."],
                                    label="Step 3: Evaluate the Answer"
                                )
                                evaluation_button = gr.Button("Submit Evaluation")

                with gr.TabItem("Analyze Evaluations"):
                    gr.Markdown(
                        """
                        ### Analyzing Evaluation Data with Datasette

                        All your interactions and evaluations are stored in a local SQLite database (`doc_investigator_prod.db`).
                        Datasette provides an instant web interface to explore this data.

                        **Instructions:**
                        1.  Open a new terminal in the same project directory.
                        2.  Click the button below to copy the command, then paste it into your terminal and press Enter.
                        3.  A new browser tab will open with the Datasette interface where you can explore the `interactions` table.
                        """
                    )
                    datasette_command = f"datasette {self.config.DB_FILE} --open"
                    with gr.Row():
                        gr.Textbox(
                            value=datasette_command,
                            label="Command to run Datasette",
                            interactive=False,
                            show_copy_button=True
                        )

            # Event Handling
            submit_btn.click(
                fn=self._handle_investigation,
                inputs=[file_uploader, prompt_input, state_full_text],
                outputs=[answer_output, state_full_text, state_last_prompt,
                         state_last_answer, evaluation_panel]
            ).then(lambda: "", outputs=[prompt_input])

            evaluation_button.click(
                fn=self._handle_evaluation,
                inputs=[state_last_prompt, state_last_answer, evaluation_radio],
                # lists all components and states that need to be reset
                outputs=[
                    file_uploader,
                    prompt_input,
                    answer_output,
                    evaluation_panel,
                    state_full_text,
                    state_last_prompt,
                    state_last_answer
                ]
            )
        return app

    def _handle_investigation(self, files: List[Any], prompt: str, current_context: Optional[str]) -> tuple:
        """Orchestrates document processing and answer generation."""
        if current_context is None:
            if not files: raise gr.Error("Please upload at least one document.")
            full_text = self.doc_processor.process_files(files)
            if len(full_text) > self.config.MAX_CONTEXT_CHARACTERS:
                warning = f"\n\n[Warning: Content truncated...]"
                current_context = full_text[:self.config.MAX_CONTEXT_CHARACTERS] + warning
            else:
                current_context = full_text
        
        answer = self.ai_service.get_answer(current_context, prompt)
        show_eval = answer != self.config.UNKNOWN_ANSWER and "error" not in answer.lower()
        
        return answer, current_context, prompt, answer, gr.update(visible=show_eval)

    def _handle_evaluation(self, prompt: str, answer: str, choice: str) -> Tuple:
            """
            Handles submission of the evaluation, logs it, and resets the UI to its initial state.
    
            Returns:
                A tuple of Gradio updates and None values to reset all relevant components and state.
                The length and order of this tuple MUST match the 'outputs' list in the click event.
            """
            if not choice:
                gr.Warning("Please select an evaluation option before submitting.")
                # Return a tuple of no-op updates to preserve the UI state.
                return (gr.update(), gr.update(), gr.update(),
                        gr.update(visible=True), gr.update(), gr.update(), gr.update())
            
            try:
                self.db_manager.log_interaction(prompt, answer, choice)
                gr.Info("Evaluation saved! The interface has been reset.")
                
                # full UI reset, order must match the 'outputs' list
                return (
                    gr.update(value=None),      # Reset file_uploader
                    gr.update(value=""),        # Reset prompt_input
                    gr.update(value="Your answer will appear here..."), # Reset answer_output
                    gr.update(visible=False),   # Hide evaluation_panel
                    None,                       # Reset state_full_text
                    None,                       # Reset state_last_prompt
                    None                        # Reset state_last_answer
                )
            except sqlite3.Error:
                print(f"gradio handle evaluation: Failed to save evaluation due to a database error")
                gr.Error("Failed to save evaluation due to a database error.")
                # Keep the panel open and state intact so the user can try again.
                return (gr.update(), gr.update(), gr.update(),
                        gr.update(visible=True), gr.update(), gr.update(), gr.update())

    def launch(self):
        """Launches the Gradio application."""
        self.app.launch(debug=True)

# --- Execution ---       
def main():
    """Main function to initialize and run the application."""
    config = Config()

    api_key = os.environ.get('GOOGLE_API_KEY')
    if not api_key:
        try:
            api_key = getpass.getpass('Enter your Google Gemini API Key: ')
        except Exception as e:
            print(f"Could not read API key: {e}")
            return

    try:
        db_manager = DatabaseManager(config.DB_FILE)
        doc_processor = DocumentProcessor()
        ai_service = GeminiService(api_key, config)
    except Exception as e:
        print(f"Application failed to initialize. Aborting. Error: {e}")
        return

    app_ui = AppUI(config, db_manager, doc_processor, ai_service)
    app_ui.launch()

if __name__ == "__main__":
    main()