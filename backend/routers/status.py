"""
Status Router
Provides endpoint for querying interrupted runs detected at startup.
The /health endpoint (includes cr_type) is registered in main.py.
"""

import asyncio
import logging
import os
from typing import Any

import httpx
from fastapi import APIRouter
from services.shared import runtime_config

logger = logging.getLogger(__name__)
router = APIRouter()

# cr_type field is exposed in /health endpoint (main.py) via runtime_config.cr_type

_interrupted_runs: list[dict[str, Any]] = []
_lock = asyncio.Lock()


async def set_interrupted_runs(runs: list[dict[str, Any]]) -> None:
    """Called from lifespan to store interrupted runs detected at startup."""
    global _interrupted_runs
    async with _lock:
        _interrupted_runs = list(runs)


@router.get("/status/interrupted")
async def get_interrupted_runs() -> dict[str, Any]:
    """Return interrupted runs, clear the stored list, and mark DB rows as cleared."""
    global _interrupted_runs
    async with _lock:
        runs = _interrupted_runs
        _interrupted_runs = []

    # Clear DB rows so they don't reappear on next Pod restart
    if runs:
        try:
            from services.shared import storage

            for run in runs:
                if run.get("id") is not None:
                    await storage.clear_running(run["id"])
        except OSError as e:
            logger.warning("[Status] Failed to clear interrupted run rows from DB: %s", e)

    return {"interrupted_runs": runs}


async def check_prometheus_health() -> bool:
    """Check Prometheus/Thanos connectivity with a lightweight query."""
    try:
        thanos_url = os.getenv("PROMETHEUS_URL", "https://thanos-querier.openshift-monitoring.svc.cluster.local:9091")

        token_path = "/var/run/secrets/kubernetes.io/serviceaccount/token"
        token = None
        if os.path.exists(token_path):
            with open(token_path) as f:
                token = f.read().strip()

        headers = {"Authorization": f"Bearer {token}"} if token else {}

        query = "1"
        async with httpx.AsyncClient(timeout=3, verify=False) as client:
            resp = await client.get(
                f"{thanos_url}/api/v1/query",
                headers=headers,
                params={"query": query},
            )
            return resp.status_code == 200
    except (httpx.HTTPError, OSError):
        return False
