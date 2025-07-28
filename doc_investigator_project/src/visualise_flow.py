# src/visualize_flow.py

"""
Simple script to generate a Burr state machine diagram.

It initialises the application's components and calls .visualize() method
on the Burr application object to generate a PNG image of the workflow graph.
See: https://burr.dagworks.io/reference/application/#graph-apis
"""

# ----------
# Imports
# ----------
import os
import sys

# adds parent dir to path to allow package imports
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from doc_investigator_strategy_pattern.app import AppUI
from doc_investigator_strategy_pattern.config import Config
from doc_investigator_strategy_pattern.database import DatabaseManager
from doc_investigator_strategy_pattern.documents import DocumentProcessor
from doc_investigator_strategy_pattern.services import GeminiService
from doc_investigator_strategy_pattern.state_machine import build_application

# ----------
# Coding
# ----------

def generate_diagram():
    """Builds the application and generates the state machine diagram."""
    
    # no real API key necessary
    os.environ["GOOGLE_API_KEY"] = "dummy_key_for_visualization"

    config = Config()
    db_manager = DatabaseManager(db_path = config.DB_FILE)
    doc_processor = DocumentProcessor(supported_extensions = config.SUPPORTED_FILE_TYPES)
    ai_service = GeminiService(api_key = os.environ["GOOGLE_API_KEY"], config = config)
    burr_app = build_application(
        config = config,
        db_manager = db_manager,
        doc_processor = doc_processor,
        ai_service = ai_service,
    )

    # creates .png   
    burr_app.visualize(
        output_file_path = "../assets/doc_invest_workflow_diagram", 
        include_conditions = True,
        include_state = False,  # State makes diagram too busy
        view = False,
        engine = 'graphviz',
        format = "png",         # engine_kwargs
        write_dot = False,
    )
    print("Workflow diagram 'doc_invest_workflow_diagram.png' has been generated and stored in assets dir.")

if __name__ == "__main__":
    generate_diagram()