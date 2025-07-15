# tests/conftest.py

"""
Global configuration and fixtures for the pytest suite.

This file is automatically discovered by pytest and is used to define
hooks and fixtures that apply to all tests.
"""

import warnings

def pytest_configure(config):
    """
    A pytest hook that is called after command-line options have been parsed
    and before test collection begins.

    Most reliable place to programmatically configure warning filters,
    as it runs before any tests or application code is imported.
    
    Filter warning settings of pyproject.toml file are not working in this project.
    """
    warnings.filterwarnings(
        "ignore",
        message="websockets.legacy is deprecated",
        category=DeprecationWarning
    )
    warnings.filterwarnings(
        "ignore",
        message="There is no current event loop",
        category=DeprecationWarning
    )
    warnings.filterwarnings(
        "ignore",
        message="websockets.server.WebSocketServerProtocol is deprecated",
        category=DeprecationWarning
    )
    warnings.filterwarnings(
        "ignore",
        message="builtin type SwigPyPacked has no __module__ attribute",
        category=DeprecationWarning
    )
    warnings.filterwarnings(
        "ignore",
        message="builtin type SwigPyObject has no __module__ attribute",
        category=DeprecationWarning
    )
    warnings.filterwarnings(
        "ignore",
        message="builtin type swigvarlink has no __module__ attribute",
        category=DeprecationWarning
    )