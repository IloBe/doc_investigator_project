# Document Investigation AI

This Gradio application allows users to upload documents of type pdf, word doc, txt and excel. Then the user can ask questions about their content using the Google Gemini API. Until the output prompt is created, the specific UI output text message located at the right side of the document upload window changes its black colour to a light grey colour. There the LLM output result and the associated evaluation window appears 

As a starting point a single script PoC file has generated and a .pdf document about a movie dataset has been added to get a first manual impression of application usage.
Afterwards, this PoC approach has been transfered to a project level. The project application features a robust architecture, comprehensive exception handling and logging. Additionally, a prompt evaluation has been implemented, that can be monitored by a <i>Datasette</i> call to get the stored evaluation information of an <i>SQLite</i> database. Furthermore, a unit test suite for database handling and some UI workflows as test examples are added.

As a prerequisite, you need a Google Gemini API Key. Put it in your own created .env file (same level as doc_investigator_project) as <i>export GOOGLE_API_KEY='your-own-key'</i>

![application user interface](https://github.com/IloBe/doc_investigator_project/assets/doc_investigation_app.JPG


## Project Structure
doc_investigator_project/<br>
├── logs/                      # Includes log files<br>
├── src/<br>
│   └── doc_investigator/<br>
│       ├── __init__.py<br>
│       ├── app.py             # Contains the AppUI class (Gradio logic)<br>
│       ├── config.py          # Contains the Config dataclass<br>
│       ├── database.py        # Contains the DatabaseManager class<br>
│       ├── documents.py       # Contains all DocumentLoader strategies<br>
│       ├── services.py        # Contains the GeminiService class<br>
│       └── logging_config.py  # Contains the Loguru setup function<br>
├── tests/<br>
│   ├── __init__.py<br>
│   └── test_database.py       # Pytest tests for the DatabaseManager<br>
│   └── test_documents.py      # Pytest tests for DocumentProcessor validation<br>
│   └── test_app.py            # Pytest tests for the AppUI logic (reset workflow)<br>
├── main.py                    # Main entry point to run the application<br>
├── requirements.txt           # Project dependencies<br>
└── README.md                  # Instructions for setup and usage<br>

## How to Generate and Run the Code
### Setup

1.  **Clone the remote repository to your local directory**
    ```bash
    git clone https://github.com/IloBe/doc_investigator_project.git
    cd doc_investigator_project
    ```

2.  **Create a virtual environment and install dependencies**
    ```bash
    python -m venv venv
    source venv/bin/activate  # On Windows, use `venv\Scripts\activate`
    pip install -r requirements.txt
    ```

3.  **Set your API Key**
    The application will prompt you for your Google Gemini API Key on first run. For a non-interactive setup, you can set it as an environment variable:
    ```bash
    export GOOGLE_API_KEY="your_api_key_here"
    ```

### Run the Application
Execute the main entry point script for the entire application:
```bash
python main.py
```
Execute the PoC script file, which has been the starting point of the project.
```bash
python3 doc_investigator_gradio_PoC.py
```

The application or the PoC script file will be available at http://127.0.0.1:7860.
Regarding the entire application, Log files for each session will be created in the logs/ directory.
For the PoC script file simple CLI prints are added only.

### Run the Tests
To ensure the components are working correctly, run the test suite using pytest:
```bash
pytest
```

### Observe the Logged Data
After using the app, you can explore the doc_investigator_prod.db database with Datasette:
```bash
datasette doc_investigator_prod.db --open
```
