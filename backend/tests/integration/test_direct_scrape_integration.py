import asyncio
import os
import time
from typing import Any

import httpx
import pytest


async def _wait_for_snapshot(client: httpx.AsyncClient, backend_url: str, params: dict[str, str]) -> dict[str, Any]:
    """Targeted /api/metrics/latest는 첫 호출에서 타깃을 등록하고 collecting을 돌려준다.

    스냅샷이 나올 때까지 짧게 폴링한다 (direct 스크랩 주기 2초).
    """
    body: dict[str, Any] = {}
    for _ in range(10):
        resp = await client.get(f"{backend_url}/api/metrics/latest", params=params)
        resp.raise_for_status()
        body = resp.json()
        if body.get("data") is not None:
            return body
        await asyncio.sleep(2)
    return body


def _target_params() -> dict[str, str]:
    return {
        "namespace": os.getenv("VLLM_NAMESPACE", "vllm-lab-dev"),
        "is_name": os.getenv("VLLM_DEPLOYMENT_NAME", "llm-ov"),
        "cr_type": os.getenv("VLLM_CR_TYPE", "inferenceservice"),
    }


@pytest.mark.integration
@pytest.mark.asyncio
async def test_direct_scrape_timestamp_freshness():
    backend_url = os.getenv("PERF_TEST_BACKEND_URL", "http://localhost:8000")
    async with httpx.AsyncClient(verify=False, timeout=15) as client:
        body = await _wait_for_snapshot(client, backend_url, _target_params())

    assert body["data"] is not None, f"no snapshot returned: {body}"
    lag = time.time() - body["data"]["timestamp"]
    collection_interval = float(os.getenv("METRICS_INTERVAL_SEC", "2"))
    assert lag < collection_interval + 6, f"timestamp lag too high: {lag:.1f}s"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_direct_scrape_kserve_returns_nonzero_metrics():
    backend_url = os.getenv("PERF_TEST_BACKEND_URL", "http://localhost:8000")
    async with httpx.AsyncClient(verify=False, timeout=15) as client:
        body = await _wait_for_snapshot(client, backend_url, _target_params())

    snapshot = body["data"]
    assert snapshot is not None, f"no snapshot returned: {body}"
    assert snapshot.get("pods", 0) >= 1
    metric_fields = ["running", "waiting", "kv_cache"]
    assert all(field in snapshot for field in metric_fields)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_thanos_path_still_works():
    """타깃별 metrics_source=thanos 경로가 실패 없이 응답하는지 확인."""
    backend_url = os.getenv("PERF_TEST_BACKEND_URL", "http://localhost:8000")
    params = _target_params()
    async with httpx.AsyncClient(verify=False, timeout=30) as client:
        resp = await client.post(
            f"{backend_url}/api/metrics/batch",
            json={
                "targets": [
                    {
                        "namespace": params["namespace"],
                        "inferenceService": params["is_name"],
                        "cr_type": params["cr_type"],
                    }
                ],
                "metrics_source": "thanos",
            },
        )
    assert resp.status_code == 200
    results = resp.json()["results"]
    key = f"{params['namespace']}/{params['is_name']}/{params['cr_type']}"
    assert key in results
    assert results[key]["status"] in ("collecting", "ready")
