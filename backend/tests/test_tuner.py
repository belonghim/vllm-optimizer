import pytest
from fastapi.testclient import TestClient

from backend.main import app


@pytest.fixture
def client():
    return TestClient(app)


def test_tuner_status_endpoint(client):
    resp = client.get("/api/tuner/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("status") in {"idle", "running", "completed", "error"}


def test_tuner_trials_endpoint_returns_list(client):
    resp = client.get("/api/tuner/trials")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)


def test_tuner_apply_best_response(client):
    resp = client.post("/api/tuner/apply-best")
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("success") is False


def test_tuner_start_endpoint(client):
    """Test starting auto-tuning"""
    from backend.models.load_test import TuningConfig
    
    config = TuningConfig(n_trials=2, eval_requests=10)
    request_data = {
        "config": config.model_dump(),
        "vllm_endpoint": "http://localhost:8000"
    }
    resp = client.post("/api/tuner/start", json=request_data)
    assert resp.status_code == 200
    data = resp.json()
    assert "success" in data
    assert "message" in data
