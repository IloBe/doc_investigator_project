# src/doc_investigator_strategy_pattern/database.py

"""
Database management module for the Document Investigator application.

Contains the DatabaseManager class, which encapsulates all interactions
with the SQLite database. It handles connection, setup, schema migration
and data logging operations, ensuring all DB logic is centralized and
decoupled from rest of applications business use case logic.
"""

import sqlite3
from datetime import datetime
from typing import List

from loguru import logger

class DatabaseManager:
    """
    Manages all interactions with the SQLite database, including robust schema
    creation and evolution to ensure all necessary columns are present.
    """

    def __init__(self, db_path: str) -> None:
        """
        Initializes the DatabaseManager and sets up the database.

        Args:
            db_path (str): file path for the SQLite database

        Raises:
            sqlite3.Error: If database connection or setup fails critically
        """
        self.db_path = db_path
        logger.info(f"Initializing DatabaseManager with database at '{db_path}'.")
        try:
            self._setup_database()
        except sqlite3.Error as e:
            logger.critical(f"FATAL: Database setup failed. Application cannot proceed. Error: {e}", exc_info=True)
            raise

    def _setup_database(self) -> None:
        """
        Initializes the database and creates/alters the interactions table.

        Ensures the 'interactions' table exists, including all required columns.
        It is designed to be idempotent, so, can safely run on startup to perform simple
        schema migration, like adding new columns to existing DB without losing data.
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                logger.debug("Ensuring 'interactions' table exists...")
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS interactions (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp TEXT NOT NULL,
                        document_names TEXT,
                        prompt TEXT,
                        answer TEXT,
                        evaluation TEXT
                    )
                """)

                # robust evolution: check for and add new columns if they don't exist
                logger.debug("Checking for schema updates...")
                table_info = cursor.execute("PRAGMA table_info(interactions)").fetchall()
                column_names: List[str] = [info[1] for info in table_info]
                
                # rename 'evaluation' to 'output_passed' for clarity (if needed)
                if 'evaluation' in column_names and 'output_passed' not in column_names:
                    logger.info("Schema migration: Renaming 'evaluation' column to 'output_passed'.")
                    cursor.execute("ALTER TABLE interactions RENAME COLUMN evaluation TO output_passed")
                    # refresh column names after rename
                    column_names = [col if col != 'evaluation' else 'output_passed' for col in column_names]

                # add new columns if they don't exist
                new_columns = {
                    "temperature": "REAL",
                    "top_p": "REAL",
                    "model_name": "TEXT",
                    "eval_reason": "TEXT"
                }
                
                for col_name, col_type in new_columns.items():
                    if col_name not in column_names:
                        logger.info(f"Schema migration: Adding '{col_name}' column to 'interactions' table.")
                        cursor.execute(f"ALTER TABLE interactions ADD COLUMN {col_name} {col_type}")

                #if 'temperature' not in column_names:
                #    logger.info("Schema migration: Adding 'temperature' column to 'interactions' table.")
                #    cursor.execute("ALTER TABLE interactions ADD COLUMN temperature REAL")

                #if 'top_p' not in column_names:
                #    logger.info("Schema migration: Adding 'top_p' column to 'interactions' table.")
                #    cursor.execute("ALTER TABLE interactions ADD COLUMN top_p REAL")

                conn.commit()
                logger.success(f"Database '{self.db_path}' is ready with required schema.")

        except sqlite3.Error as e:
            # critical failure, log and re-raise to be caught by __init__
            logger.error(f"Could not initialize or migrate the database schema. Error: {e}", exc_info=True)
            raise

    def log_interaction(self, document_names: str,
                        prompt: str,
                        answer: str,
                        output_passed: str,
                        eval_reason: str,
                        model_name: str,
                        temperature: float,
                        top_p: float) -> None:
        """
        Logs user interaction record to SQLite database.

        Args:
            document_names (str): string containing names of uploaded docs
            prompt (str): user's input prompt
            answer (str): LLM's generated answer result
            output_passed (str): user's evaluation passed decision of the answer ('yes' or 'no')
            eval_reason (str): user's written reason for their evaluation passed decision
            model_name (str): LLM name used for interaction
            temperature (float): LLM temperature value
            top_p (float): LLM top_p value

        Raises:
            sqlite3.Error: If there is an issue with DB transaction, allows
                           caller (UI layer) to handle error gracefully
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT INTO interactions (timestamp, document_names, prompt, answer, output_passed, eval_reason, model_name, temperature, top_p)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (datetime.now().isoformat(),
                     document_names,
                     prompt,
                     answer,
                     output_passed,
                     eval_reason,
                     model_name,
                     temperature,
                     top_p)
                )
                conn.commit()
                logger.info(f"Successfully logged interaction for evaluation: '{output_passed}'.")
        except sqlite3.Error as e:
            logger.error(f"Failed to log interaction to the database. Error: {e}", exc_info=True)
            raise # Re-raise to be handled by the caller (e.g., the UI to show an error message)