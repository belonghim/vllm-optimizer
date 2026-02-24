import pytest
from fastapi.testclient import TestClient

from backend.main import app


@pytest.fixture
def client():
    return TestClient(app)


def test_metrics_latest_endpoint(client):
    response = client.get("/api/metrics/latest")
    assert response.status_code == 200
    data = response.json()
    # Basic shape checks
    assert "timestamp" in data
    assert "tps" in data
    assert "latency_mean" in data


def test_metrics_history_endpoint_returns_list(client):
    response = client.get("/api/metrics/history?last_n=5")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
