# tests/test_database.py

"""
Unit tests for the DatabaseManager class.
"""

import sqlite3
import pytest
import sys
import os

from doc_investigator_strategy_pattern.database import DatabaseManager

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
                            'evaluation',
                            'temperature',
                            'top_p']
        assert all(col in columns for col in expected_columns), "Not all expected columns were created."

def test_log_interaction_inserts_correct_data(db_manager):
    """
    Tests if the log_interaction method correctly inserts a row into the database.
    """
    # Define mock data to be inserted
    test_data = {
        "document_names": "test.pdf, report.docx",
        "prompt": "What is the summary?",
        "answer": "This is the summary.",
        "evaluation": "yes",
        "temperature": 0.5,
        "top_p": 0.9
    }

    # method under test
    db_manager.log_interaction(**test_data)

    with sqlite3.connect(db_manager.db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT document_names, prompt, answer, evaluation, temperature, top_p FROM interactions")
        row = cursor.fetchone()
        assert row is not None, "No row was inserted into the database."
        
        retrieved_data = dict(zip(test_data.keys(), row))
        assert retrieved_data == test_data

def test_schema_migration_adds_missing_columns(tmp_path):
    """
    Tests that the DatabaseManager can add missing columns to an existing
    database, simulating a schema migration.
    """
    db_path = tmp_path / "migration_test.db"

    # old version of db (without temp and top_p)
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE interactions (
                id INTEGER PRIMARY KEY,
                timestamp TEXT,
                prompt TEXT,
                answer TEXT,
                evaluation TEXT
            )
        """)
        conn.commit()

    # initialize DatabaseManager on existing, old-schema database,
    # shall trigger migration logic in _setup_database
    DatabaseManager(db_path=str(db_path))

    # verify new columns added
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(interactions)")
        columns = [row[1] for row in cursor.fetchall()]
        assert 'temperature' in columns, "Migration failed to add 'temperature' column."
        assert 'top_p' in columns, "Migration failed to add 'top_p' column."