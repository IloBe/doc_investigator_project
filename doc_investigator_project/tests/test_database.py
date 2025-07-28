# tests/test_database.py

"""
Unit tests for the DatabaseManager class.
"""

# ----------
# Imports
# ----------
import sqlite3
import pytest
import sys

from doc_investigator_strategy_pattern.database import DatabaseManager, InteractionLog

# ----------
# Coding
# ----------

# Pytest fixture to create a fresh DatabaseManager instance for each test function
# using a temporary database file.
@pytest.fixture
def db_manager(tmp_path):
    """Provides a DatabaseManager instance with a temporary database."""
    # tmp_path is a pytest fixture that provides a temporary directory (Path object)
    db_path = tmp_path / "test.db"
    return DatabaseManager(db_path = str(db_path))

def test_initialization_creates_table_and_columns(db_manager):
    """
    Tests if the database and the 'interactions' table with all columns
    are created upon initialization.
    """
    # Assert
    with sqlite3.connect(db_manager.db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='interactions'")
        assert cursor.fetchone() is not None, "The 'interactions' table was not created."

        cursor.execute("PRAGMA table_info(interactions)")
        columns = [row[1] for row in cursor.fetchall()]
        expected_columns = ['id',
                            'timestamp',
                            'document_names',
                            'prompt',
                            'answer',
                            'output_passed',
                            'eval_reason',
                            'model_name',
                            'temperature',
                            'top_p']
        assert all(col in columns for col in expected_columns), "Not all expected columns were created."
        assert 'evaluation' not in columns, "Old 'evaluation' column should have been renamed."

def test_log_interaction_inserts_correct_data(db_manager):
    """
    Tests if the log_interaction method correctly inserts a row into the database.
    """
    # Arrange
    # inserted mock data
    test_log_entry = InteractionLog(
        document_names = "test.pdf, report.docx",
        prompt = "What is the summary?",
        answer = "This is the summary.",
        output_passed = "yes",
        eval_reason = "The summary was concise and accurate.",
        model_name = "gemini-2.5-pro",
        temperature = 0.5,
        top_p = 0.9
    )

    # Act
    db_manager.log_interaction(test_log_entry)

    # Assert
    with sqlite3.connect(db_manager.db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT document_names,
                prompt,
                answer,
                output_passed,
                eval_reason,
                model_name,
                temperature,
                top_p FROM interactions
        """)
        row = cursor.fetchone()
        assert row is not None, "No row was inserted into the database."
        
        assert row[0] == test_log_entry.document_names, "document names doesn't Pydantic's model data"
        assert row[1] == test_log_entry.prompt, "user prompt doesn't Pydantic's model data" 
        assert row[2] == test_log_entry.answer, "LLM output doesn't Pydantic's model data"
        assert row[3] == test_log_entry.output_passed, "users yes or no passed answer doesn't Pydantic's model data"
        assert row[4] == test_log_entry.eval_reason, "users eval reason doesn't Pydantic's model data"
        assert row[5] == test_log_entry.model_name, "LLM name doesn't Pydantic's model data"
        assert row[6] == test_log_entry.temperature, "LLM temperatur doesn't Pydantic's model data"
        assert row[7] == test_log_entry.top_p, "LLM top_p names doesn't Pydantic's model data"
        
def test_schema_migration_handles_rename_and_addition(tmp_path):
    """
    Tests that the DatabaseManager correctly migrates an old-schema database,
    renaming 'evaluation' and adding all new columns.
    """
    # Arrange
    db_path = tmp_path / "migration_test.db"

    # creates DB with OLD schema
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE interactions (
                id INTEGER PRIMARY KEY,
                timestamp TEXT,
                document_names TEXT,
                prompt TEXT,
                answer TEXT,
                evaluation TEXT
            )
        """)
        # add data row to ensure it's preserved
        cursor.execute("INSERT INTO interactions (evaluation) VALUES ('yes')")
        conn.commit()

    # Act
    # initialize DatabaseManager on existing, old-schema database,
    # shall trigger migration logic in _setup_database
    DatabaseManager(db_path=str(db_path))

    # Assert
    # verify schema is now correct and data intact
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(interactions)")
        columns = [row[1] for row in cursor.fetchall()]

        assert 'output_passed' in columns, "Migration failed to rename 'evaluation'."
        assert 'evaluation' not in columns, "Old 'evaluation' column should no longer exist."
        assert 'model_name' in columns, "Migration failed to add 'model_name' column."
        assert 'eval_reason' in columns, "Migration failed to add 'eval_reason' column."
        assert 'temperature' in columns, "Migration failed to add 'temperature' column."
        assert 'top_p' in columns, "Migration failed to add 'top_p' column."

        cursor.execute("SELECT output_passed FROM interactions")
        data = cursor.fetchone()
        assert data[0] == 'yes', "Data was not preserved during column rename."        
