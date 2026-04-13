"""
Tests for GuideLLM JSON parser and import endpoint.
"""

import asyncio
import io
import json

import pytest


@pytest.fixture
def client(isolated_client, monkeypatch):
    """TestClient with in-memory storage for benchmark tests."""
    from routers.benchmark import get_storage
    from services.storage import Storage

    test_storage = Storage(":memory:")

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(test_storage.initialize())

    isolated_client.app.dependency_overrides[get_storage] = lambda: test_storage

    yield isolated_client

    if get_storage in isolated_client.app.dependency_overrides:
        del isolated_client.app.dependency_overrides[get_storage]

    loop.run_until_complete(test_storage.close())
    loop.close()


def test_parse_valid_json():
    """Test parsing valid GuideLLM JSON returns 2 Benchmark objects with source='guidellm'."""
    from services.guidellm_parser import parse_guidellm_json

    data = {
        "metadata": {"version": 1, "guidellm_version": "0.3.0"},
        "benchmarks": [
            {
                "config": {"target": "http://example.com", "model": "test-model"},
                "scheduler_metrics": {
                    "requests_made": {"total": 10, "successful": 9, "errored": 1, "incomplete": 0},
                    "measure_start_time": 1000.0,
                    "measure_end_time": 1010.0,
                },
                "metrics": {
                    "request_latency": {
                        "successful": {"mean": 0.5, "median": 0.45, "p95": 0.9, "p99": 1.0, "min": 0.2, "max": 1.2}
                    },
                    "time_to_first_token_ms": {
                        "successful": {
                            "mean": 50.0,
                            "median": 48.0,
                            "p95": 90.0,
                            "p99": 100.0,
                            "min": 20.0,
                            "max": 120.0,
                        }
                    },
                    "inter_token_latency_ms": {"successful": {"mean": 5.0, "median": 4.8, "p95": 9.0, "p99": 10.0}},
                    "tokens_per_second": {"successful": {"mean": 45.0}},
                },
            },
            {
                "config": {"target": "http://example.com", "model": "test-model"},
                "scheduler_metrics": {
                    "requests_made": {"total": 20, "successful": 19, "errored": 1, "incomplete": 0},
                    "measure_start_time": 2000.0,
                    "measure_end_time": 2020.0,
                },
                "metrics": {
                    "request_latency": {
                        "successful": {"mean": 0.6, "median": 0.55, "p95": 1.0, "p99": 1.2, "min": 0.3, "max": 1.5}
                    },
                    "time_to_first_token_ms": {
                        "successful": {
                            "mean": 60.0,
                            "median": 58.0,
                            "p95": 100.0,
                            "p99": 120.0,
                            "min": 25.0,
                            "max": 150.0,
                        }
                    },
                    "inter_token_latency_ms": {"successful": {"mean": 6.0, "median": 5.8, "p95": 10.0, "p99": 12.0}},
                    "tokens_per_second": {"successful": {"mean": 40.0}},
                },
            },
        ],
    }

    results = parse_guidellm_json(data)

    assert len(results) == 2
    assert all(bm.metadata.source == "guidellm" for bm in results)  # type: ignore[union-attr]
    assert results[0].config.endpoint == "http://example.com"
    assert results[0].config.model == "test-model"
    assert results[1].config.endpoint == "http://example.com"


def test_ms_to_seconds_conversion():
    """Test TTFT conversion from ms to seconds: 50ms -> 0.05s."""
    from services.guidellm_parser import parse_guidellm_json

    data = {
        "metadata": {"version": 1, "guidellm_version": "0.3.0"},
        "benchmarks": [
            {
                "config": {"target": "http://example.com", "model": "test-model"},
                "scheduler_metrics": {
                    "requests_made": {"total": 10, "successful": 10, "errored": 0, "incomplete": 0},
                    "measure_start_time": 1000.0,
                    "measure_end_time": 1010.0,
                },
                "metrics": {
                    "request_latency": {
                        "successful": {"mean": 0.5, "median": 0.45, "p95": 0.9, "p99": 1.0, "min": 0.2, "max": 1.2}
                    },
                    "time_to_first_token_ms": {
                        "successful": {
                            "mean": 50.0,
                            "median": 48.0,
                            "p95": 90.0,
                            "p99": 100.0,
                            "min": 20.0,
                            "max": 120.0,
                        }
                    },
                    "inter_token_latency_ms": {"successful": {"mean": 5.0, "median": 4.8, "p95": 9.0, "p99": 10.0}},
                    "tokens_per_second": {"successful": {"mean": 45.0}},
                },
            },
        ],
    }


def test_ms_to_seconds_conversion():
    """Test TTFT conversion from ms to seconds: 50ms -> 0.05s."""
    from services.guidellm_parser import parse_guidellm_json

    data = {
        "metadata": {"version": 1, "guidellm_version": "0.3.0"},
        "benchmarks": [
            {
                "config": {"target": "http://example.com", "model": "test-model"},
                "metrics": {
                    "time_to_first_token_ms": {"successful": {"mean": 50.0, "median": 45.0, "p95": 90.0, "p99": 100.0}},
                    "inter_token_latency_ms": {"successful": {"mean": 5.0, "median": 4.8, "p95": 9.0, "p99": 10.0}},
                    "tokens_per_second": {"successful": {"mean": 45.0}},
                },
            },
        ],
    }

    results = parse_guidellm_json(data)

    assert abs(results[0].result.ttft.p95 - 0.09) < 0.001
    itl_result = results[0].result.itl
    assert isinstance(itl_result, dict) and abs(itl_result.get("mean", 0) - 0.005) < 0.001


def test_rejects_wrong_version():
    """Test that version != 1 raises ValueError."""
    from services.guidellm_parser import parse_guidellm_json

    data = {
        "metadata": {"version": 2, "guidellm_version": "0.3.0"},
        "benchmarks": [
            {
                "config": {"target": "http://example.com", "model": "test-model"},
                "scheduler_metrics": {
                    "requests_made": {"total": 10, "successful": 10, "errored": 0, "incomplete": 0},
                    "measure_start_time": 1000.0,
                    "measure_end_time": 1010.0,
                },
                "metrics": {
                    "request_latency": {"successful": {"mean": 0.5}},
                    "time_to_first_token_ms": {"successful": {"mean": 50.0}},
                    "tokens_per_second": {"successful": {"mean": 45.0}},
                },
            },
        ],
    }

    with pytest.raises(ValueError, match="Unsupported GuideLLM JSON version"):
        parse_guidellm_json(data)


def test_rejects_empty_benchmarks():
    """Test that empty benchmarks array raises ValueError."""
    from services.guidellm_parser import parse_guidellm_json

    data = {
        "metadata": {"version": 1, "guidellm_version": "0.3.0"},
        "benchmarks": [],
    }

    with pytest.raises(ValueError, match="No benchmarks found"):
        parse_guidellm_json(data)


def test_import_endpoint_valid(client):
    """Test POST /api/benchmark/import with valid GuideLLM JSON returns 200 with imported_count >= 1."""
    json_data = {
        "metadata": {"version": 1, "guidellm_version": "0.3.0"},
        "benchmarks": [
            {
                "config": {"target": "http://example.com", "model": "test-model"},
                "scheduler_metrics": {
                    "requests_made": {"total": 10, "successful": 9, "errored": 1, "incomplete": 0},
                    "measure_start_time": 1000.0,
                    "measure_end_time": 1010.0,
                },
                "metrics": {
                    "request_latency": {
                        "successful": {"mean": 0.5, "median": 0.45, "p95": 0.9, "p99": 1.0, "min": 0.2, "max": 1.2}
                    },
                    "time_to_first_token_ms": {
                        "successful": {
                            "mean": 50.0,
                            "median": 48.0,
                            "p95": 90.0,
                            "p99": 100.0,
                            "min": 20.0,
                            "max": 120.0,
                        }
                    },
                    "inter_token_latency_ms": {"successful": {"mean": 5.0, "median": 4.8, "p95": 9.0, "p99": 10.0}},
                    "tokens_per_second": {"successful": {"mean": 45.0}},
                },
            },
            {
                "config": {"target": "http://example.com", "model": "test-model"},
                "scheduler_metrics": {
                    "requests_made": {"total": 20, "successful": 19, "errored": 1, "incomplete": 0},
                    "measure_start_time": 2000.0,
                    "measure_end_time": 2020.0,
                },
                "metrics": {
                    "request_latency": {
                        "successful": {"mean": 0.6, "median": 0.55, "p95": 1.0, "p99": 1.2, "min": 0.3, "max": 1.5}
                    },
                    "time_to_first_token_ms": {
                        "successful": {
                            "mean": 60.0,
                            "median": 58.0,
                            "p95": 100.0,
                            "p99": 120.0,
                            "min": 25.0,
                            "max": 150.0,
                        }
                    },
                    "inter_token_latency_ms": {"successful": {"mean": 6.0, "median": 5.8, "p95": 10.0, "p99": 12.0}},
                    "tokens_per_second": {"successful": {"mean": 40.0}},
                },
            },
        ],
    }

    response = client.post(
        "/api/benchmark/import",
        files={"file": ("test.json", io.BytesIO(json.dumps(json_data).encode()), "application/json")},
    )

    assert response.status_code == 200
    data = response.json()
    assert "imported_count" in data
    assert data["imported_count"] >= 1
    assert "benchmark_ids" in data
    assert isinstance(data["benchmark_ids"], list)


def test_import_endpoint_invalid_json(client):
    """Test POST /api/benchmark/import with invalid JSON returns 400."""
    response = client.post(
        "/api/benchmark/import",
        files={"file": ("test.json", io.BytesIO(b"not json"), "application/json")},
    )

    assert response.status_code == 400
    data = response.json()
    assert "detail" in data
