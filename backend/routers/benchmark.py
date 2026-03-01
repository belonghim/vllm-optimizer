"""
Benchmark Router
Provides endpoints for saving, retrieving, and managing benchmark results.
"""
from fastapi import APIRouter, HTTPException
from typing import List, Dict, Any
from datetime import datetime
from models.load_test import Benchmark

router = APIRouter()

# In-memory storage stub (will be replaced with database in future)
benchmark_storage: List[Benchmark] = []


@router.get("/list", response_model=List[Benchmark])
async def list_benchmarks() -> List[Benchmark]:
    """Get list of all saved benchmarks."""
    return benchmark_storage


@router.post("/save", response_model=Benchmark)
async def save_benchmark(benchmark: Benchmark) -> Benchmark:
    """Save a benchmark result for later comparison."""
    benchmark.id = len(benchmark_storage) + 1
    benchmark.timestamp = datetime.utcnow().timestamp()
    benchmark_storage.append(benchmark)
    return benchmark


@router.get("/{benchmark_id}", response_model=Benchmark)
async def get_benchmark(benchmark_id: int) -> Benchmark:
    """Retrieve a specific benchmark by ID."""
    for benchmark in benchmark_storage:
        if benchmark.id == benchmark_id:
            return benchmark
    raise HTTPException(status_code=404, detail=f"Benchmark {benchmark_id} not found")


@router.delete("/{benchmark_id}")
async def delete_benchmark(benchmark_id: int) -> Dict[str, Any]:
    """Delete a saved benchmark."""
    for i, benchmark in enumerate(benchmark_storage):
        if benchmark.id == benchmark_id:
            del benchmark_storage[i]
            return {
                "status": "deleted",
                "benchmark_id": benchmark_id,
                "message": "Benchmark deleted successfully"
            }
    raise HTTPException(status_code=404, detail=f"Benchmark {benchmark_id} not found")
