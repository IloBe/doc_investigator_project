# src/doc_investigator_strategy_pattern/database.py

"""
Database management module for the Document Investigator application.

Contains the DatabaseManager class, which encapsulates all interactions
with the SQLite database. It handles connection, setup, schema migration
and data logging operations, ensuring all DB logic is centralized and
decoupled from rest of applications business use case logic.

Additionally, a hash-based caching feature is implemented, not a semantic cache feature by now.
The cache key uniquely identifies a request, which is a combination of the business components:
document content, the user's prompt and the complete set of LLM parameters.
A new cache table is created in our SQLite database.
The Burr state machine orchestrates this logic: the cache-check step happens right before the expensive LLM call.
If an answer is available for the same document and user question resp. task, it will be shown in the app UI.
"""

# ----------
# Imports
# ----------
import sqlite3
from datetime import datetime
from typing import List, Optional
from loguru import logger
from pydantic import BaseModel, Field

# ----------
# Coding
# ----------

class InteractionLog(BaseModel):
    """
    A Pydantic model representing a single user interaction record.
    Provides data validation and a clear schema.
    """
    timestamp: datetime = Field(default_factory=datetime.now)
    document_names: str
    prompt: str
    answer: str
    output_passed: str
    eval_reason: str
    model_name: str
    temperature: float
    top_p: float


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
            logger.critical(f"FATAL: Database setup failed. Application cannot proceed. Error: {e}", exc_info = True)
            raise

    def _setup_database(self) -> None:
        """
        Initializes the database and creates resp. alters the interactions table.

        Ensures the 'interactions' table exists, including all required columns.
        It is designed to be idempotent, so, can safely run on startup to perform simple
        schema migration, like adding new columns to existing DB without losing data.

        Second table is the interactions cache table.
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                # interactions table setup
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

                # interactions_cache table setup
                logger.debug("Ensuring 'interactions_cache' table exists...")
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS interactions_cache (
                        cache_key TEXT PRIMARY KEY,
                        llm_answer TEXT NOT NULL,
                        created_at TEXT NOT NULL
                    )
                """)    

                conn.commit()
                logger.success(f"Database '{self.db_path}' is ready with all required schemas and tables.")

        except sqlite3.Error as e:
            # critical failure, log and re-raise to be caught by __init__
            logger.error(f"Could not initialize or migrate the database schemas. Error: {e}", exc_info=True)
            raise

    def log_interaction(self, interaction_log: InteractionLog) -> None:
        """
        Logs a validated user interaction record to SQLite database.

        Args:
            interaction_log (InteractionLog): Pydantic model containing all
                                              necessary data for the log entry

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
                    (
                        interaction_log.timestamp.isoformat(),
                        interaction_log.document_names,
                        interaction_log.prompt,
                        interaction_log.answer,
                        interaction_log.output_passed,
                        interaction_log.eval_reason,
                        interaction_log.model_name,
                        interaction_log.temperature,
                        interaction_log.top_p,
                    )
                )
                conn.commit()
                logger.info(f"Successfully logged interaction for evaluation: '{interaction_log.output_passed}'.")
        except sqlite3.Error as e:
            logger.error(f"Failed to log interaction to the database. Error: {e}", exc_info = True)
            raise # Re-raise to be handled by the caller (e.g., the UI to show an error message)

    def get_cached_answer(self, cache_key: str) -> Optional[str]:
        """
        Retrieves a cached LLM answer from the database using a cache key.

        Args:
            cache_key: SHA-256 hash representing the unique request

        Returns:
            The cached answer as a string, or None if not found
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT llm_answer FROM interactions_cache WHERE cache_key = ?", (cache_key,))
                result = cursor.fetchone()
                if result:
                    logger.info(f"Cache HIT for key: {cache_key[:10]}...")
                    return result[0]
                logger.info(f"Cache MISS for key: {cache_key[:10]}...")
                return None
        except sqlite3.Error as e:
            logger.error(f"Failed to query cache. Error: {e}", exc_info = True)
            return None # fail safe on error, act as a cache miss

    def set_cached_answer(self, cache_key: str, answer: str) -> None:
        """
        Stores a new LLM answer in the cache.

        Args:
            cache_key: SHA-256 hash representing the unique request
            answer: LLM's generated answer to store
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT OR REPLACE INTO interactions_cache (cache_key, llm_answer, created_at) VALUES (?, ?, ?)",
                    (cache_key, answer, datetime.now().isoformat())
                )
                conn.commit()
                logger.success(f"Successfully cached new answer for key: {cache_key[:10]}...")
        except sqlite3.Error as e:
            logger.error(f"Failed to write to cache. Error: {e}", exc_info = True)
            # non-critical error, just log it and move on           