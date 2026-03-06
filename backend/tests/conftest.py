"""
Pytest configuration and shared fixtures for backend tests.

This module provides minimal fixtures to enable test discovery without
requiring heavy dependencies or external services.
"""

import sys
import os

# Add the 'backend' directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pytest


@pytest.fixture
def sample_fixture():
    """A minimal fixture for testing."""
    return {"test": "value"}


@pytest.fixture(scope="session")
def test_config():
    """Session-scoped configuration for tests."""
    return {
        "backend_url": "http://localhost:8000",
        "test_mode": True,
    }
