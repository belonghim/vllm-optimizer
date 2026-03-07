import os
import time
import pytest

pytestmark = [pytest.mark.integration, pytest.mark.performance, pytest.mark.slow]


class TestLoadTestThroughput:

    def test_load_test_completes_successfully(self, http_client, skip_if_overloaded):
        """실제 vLLM 대상 부하 테스트 실행 및 결과 검증."""
        config = {
            "endpoint": os.getenv("VLLM_ENDPOINT", "http://vllm.vllm.svc.cluster.local:8000"),
            "model": os.getenv("VLLM_MODEL", "default"),
            "prompt_template": "Hello, how are you?",
            "total_requests": 20,
            "concurrency": 4,
            "rps": 2,
            "max_tokens": 50,
            "temperature": 0.7,
            "stream": False,
        }

        assert skip_if_overloaded is None

        resp = http_client.post("/api/load_test/start", json=config, timeout=10)
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("test_id") or data.get("id") or data.get("status")

        for _ in range(24):
            time.sleep(5)
            status_resp = http_client.get("/api/load_test/status")
            if status_resp.status_code == 200:
                status = status_resp.json()
                if not status.get("running", True):
                    break
        else:
            pytest.fail("Load test did not complete within 120 seconds")

        history_resp = http_client.get("/api/load_test/history")
        assert history_resp.status_code == 200
        history = history_resp.json()
        assert len(history) > 0

        latest = history[-1]
        result = latest.get("result", {})
        assert result.get("total", 0) > 0
        assert result.get("success", 0) > 0
        assert result.get("rps_actual", 0) > 0
        assert result["latency"]["mean"] > 0
        assert result["latency"]["p95"] > 0
