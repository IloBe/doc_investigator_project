# src/doc_investigator_strategy_pattern/documents.py

"""
Document processing module for the Document Investigator application.

Implements the Strategy design pattern to handle text extraction from
various file types.

Classes:
    - InvalidFileTypeException: Custom exception for unsupported file types
    - DocumentLoaderStrategy: Abstract base class for all file loaders
    - PDFLoaderStrategy, DocxLoaderStrategy, etc.: Concrete strategy implementations
    - DocumentProcessor: Context class that uses a strategy to process files
"""

# ----------
# Imports
# ----------
import abc
import os
from typing import Any, Dict, List

import docx
import fitz  # PyMuPDF
import openpyxl
from loguru import logger

# ----------
# Coding
# ----------

# --- Custom Exception ---
class InvalidFileTypeException(Exception):
    """Custom exception raised for unsupported file types."""
    pass

# --- Strategy Pattern for Document Loading ---
class DocumentLoaderStrategy(abc.ABC):
    """Abstract base class for a document loading strategy."""

    @abc.abstractmethod
    def load(self, file_path: str) -> str:
        """Loads a file and returns its text content as a string."""
        pass

class PDFLoaderStrategy(DocumentLoaderStrategy):
    """Strategy for loading text from PDF files."""
    def load(self, file_path: str) -> str:
        try:
            text = ""
            with fitz.open(file_path) as doc:
                for page in doc:
                    text += page.get_text()
            logger.debug(f"Successfully extracted text from PDF: {os.path.basename(file_path)}")
            return text
        except (FileNotFoundError, fitz.fitz.PyMuPDFError) as e:
            logger.error(f"Error loading PDF '{file_path}': {e}", exc_info=True)
            return f"[Error processing PDF: {os.path.basename(file_path)} - The file may be corrupt or unreadable.]"

class DocxLoaderStrategy(DocumentLoaderStrategy):
    """Strategy for loading text from DOCX files."""
    def load(self, file_path: str) -> str:
        try:
            doc = docx.Document(file_path)
            full_text = [para.text for para in doc.paragraphs]
            logger.debug(f"Successfully extracted text from DOCX: {os.path.basename(file_path)}")
            return "\n".join(full_text)
        except (FileNotFoundError, Exception) as e: # python-docx can have various errors
            logger.error(f"Error loading DOCX '{file_path}': {e}", exc_info=True)
            return f"[Error processing DOCX: {os.path.basename(file_path)} - The file may be corrupt or incompatible.]"

class TextLoaderStrategy(DocumentLoaderStrategy):
    """Strategy for loading text from TXT files."""
    def load(self, file_path: str) -> str:
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            logger.debug(f"Successfully extracted text from TXT: {os.path.basename(file_path)}")
            return content
        except (FileNotFoundError, IOError) as e:
            logger.error(f"Error loading TXT '{file_path}': {e}", exc_info=True)
            return f"[Error processing TXT: {os.path.basename(file_path)}]"

class ExcelLoaderStrategy(DocumentLoaderStrategy):
    """Strategy for loading text from XLSX files."""
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
            logger.debug(f"Successfully extracted text from XLSX: {os.path.basename(file_path)}")
            return "\n".join(content)
        except (FileNotFoundError, Exception) as e: # openpyxl can raise various errors
            logger.error(f"Error loading XLSX '{file_path}': {e}", exc_info=True)
            return f"[Error processing XLSX: {os.path.basename(file_path)} - File may be corrupt.]"


# --- Main Processor (Context Class) ---
class DocumentProcessor:
    """
    Context class uses the strategy to validate and process documents.

    Initialized with a set of supported file types and uses a dictionary
    of loader strategies to perform the actual text extraction.
    """
    def __init__(self, supported_extensions: List[str]):
        """
        Initializes the DocumentProcessor with a mapping of extensions to loaders.

        Args:
            supported_extensions (List[str]): A list of supported file extensions
                                              (e.g., ['.pdf', '.docx'])
        """
        self.supported_extensions: List[str] = supported_extensions
        self._strategies: Dict[str, DocumentLoaderStrategy] = {
            '.pdf': PDFLoaderStrategy(),
            '.docx': DocxLoaderStrategy(),
            '.txt': TextLoaderStrategy(),
            '.xlsx': ExcelLoaderStrategy(),
        }
        logger.info(f"DocumentProcessor initialized for types: {', '.join(supported_extensions)}")

    def validate_files(self, files: List[Any]) -> None:
        """
        Validates that all uploaded files have a supported extension.

        Args:
            files (List[Any]): A list of file-like objects (from Gradio)

        Raises:
            InvalidFileTypeException: If any file has an unsupported extension
        """
        logger.info(f"Validating {len(files)} uploaded files...")
        for file in files:
            file_name = os.path.basename(file.name)
            _, file_extension = os.path.splitext(file_name)
            if file_extension.lower() not in self.supported_extensions:
                error_msg = f"Unsupported file type: '{file_extension}' in file '{file_name}'."
                logger.warning(error_msg)
                raise InvalidFileTypeException(error_msg)
        logger.success(f"All {len(files)} files passed validation.")

    def process_files(self, files: List[Any]) -> str:
        """
        Extracts text from a list of pre-validated Gradio file objects.

        This method iterates through the files, selects the appropriate loading
        strategy based on file extension, and aggregates the content.

        Args:
            files (List[Any]): list of validated file-like objects

        Returns:
            str: combined text content of all files, with headers indicating source
        """
        logger.info(f"Processing {len(files)} validated files to extract text...")
        all_texts: List[str] = []
        for file in files:
            file_path: str = file.name
            file_name: str = os.path.basename(file_path)
            _, file_extension = os.path.splitext(file_path)

            strategy = self._strategies.get(file_extension.lower())
            # This check is a safeguard, though validation should prevent this.
            if not strategy:
                logger.warning(f"No loader strategy found for validated file '{file_name}'. Skipping.")
                continue

            text = strategy.load(file_path)
            all_texts.append(f"--- CONTENT FROM {file_name} ---\n{text}")

        logger.success("Text extraction from all files complete.")
        return "\n\n".join(all_texts)