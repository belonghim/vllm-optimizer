"""
Status Router
Provides endpoint for querying interrupted runs detected at startup.
"""
import logging
from typing import Any

from fastapi import APIRouter

logger = logging.getLogger(__name__)
router = APIRouter()

_interrupted_runs: list[dict[str, Any]] = []


def set_interrupted_runs(runs: list[dict[str, Any]]) -> None:
    """Called from lifespan to store interrupted runs detected at startup."""
    global _interrupted_runs
    _interrupted_runs = list(runs)


@router.get("/status/interrupted")
async def get_interrupted_runs() -> dict[str, Any]:
    """Return interrupted runs and clear the stored list."""
    global _interrupted_runs
    runs = _interrupted_runs
    _interrupted_runs = []
    return {"interrupted_runs": runs}
