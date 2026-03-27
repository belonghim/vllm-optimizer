"""Tests for /health endpoint."""

import os

import pytest
from fastapi.testclient import TestClient


def test_health_includes_cr_type(isolated_client: TestClient) -> None:
    """Test that /health endpoint returns cr_type field."""
    response = isolated_client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert "cr_type" in data, "cr_type field missing from /health response"


def test_health_cr_type_default_value(isolated_client: TestClient) -> None:
    """Test that cr_type defaults to 'llminferenceservice' when VLLM_CR_TYPE is not set."""
    response = isolated_client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["cr_type"] == "llminferenceservice", f"Expected cr_type='llminferenceservice', got '{data['cr_type']}'"


def test_health_response_structure(isolated_client: TestClient) -> None:
    """Test that /health response contains all expected fields."""
    response = isolated_client.get("/health")
    assert response.status_code == 200
    data = response.json()

    # Verify all required fields are present
    required_fields = {"status", "cr_type", "dependencies", "timestamp"}
    assert required_fields.issubset(set(data.keys())), (
        f"Missing fields in /health response. Expected {required_fields}, got {set(data.keys())}"
    )

    # Verify field types
    assert isinstance(data["status"], str)
    assert isinstance(data["cr_type"], str)
    assert isinstance(data["dependencies"], dict)
    assert isinstance(data["timestamp"], (int, float))


def test_health_deep_check_includes_cr_type(isolated_client: TestClient) -> None:
    """Test that deep health check also includes cr_type."""
    response = isolated_client.get("/health?deep=1")
    assert response.status_code in (200, 503)
    data = response.json()
    assert "cr_type" in data, "cr_type field missing from deep /health check"
    assert data["cr_type"] == "llminferenceservice"
