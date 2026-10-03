"""
Targets Router
Provides endpoints for saving and loading target configurations to SQLite.
"""

import json
import logging
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from models.load_test import ErrorResponse
from pydantic import BaseModel
from services.storage import Storage

router = APIRouter()
logger = logging.getLogger(__name__)


def get_storage() -> Storage:
    """Return the shared storage instance."""
    from services import shared

    return shared.storage


class TargetItem(BaseModel):
    namespace: str
    name: str
    cr_type: Literal["inferenceservice", "llminferenceservice"] = "inferenceservice"
    metrics_source: Literal["direct", "thanos"] = "direct"


class SaveTargetsRequest(BaseModel):
    targets: list[TargetItem]


class LoadTargetsResponse(BaseModel):
    targets: list[TargetItem]
    loaded: bool


@router.post(
    "/save",
    response_model=LoadTargetsResponse,
    responses={
        500: {"model": ErrorResponse},
    },
)
async def save_targets(
    request: Request,
    payload: SaveTargetsRequest,
    storage: Storage = Depends(get_storage),
) -> LoadTargetsResponse:
    """Save target list to SQLite (single slot, overwrite)."""
    try:
        targets_json = json.dumps([t.model_dump() for t in payload.targets])
        now = datetime.now().isoformat()

        await storage.save_targets(targets_json, now)

        logger.info("[Targets] Saved %d targets", len(payload.targets))
        return LoadTargetsResponse(targets=payload.targets, loaded=True)
    except Exception as e:
        logger.error("[Targets] Failed to save targets: %s", e)
        raise HTTPException(
            status_code=500,
            detail=ErrorResponse(error="Failed to save targets", error_type="storage").model_dump(),
        ) from e


@router.get(
    "/load",
    response_model=LoadTargetsResponse,
    responses={
        500: {"model": ErrorResponse},
    },
)
async def load_targets(
    request: Request,
    storage: Storage = Depends(get_storage),
) -> LoadTargetsResponse:
    """Load saved targets from SQLite."""
    try:
        result = await storage.load_targets()
        if result is None:
            return LoadTargetsResponse(targets=[], loaded=False)

        targets_list = []
        for t in result.get("targets", []):
            try:
                targets_list.append(TargetItem(**t))
            except Exception as e:
                logger.warning("[Targets] Failed to parse target: %s", e)

        loaded = len(targets_list) > 0
        return LoadTargetsResponse(targets=targets_list, loaded=loaded)
    except Exception as e:
        logger.error("[Targets] Failed to load targets: %s", e)
        raise HTTPException(
            status_code=500,
            detail=ErrorResponse(error="Failed to load targets", error_type="storage").model_dump(),
        ) from e
