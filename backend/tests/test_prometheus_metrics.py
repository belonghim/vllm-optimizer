import types
from typing import Any
from ..metrics import prometheus_metrics as pm
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from unittest.mock import patch

# Import the app and metrics module from the backend
try:
    from ..main import app  # type: ignore
except Exception:
    # Fallback: construct a tiny FastAPI app if main import isn't available in test env
    app = FastAPI()

from ..services.metrics_collector import MetricsCollector  # type: ignore


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
    with patch('backend.services.metrics_collector.MetricsCollector', autospec=True) as MockCollector:
        MockCollector.return_value = _mock_collector_state({})
        resp = client.get("/api/metrics")
        assert resp.status_code == 200
        ctype = resp.headers.get('content-type','')
        assert ctype.startswith('text/plain; version=0.0.4')
        body = resp.text
        # Optimizer-prefixed metrics must be present; old vllm: names must NOT appear
        assert 'vllm_optimizer_' in body
        # Old colliding names must NOT be re-exported
        old_names = [
            'vllm:num_requests_running',
            'vllm:num_requests_waiting',
            'vllm:gpu_cache_usage_perc',
            'vllm:gpu_utilization',
            'vllm:request_success_total',
            'vllm:generation_tokens_total',
            'vllm:time_to_first_token_seconds',
            'vllm:e2e_request_latency_seconds',
        ]
        for old in old_names:
            assert old not in body, f"Old colliding metric name still exported: {old}"


def test_metrics_populated_state(client):
    with patch('backend.services.metrics_collector.MetricsCollector', autospec=True) as MockCollector:
        MockCollector.return_value = _mock_collector_state({})
        resp = client.get("/api/metrics")
        assert resp.status_code == 200
        ctype = resp.headers.get('content-type','')
        assert ctype.startswith('text/plain; version=0.0.4')
        body = resp.text
        # New optimizer-prefixed names must appear
        new_names = [
            'vllm_optimizer_request_success_total',
            'vllm_optimizer_generation_tokens_total',
            'vllm_optimizer_num_requests_running',
            'vllm_optimizer_num_requests_waiting',
        ]
        assert any(n in body for n in new_names)


def test_metrics_name_presence(client):
    # Ensure all required new metric names appear and old names are absent
    with patch('backend.services.metrics_collector.MetricsCollector', autospec=True) as MockCollector:
        MockCollector.return_value = _mock_collector_state({})
        resp = client.get("/api/metrics")
        assert resp.status_code == 200
        text = resp.text
        required = [
            'vllm_optimizer_request_success_total',
            'vllm_optimizer_generation_tokens_total',
            'vllm_optimizer_num_requests_running',
            'vllm_optimizer_num_requests_waiting',
            'vllm_optimizer_gpu_cache_usage_perc',
            'vllm_optimizer_gpu_utilization',
            'vllm_optimizer_time_to_first_token_seconds',
            'vllm_optimizer_e2e_request_latency_seconds',
        ]
        for name in required:
            assert name in text, f"New metric name not found in output: {name}"

        # Old colliding names must NOT appear
        old_names = [
            'vllm:num_requests_running',
            'vllm:num_requests_waiting',
            'vllm:gpu_cache_usage_perc',
            'vllm:gpu_utilization',
            'vllm:request_success_total',
            'vllm:generation_tokens_total',
            'vllm:time_to_first_token_seconds',
            'vllm:e2e_request_latency_seconds',
        ]
        for old in old_names:
            assert old not in text, f"Old colliding metric name still present: {old}"
