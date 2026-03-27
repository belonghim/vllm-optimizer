import time

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.performance]


class TestItlAccuracy:
    @pytest.mark.integration
    def test_itl_percentile_ordering(self, http_client, skip_if_overloaded, vllm_endpoint, vllm_model):
        config = {
            "endpoint": vllm_endpoint,
            "model": vllm_model,
            "prompt_template": "Count from 1 to 10.",
            "total_requests": 5,
            "concurrency": 1,
            "rps": 1,
            "max_tokens": 30,
            "temperature": 0.0,
            "stream": True,
        }

        resp = http_client.post("/api/load_test/start", json=config, timeout=10)
        assert resp.status_code == 200
        test_id = resp.json().get("test_id")

        for _ in range(60):
            time.sleep(5)
            status_resp = http_client.get("/api/load_test/status")
            if status_resp.status_code == 200 and not status_resp.json().get("running", True):
                break
        else:
            pytest.fail("Load test did not complete within 300 seconds")

        time.sleep(3)
        history_resp = http_client.get("/api/load_test/history")
        assert history_resp.status_code == 200
        history = history_resp.json()

        entry = next((e for e in history if e.get("test_id") == test_id), None)
        assert entry is not None, f"No history entry for test_id={test_id}"

        itl = entry.get("result", {}).get("itl")
        if itl is None:
            pytest.skip("ITL not available (non-streaming or unsupported backend)")

        p50 = itl.get("p50")
        p95 = itl.get("p95")
        p99 = itl.get("p99")
        assert p50 is not None and p95 is not None and p99 is not None, f"ITL percentiles incomplete: {itl}"
        assert p50 <= p95, f"p50 ({p50}) > p95 ({p95})"
        assert p95 <= p99, f"p95 ({p95}) > p99 ({p99})"

    @pytest.mark.integration
    def test_itl_values_in_range(self, http_client, skip_if_overloaded, vllm_endpoint, vllm_model):
        config = {
            "endpoint": vllm_endpoint,
            "model": vllm_model,
            "prompt_template": "What is the capital of France?",
            "total_requests": 5,
            "concurrency": 1,
            "rps": 1,
            "max_tokens": 30,
            "temperature": 0.0,
            "stream": True,
        }

        resp = http_client.post("/api/load_test/start", json=config, timeout=10)
        assert resp.status_code == 200
        test_id = resp.json().get("test_id")

        for _ in range(60):
            time.sleep(5)
            status_resp = http_client.get("/api/load_test/status")
            if status_resp.status_code == 200 and not status_resp.json().get("running", True):
                break
        else:
            pytest.fail("Load test did not complete within 300 seconds")

        time.sleep(3)
        history_resp = http_client.get("/api/load_test/history")
        assert history_resp.status_code == 200
        history = history_resp.json()

        entry = next((e for e in history if e.get("test_id") == test_id), None)
        assert entry is not None, f"No history entry for test_id={test_id}"

        itl = entry.get("result", {}).get("itl")
        if itl is None:
            pytest.skip("ITL not available (non-streaming or unsupported backend)")

        p50 = itl.get("p50")
        assert p50 is not None, f"ITL p50 missing: {itl}"
        assert 0.001 <= p50 <= 2.0, f"ITL p50 ({p50}s) outside expected range [0.001, 2.0]"
