"""
Unit tests for the Storage class — SQLite persistence layer.

All tests use ':memory:' SQLite for complete isolation.
Tests cover:
- Table creation and schema
- CRUD operations for benchmarks, load_test_history, tuner_trials
- Concurrent write handling (WAL mode + busy_timeout)
- Data persistence across re-initialization
"""
import asyncio
import pytest

from services.storage import Storage
from models.load_test import (
    Benchmark,
    LoadTestConfig,
    LoadTestResult,
    LatencyStats,
    TpsStats,
    TuningTrial,
)


# ==================== Fixtures ====================


@pytest.fixture
async def storage():
    """Create an in-memory Storage instance for each test."""
    s = Storage(":memory:")
    await s.initialize()
    yield s
    await s.close()


def _make_benchmark(name: str = "test-benchmark", total: int = 100) -> Benchmark:
    """Factory helper to create a Benchmark with minimal config."""
    return Benchmark(
        name=name,
        config=LoadTestConfig(
            endpoint="http://localhost:8000",
            model="test-model",
            total_requests=total,
            concurrency=10,
        ),
        result=LoadTestResult(
            elapsed=1.0,
            total=total,
            success=total,
            failed=0,
            rps_actual=100.0,
            latency=LatencyStats(mean=0.1, p50=0.1, p95=0.2, p99=0.3, min=0.05, max=0.5),
            ttft=LatencyStats(mean=0.05, p50=0.05, p95=0.08, p99=0.1, min=0.01, max=0.2),
            tps=TpsStats(mean=500.0, total=5000.0),
        ),
    )


def _make_trial(trial_id: int, tps: float = 100.0, p99: float = 0.5) -> TuningTrial:
    """Factory helper to create a TuningTrial."""
    return TuningTrial(
        trial_id=trial_id,
        params={"max_num_seqs": 128, "gpu_memory_utilization": 0.9},
        tps=tps,
        p99_latency=p99,
        score=tps / p99,
        status="completed",
        is_pareto_optimal=False,
        pruned=False,
    )


# ==================== Table Creation Tests ====================


@pytest.mark.asyncio
async def test_create_tables(storage):
    """Verify tables are created correctly on initialization."""
    assert storage._conn is not None

    # Check benchmarks table exists
    cursor = await storage._conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='benchmarks'"
    )
    row = await cursor.fetchone()
    assert row is not None, "benchmarks table should exist"

    # Check load_test_history table exists
    cursor = await storage._conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='load_test_history'"
    )
    row = await cursor.fetchone()
    assert row is not None, "load_test_history table should exist"

    # Check tuner_trials table exists
    cursor = await storage._conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='tuner_trials'"
    )
    row = await cursor.fetchone()
    assert row is not None, "tuner_trials table should exist"

    # Note: In-memory databases always report "memory" journal mode.
    # WAL mode is only applicable to file-based databases.
    cursor = await storage._conn.execute("PRAGMA journal_mode")
    row = await cursor.fetchone()
    # For :memory: databases, journal_mode is always "memory" (WAL not supported)
    assert row[0].lower() == "memory", "In-memory DB should use memory journal mode"

    # Verify busy_timeout is set (should be 5000ms)
    cursor = await storage._conn.execute("PRAGMA busy_timeout")
    row = await cursor.fetchone()
    assert row[0] == 5000, "busy_timeout should be 5000ms"


# ==================== Benchmark CRUD Tests ====================


@pytest.mark.asyncio
async def test_save_and_list_benchmarks(storage):
    """Test save → list round-trip for benchmarks."""
    # Initially empty
    benchmarks = await storage.list_benchmarks()
    assert len(benchmarks) == 0

    # Save first benchmark
    b1 = _make_benchmark("benchmark-1", total=100)
    saved1 = await storage.save_benchmark(b1)
    assert saved1.id is not None, "Saved benchmark should have an ID"
    assert saved1.timestamp is not None, "Saved benchmark should have a timestamp"
    assert saved1.name == "benchmark-1"

    # Save second benchmark
    b2 = _make_benchmark("benchmark-2", total=200)
    saved2 = await storage.save_benchmark(b2)
    assert saved2.id is not None
    assert saved2.id != saved1.id, "Each benchmark should have a unique ID"

    # List should return both, ordered by timestamp DESC (newest first)
    benchmarks = await storage.list_benchmarks()
    assert len(benchmarks) == 2
    # saved2 was saved after saved1, so it should be first
    assert benchmarks[0].name == "benchmark-2"
    assert benchmarks[1].name == "benchmark-1"

    # Verify data integrity
    assert benchmarks[0].config.total_requests == 200
    assert benchmarks[1].result.success == 100


@pytest.mark.asyncio
async def test_delete_benchmark(storage):
    """Test benchmark deletion."""
    # Save a benchmark
    b = _make_benchmark("to-delete")
    saved = await storage.save_benchmark(b)
    assert saved.id is not None
    benchmark_id = saved.id

    # Verify it exists
    retrieved = await storage.get_benchmark(benchmark_id)
    assert retrieved is not None
    assert retrieved.name == "to-delete"

    # Delete it
    deleted = await storage.delete_benchmark(benchmark_id)
    assert deleted is True

    # Verify it's gone
    retrieved_after = await storage.get_benchmark(benchmark_id)
    assert retrieved_after is None

    # List should be empty
    benchmarks = await storage.list_benchmarks()
    assert len(benchmarks) == 0

    # Deleting non-existent ID should return False
    deleted_again = await storage.delete_benchmark(benchmark_id)
    assert deleted_again is False


# ==================== Load Test History Tests ====================


@pytest.mark.asyncio
async def test_save_load_test_history(storage):
    """Test load test history save and 100-entry limit on retrieval."""
    import time

    # Save 120 entries to exceed the default limit of 100
    base_time = time.time()
    for i in range(120):
        entry = {
            "test_id": f"test-{i:03d}",
            "config": {"endpoint": "http://test", "model": "test-model"},
            "result": {"elapsed": i * 0.1, "success": i},
            "timestamp": base_time + i,  # Incrementing timestamps
        }
        await storage.save_load_test(entry)

    # Retrieve with default limit (100)
    history = await storage.get_load_test_history(limit=100)
    assert len(history) == 100, "Should return at most 100 entries"

    # Verify entries are ordered by timestamp DESC (newest first)
    # The last entry saved (test-119) should be first
    assert history[0]["test_id"] == "test-119"
    assert history[99]["test_id"] == "test-020"  # 100th newest

    # Verify we can request a smaller limit
    history_small = await storage.get_load_test_history(limit=10)
    assert len(history_small) == 10
    assert history_small[0]["test_id"] == "test-119"

    # Verify data integrity
    assert history[0]["result"]["success"] == 119


# ==================== Tuner Trials Tests ====================


@pytest.mark.asyncio
async def test_save_and_get_trials(storage):
    """Test trial save and retrieval."""
    # Initially empty
    trials = await storage.get_trials()
    assert len(trials) == 0

    # Save multiple trials out of order
    t3 = _make_trial(trial_id=3, tps=150.0)
    t1 = _make_trial(trial_id=1, tps=100.0)
    t2 = _make_trial(trial_id=2, tps=120.0)

    await storage.save_trial(t3)
    await storage.save_trial(t1)
    await storage.save_trial(t2)

    # Retrieve — should be ordered by trial_id ASC
    trials = await storage.get_trials()
    assert len(trials) == 3
    assert trials[0].trial_id == 1
    assert trials[1].trial_id == 2
    assert trials[2].trial_id == 3

    # Verify data integrity
    assert trials[0].tps == 100.0
    assert trials[2].tps == 150.0
    assert trials[1].params["max_num_seqs"] == 128

    # Test upsert — update existing trial
    t1_updated = _make_trial(trial_id=1, tps=110.0)
    t1_updated.status = "updated"
    await storage.save_trial(t1_updated)

    trials_after = await storage.get_trials()
    assert len(trials_after) == 3, "Should still have 3 trials (upsert, not insert)"
    assert trials_after[0].tps == 110.0
    assert trials_after[0].status == "updated"


@pytest.mark.asyncio
async def test_clear_trials(storage):
    """Test clearing all trials."""
    # Save some trials
    for i in range(5):
        t = _make_trial(trial_id=i, tps=100.0 + i * 10)
        await storage.save_trial(t)

    # Verify they exist
    trials = await storage.get_trials()
    assert len(trials) == 5

    # Clear all
    await storage.clear_trials()

    # Verify empty
    trials_after = await storage.get_trials()
    assert len(trials_after) == 0


# ==================== Concurrent Write Tests ====================


@pytest.mark.asyncio
async def test_concurrent_writes(storage):
    """Test 50 concurrent writes don't cause SQLITE_BUSY errors."""

    async def save_benchmark(idx: int):
        """Save a single benchmark."""
        b = _make_benchmark(f"concurrent-{idx:02d}", total=idx + 1)
        result = await storage.save_benchmark(b)
        return result

    # Fire 50 concurrent saves
    tasks = [save_benchmark(i) for i in range(50)]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Check no exceptions occurred
    exceptions = [r for r in results if isinstance(r, Exception)]
    assert len(exceptions) == 0, f"No exceptions expected, got: {exceptions}"

    # Verify all 50 benchmarks were saved
    benchmarks = await storage.list_benchmarks()
    assert len(benchmarks) == 50

    # Verify all have unique IDs
    ids = [b.id for b in benchmarks]
    assert len(set(ids)) == 50, "All benchmarks should have unique IDs"


# ==================== Re-initialization Tests ====================


@pytest.mark.asyncio
async def test_wal_mode_on_file_db():
    """Test that WAL mode is enabled on file-based databases."""
    import tempfile
    import os

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        storage = Storage(db_path)
        await storage.initialize()

        # Verify WAL mode is enabled for file-based DB
        cursor = await storage._conn.execute("PRAGMA journal_mode")
        row = await cursor.fetchone()
        assert row[0].lower() == "wal", "File-based DB should use WAL mode"

        await storage.close()

    finally:
        # Cleanup temp files (including WAL files)
        for suffix in ["", "-wal", "-shm"]:
            path = db_path + suffix
            if os.path.exists(path):
                os.unlink(path)


@pytest.mark.asyncio
async def test_startup_with_existing_db():
    """Test that re-initializing Storage preserves existing data."""
    import tempfile
    import os

    # Create a temp file for the database
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        # First session: create and populate
        storage1 = Storage(db_path)
        await storage1.initialize()

        # Save some data
        b1 = _make_benchmark("persistent-1")
        saved1 = await storage1.save_benchmark(b1)
        assert saved1.id is not None

        t1 = _make_trial(trial_id=1, tps=200.0)
        await storage1.save_trial(t1)

        # Close first session
        await storage1.close()

        # Second session: reconnect and verify data persists
        storage2 = Storage(db_path)
        await storage2.initialize()

        # Verify benchmarks persist
        benchmarks = await storage2.list_benchmarks()
        assert len(benchmarks) == 1
        assert benchmarks[0].name == "persistent-1"

        # Verify trials persist
        trials = await storage2.get_trials()
        assert len(trials) == 1
        assert trials[0].tps == 200.0

        # Add more data in second session
        b2 = _make_benchmark("persistent-2")
        await storage2.save_benchmark(b2)

        benchmarks_after = await storage2.list_benchmarks()
        assert len(benchmarks_after) == 2

        await storage2.close()

    finally:
        # Cleanup temp files (including WAL files)
        for suffix in ["", "-wal", "-shm"]:
            path = db_path + suffix
            if os.path.exists(path):
                os.unlink(path)


# ==================== Edge Case Tests ====================


@pytest.mark.asyncio
async def test_operations_before_initialize():
    """Test that operations on uninitialized Storage return safe defaults."""
    storage = Storage(":memory:")
    # Don't call initialize()

    # Operations should return safe defaults, not crash
    benchmarks = await storage.list_benchmarks()
    assert benchmarks == []

    b = _make_benchmark("test")
    result = await storage.save_benchmark(b)
    # Returns the original benchmark without modification
    assert result.id is None

    trials = await storage.get_trials()
    assert trials == []

    history = await storage.get_load_test_history()
    assert history == []


@pytest.mark.asyncio
async def test_get_nonexistent_benchmark(storage):
    """Test getting a benchmark that doesn't exist."""
    result = await storage.get_benchmark(9999)
    assert result is None


@pytest.mark.asyncio
async def test_benchmark_with_explicit_id(storage):
    """Test saving a benchmark with an explicit ID (upsert behavior)."""
    # Save with explicit ID
    b = _make_benchmark("explicit-id")
    b.id = 42
    saved = await storage.save_benchmark(b)
    assert saved.id == 42

    # Retrieve it
    retrieved = await storage.get_benchmark(42)
    assert retrieved is not None
    assert retrieved.name == "explicit-id"

    # Update with same ID
    b_updated = _make_benchmark("updated-name")
    b_updated.id = 42
    await storage.save_benchmark(b_updated)

    retrieved_after = await storage.get_benchmark(42)
    assert retrieved_after.name == "updated-name"

    # Should still be only 1 benchmark
    benchmarks = await storage.list_benchmarks()
    assert len(benchmarks) == 1
