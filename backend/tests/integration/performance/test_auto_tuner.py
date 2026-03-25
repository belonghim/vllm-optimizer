import time

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.performance, pytest.mark.slow]


class TestAutoTuner:
    def test_auto_tuner_completes_with_results(
        self, http_client, backup_restore_is_args, skip_if_overloaded, vllm_endpoint
    ):
        """AutoTuner 2 trial 실행 후 best_metric > 0 확인."""

        start_resp = http_client.post(
            "/api/tuner/start",
            json={
                "n_trials": 2,
                "eval_requests": 3,
                "objective": "tps",
                "max_num_seqs_min": 64,
                "max_num_seqs_max": 256,
                "gpu_memory_min": 0.80,
                "gpu_memory_max": 0.95,
                "max_model_len_min": 2048,
                "max_model_len_max": 4096,
                "vllm_endpoint": vllm_endpoint,
            },
            timeout=30,
        )
        assert start_resp.status_code == 200
        start_data = start_resp.json()
        assert start_data.get("success") is True

        status = {}
        for _ in range(120):
            time.sleep(5)
            status_resp = http_client.get("/api/tuner/status")
            if status_resp.status_code == 200:
                status = status_resp.json()
                if status.get("status") != "running":
                    break
        else:
            pytest.fail("AutoTuner did not complete within 600 seconds")

        assert status.get("best") is not None, f"best is None: {status}"
        assert status["best"].get("tps", 0) > 0, f"best.tps not > 0: {status['best']}"

        trials_resp = http_client.get("/api/tuner/trials")
        assert trials_resp.status_code == 200
        trials = trials_resp.json()
        assert len(trials) >= 2

        if "wait_metrics" in status and status["wait_metrics"]:
            wm = status["wait_metrics"]
            assert wm["total_wait_seconds"] >= 0
            assert wm["poll_count"] >= 0
