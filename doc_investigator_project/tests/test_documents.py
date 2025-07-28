# tests/test_documents.py

"""
Unit tests for the DocumentProcessor and its strategies.
"""

# ----------
# Imports
# ----------
import pytest
import sys
import os

from doc_investigator_strategy_pattern.documents import DocumentProcessor, InvalidFileTypeException

# ----------
# Coding
# ----------

# A fixture to provide a configured DocumentProcessor instance
@pytest.fixture
def doc_processor():
    """Provides a DocumentProcessor instance for testing."""
    # These are the extensions our app is configured to support
    supported_extensions = ['.pdf', '.docx', '.txt', '.xlsx']
    return DocumentProcessor(supported_extensions=supported_extensions)

# A fixture to create mock Gradio file objects
@pytest.fixture
def mock_gradio_file(tmp_path):
    """Creates a factory for mock Gradio file objects."""
    class MockFile:
        def __init__(self, name):
            self.name = name

    def _create_file(filename, content = ""):
        file_path = tmp_path / filename
        file_path.write_text(content)
        return MockFile(name = str(file_path))

    return _create_file

def test_validate_files_success(doc_processor, mock_gradio_file):
    """Tests that validate_files passes with a list of supported file types."""
    valid_files = [
        mock_gradio_file("report.docx"),
        mock_gradio_file("data.txt")
    ]
    # should run without raising an exception
    doc_processor.validate_files(valid_files)

def test_validate_files_failure(doc_processor, mock_gradio_file):
    """Tests that validate_files raises InvalidFileTypeException for unsupported types."""
    invalid_files = [
        mock_gradio_file("report.docx"),
        mock_gradio_file("image.png") # not supported doc type
    ]
    with pytest.raises(InvalidFileTypeException, match = "Unsupported file type: '.png'"):
        doc_processor.validate_files(invalid_files)

def test_process_single_txt_file(doc_processor, mock_gradio_file):
    """Tests text extraction from a single .txt file."""
    # Arrange
    file_content = "This is a test text file."
    files = [mock_gradio_file("test.txt", content = file_content)]
    
    # Act
    result = doc_processor.process_files(files)
    
    # Assert
    assert file_content in result, "Primary file content not as expected in text result"
    assert "--- CONTENT FROM test.txt ---" in result, "Final file content text line not in text result"
    
def test_process_multiple_files(doc_processor, mock_gradio_file):
    """Tests text extraction from multiple files, ensuring content is combined."""
    # Arrange
    content1 = "Content from file one."
    content2 = "Content from file two."
    files = [
        mock_gradio_file("one.txt", content=content1),
        mock_gradio_file("two.txt", content=content2)
    ]

    # Act
    result = doc_processor.process_files(files)

    # Assert
    assert content1 in result, "Content 1 not in combined text result"
    assert content2 in result, "Content 2 not in combined text result"
    assert "--- CONTENT FROM one.txt ---" in result, "Final file content 1 text line not in combined text result"
    assert "--- CONTENT FROM two.txt ---" in result, "Final file content 2 text line not in combined text result"
    assert result.count("\n\n") >= 1, "Page breaks not as expected in combined text result"      

def test_loader_strategy_for_nonexistent_file(doc_processor, tmp_path):
    """Tests that loaders handle non-existent files gracefully."""
    # Note: testing this through main processor
    # Arrange
    class MockNonExistentFile:
        name = str(tmp_path / "nonexistent.txt")
    
    # Act
    files = [MockNonExistentFile()]
    
    # Assert
    # expect an error message inside the content, not an exception
    result = doc_processor.process_files(files)
    assert "[Error processing TXT: nonexistent.txt]" in result, "Error message of non existing file not as expected"