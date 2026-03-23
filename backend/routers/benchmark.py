"""
Benchmark Router
Provides endpoints for saving, retrieving, and managing benchmark results.
"""
import logging
from fastapi import APIRouter, HTTPException
from typing import List, Dict, Any
from models.load_test import Benchmark, ErrorResponse
from services.shared import storage

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/list", response_model=List[Benchmark])
async def list_benchmarks() -> List[Benchmark]:
    try:
        return await storage.list_benchmarks()
    except Exception as e:
        logger.error("[Benchmark] Failed to list benchmarks: %s", e)
        raise HTTPException(
            status_code=500,
            detail=ErrorResponse(error="Failed to list benchmarks", error_type="storage").model_dump(),
        )


@router.post("/save", response_model=Benchmark)
async def save_benchmark(benchmark: Benchmark) -> Benchmark:
    try:
        return await storage.save_benchmark(benchmark)
    except Exception as e:
        logger.error("[Benchmark] Failed to save benchmark: %s", e)
        raise HTTPException(
            status_code=500,
            detail=ErrorResponse(error="Failed to save benchmark", error_type="storage").model_dump(),
        )


@router.get("/by-model", response_model=Dict[str, Any])
async def benchmarks_by_model() -> Dict[str, Any]:
    try:
        benchmarks = await storage.list_benchmarks()
    except Exception as e:
        logger.error("[Benchmark] Failed to list benchmarks for by-model: %s", e)
        raise HTTPException(
            status_code=500,
            detail=ErrorResponse(error="Failed to list benchmarks", error_type="storage").model_dump(),
        )
    groups: Dict[str, list[Any]] = {}
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


@router.get("/{benchmark_id}", response_model=Benchmark)
async def get_benchmark(benchmark_id: int) -> Benchmark:
    try:
        benchmark = await storage.get_benchmark(benchmark_id)
    except Exception as e:
        logger.error("[Benchmark] Failed to get benchmark %d: %s", benchmark_id, e)
        raise HTTPException(
            status_code=500,
            detail=ErrorResponse(error="Failed to retrieve benchmark", error_type="storage").model_dump(),
        )
    if benchmark is None:
        raise HTTPException(
            status_code=404,
            detail=ErrorResponse(error=f"Benchmark {benchmark_id} not found", error_type="not_found").model_dump(),
        )
    return benchmark


@router.delete("/{benchmark_id}")
async def delete_benchmark(benchmark_id: int) -> Dict[str, Any]:
    try:
        deleted = await storage.delete_benchmark(benchmark_id)
    except Exception as e:
        logger.error("[Benchmark] Failed to delete benchmark %d: %s", benchmark_id, e)
        raise HTTPException(
            status_code=500,
            detail=ErrorResponse(error="Failed to delete benchmark", error_type="storage").model_dump(),
        )
    if not deleted:
        raise HTTPException(
            status_code=404,
            detail=ErrorResponse(error=f"Benchmark {benchmark_id} not found", error_type="not_found").model_dump(),
        )
    return {
        "status": "deleted",
        "benchmark_id": benchmark_id,
        "message": "Benchmark deleted successfully"
    }
