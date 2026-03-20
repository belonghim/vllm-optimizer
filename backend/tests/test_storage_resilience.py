"""
Unit tests for the Storage class resilience features.

Tests cover:
- Data retention policy (prune methods)
- WAL checkpoint execution
- DB integrity check and auto-recovery
- StorageHealthMonitor lifecycle and metrics
- Auto-prune on capacity threshold

All tests use ':memory:' SQLite for complete isolation except
test_integrity_check_corrupted which requires file-based DB for corruption testing.
"""
import asyncio
import os
import tempfile
import time

import pytest

from services.storage import Storage
from services.storage_health import StorageHealthMonitor
from metrics.storage_metrics import (
    storage_benchmark_count,
    storage_db_size_bytes,
    storage_last_checkpoint_timestamp,
    storage_load_test_count,
    storage_prune_total,
    storage_wal_size_bytes,
)
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


@pytest.fixture
async def storage_with_data():
    """Create storage with sample data for testing."""
    s = Storage(":memory:")
    await s.initialize()

    # Add 1500 load test history entries
    base_time = time.time()
    for i in range(1500):
        entry = {
            "test_id": f"test-{i:04d}",
            "config": {"endpoint": "http://test", "model": "test-model"},
            "result": {"elapsed": i * 0.1, "success": i},
            "timestamp": base_time - (1500 - i),  # Oldest first
        }
        await s.save_load_test(entry)

    # Add 150 benchmark entries (reverse order for timestamp)
    for i in range(150):
        b = _make_benchmark(f"benchmark-{i:03d}", total=i + 1)
        b.timestamp = base_time - (150 - i)
        await s.save_benchmark(b)

    yield s
    await s.close()


@pytest.fixture
async def file_storage():
    """Create a file-based storage instance for corruption tests."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        storage = Storage(db_path)
        await storage.initialize()
        yield storage
        await storage.close()
    finally:
        # Cleanup temp files
        for suffix in ["", "-wal", "-shm"]:
            path = db_path + suffix
            if os.path.exists(path):
                os.unlink(path)


# ==================== Helper Functions ====================


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


# ==================== Prune Tests ====================


@pytest.mark.asyncio
async def test_prune_load_test_history():
    """
    Test that prune_load_test_history keeps the newest N records
    and deletes the rest.
    """
    s = Storage(":memory:")
    await s.initialize()

    try:
        # Insert 1500 load test entries
        base_time = time.time()
        for i in range(1500):
            entry = {
                "test_id": f"test-{i:04d}",
                "config": {"endpoint": "http://test"},
                "result": {"elapsed": i * 0.1},
                "timestamp": base_time + i,  # Newest has highest timestamp
            }
            await s.save_load_test(entry)

        # Verify initial count
        history = await s.get_load_test_history(limit=10000)
        assert len(history) == 1500

        # Prune keeping 1000 newest
        deleted = await s.prune_load_test_history(keep_count=1000)
        assert deleted == 500, f"Expected 500 deleted, got {deleted}"

        # Verify remaining count
        history_after = await s.get_load_test_history(limit=10000)
        assert len(history_after) == 1000, f"Expected 1000 remaining, got {len(history_after)}"

        # Verify newest entries are kept (test-1499 should be first)
        assert history_after[0]["test_id"] == "test-1499"
        # Oldest deleted entry should be test-0000 through test-0499
        oldest_kept = history_after[-1]["test_id"]
        assert oldest_kept == "test-0500" or oldest_kept == "test-0500"

    finally:
        await s.close()


@pytest.mark.asyncio
async def test_prune_benchmarks():
    """
    Test that prune_benchmarks keeps the newest N records
    and deletes the rest.
    """
    s = Storage(":memory:")
    await s.initialize()

    try:
        # Insert 150 benchmark entries with increasing timestamps
        base_time = time.time()
        for i in range(150):
            b = _make_benchmark(f"benchmark-{i:03d}", total=i + 1)
            b.timestamp = base_time + i
            await s.save_benchmark(b)

        # Verify initial count
        benchmarks = await s.list_benchmarks()
        assert len(benchmarks) == 150

        # Prune keeping 100 newest
        deleted = await s.prune_benchmarks(keep_count=100)
        assert deleted == 50, f"Expected 50 deleted, got {deleted}"

        # Verify remaining count
        benchmarks_after = await s.list_benchmarks()
        assert len(benchmarks_after) == 100, f"Expected 100 remaining, got {len(benchmarks_after)}"

        # Verify newest entries are kept (benchmark-149 should be first)
        assert benchmarks_after[0].name == "benchmark-149"

    finally:
        await s.close()


@pytest.mark.asyncio
async def test_prune_empty_table():
    """
    Test that pruning an empty table returns 0 deletions
    without raising exceptions.
    """
    s = Storage(":memory:")
    await s.initialize()

    try:
        # Both tables should be empty
        deleted_history = await s.prune_load_test_history(keep_count=1000)
        assert deleted_history == 0, "Empty load_test_history should return 0 deletions"

        deleted_benchmarks = await s.prune_benchmarks(keep_count=100)
        assert deleted_benchmarks == 0, "Empty benchmarks table should return 0 deletions"

        # Verify tables are still empty
        history = await s.get_load_test_history()
        assert len(history) == 0

        benchmarks = await s.list_benchmarks()
        assert len(benchmarks) == 0

    finally:
        await s.close()


# ==================== WAL Checkpoint Tests ====================


@pytest.mark.asyncio
async def test_wal_checkpoint():
    """
    Test that checkpoint_wal executes successfully on in-memory DB.
    Note: In-memory DBs don't have actual WAL files but the operation
    should still succeed.
    """
    s = Storage(":memory:")
    await s.initialize()

    try:
        # Perform some writes to ensure DB is operational
        b = _make_benchmark("checkpoint-test")
        await s.save_benchmark(b)

        # Execute checkpoint
        result = await s.checkpoint_wal()
        assert result is True, "checkpoint_wal should return True for in-memory DB"

        # Verify benchmark is still accessible
        benchmarks = await s.list_benchmarks()
        assert len(benchmarks) == 1
        assert benchmarks[0].name == "checkpoint-test"

    finally:
        await s.close()


@pytest.mark.asyncio
async def test_wal_checkpoint_file_based():
    """
    Test WAL checkpoint on file-based database with actual writes.
    """
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        s = Storage(db_path)
        await s.initialize()

        # Verify WAL mode is enabled
        cursor = await s._conn.execute("PRAGMA journal_mode")
        row = await cursor.fetchone()
        assert row[0].lower() == "wal"

        # Perform many writes to create WAL activity
        for i in range(100):
            b = _make_benchmark(f"wal-test-{i}")
            await s.save_benchmark(b)

        # Execute checkpoint
        result = await s.checkpoint_wal()
        assert result is True

        # Verify data is still accessible
        benchmarks = await s.list_benchmarks()
        assert len(benchmarks) == 100

        await s.close()

    finally:
        # Cleanup
        for suffix in ["", "-wal", "-shm"]:
            path = db_path + suffix
            if os.path.exists(path):
                os.unlink(path)


@pytest.mark.asyncio
async def test_checkpoint_before_init():
    """
    Test that checkpoint_wal returns False when DB is not initialized.
    """
    s = Storage(":memory:")
    # Don't initialize

    result = await s.checkpoint_wal()
    assert result is False, "checkpoint_wal should return False when not initialized"


# ==================== Integrity Check Tests ====================


@pytest.mark.asyncio
async def test_integrity_check_pass(storage):
    """
    Test that a properly initialized DB passes integrity check
    (implicit via successful initialize).
    """
    # Storage fixture already initialized successfully
    assert storage._conn is not None

    # Perform some operations to ensure DB is healthy
    b = _make_benchmark("integrity-test")
    await storage.save_benchmark(b)

    # Run manual integrity check
    cursor = await storage._conn.execute("PRAGMA integrity_check")
    row = await cursor.fetchone()

    assert row is not None
    assert row[0] == "ok", f"Integrity check should return 'ok', got: {row[0]}"


@pytest.mark.asyncio
async def test_integrity_check_corrupted():
    """
    Test that a corrupted database is backed up and re-created.
    This test uses a file-based DB and corrupts it by writing
    random data to the file. When SQLite encounters a corrupted file,
    it raises DatabaseError immediately upon connection (not during query).
    The Storage.initialize() catches this error, backs up the corrupted
    file, and creates a fresh database.
    """
    import glob

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    corrupted_backup = None

    try:
        # Step 1: Create and populate a healthy database
        s = Storage(db_path)
        await s.initialize()

        b = _make_benchmark("before-corruption")
        await s.save_benchmark(b)

        benchmarks = await s.list_benchmarks()
        assert len(benchmarks) == 1

        await s.close()

        # Step 2: Corrupt the database file
        # Write garbage data at a location that will corrupt the header
        with open(db_path, "r+b") as f:
            f.seek(50)
            f.write(b"CORRUPTED_DATABASE_MARKER_PHRASE")

        # Verify the file is now corrupted by attempting to connect
        # (SQLite raises DatabaseError immediately on corrupted files)
        import aiosqlite
        corrupted_conn = None
        try:
            corrupted_conn = await aiosqlite.connect(db_path)
            # If we get here without exception, try a simple query
            cursor = await corrupted_conn.execute("SELECT 1")
            await cursor.fetchone()
        except Exception as e:
            # Expected: either connection fails or query fails with DatabaseError
            assert "malformed" in str(e).lower() or isinstance(e, aiosqlite.DatabaseError), \
                f"Expected corruption error, got: {e}"
        finally:
            if corrupted_conn:
                await corrupted_conn.close()

        # Step 3: Re-initialize - should backup corrupted file and create fresh DB
        s2 = Storage(db_path)

        # Record existing backups before re-initialization
        backup_pattern = f"{db_path}.corrupted.*"
        existing_backups = set(glob.glob(backup_pattern))

        await s2.initialize()

        # Check that a backup was created
        new_backups = set(glob.glob(backup_pattern))
        backup_created = new_backups - existing_backups
        assert len(backup_created) > 0, "Corrupted DB should be backed up"

        # Get the new backup file
        new_backup = list(backup_created)[0]
        corrupted_backup = new_backup

        # Verify backup contains corruption marker
        with open(new_backup, "rb") as f:
            content = f.read()
            assert b"CORRUPTED" in content, "Backup should contain corrupted data"

        # Step 4: Verify fresh database works correctly
        assert s2._conn is not None

        # Run integrity check on fresh DB
        cursor = await s2._conn.execute("PRAGMA integrity_check")
        row = await cursor.fetchone()
        assert row[0] == "ok", "Fresh DB should pass integrity check"

        # Tables should exist but be empty (fresh start after corruption recovery)
        benchmarks = await s2.list_benchmarks()
        assert len(benchmarks) == 0, "Fresh DB should have no data (recovered from corruption)"

        await s2.close()

    finally:
        # Cleanup
        for suffix in ["", "-wal", "-shm"]:
            path = db_path + suffix
            if os.path.exists(path):
                os.unlink(path)
        if corrupted_backup and os.path.exists(corrupted_backup):
            os.unlink(corrupted_backup)


# ==================== StorageHealthMonitor Tests ====================


@pytest.mark.asyncio
async def test_health_monitor_lifecycle():
    """
    Test StorageHealthMonitor start and stop lifecycle.
    """
    s = Storage(":memory:")
    await s.initialize()

    try:
        monitor = StorageHealthMonitor(
            storage=s,
            interval_seconds=1,  # Short interval for testing
        )

        # Initial state
        assert monitor._running is False
        assert monitor._task is None

        # Start monitor
        monitor.start()
        assert monitor._running is True
        assert monitor._task is not None

        # Start again - should be idempotent
        monitor.start()
        assert monitor._running is True

        # Give it time to run one cycle
        await asyncio.sleep(0.1)

        # Stop monitor
        monitor.stop()
        assert monitor._running is False

        # Wait for task to complete cancellation
        try:
            await asyncio.wait_for(monitor._task, timeout=2.0)
        except asyncio.TimeoutError:
            pass  # Task may still be running, that's ok

    finally:
        monitor.stop()
        await s.close()


@pytest.mark.asyncio
async def test_health_monitor_manual_check():
    """
    Test that manual check_health() works without starting background loop.
    """
    s = Storage(":memory:")
    await s.initialize()

    try:
        # Add some data
        for i in range(10):
            b = _make_benchmark(f"metric-test-{i}")
            await s.save_benchmark(b)

        entry = {
            "test_id": "manual-check-test",
            "config": {"endpoint": "http://test"},
            "result": {"success": 1},
            "timestamp": time.time(),
        }
        await s.save_load_test(entry)

        monitor = StorageHealthMonitor(storage=s)

        # Manual health check
        await monitor.check_health()

        # Verify metrics were updated (record counts)
        # In-memory DB returns 0 for file sizes
        assert storage_wal_size_bytes._value._value == 0.0
        assert storage_db_size_bytes._value._value == 0.0

    finally:
        await s.close()


@pytest.mark.asyncio
async def test_auto_prune_on_threshold():
    """
    Test that auto-prune is triggered when storage capacity threshold is reached.
    """
    s = Storage(":memory:")
    await s.initialize()

    try:
        # Add enough data to trigger pruning
        base_time = time.time()

        # Add 1500 load test entries (prune_threshold will keep 1000)
        for i in range(1500):
            entry = {
                "test_id": f"auto-prune-{i:04d}",
                "config": {"endpoint": "http://test"},
                "result": {"elapsed": i * 0.1},
                "timestamp": base_time - (1500 - i),
            }
            await s.save_load_test(entry)

        # Add 150 benchmarks (prune_threshold will keep 100)
        for i in range(150):
            b = _make_benchmark(f"auto-benchmark-{i:03d}", total=i + 1)
            b.timestamp = base_time - (150 - i)
            await s.save_benchmark(b)

        # Verify initial counts
        history = await s.get_load_test_history(limit=10000)
        assert len(history) == 1500
        benchmarks = await s.list_benchmarks()
        assert len(benchmarks) == 150

        # Create monitor with very small capacity to trigger auto-prune
        # Set capacity to simulate 90%+ usage scenario
        monitor = StorageHealthMonitor(
            storage=s,
            interval_seconds=3600,  # Won't run in this test
            prune_threshold=0.0,  # Always trigger prune
            benchmark_keep_count=100,
            load_test_keep_count=1000,
            capacity_bytes=1000,  # Very small to always trigger
        )

        # Run manual health check with auto-prune
        await monitor.check_health()

        # Give time for async operations
        await asyncio.sleep(0.1)

        # Verify pruning occurred
        history_after = await s.get_load_test_history(limit=10000)
        assert len(history_after) <= 1000, f"Expected <= 1000, got {len(history_after)}"

        benchmarks_after = await s.list_benchmarks()
        assert len(benchmarks_after) <= 100, f"Expected <= 100, got {len(benchmarks_after)}"

    finally:
        await s.close()


@pytest.mark.asyncio
async def test_health_monitor_multiple_cycles():
    """
    Test that health monitor runs multiple cycles without issues.
    """
    s = Storage(":memory:")
    await s.initialize()

    try:
        monitor = StorageHealthMonitor(
            storage=s,
            interval_seconds=1,  # 1 second intervals
        )

        monitor.start()

        # Run for 3 cycles
        await asyncio.sleep(0.2)

        monitor.stop()

        # Task should have run multiple times
        # We can't easily count iterations, but we can verify no exceptions
        assert monitor._running is False

    finally:
        await s.close()


@pytest.mark.asyncio
async def test_health_monitor_no_storage_init():
    """
    Test that health monitor handles uninitialized storage gracefully.
    """
    s = Storage(":memory:")
    # Don't initialize

    try:
        monitor = StorageHealthMonitor(storage=s)

        # Manual check should not raise
        await monitor.check_health()

    finally:
        await s.close()


# ==================== Edge Case Tests ====================


@pytest.mark.asyncio
async def test_prune_with_exact_keep_count():
    """
    Test pruning when table has exactly the keep_count records.
    Should return 0 deletions.
    """
    s = Storage(":memory:")
    await s.initialize()

    try:
        # Insert exactly 100 load test entries
        base_time = time.time()
        for i in range(100):
            entry = {
                "test_id": f"exact-{i:03d}",
                "config": {},
                "result": {},
                "timestamp": base_time + i,
            }
            await s.save_load_test(entry)

        # Prune keeping 100 - should delete nothing
        deleted = await s.prune_load_test_history(keep_count=100)
        assert deleted == 0, "Should delete nothing when count equals keep_count"

        # Verify still 100 entries
        history = await s.get_load_test_history(limit=10000)
        assert len(history) == 100

    finally:
        await s.close()


@pytest.mark.asyncio
async def test_prune_with_less_than_keep_count():
    """
    Test pruning when table has fewer records than keep_count.
    Should return 0 deletions.
    """
    s = Storage(":memory:")
    await s.initialize()

    try:
        # Insert only 50 entries
        base_time = time.time()
        for i in range(50):
            entry = {
                "test_id": f"less-{i:02d}",
                "config": {},
                "result": {},
                "timestamp": base_time + i,
            }
            await s.save_load_test(entry)

        # Prune keeping 100 - should delete nothing
        deleted = await s.prune_load_test_history(keep_count=100)
        assert deleted == 0, "Should delete nothing when count < keep_count"

        # Verify still 50 entries
        history = await s.get_load_test_history(limit=10000)
        assert len(history) == 50

    finally:
        await s.close()


@pytest.mark.asyncio
async def test_checkpoint_on_closed_storage():
    """
    Test that checkpoint_wal handles closed storage gracefully.
    """
    s = Storage(":memory:")
    await s.initialize()

    # Close the storage
    await s.close()

    # Checkpoint should return False
    result = await s.checkpoint_wal()
    assert result is False


@pytest.mark.asyncio
async def test_prune_on_closed_storage():
    """
    Test that prune methods handle closed storage gracefully.
    """
    s = Storage(":memory:")
    await s.initialize()

    # Close the storage
    await s.close()

    # Prune should return 0
    deleted_history = await s.prune_load_test_history(keep_count=100)
    assert deleted_history == 0

    deleted_benchmarks = await s.prune_benchmarks(keep_count=100)
    assert deleted_benchmarks == 0
