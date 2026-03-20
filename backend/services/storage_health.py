import asyncio
import logging
import os
import shutil
from datetime import datetime
from typing import Protocol

from metrics.storage_metrics import (
    storage_benchmark_count,
    storage_db_size_bytes,
    storage_last_checkpoint_timestamp,
    storage_load_test_count,
    storage_prune_total,
    storage_wal_size_bytes,
)
from services.storage import Storage

logger = logging.getLogger(__name__)


class SettableMetric(Protocol):
    def set(self, value: float) -> None:
        ...


class StorageHealthMonitor:
    def __init__(
        self,
        storage: Storage,
        interval_seconds: int = 300,
        warning_threshold: float = 0.8,
        prune_threshold: float = 0.9,
        benchmark_keep_count: int = 100,
        load_test_keep_count: int = 1000,
        capacity_bytes: int | None = None,
    ) -> None:
        self._storage = storage
        self._interval_seconds = interval_seconds
        self._warning_threshold = warning_threshold
        self._prune_threshold = prune_threshold
        self._benchmark_keep_count = benchmark_keep_count
        self._load_test_keep_count = load_test_keep_count
        env_capacity = os.getenv("STORAGE_CAPACITY_BYTES", "").strip()
        self._capacity_bytes = capacity_bytes
        if self._capacity_bytes is None and env_capacity.isdigit():
            self._capacity_bytes = int(env_capacity)
        self._task: asyncio.Task[None] | None = None
        self._running = False

    def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        self._running = True
        try:
            self._task = asyncio.create_task(self._monitor_loop())
            logger.info("[StorageHealthMonitor] Started background monitor")
        except RuntimeError as e:
            self._running = False
            self._task = None
            logger.error("[StorageHealthMonitor] Failed to start background monitor: %s", e)

    def stop(self) -> None:
        self._running = False
        if self._task is not None and not self._task.done():
            self._task.cancel()
            logger.info("[StorageHealthMonitor] Stop requested")

    async def check_health(self) -> None:
        db_path = getattr(self._storage, "_db_path", os.getenv("STORAGE_PATH", "/data/app.db"))

        db_size, wal_size = await self._collect_file_sizes(db_path)
        self._set_metric(storage_db_size_bytes, float(db_size), "storage_db_size_bytes")
        self._set_metric(storage_wal_size_bytes, float(wal_size), "storage_wal_size_bytes")

        load_test_count, benchmark_count = await self._collect_record_counts()
        self._set_metric(storage_load_test_count, float(load_test_count), "storage_load_test_count")
        self._set_metric(storage_benchmark_count, float(benchmark_count), "storage_benchmark_count")

        await self._check_capacity_and_prune_if_needed(db_size=db_size, wal_size=wal_size, db_path=db_path)
        await self._run_checkpoint()

    async def _monitor_loop(self) -> None:
        try:
            while self._running:
                try:
                    await self.check_health()
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    logger.error("[StorageHealthMonitor] Health check failed: %s", e)

                await asyncio.sleep(self._interval_seconds)
        except asyncio.CancelledError:
            logger.info("[StorageHealthMonitor] Background monitor cancelled")
        finally:
            self._running = False

    async def _collect_file_sizes(self, db_path: str) -> tuple[int, int]:
        if db_path == ":memory:":
            return 0, 0

        db_size = 0
        wal_size = 0
        wal_path = f"{db_path}-wal"

        try:
            if await asyncio.to_thread(os.path.exists, db_path):
                db_size = await asyncio.to_thread(os.path.getsize, db_path)
        except Exception as e:
            logger.error("[StorageHealthMonitor] Failed to read DB size: %s", e)

        try:
            if await asyncio.to_thread(os.path.exists, wal_path):
                wal_size = await asyncio.to_thread(os.path.getsize, wal_path)
        except Exception as e:
            logger.error("[StorageHealthMonitor] Failed to read WAL size: %s", e)

        return db_size, wal_size

    async def _collect_record_counts(self) -> tuple[int, int]:
        conn = getattr(self._storage, "_conn", None)
        if conn is None:
            logger.error("[StorageHealthMonitor] Cannot collect record counts: database not initialized")
            return 0, 0

        load_test_count = 0
        benchmark_count = 0

        try:
            cursor = await conn.execute("SELECT COUNT(*) FROM load_test_history")
            row = await cursor.fetchone()
            load_test_count = int(row[0]) if row and row[0] is not None else 0
        except Exception as e:
            logger.error("[StorageHealthMonitor] Failed to count load_test_history: %s", e)

        try:
            cursor = await conn.execute("SELECT COUNT(*) FROM benchmarks")
            row = await cursor.fetchone()
            benchmark_count = int(row[0]) if row and row[0] is not None else 0
        except Exception as e:
            logger.error("[StorageHealthMonitor] Failed to count benchmarks: %s", e)

        return load_test_count, benchmark_count

    async def _check_capacity_and_prune_if_needed(self, db_size: int, wal_size: int, db_path: str) -> None:
        used_bytes = db_size + wal_size
        capacity_bytes = await self._resolve_capacity_bytes(db_path)
        if capacity_bytes <= 0:
            return

        usage_ratio = used_bytes / capacity_bytes
        usage_percent = usage_ratio * 100.0

        if usage_ratio >= self._prune_threshold:
            logger.warning(
                "[StorageHealthMonitor] Storage usage reached %.2f%% (>= %.0f%%). Running auto-prune.",
                usage_percent,
                self._prune_threshold * 100,
            )
            await self._run_auto_prune()
            return

        if usage_ratio >= self._warning_threshold:
            logger.warning(
                "[StorageHealthMonitor] Storage usage reached %.2f%% (>= %.0f%% warning threshold)",
                usage_percent,
                self._warning_threshold * 100,
            )

    async def _resolve_capacity_bytes(self, db_path: str) -> int:
        if self._capacity_bytes is not None:
            return self._capacity_bytes

        if db_path == ":memory:":
            return 0

        target_path = db_path
        try:
            if not await asyncio.to_thread(os.path.exists, target_path):
                target_path = os.path.dirname(db_path) or "."
            usage = await asyncio.to_thread(shutil.disk_usage, target_path)
            return int(usage.total)
        except Exception as e:
            logger.error("[StorageHealthMonitor] Failed to resolve storage capacity: %s", e)
            return 0

    async def _run_auto_prune(self) -> None:
        pruned_total = 0

        try:
            pruned_benchmarks = await self._storage.prune_benchmarks(keep_count=self._benchmark_keep_count)
            pruned_total += int(pruned_benchmarks)
        except Exception as e:
            logger.error("[StorageHealthMonitor] Failed to prune benchmarks: %s", e)

        try:
            pruned_history = await self._storage.prune_load_test_history(keep_count=self._load_test_keep_count)
            pruned_total += int(pruned_history)
        except Exception as e:
            logger.error("[StorageHealthMonitor] Failed to prune load test history: %s", e)

        if pruned_total > 0:
            try:
                storage_prune_total.inc(pruned_total)
            except Exception as e:
                logger.error("[StorageHealthMonitor] Failed to update storage_prune_total metric: %s", e)

    async def _run_checkpoint(self) -> None:
        checkpoint_ok = False
        try:
            checkpoint_ok = await self._storage.checkpoint_wal()
        except Exception as e:
            logger.error("[StorageHealthMonitor] WAL checkpoint execution failed: %s", e)

        if checkpoint_ok:
            try:
                storage_last_checkpoint_timestamp.set(datetime.utcnow().timestamp())
            except Exception as e:
                logger.error(
                    "[StorageHealthMonitor] Failed to update storage_last_checkpoint_timestamp metric: %s",
                    e,
                )

    def _set_metric(self, metric: SettableMetric, value: float, metric_name: str) -> None:
        try:
            metric.set(value)
        except Exception as e:
            logger.error("[StorageHealthMonitor] Failed to set %s: %s", metric_name, e)
