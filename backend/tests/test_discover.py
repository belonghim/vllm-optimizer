"""Unit tests for the /api/metrics/discover endpoint."""

import pytest
from unittest.mock import MagicMock
from fastapi.testclient import TestClient

pytestmark = pytest.mark.slow


def test_discover_endpoint_requires_namespace(isolated_client):
    """Test that GET /api/metrics/discover without namespace returns 400."""
    response = isolated_client.get("/api/metrics/discover")
    assert response.status_code == 400
    data = response.json()
    assert "detail" in data
    assert "namespace" in data["detail"].lower()


def test_discover_endpoint_returns_isvc_and_llmisvc_arrays(isolated_client, monkeypatch):
    """Test that GET /api/metrics/discover?namespace=xxx returns isvc and llmisvc arrays."""
    from unittest.mock import MagicMock

    mock_isvc_items = [
        {"metadata": {"name": "isvc-1", "namespace": "test-ns"}},
        {"metadata": {"name": "isvc-2", "namespace": "test-ns"}},
    ]
    mock_llmisvc_items = [
        {"metadata": {"name": "llmisvc-1", "namespace": "test-ns"}},
    ]

    def mock_list_ns(plural):
        if plural == "inferenceservices":
            return {"items": mock_isvc_items}
        elif plural == "llminferenceservices":
            return {"items": mock_llmisvc_items}
        return {"items": []}

    def create_mock_api():
        mock = MagicMock()
        mock.list_namespaced_custom_object = lambda *args, **kwargs: mock_list_ns(kwargs.get("plural", ""))
        return mock

    monkeypatch.setattr(
        "kubernetes.client.CustomObjectsApi",
        create_mock_api,
    )

    response = isolated_client.get("/api/metrics/discover?namespace=test-ns")
    assert response.status_code == 200
    data = response.json()
    assert "isvc" in data
    assert "llmisvc" in data
    assert isinstance(data["isvc"], list)
    assert isinstance(data["llmisvc"], list)
    assert len(data["isvc"]) == 2
    assert len(data["llmisvc"]) == 1
    assert data["isvc"][0] == {"name": "isvc-1", "namespace": "test-ns"}
    assert data["isvc"][1] == {"name": "isvc-2", "namespace": "test-ns"}
    assert data["llmisvc"][0] == {"name": "llmisvc-1", "namespace": "test-ns"}


def test_discover_endpoint_nonexistent_namespace_returns_empty(isolated_client, monkeypatch):
    """Test that GET /api/metrics/discover?namespace=nonexistent returns empty arrays."""

    def mock_list_ns(plural):
        return {"items": []}

    def create_mock_api():
        mock = MagicMock()
        mock.list_namespaced_custom_object = lambda *args, **kwargs: mock_list_ns(kwargs.get("plural", ""))
        return mock

    monkeypatch.setattr(
        "kubernetes.client.CustomObjectsApi",
        create_mock_api,
    )

    response = isolated_client.get("/api/metrics/discover?namespace=nonexistent-ns")
    assert response.status_code == 200
    data = response.json()
    assert "isvc" in data
    assert "llmisvc" in data
    assert data["isvc"] == []
    assert data["llmisvc"] == []
