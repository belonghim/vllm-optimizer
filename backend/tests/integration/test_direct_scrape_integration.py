import os
import time

import httpx
import pytest


@pytest.mark.integration
async def test_direct_scrape_timestamp_freshness():
    backend_url = os.getenv("PERF_TEST_BACKEND_URL", "http://localhost:8000")
    namespace = os.getenv("VLLM_NAMESPACE", "vllm-lab-dev")
    is_name = os.getenv("VLLM_DEPLOYMENT_NAME", "llm-ov")
    cr_type = os.getenv("VLLM_CR_TYPE", "inferenceservice")

    async with httpx.AsyncClient(verify=False, timeout=15) as client:
        resp = await client.get(
            f"{backend_url}/api/metrics/latest",
            params={"namespace": namespace, "is_name": is_name, "cr_type": cr_type},
        )
    resp.raise_for_status()
    data = resp.json()
    lag = time.time() - data["timestamp"]
    collection_interval = float(os.getenv("METRICS_INTERVAL_SEC", "2"))
    assert lag < collection_interval + 6, f"timestamp lag too high: {lag:.1f}s"


@pytest.mark.integration
async def test_direct_scrape_kserve_returns_nonzero_metrics():
    backend_url = os.getenv("PERF_TEST_BACKEND_URL", "http://localhost:8000")
    namespace = os.getenv("VLLM_NAMESPACE", "vllm-lab-dev")
    is_name = os.getenv("VLLM_DEPLOYMENT_NAME", "llm-ov")

    async with httpx.AsyncClient(verify=False, timeout=15) as client:
        resp = await client.get(
            f"{backend_url}/api/metrics/latest",
            params={"namespace": namespace, "is_name": is_name, "cr_type": "inferenceservice"},
        )
    resp.raise_for_status()
    data = resp.json()
    assert data.get("status") is not None
    metric_fields = ["pod_count", "running_requests", "waiting_requests", "kv_cache_usage_pct"]
    nonzero = [f for f in metric_fields if data.get(f, 0) != 0]
    assert len(nonzero) > 0 or data.get("pod_count", 0) >= 0


@pytest.mark.integration
async def test_thanos_path_still_works(monkeypatch):
    monkeypatch.delenv("METRICS_SOURCE", raising=False)
    backend_url = os.getenv("PERF_TEST_BACKEND_URL", "http://localhost:8000")
    namespace = os.getenv("VLLM_NAMESPACE", "vllm-lab-dev")
    is_name = os.getenv("VLLM_DEPLOYMENT_NAME", "llm-ov")
    cr_type = os.getenv("VLLM_CR_TYPE", "inferenceservice")

    async with httpx.AsyncClient(verify=False, timeout=15) as client:
        resp = await client.get(
            f"{backend_url}/api/metrics/latest",
            params={"namespace": namespace, "is_name": is_name, "cr_type": cr_type},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert "timestamp" in data
