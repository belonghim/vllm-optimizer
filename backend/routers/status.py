"""
Status Router
Provides endpoint for querying interrupted runs detected at startup.
"""

import asyncio
import logging
from typing import Any

from fastapi import APIRouter

logger = logging.getLogger(__name__)
router = APIRouter()

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
        except Exception as e:
            logger.warning("[Status] Failed to clear interrupted run rows from DB: %s", e)

    return {"interrupted_runs": runs}
