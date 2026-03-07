import os
import time
import pytest

pytestmark = [pytest.mark.integration, pytest.mark.performance, pytest.mark.slow]


class TestAutoTuner:

    def test_auto_tuner_completes_with_results(self, http_client, backup_restore_vllm_config, skip_if_overloaded):
        """AutoTuner 2 trial 실행 후 best_metric > 0 확인."""
        assert backup_restore_vllm_config is None
        assert skip_if_overloaded is None

        start_resp = http_client.post("/api/tuner/start", json={
            "config": {
                "n_trials": 2,
                "eval_requests": 10,
                "objective": "tps",
                "max_num_seqs_range": [64, 512],
                "gpu_memory_utilization_range": [0.80, 0.95],
                "max_model_len_range": [2048, 8192],
            },
            "vllm_endpoint": os.getenv("VLLM_ENDPOINT", "http://vllm.vllm.svc.cluster.local:8000"),
        }, timeout=10)
        assert start_resp.status_code == 200
        start_data = start_resp.json()
        assert start_data.get("success") is True

        status = {}
        for _ in range(60):
            time.sleep(5)
            status_resp = http_client.get("/api/tuner/status")
            if status_resp.status_code == 200:
                status = status_resp.json()
                if status.get("status") != "running":
                    break
        else:
            pytest.fail("AutoTuner did not complete within 300 seconds")

        assert status.get("best_metric") is not None
        assert status["best_metric"] > 0

        trials_resp = http_client.get("/api/tuner/trials")
        assert trials_resp.status_code == 200
        trials = trials_resp.json()
        assert len(trials) >= 2

        if "wait_metrics" in status and status["wait_metrics"]:
            wm = status["wait_metrics"]
            assert wm["total_wait_seconds"] >= 0
            assert wm["poll_count"] >= 0
