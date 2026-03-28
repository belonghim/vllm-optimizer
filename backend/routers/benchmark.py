"""
Benchmark Router
Provides endpoints for saving, retrieving, and managing benchmark results.
"""

import json
import logging
import os
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile
from models.load_test import Benchmark, BenchmarkMetadata, ErrorResponse
from services.guidellm_parser import parse_guidellm_json
from services.model_resolver import resolve_model_name
from services.shared import multi_target_collector
from services.storage import Storage

router = APIRouter()
logger = logging.getLogger(__name__)


def get_storage() -> Storage:
    from services import shared

    return shared.storage


@router.get(
    "/list",
    response_model=list[Benchmark],
    responses={
        500: {"model": ErrorResponse},
    },
)
async def list_benchmarks(
    limit: int = Query(default=20, ge=1),
    offset: int = Query(default=0, ge=0),
    response: Response = None,
    storage: Storage = Depends(get_storage),
) -> list[Benchmark]:
    try:
        total = await storage.count_benchmarks()
        benchmarks = await storage.list_benchmarks(limit=limit, offset=offset)
        if response is not None:
            response.headers["X-Total-Count"] = str(total)
        return benchmarks
    except ValueError as e:
        logger.error("[Benchmark] Failed to list benchmarks: %s", e)
        raise HTTPException(
            status_code=500,
            detail=ErrorResponse(error="Failed to list benchmarks", error_type="storage").model_dump(),
        ) from e


@router.post(
    "/save",
    response_model=Benchmark,
    responses={
        500: {"model": ErrorResponse},
    },
)
async def save_benchmark(
    benchmark: Benchmark,
    storage: Storage = Depends(get_storage),
) -> Benchmark:
    try:
        auto_meta: dict[str, Any] = {}

        try:
            endpoint = benchmark.config.endpoint or os.getenv("VLLM_ENDPOINT", "")
            if endpoint:
                model_name = await resolve_model_name(endpoint, fallback="")
                if model_name:
                    auto_meta["model_identifier"] = model_name
        except (OSError, ValueError):
            pass

        try:
            snapshot = multi_target_collector.latest
            if snapshot and snapshot.pod_ready is not None:
                auto_meta["replica_count"] = snapshot.pod_ready
        except AttributeError:
            pass

        if auto_meta:
            existing_meta = benchmark.metadata or BenchmarkMetadata()
            merged = BenchmarkMetadata(
                **{
                    **auto_meta,
                    **existing_meta.model_dump(exclude_none=True),
                }
            )
            benchmark = benchmark.model_copy(update={"metadata": merged})

        return await storage.save_benchmark(benchmark)
    except ValueError as e:
        logger.error("[Benchmark] Failed to save benchmark: %s", e)
        raise HTTPException(
            status_code=500,
            detail=ErrorResponse(error="Failed to save benchmark", error_type="storage").model_dump(),
        ) from e


@router.get(
    "/by-model",
    response_model=dict[str, Any],
    responses={
        500: {"model": ErrorResponse},
    },
)
async def benchmarks_by_model(
    storage: Storage = Depends(get_storage),
) -> dict[str, Any]:
    try:
        benchmarks = await storage.list_benchmarks()
    except ValueError as e:
        logger.error("[Benchmark] Failed to list benchmarks for by-model: %s", e)
        raise HTTPException(
            status_code=500,
            detail=ErrorResponse(error="Failed to list benchmarks", error_type="storage").model_dump(),
        ) from e
    groups: dict[str, list[Any]] = {}
    for b in benchmarks:
        model_key = (b.config.model if b.config else None) or "unknown"
        gpu_efficiency = None
        if b.result and b.result.gpu_utilization_avg and b.result.gpu_utilization_avg > 0:
            gpu_efficiency = b.result.tps.mean / b.result.gpu_utilization_avg
        entry = {
            **b.model_dump(),
            "gpu_efficiency": gpu_efficiency,
        }
        groups.setdefault(model_key, []).append(entry)
    return {"models": groups}


@router.post("/import")
async def import_guidellm_benchmark(
    file: UploadFile = File(...),
    storage: Storage = Depends(get_storage),
) -> dict:
    contents = await file.read()
    if len(contents) > 50 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File too large (max 50MB)")
    try:
        data = json.loads(contents)
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail=f"Invalid JSON: {e}") from e
    try:
        benchmarks = parse_guidellm_json(data)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    ids = []
    for bm in benchmarks:
        saved = await storage.save_benchmark(bm)
        ids.append(saved.id)
    return {"imported_count": len(ids), "benchmark_ids": ids}


@router.get(
    "/{benchmark_id}",
    response_model=Benchmark,
    responses={
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def get_benchmark(
    benchmark_id: int,
    storage: Storage = Depends(get_storage),
) -> Benchmark:
    try:
        benchmark = await storage.get_benchmark(benchmark_id)
    except ValueError as e:
        logger.error("[Benchmark] Failed to get benchmark %d: %s", benchmark_id, e)
        raise HTTPException(
            status_code=500,
            detail=ErrorResponse(error="Failed to retrieve benchmark", error_type="storage").model_dump(),
        ) from e
    if benchmark is None:
        raise HTTPException(
            status_code=404,
            detail=ErrorResponse(error=f"Benchmark {benchmark_id} not found", error_type="not_found").model_dump(),
        )
    return benchmark


@router.delete(
    "/{benchmark_id}",
    responses={
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def delete_benchmark(
    benchmark_id: int,
    storage: Storage = Depends(get_storage),
) -> dict[str, Any]:
    try:
        deleted = await storage.delete_benchmark(benchmark_id)
    except ValueError as e:
        logger.error("[Benchmark] Failed to delete benchmark %d: %s", benchmark_id, e)
        raise HTTPException(
            status_code=500,
            detail=ErrorResponse(error="Failed to delete benchmark", error_type="storage").model_dump(),
        ) from e
    if not deleted:
        raise HTTPException(
            status_code=404,
            detail=ErrorResponse(error=f"Benchmark {benchmark_id} not found", error_type="not_found").model_dump(),
        )
    return {"status": "deleted", "benchmark_id": benchmark_id, "message": "Benchmark deleted successfully"}


@router.patch(
    "/{benchmark_id}/metadata",
    response_model=Benchmark,
    responses={
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def patch_benchmark_metadata(
    benchmark_id: int,
    metadata: BenchmarkMetadata,
    storage: Storage = Depends(get_storage),
) -> Benchmark:
    try:
        existing = await storage.get_benchmark(benchmark_id)
        if existing is None:
            raise HTTPException(
                status_code=404,
                detail=ErrorResponse(error=f"Benchmark {benchmark_id} not found", error_type="not_found").model_dump(),
            )

        existing_metadata = existing.metadata or BenchmarkMetadata()
        merged_metadata = BenchmarkMetadata(
            **{
                **existing_metadata.model_dump(),
                **metadata.model_dump(exclude_unset=True),
            }
        )
        updated = await storage.update_benchmark_metadata(benchmark_id, merged_metadata)
    except (HTTPException, ValueError) as e:
        if isinstance(e, HTTPException):
            raise e
        logger.error("[Benchmark] Failed to patch benchmark metadata %d: %s", benchmark_id, e)
        raise HTTPException(
            status_code=500,
            detail=ErrorResponse(error="Failed to update benchmark metadata", error_type="storage").model_dump(),
        ) from e
    if updated is None:
        raise HTTPException(
            status_code=404,
            detail=ErrorResponse(error=f"Benchmark {benchmark_id} not found", error_type="not_found").model_dump(),
        )
    return updated
