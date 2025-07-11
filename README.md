# Document Investigation AI

This Gradio application allows users to upload documents of type pdf, word doc, txt and excel. Then the user can ask questions about their content using the Google Gemini API. The application features a robust architecture, comprehensive logging that can be monitored by Datasette, and a test suite for the database handling and some UI workflows as a test example.

As a prerequisite, you need a Google Gemini API Key. Put it in your own created .env file (same level as doc_investigator_project) as <i>export GOOGLE_API_KEY='your-own-key'</i>

Have in mind that this is not a full production grade software code. It is tested on Ubuntu with Python V3.10.9.

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
Execute the main entry point script:
```bash
python main.py
```

The application will be available at http://127.0.0.1:7860. Log files for each session will be created in the logs/ directory.

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
