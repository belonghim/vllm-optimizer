import json
import time

import httpx
import pytest

pytestmark = [pytest.mark.integration, pytest.mark.performance, pytest.mark.slow]


class TestSweepE2E:
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_sweep_sse_events_received(self, async_http_client, skip_if_overloaded, vllm_endpoint, vllm_model):
        base_url = async_http_client

        config = {
            "endpoint": vllm_endpoint,
            "model": vllm_model,
            "rps_start": 1,
            "rps_end": 3,
            "rps_step": 1,
            "requests_per_step": 3,
            "concurrency": 1,
            "max_tokens": 20,
            "stream": True,
            "prompt": "Hello, what is 1+1?",
        }

        async with httpx.AsyncClient(base_url=base_url, timeout=300) as client:
            resp = await client.post("/api/load_test/sweep", json=config)
            assert resp.status_code == 200, f"Sweep start failed: {resp.text}"

            events: list[dict] = []
            buffer = ""
            try:
                async with client.stream("GET", "/api/load_test/stream", timeout=300) as stream:
                    async for chunk in stream.aiter_text():
                        buffer += chunk
                        while "\n\n" in buffer:
                            event_str, buffer = buffer.split("\n\n", 1)
                            for line in event_str.split("\n"):
                                if line.startswith("data: "):
                                    try:
                                        data = json.loads(line[6:])
                                        events.append(data)
                                    except json.JSONDecodeError:
                                        pass
                            if any(e.get("type") == "sweep_completed" for e in events):
                                break
            except (httpx.ReadTimeout, httpx.RemoteProtocolError):
                pass

        sweep_step_events = [e for e in events if e.get("type") == "sweep_step"]
        assert len(sweep_step_events) >= 1, (
            f"Expected at least 1 sweep_step SSE event, got {len(sweep_step_events)}. "
            f"All event types: {[e.get('type') for e in events]}"
        )

    @pytest.mark.integration
    def test_sweep_result_structure(self, http_client, skip_if_overloaded, vllm_endpoint, vllm_model):
        config = {
            "endpoint": vllm_endpoint,
            "model": vllm_model,
            "rps_start": 1,
            "rps_end": 3,
            "rps_step": 1,
            "requests_per_step": 3,
            "concurrency": 1,
            "max_tokens": 20,
            "stream": True,
            "prompt": "Hello, what is 2+2?",
        }

        resp = http_client.post("/api/load_test/sweep", json=config, timeout=30)
        assert resp.status_code == 200, f"Sweep start failed: {resp.text}"

        for _ in range(60):
            time.sleep(5)
            status_resp = http_client.get("/api/load_test/status")
            if status_resp.status_code == 200:
                status = status_resp.json()
                if not status.get("is_sweeping", True):
                    break
        else:
            pytest.fail("Sweep did not complete within 300 seconds")

        status_resp = http_client.get("/api/load_test/status")
        assert status_resp.status_code == 200
        status = status_resp.json()

        sweep_result = status.get("sweep_result")
        assert sweep_result is not None, "sweep_result is None after sweep completed"

        assert "steps" in sweep_result, f"Missing 'steps' in sweep_result: {list(sweep_result.keys())}"
        assert "saturation_point" in sweep_result, "Missing 'saturation_point' in sweep_result"

        steps = sweep_result["steps"]
        assert len(steps) >= 1, "sweep_result.steps is empty"

        for i, step in enumerate(steps):
            assert "rps" in step, f"Step {i} missing 'rps' (target_rps): {list(step.keys())}"
            assert "stats" in step, f"Step {i} missing 'stats': {list(step.keys())}"
            stats = step["stats"]
            assert "rps_actual" in stats, f"Step {i} stats missing 'rps_actual': {list(stats.keys())}"
            # throughput: either tokens_per_sec or tps.total
            has_throughput = "tokens_per_sec" in stats or "tps" in stats
            assert has_throughput, f"Step {i} stats missing throughput field: {list(stats.keys())}"
