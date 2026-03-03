import types
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


def _mock_collector_state(state: dict):
    """Helper to patch MetricsCollector to return a deterministic state."""
    class DummyCollector:
        def __init__(self):
            pass

        def collect(self):
            # Return a mapping of metric names to values
            return state

    return DummyCollector()


def test_metrics_empty_state(client):
    empty_state = {
        'vllm:request_success_total': 0,
        'vllm:generation_tokens_total': 0,
        'vllm:num_requests_running': 0,
        'vllm:num_requests_waiting': 0,
        'vllm:gpu_cache_usage_perc': 0,
        'vllm:gpu_utilization': 0,
        'vllm:time_to_first_token_seconds': 0.0,
        'vllm:e2e_request_latency_seconds': 0.0,
    }

    with patch('backend.services.metrics_collector.MetricsCollector', autospec=True) as MockCollector:
        MockCollector.return_value = _mock_collector_state(empty_state)
        resp = client.get("/api/metrics")
        assert resp.status_code == 200
        ctype = resp.headers.get('content-type','')
        assert ctype.startswith('text/plain; version=0.0.4')
        body = resp.text
        # At least one vllm: metric should be present in the body
        assert 'vllm:' in body


def test_metrics_populated_state(client):
    populated_state = {
        'vllm:request_success_total': 42,
        'vllm:generation_tokens_total': 12345,
        'vllm:num_requests_running': 2,
        'vllm:num_requests_waiting': 1,
        'vllm:gpu_cache_usage_perc': 75,
        'vllm:gpu_utilization': 65,
        'vllm:time_to_first_token_seconds': 0.123,
        'vllm:e2e_request_latency_seconds': 0.456,
    }

    with patch('backend.services.metrics_collector.MetricsCollector', autospec=True) as MockCollector:
        MockCollector.return_value = _mock_collector_state(populated_state)
        resp = client.get("/api/metrics")
        assert resp.status_code == 200
        ctype = resp.headers.get('content-type','')
        assert ctype.startswith('text/plain; version=0.0.4')
        body = resp.text
        # Do not rely on exact numeric values; ensure metric names appear
        assert any(n in body for n in populated_state.keys())


def test_metrics_name_presence(client):
    # Ensure all required metric names appear regardless of values
    any_state = {
        'vllm:request_success_total': 0,
        'vllm:generation_tokens_total': 1,
        'vllm:num_requests_running': 0,
        'vllm:num_requests_waiting': 0,
        'vllm:gpu_cache_usage_perc': 50,
        'vllm:gpu_utilization': 30,
        'vllm:time_to_first_token_seconds': 0.5,
        'vllm:e2e_request_latency_seconds': 0.8,
    }

    with patch('backend.services.metrics_collector.MetricsCollector', autospec=True) as MockCollector:
        MockCollector.return_value = _mock_collector_state(any_state)
        resp = client.get("/api/metrics")
        assert resp.status_code == 200
        text = resp.text
        required = [
            'vllm:request_success_total',
            'vllm:generation_tokens_total',
            'vllm:num_requests_running',
            'vllm:num_requests_waiting',
            'vllm:gpu_cache_usage_perc',
            'vllm:gpu_utilization',
            'vllm:time_to_first_token_seconds',
            'vllm:e2e_request_latency_seconds',
        ]
        for name in required:
            assert name in text
