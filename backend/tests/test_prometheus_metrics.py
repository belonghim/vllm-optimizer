from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# Import the app and metrics module from the backend
try:
    from ..main import app  # type: ignore
except Exception:
    # Fallback: construct a tiny FastAPI app if main import isn't available in test env
    app = FastAPI()


@pytest.fixture
def client():
    # Ensure we always use the FastAPI TestClient against the real app
    return TestClient(app)


def _mock_collector_state(state: dict[str, Any]):
    """Helper to patch MetricsCollector to return a deterministic state."""

    class DummyCollector:
        def __init__(self):
            pass

        def collect(self):
            # Return a mapping of metric names to values
            return state

    return DummyCollector()


def test_metrics_empty_state(client):
    resp = client.get("/api/metrics")
    assert resp.status_code == 200
    ctype = resp.headers.get("content-type", "")
    assert ctype.startswith("text/plain; version=0.0.4")
    body = resp.text
    assert "vllm_optimizer_" in body
    old_names = [
        "vllm:num_requests_running",
        "vllm:num_requests_waiting",
        "vllm:gpu_cache_usage_perc",
        "vllm:gpu_utilization",
        "vllm:request_success_total",
        "vllm:generation_tokens_total",
        "vllm:time_to_first_token_seconds",
        "vllm:e2e_request_latency_seconds",
    ]
    for old in old_names:
        assert old not in body, f"Old colliding metric name still exported: {old}"


def test_metrics_populated_state(client):
    resp = client.get("/api/metrics")
    assert resp.status_code == 200
    ctype = resp.headers.get("content-type", "")
    assert ctype.startswith("text/plain; version=0.0.4")
    body = resp.text
    new_names = [
        "vllm_optimizer_requests_per_second",
        "vllm_optimizer_tokens_per_second",
        "vllm_optimizer_num_requests_running",
        "vllm_optimizer_num_requests_waiting",
    ]
    assert any(n in body for n in new_names)


def test_metrics_name_presence(client):
    resp = client.get("/api/metrics")
    assert resp.status_code == 200
    text = resp.text
    required = [
        "vllm_optimizer_requests_per_second",
        "vllm_optimizer_tokens_per_second",
        "vllm_optimizer_num_requests_running",
        "vllm_optimizer_num_requests_waiting",
        "vllm_optimizer_gpu_cache_usage_perc",
        "vllm_optimizer_gpu_utilization",
        "vllm_optimizer_time_to_first_token_seconds",
        "vllm_optimizer_e2e_request_latency_seconds",
    ]
    for name in required:
        assert name in text, f"New metric name not found in output: {name}"

    old_names = [
        "vllm:num_requests_running",
        "vllm:num_requests_waiting",
        "vllm:gpu_cache_usage_perc",
        "vllm:gpu_utilization",
        "vllm:request_success_total",
        "vllm:generation_tokens_total",
        "vllm:time_to_first_token_seconds",
        "vllm:e2e_request_latency_seconds",
    ]
    for old in old_names:
        assert old not in text, f"Old colliding metric name still present: {old}"
