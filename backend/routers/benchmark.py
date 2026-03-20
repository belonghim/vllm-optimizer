"""
Benchmark Router
Provides endpoints for saving, retrieving, and managing benchmark results.
"""
from fastapi import APIRouter, HTTPException
from typing import List, Dict, Any
from models.load_test import Benchmark
from services.shared import storage

router = APIRouter()


@router.get("/list", response_model=List[Benchmark])
async def list_benchmarks() -> List[Benchmark]:
    """Get list of all saved benchmarks."""
    return await storage.list_benchmarks()


@router.post("/save", response_model=Benchmark)
async def save_benchmark(benchmark: Benchmark) -> Benchmark:
    """Save a benchmark result for later comparison."""
    return await storage.save_benchmark(benchmark)


@router.get("/by-model", response_model=Dict[str, Any])
async def benchmarks_by_model() -> Dict[str, Any]:
    """Get benchmarks grouped by model name, with GPU efficiency calculated."""
    benchmarks = await storage.list_benchmarks()
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
    """Retrieve a specific benchmark by ID."""
    benchmark = await storage.get_benchmark(benchmark_id)
    if benchmark is None:
        raise HTTPException(status_code=404, detail=f"Benchmark {benchmark_id} not found")
    return benchmark


@router.delete("/{benchmark_id}")
async def delete_benchmark(benchmark_id: int) -> Dict[str, Any]:
    """Delete a saved benchmark."""
    deleted = await storage.delete_benchmark(benchmark_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Benchmark {benchmark_id} not found")
    return {
        "status": "deleted",
        "benchmark_id": benchmark_id,
        "message": "Benchmark deleted successfully"
    }
