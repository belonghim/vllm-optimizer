from unittest.mock import AsyncMock, MagicMock

import pytest

from ..services.storage_health import StorageHealthMonitor


def _make_storage(db_path: str = ":memory:") -> MagicMock:
    storage = MagicMock()
    storage._db_path = db_path
    storage._conn = None
    storage.prune_benchmarks = AsyncMock(return_value=0)
    storage.prune_load_test_history = AsyncMock(return_value=0)
    storage.checkpoint_wal = AsyncMock(return_value=True)
    return storage


class TestStorageHealthMonitorInit:
    def test_default_values(self) -> None:
        monitor = StorageHealthMonitor(_make_storage())
        assert monitor._interval_seconds == 300
        assert monitor._warning_threshold == 0.8
        assert monitor._prune_threshold == 0.9
        assert monitor._benchmark_keep_count == 100
        assert monitor._load_test_keep_count == 1000
        assert monitor._running is False

    def test_custom_values(self) -> None:
        monitor = StorageHealthMonitor(
            _make_storage(),
            interval_seconds=60,
            warning_threshold=0.5,
            prune_threshold=0.7,
            benchmark_keep_count=10,
            load_test_keep_count=50,
            capacity_bytes=1_000_000,
        )
        assert monitor._interval_seconds == 60
        assert monitor._warning_threshold == 0.5
        assert monitor._prune_threshold == 0.7
        assert monitor._capacity_bytes == 1_000_000

    def test_capacity_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("STORAGE_CAPACITY_BYTES", "52428800")
        monitor = StorageHealthMonitor(_make_storage())
        assert monitor._capacity_bytes == 52428800

    def test_explicit_capacity_takes_precedence_over_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("STORAGE_CAPACITY_BYTES", "99999")
        monitor = StorageHealthMonitor(_make_storage(), capacity_bytes=12345)
        assert monitor._capacity_bytes == 12345


class TestCollectFileSizes:
    @pytest.mark.asyncio
    async def test_memory_db_returns_zeros(self) -> None:
        monitor = StorageHealthMonitor(_make_storage())
        db_size, wal_size = await monitor._collect_file_sizes(":memory:")
        assert db_size == 0
        assert wal_size == 0

    @pytest.mark.asyncio
    async def test_nonexistent_file_returns_zeros(self) -> None:
        monitor = StorageHealthMonitor(_make_storage())
        db_size, wal_size = await monitor._collect_file_sizes("/nonexistent/path/app.db")
        assert db_size == 0
        assert wal_size == 0

    @pytest.mark.asyncio
    async def test_existing_file_returns_size(self, tmp_path: pytest.TempPathFactory) -> None:
        db_file = tmp_path / "test.db"  # type: ignore[operator]
        db_file.write_bytes(b"x" * 1024)

        monitor = StorageHealthMonitor(_make_storage())
        db_size, wal_size = await monitor._collect_file_sizes(str(db_file))

        assert db_size == 1024
        assert wal_size == 0

    @pytest.mark.asyncio
    async def test_existing_file_with_wal_returns_both(self, tmp_path: pytest.TempPathFactory) -> None:
        db_file = tmp_path / "test.db"  # type: ignore[operator]
        wal_file = tmp_path / "test.db-wal"  # type: ignore[operator]
        db_file.write_bytes(b"x" * 512)
        wal_file.write_bytes(b"y" * 256)

        monitor = StorageHealthMonitor(_make_storage())
        db_size, wal_size = await monitor._collect_file_sizes(str(db_file))

        assert db_size == 512
        assert wal_size == 256


class TestCollectRecordCounts:
    @pytest.mark.asyncio
    async def test_no_conn_returns_zeros(self) -> None:
        storage = _make_storage()
        storage._conn = None
        monitor = StorageHealthMonitor(storage)

        lt_count, bm_count = await monitor._collect_record_counts()

        assert lt_count == 0
        assert bm_count == 0

    @pytest.mark.asyncio
    async def test_with_conn_returns_counts(self) -> None:
        storage = _make_storage()

        async def _execute(query: str) -> AsyncMock:
            cursor = AsyncMock()
            if "load_test_history" in query:
                cursor.fetchone = AsyncMock(return_value=(42,))
            else:
                cursor.fetchone = AsyncMock(return_value=(7,))
            return cursor

        mock_conn = MagicMock()
        mock_conn.execute = _execute
        storage._conn = mock_conn
        monitor = StorageHealthMonitor(storage)

        lt_count, bm_count = await monitor._collect_record_counts()

        assert lt_count == 42
        assert bm_count == 7

    @pytest.mark.asyncio
    async def test_conn_execute_raises_returns_zeros(self) -> None:
        storage = _make_storage()

        async def _execute(query: str) -> None:
            raise OSError("disk error")

        mock_conn = MagicMock()
        mock_conn.execute = _execute
        storage._conn = mock_conn
        monitor = StorageHealthMonitor(storage)

        lt_count, bm_count = await monitor._collect_record_counts()

        assert lt_count == 0
        assert bm_count == 0


class TestCapacityAndPrune:
    @pytest.mark.asyncio
    async def test_no_prune_below_warning_threshold(self) -> None:
        storage = _make_storage()
        monitor = StorageHealthMonitor(storage, capacity_bytes=1_000_000)

        await monitor._check_capacity_and_prune_if_needed(db_size=100_000, wal_size=0, db_path=":memory:")

        storage.prune_benchmarks.assert_not_called()
        storage.prune_load_test_history.assert_not_called()

    @pytest.mark.asyncio
    async def test_prune_triggered_above_prune_threshold(self) -> None:
        storage = _make_storage()
        monitor = StorageHealthMonitor(storage, capacity_bytes=1_000_000)

        await monitor._check_capacity_and_prune_if_needed(db_size=950_000, wal_size=0, db_path=":memory:")

        storage.prune_benchmarks.assert_called_once()
        storage.prune_load_test_history.assert_called_once()

    @pytest.mark.asyncio
    async def test_zero_capacity_skips_check(self) -> None:
        storage = _make_storage()
        monitor = StorageHealthMonitor(storage)

        await monitor._check_capacity_and_prune_if_needed(db_size=999_999, wal_size=0, db_path=":memory:")

        storage.prune_benchmarks.assert_not_called()

    @pytest.mark.asyncio
    async def test_resolve_capacity_bytes_explicit(self) -> None:
        monitor = StorageHealthMonitor(_make_storage(), capacity_bytes=5_000_000)
        result = await monitor._resolve_capacity_bytes("/any/path")
        assert result == 5_000_000

    @pytest.mark.asyncio
    async def test_resolve_capacity_bytes_memory_returns_zero(self) -> None:
        monitor = StorageHealthMonitor(_make_storage())
        result = await monitor._resolve_capacity_bytes(":memory:")
        assert result == 0


class TestRunAutoPrune:
    @pytest.mark.asyncio
    async def test_prune_calls_storage_with_keep_counts(self) -> None:
        storage = _make_storage()
        storage.prune_benchmarks = AsyncMock(return_value=3)
        storage.prune_load_test_history = AsyncMock(return_value=7)
        monitor = StorageHealthMonitor(storage, benchmark_keep_count=50, load_test_keep_count=200)

        await monitor._run_auto_prune()

        storage.prune_benchmarks.assert_called_once_with(keep_count=50)
        storage.prune_load_test_history.assert_called_once_with(keep_count=200)

    @pytest.mark.asyncio
    async def test_prune_storage_error_does_not_raise(self) -> None:
        storage = _make_storage()
        storage.prune_benchmarks = AsyncMock(side_effect=OSError("disk full"))
        monitor = StorageHealthMonitor(storage)

        await monitor._run_auto_prune()


class TestRunCheckpoint:
    @pytest.mark.asyncio
    async def test_checkpoint_success(self) -> None:
        storage = _make_storage()
        storage.checkpoint_wal = AsyncMock(return_value=True)
        monitor = StorageHealthMonitor(storage)

        await monitor._run_checkpoint()

        storage.checkpoint_wal.assert_called_once()

    @pytest.mark.asyncio
    async def test_checkpoint_returns_false_does_not_raise(self) -> None:
        storage = _make_storage()
        storage.checkpoint_wal = AsyncMock(return_value=False)
        monitor = StorageHealthMonitor(storage)

        await monitor._run_checkpoint()

        storage.checkpoint_wal.assert_called_once()

    @pytest.mark.asyncio
    async def test_checkpoint_raises_does_not_propagate(self) -> None:
        storage = _make_storage()
        storage.checkpoint_wal = AsyncMock(side_effect=OSError("wal locked"))
        monitor = StorageHealthMonitor(storage)

        await monitor._run_checkpoint()


class TestCheckHealth:
    @pytest.mark.asyncio
    async def test_check_health_memory_db_runs_without_error(self) -> None:
        storage = _make_storage()
        storage._db_path = ":memory:"
        storage._conn = None
        monitor = StorageHealthMonitor(storage)

        await monitor.check_health()

        storage.checkpoint_wal.assert_called_once()

    def test_set_metric_exception_does_not_propagate(self) -> None:
        bad_metric = MagicMock()
        bad_metric.set.side_effect = RuntimeError("prometheus error")
        monitor = StorageHealthMonitor(_make_storage())

        monitor._set_metric(bad_metric, 1.0, "bad_metric")


class TestStartStop:
    def test_stop_when_not_started_is_safe(self) -> None:
        monitor = StorageHealthMonitor(_make_storage())
        assert monitor._running is False
        monitor.stop()

    @pytest.mark.asyncio
    async def test_start_twice_does_not_create_second_task(self) -> None:
        monitor = StorageHealthMonitor(_make_storage(), interval_seconds=9999)
        monitor.start()
        task1 = monitor._task
        monitor.start()
        task2 = monitor._task
        assert task1 is task2
        monitor.stop()
