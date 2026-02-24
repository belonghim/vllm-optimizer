import pytest
from fastapi.testclient import TestClient

from main import app
from backend.models.load_test import LoadTestConfig


@pytest.fixture
def client():
    return TestClient(app)


def test_load_test_start_endpoint(client):
    config = LoadTestConfig()
    response = client.post("/api/load_test/start", json=config.model_dump())
    assert response.status_code == 200
    data = response.json()
    assert data.get("test_id") is not None  # Now returns UUID
    assert data.get("status") == "started"
    assert data.get("config") is not None


def test_load_test_status_endpoint_defaults(client):
    response = client.get("/api/load_test/status")
    assert response.status_code == 200
    data = response.json()
    assert data.get("test_id") is None
    assert data.get("running") is False
    assert data.get("config") is None
    assert data.get("elapsed") == 0.0


def test_load_test_history_endpoint_returns_list(client):
    response = client.get("/api/load_test/history?limit=5")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
