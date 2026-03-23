"""
Storage Layer — aiosqlite 기반 비동기 SQLite CRUD 모듈

Provides persistent storage for:
- Benchmarks (load test results saved for comparison)
- Load test history (recent test runs)
- Tuner trials (Bayesian optimization results)
"""
import logging
import asyncio
import os
import shutil
import aiosqlite
from typing import Any, Optional, List
from datetime import datetime, timezone

from models.load_test import (
    Benchmark,
    BenchmarkMetadata,
    LoadTestConfig,
    LoadTestResult,
    TuningTrial,
)
from models.sla import SlaProfile, SlaThresholds

logger = logging.getLogger(__name__)


class Storage:
    """
    Async SQLite storage with WAL mode for concurrent reads.
    
    Default DB path is /data/app.db (PVC mount point).
    Use ':memory:' for testing.
    """

    def __init__(self, db_path: str = "/data/app.db") -> None:
        self._db_path = db_path
        self._conn: Optional[aiosqlite.Connection] = None

    async def initialize(self) -> None:
        """
        Initialize DB connection, enable WAL mode, and create tables.
        
        WAL mode allows concurrent reads while writing.
        busy_timeout prevents SQLITE_BUSY errors under contention.
        """
        max_attempts = 3
        last_error: Optional[Exception] = None

        for attempt in range(1, max_attempts + 1):
            db_exists = self._db_path != ":memory:" and await asyncio.to_thread(
                os.path.exists, self._db_path
            )

            try:
                self._conn = await aiosqlite.connect(self._db_path)
                self._conn.row_factory = aiosqlite.Row

                if db_exists:
                    integrity_result = "ok"
                    try:
                        cursor = await self._conn.execute("PRAGMA integrity_check")
                        row = await cursor.fetchone()
                        integrity_result = row[0] if row and row[0] else "unknown"
                    except Exception as integrity_error:
                        integrity_result = f"error: {integrity_error}"

                    if integrity_result != "ok":
                        logger.warning(
                            "[Storage] Integrity check failed for %s: %s",
                            self._db_path,
                            integrity_result,
                        )
                        await self._conn.close()
                        self._conn = None

                        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
                        backup_path = f"{self._db_path}.corrupted.{timestamp}"
                        try:
                            await asyncio.to_thread(shutil.move, self._db_path, backup_path)
                            logger.warning(
                                "[Storage] Backed up corrupted database to %s",
                                backup_path,
                            )
                        except Exception as backup_error:
                            logger.error(
                                "[Storage] Failed to backup corrupted database %s: %s",
                                self._db_path,
                                backup_error,
                            )
                            raise

                        continue

                # Enable WAL mode for better concurrency
                await self._conn.execute("PRAGMA journal_mode=WAL")
                # Set busy timeout to 5 seconds to handle contention
                await self._conn.execute("PRAGMA busy_timeout=5000")

                await self._create_tables()
                logger.info("[Storage] Initialized SQLite database at %s", self._db_path)
                return
            except Exception as e:
                last_error = e
                logger.error(
                    "[Storage] Failed to initialize database (attempt %s/%s): %s",
                    attempt,
                    max_attempts,
                    e,
                )

                if self._conn is not None:
                    try:
                        await self._conn.close()
                    except Exception:
                        pass
                    self._conn = None

                if attempt == max_attempts:
                    break

        assert last_error is not None
        raise last_error

    async def _create_tables(self) -> None:
        """Create tables if they don't exist."""
        assert self._conn is not None

        # Benchmarks table
        await self._conn.execute("""
            CREATE TABLE IF NOT EXISTS benchmarks (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                timestamp REAL NOT NULL,
                config_json TEXT NOT NULL,
                result_json TEXT NOT NULL
            )
        """)

        try:
            await self._conn.execute("ALTER TABLE benchmarks ADD COLUMN metadata_json TEXT DEFAULT NULL")
            await self._conn.commit()
        except Exception:
            pass

        # Load test history table
        await self._conn.execute("""
            CREATE TABLE IF NOT EXISTS load_test_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                test_id TEXT NOT NULL,
                config_json TEXT NOT NULL,
                result_json TEXT NOT NULL,
                timestamp REAL NOT NULL
            )
        """)

        # Tuner trials table
        await self._conn.execute("""
            CREATE TABLE IF NOT EXISTS tuner_trials (
                id INTEGER PRIMARY KEY,
                trial_id INTEGER NOT NULL,
                params_json TEXT NOT NULL,
                tps REAL NOT NULL,
                p99_latency REAL NOT NULL,
                score REAL NOT NULL,
                status TEXT NOT NULL,
                is_pareto_optimal INTEGER NOT NULL DEFAULT 0,
                pruned INTEGER NOT NULL DEFAULT 0
            )
        """)

        # Running state table
        await self._conn.execute("""
            CREATE TABLE IF NOT EXISTS running_state (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_type TEXT NOT NULL,
                started_at REAL NOT NULL,
                cleared_at REAL
            )
        """)

        # SLA profiles table
        await self._conn.execute("""
            CREATE TABLE IF NOT EXISTS sla_profiles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                model TEXT NOT NULL,
                thresholds_json TEXT NOT NULL,
                created_at REAL NOT NULL
            )
        """)

        await self._conn.commit()
        logger.debug("[Storage] Tables created successfully")

    async def close(self) -> None:
        """Close the database connection."""
        if self._conn is not None:
            try:
                await self._conn.close()
                self._conn = None
                logger.info("[Storage] Database connection closed")
            except Exception as e:
                logger.error("[Storage] Error closing database: %s", e)

    # ==================== Benchmark CRUD ====================

    async def save_benchmark(self, b: Benchmark) -> Benchmark:
        """
        Save a benchmark to the database.
        
        If id is None, auto-generates a new id.
        Returns the benchmark with id and timestamp set.
        """
        if self._conn is None:
            logger.error("[Storage] Cannot save benchmark: database not initialized")
            return b

        try:
            import time
            if b.timestamp is None:
                b.timestamp = time.time()

            config_json = b.config.model_dump_json()
            result_json = b.result.model_dump_json()
            metadata_json = b.metadata.model_dump_json() if b.metadata else None

            if b.id is None:
                # Insert new benchmark (auto-generate id)
                cursor = await self._conn.execute(
                    """
                    INSERT INTO benchmarks (name, timestamp, config_json, result_json, metadata_json)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (b.name, b.timestamp, config_json, result_json, metadata_json),
                )
                b.id = cursor.lastrowid
            else:
                # Insert with explicit id (upsert)
                await self._conn.execute(
                    """
                    INSERT OR REPLACE INTO benchmarks (id, name, timestamp, config_json, result_json, metadata_json)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (b.id, b.name, b.timestamp, config_json, result_json, metadata_json),
                )

            await self._conn.commit()
            logger.debug("[Storage] Saved benchmark id=%s name=%s", b.id, b.name)
            return b
        except Exception as e:
            logger.error("[Storage] Failed to save benchmark: %s", e)
            return b

    async def list_benchmarks(self) -> List[Benchmark]:
        """Get all saved benchmarks, ordered by timestamp descending."""
        if self._conn is None:
            logger.error("[Storage] Cannot list benchmarks: database not initialized")
            return []

        try:
            cursor = await self._conn.execute(
                "SELECT id, name, timestamp, config_json, result_json, metadata_json FROM benchmarks ORDER BY timestamp DESC"
            )
            rows = await cursor.fetchall()
            benchmarks: List[Benchmark] = []
            for row in rows:
                try:
                    config = LoadTestConfig.model_validate_json(row["config_json"])
                    result = LoadTestResult.model_validate_json(row["result_json"])
                    metadata = None
                    if row["metadata_json"]:
                        try:
                            metadata = BenchmarkMetadata.model_validate_json(row["metadata_json"])
                        except Exception:
                            metadata = None
                    benchmarks.append(Benchmark(
                        id=row["id"],
                        name=row["name"],
                        timestamp=row["timestamp"],
                        config=config,
                        result=result,
                        metadata=metadata,
                    ))
                except Exception as e:
                    logger.warning("[Storage] Failed to parse benchmark row %s: %s", row["id"], e)
            return benchmarks
        except Exception as e:
            logger.error("[Storage] Failed to list benchmarks: %s", e)
            return []

    async def get_benchmark(self, id: int) -> Optional[Benchmark]:
        """Get a single benchmark by id."""
        if self._conn is None:
            logger.error("[Storage] Cannot get benchmark: database not initialized")
            return None

        try:
            cursor = await self._conn.execute(
                "SELECT id, name, timestamp, config_json, result_json, metadata_json FROM benchmarks WHERE id = ?",
                (id,),
            )
            row = await cursor.fetchone()
            if row is None:
                return None

            config = LoadTestConfig.model_validate_json(row["config_json"])
            result = LoadTestResult.model_validate_json(row["result_json"])
            metadata = None
            if row["metadata_json"]:
                try:
                    metadata = BenchmarkMetadata.model_validate_json(row["metadata_json"])
                except Exception:
                    metadata = None
            return Benchmark(
                id=row["id"],
                name=row["name"],
                timestamp=row["timestamp"],
                config=config,
                result=result,
                metadata=metadata,
            )
        except Exception as e:
            logger.error("[Storage] Failed to get benchmark id=%s: %s", id, e)
            return None

    async def delete_benchmark(self, id: int) -> bool:
        """Delete a benchmark by id. Returns True if deleted, False otherwise."""
        if self._conn is None:
            logger.error("[Storage] Cannot delete benchmark: database not initialized")
            return False

        try:
            cursor = await self._conn.execute(
                "DELETE FROM benchmarks WHERE id = ?",
                (id,),
            )
            await self._conn.commit()
            deleted = cursor.rowcount > 0
            if deleted:
                logger.debug("[Storage] Deleted benchmark id=%s", id)
            return deleted
        except Exception as e:
            logger.error("[Storage] Failed to delete benchmark id=%s: %s", id, e)
            return False

    async def update_benchmark_metadata(
        self, benchmark_id: int, metadata: BenchmarkMetadata
    ) -> Optional[Benchmark]:
        if self._conn is None:
            logger.error("[Storage] Cannot update benchmark metadata: database not initialized")
            return None

        existing = await self.get_benchmark(benchmark_id)
        if existing is None:
            return None

        try:
            metadata_json = metadata.model_dump_json()
            await self._conn.execute(
                "UPDATE benchmarks SET metadata_json = ? WHERE id = ?",
                (metadata_json, benchmark_id),
            )
            await self._conn.commit()
            return await self.get_benchmark(benchmark_id)
        except Exception as e:
            logger.error("[Storage] Failed to update benchmark metadata id=%s: %s", benchmark_id, e)
            return None

    # ==================== Load Test History CRUD ====================

    async def save_load_test(self, entry: dict[str, Any]) -> None:
        """
        Save a load test history entry.
        
        Expected entry format:
        {
            "test_id": str,
            "config": dict (from LoadTestConfig.model_dump()),
            "result": dict (from LoadTestResult or raw dict),
            "timestamp": float
        }
        """
        if self._conn is None:
            logger.error("[Storage] Cannot save load test: database not initialized")
            return

        try:
            import json
            test_id = entry.get("test_id", "")
            config_json = json.dumps(entry.get("config", {}))
            result_json = json.dumps(entry.get("result", {}))
            timestamp = entry.get("timestamp", 0.0)

            await self._conn.execute(
                """
                INSERT INTO load_test_history (test_id, config_json, result_json, timestamp)
                VALUES (?, ?, ?, ?)
                """,
                (test_id, config_json, result_json, timestamp),
            )
            await self._conn.commit()
            logger.debug("[Storage] Saved load test history test_id=%s", test_id)
        except Exception as e:
            logger.error("[Storage] Failed to save load test history: %s", e)

    async def get_load_test_history(self, limit: int = 100) -> List[dict[str, Any]]:
        """Get recent load test history entries, ordered by timestamp descending."""
        if self._conn is None:
            logger.error("[Storage] Cannot get load test history: database not initialized")
            return []

        try:
            import json
            cursor = await self._conn.execute(
                """
                SELECT test_id, config_json, result_json, timestamp
                FROM load_test_history
                ORDER BY timestamp DESC
                LIMIT ?
                """,
                (limit,),
            )
            rows = await cursor.fetchall()
            history: List[dict[str, Any]] = []
            for row in rows:
                try:
                    history.append({
                        "test_id": row[0],
                        "config": json.loads(row[1]),
                        "result": json.loads(row[2]),
                        "timestamp": row[3],
                    })
                except Exception as e:
                    logger.warning("[Storage] Failed to parse load test row: %s", e)
            return history
        except Exception as e:
            logger.error("[Storage] Failed to get load test history: %s", e)
            return []

    # ==================== Tuner Trials CRUD ====================

    async def save_trial(self, t: TuningTrial) -> None:
        """Save or update a tuning trial."""
        if self._conn is None:
            logger.error("[Storage] Cannot save trial: database not initialized")
            return

        try:
            import json
            params_json = json.dumps(t.params)

            await self._conn.execute(
                """
                INSERT OR REPLACE INTO tuner_trials 
                (id, trial_id, params_json, tps, p99_latency, score, status, is_pareto_optimal, pruned)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    t.trial_id,  # Use trial_id as primary key
                    t.trial_id,
                    params_json,
                    t.tps,
                    t.p99_latency,
                    t.score,
                    t.status,
                    1 if t.is_pareto_optimal else 0,
                    1 if t.pruned else 0,
                ),
            )
            await self._conn.commit()
            logger.debug("[Storage] Saved trial id=%s status=%s", t.trial_id, t.status)
        except Exception as e:
            logger.error("[Storage] Failed to save trial: %s", e)

    async def get_trials(self) -> List[TuningTrial]:
        """Get all tuner trials, ordered by trial_id ascending."""
        if self._conn is None:
            logger.error("[Storage] Cannot get trials: database not initialized")
            return []

        try:
            import json
            cursor = await self._conn.execute(
                """
                SELECT trial_id, params_json, tps, p99_latency, score, status, is_pareto_optimal, pruned
                FROM tuner_trials
                ORDER BY trial_id ASC
                """
            )
            rows = await cursor.fetchall()
            trials: List[TuningTrial] = []
            for row in rows:
                try:
                    trials.append(TuningTrial(
                        trial_id=row[0],
                        params=json.loads(row[1]),
                        tps=row[2],
                        p99_latency=row[3],
                        score=row[4],
                        status=row[5],
                        is_pareto_optimal=bool(row[6]),
                        pruned=bool(row[7]),
                    ))
                except Exception as e:
                    logger.warning("[Storage] Failed to parse trial row %s: %s", row[0], e)
            return trials
        except Exception as e:
            logger.error("[Storage] Failed to get trials: %s", e)
            return []

    async def clear_trials(self) -> None:
        """Clear all tuner trials from the database."""
        if self._conn is None:
            logger.error("[Storage] Cannot clear trials: database not initialized")
            return

        try:
            await self._conn.execute("DELETE FROM tuner_trials")
            await self._conn.commit()
            logger.info("[Storage] Cleared all tuner trials")
        except Exception as e:
            logger.error("[Storage] Failed to clear trials: %s", e)

    # ==================== Prune Methods ====================

    async def prune_load_test_history(self, keep_count: int = 1000) -> int:
        """
        Delete old load test history records, keeping only the newest keep_count.

        Args:
            keep_count: Number of newest records to retain (default: 1000)

        Returns:
            Number of records deleted
        """
        if self._conn is None:
            logger.error("[Storage] Cannot prune load test history: database not initialized")
            return 0

        try:
            # Get the timestamp threshold: keep records newer than the keep_count-th newest
            cursor = await self._conn.execute(
                """
                SELECT timestamp FROM load_test_history
                ORDER BY timestamp DESC
                LIMIT 1 OFFSET ?
                """,
                (keep_count - 1,),
            )
            row = await cursor.fetchone()

            if row is None:
                # Not enough records to prune
                logger.debug("[Storage] No load test history to prune (count <= %s)", keep_count)
                return 0

            threshold = row[0]

            # Count records to be deleted
            count_cursor = await self._conn.execute(
                "SELECT COUNT(*) FROM load_test_history WHERE timestamp < ?",
                (threshold,),
            )
            count_row = await count_cursor.fetchone()
            delete_count = count_row[0] if count_row else 0

            if delete_count == 0:
                return 0

            await self._conn.execute(
                "DELETE FROM load_test_history WHERE timestamp < ?",
                (threshold,),
            )
            await self._conn.commit()
            logger.info("[Storage] Pruned %s load test history records (keep_count=%s)", delete_count, keep_count)
            return delete_count
        except Exception as e:
            logger.error("[Storage] Failed to prune load test history: %s", e)
            return 0

    async def prune_benchmarks(self, keep_count: int = 100) -> int:
        """
        Delete old benchmark records, keeping only the newest keep_count.

        Args:
            keep_count: Number of newest records to retain (default: 100)

        Returns:
            Number of records deleted
        """
        if self._conn is None:
            logger.error("[Storage] Cannot prune benchmarks: database not initialized")
            return 0

        try:
            # Get the timestamp threshold: keep records newer than the keep_count-th newest
            cursor = await self._conn.execute(
                """
                SELECT timestamp FROM benchmarks
                ORDER BY timestamp DESC
                LIMIT 1 OFFSET ?
                """,
                (keep_count - 1,),
            )
            row = await cursor.fetchone()

            if row is None:
                # Not enough records to prune
                logger.debug("[Storage] No benchmarks to prune (count <= %s)", keep_count)
                return 0

            threshold = row[0]

            # Count records to be deleted
            count_cursor = await self._conn.execute(
                "SELECT COUNT(*) FROM benchmarks WHERE timestamp < ?",
                (threshold,),
            )
            count_row = await count_cursor.fetchone()
            delete_count = count_row[0] if count_row else 0

            if delete_count == 0:
                return 0

            await self._conn.execute(
                "DELETE FROM benchmarks WHERE timestamp < ?",
                (threshold,),
            )
            await self._conn.commit()
            logger.info("[Storage] Pruned %s benchmark records (keep_count=%s)", delete_count, keep_count)
            return delete_count
        except Exception as e:
            logger.error("[Storage] Failed to prune benchmarks: %s", e)
            return 0

    async def checkpoint_wal(self) -> bool:
        """
        Execute PRAGMA wal_checkpoint(TRUNCATE) to checkpoint and truncate WAL file.

        This forces all WAL changes to be written to the main database file
        and truncates the WAL file to zero bytes, preventing unbounded growth.

        Returns:
            True if checkpoint succeeded, False otherwise.
        """
        if self._conn is None:
            logger.error("[Storage] Cannot checkpoint WAL: database not initialized")
            return False

        try:
            cursor = await self._conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            row = await cursor.fetchone()
            if row:
                wal_mode, pages_written, pages_moved = row
                logger.info(
                    "[Storage] WAL checkpoint completed: "
                    "mode=%s pages_written=%s pages_moved=%s",
                    wal_mode,
                    pages_written,
                    pages_moved,
                )
            return True
        except Exception as e:
            logger.error("[Storage] Failed to checkpoint WAL: %s", e)
            return False

    # ==================== Running State Methods ====================

    async def set_running(self, task_type: str) -> int:
        """
        Record that a task is running.

        Args:
            task_type: Type of task (e.g., "tuner", "load_test")

        Returns:
            Row ID of the inserted record
        """
        if self._conn is None:
            logger.error("[Storage] Cannot set running: database not initialized")
            return -1

        try:
            started_at = datetime.now(timezone.utc).timestamp()
            cursor = await self._conn.execute(
                """
                INSERT INTO running_state (task_type, started_at, cleared_at)
                VALUES (?, ?, NULL)
                """,
                (task_type, started_at),
            )
            await self._conn.commit()
            row_id = int(cursor.lastrowid) if cursor.lastrowid is not None else -1
            logger.debug("[Storage] Set running: task_type=%s row_id=%s", task_type, row_id)
            return row_id
        except Exception as e:
            logger.error("[Storage] Failed to set running: %s", e)
            return -1

    async def clear_running(self, row_id: int) -> None:
        """
        Mark a running task as cleared.

        Args:
            row_id: Row ID returned from set_running()
        """
        if self._conn is None:
            logger.error("[Storage] Cannot clear running: database not initialized")
            return

        try:
            cleared_at = datetime.now(timezone.utc).timestamp()
            await self._conn.execute(
                """
                UPDATE running_state
                SET cleared_at = ?
                WHERE id = ?
                """,
                (cleared_at, row_id),
            )
            await self._conn.commit()
            logger.debug("[Storage] Cleared running: row_id=%s", row_id)
        except Exception as e:
            logger.error("[Storage] Failed to clear running: %s", e)

    async def get_interrupted_runs(self) -> List[dict[str, Any]]:
        """
        Get all interrupted runs (started but not cleared).

        Returns:
            List of dicts with keys: id, task_type, started_at
        """
        if self._conn is None:
            logger.error("[Storage] Cannot get interrupted runs: database not initialized")
            return []

        try:
            cursor = await self._conn.execute(
                """
                SELECT id, task_type, started_at
                FROM running_state
                WHERE cleared_at IS NULL
                ORDER BY started_at DESC
                """
            )
            rows = await cursor.fetchall()
            result: List[dict[str, Any]] = []
            for row in rows:
                result.append({
                    "id": row[0],
                    "task_type": row[1],
                    "started_at": row[2],
                })
            logger.debug("[Storage] Retrieved %s interrupted runs", len(result))
            return result
        except Exception as e:
            logger.error("[Storage] Failed to get interrupted runs: %s", e)
            return []

    async def get_all_running(self) -> List[dict[str, Any]]:
        """
        Get all uncleared running_state rows (for shutdown cleanup).

        Returns:
            List of dicts with keys: id, task_type, started_at
        """
        if self._conn is None:
            logger.error("[Storage] Cannot get all running: database not initialized")
            return []

        try:
            cursor = await self._conn.execute(
                """
                SELECT id, task_type, started_at
                FROM running_state
                WHERE cleared_at IS NULL
                """
            )
            rows = await cursor.fetchall()
            result: List[dict[str, Any]] = []
            for row in rows:
                result.append({
                    "id": row[0],
                    "task_type": row[1],
                    "started_at": row[2],
                })
            logger.debug("[Storage] Retrieved %s uncleared running rows", len(result))
            return result
        except Exception as e:
            logger.warning("[Storage] get_all_running failed: %s", e)
            return []

    # ==================== SLA Profiles CRUD ====================

    async def save_sla_profile(self, profile: SlaProfile) -> SlaProfile:
        """Save an SLA profile to the database."""
        if self._conn is None:
            logger.error("[Storage] Cannot save SLA profile: database not initialized")
            return profile

        try:
            import time
            created_at = time.time()
            thresholds_json = profile.thresholds.model_dump_json()
            cursor = await self._conn.execute(
                "INSERT INTO sla_profiles (name, model, thresholds_json, created_at) VALUES (?, ?, ?, ?)",
                (profile.name, profile.model, thresholds_json, created_at),
            )
            profile_id = cursor.lastrowid
            await self._conn.commit()
            logger.debug("[Storage] Saved SLA profile id=%s name=%s", profile_id, profile.name)
            return SlaProfile(
                id=profile_id,
                name=profile.name,
                model=profile.model,
                thresholds=profile.thresholds,
                created_at=created_at,
            )
        except Exception as e:
            logger.error("[Storage] Failed to save SLA profile: %s", e)
            return profile

    async def list_sla_profiles(self) -> List[SlaProfile]:
        """Get all saved SLA profiles, ordered by created_at descending."""
        if self._conn is None:
            logger.error("[Storage] Cannot list SLA profiles: database not initialized")
            return []

        try:
            cursor = await self._conn.execute(
                "SELECT id, name, model, thresholds_json, created_at FROM sla_profiles ORDER BY created_at DESC"
            )
            rows = await cursor.fetchall()
            profiles: List[SlaProfile] = []
            for row in rows:
                try:
                    thresholds = SlaThresholds.model_validate_json(row[3])
                    profiles.append(SlaProfile(
                        id=row[0],
                        name=row[1],
                        model=row[2],
                        thresholds=thresholds,
                        created_at=row[4],
                    ))
                except Exception as e:
                    logger.warning("[Storage] Failed to parse SLA profile row %s: %s", row[0], e)
            return profiles
        except Exception as e:
            logger.error("[Storage] Failed to list SLA profiles: %s", e)
            return []

    async def get_sla_profile(self, profile_id: int) -> Optional[SlaProfile]:
        """Get a single SLA profile by id."""
        if self._conn is None:
            logger.error("[Storage] Cannot get SLA profile: database not initialized")
            return None

        try:
            cursor = await self._conn.execute(
                "SELECT id, name, model, thresholds_json, created_at FROM sla_profiles WHERE id = ?",
                (profile_id,),
            )
            row = await cursor.fetchone()
            if row is None:
                return None

            thresholds = SlaThresholds.model_validate_json(row[3])
            return SlaProfile(
                id=row[0],
                name=row[1],
                model=row[2],
                thresholds=thresholds,
                created_at=row[4],
            )
        except Exception as e:
            logger.error("[Storage] Failed to get SLA profile id=%s: %s", profile_id, e)
            return None

    async def update_sla_profile(self, profile_id: int, profile: SlaProfile) -> Optional[SlaProfile]:
        """Update an SLA profile by id."""
        if self._conn is None:
            logger.error("[Storage] Cannot update SLA profile: database not initialized")
            return None

        try:
            existing = await self.get_sla_profile(profile_id)
            if existing is None:
                return None

            thresholds_json = profile.thresholds.model_dump_json()
            await self._conn.execute(
                "UPDATE sla_profiles SET name = ?, model = ?, thresholds_json = ? WHERE id = ?",
                (profile.name, profile.model, thresholds_json, profile_id),
            )
            await self._conn.commit()
            logger.debug("[Storage] Updated SLA profile id=%s", profile_id)
            return SlaProfile(
                id=profile_id,
                name=profile.name,
                model=profile.model,
                thresholds=profile.thresholds,
                created_at=existing.created_at,
            )
        except Exception as e:
            logger.error("[Storage] Failed to update SLA profile id=%s: %s", profile_id, e)
            return None

    async def delete_sla_profile(self, profile_id: int) -> bool:
        """Delete an SLA profile by id. Returns True if deleted, False otherwise."""
        if self._conn is None:
            logger.error("[Storage] Cannot delete SLA profile: database not initialized")
            return False

        try:
            existing = await self.get_sla_profile(profile_id)
            if existing is None:
                return False

            cursor = await self._conn.execute(
                "DELETE FROM sla_profiles WHERE id = ?",
                (profile_id,),
            )
            await self._conn.commit()
            deleted = cursor.rowcount > 0
            if deleted:
                logger.debug("[Storage] Deleted SLA profile id=%s", profile_id)
            return deleted
        except Exception as e:
            logger.error("[Storage] Failed to delete SLA profile id=%s: %s", profile_id, e)
            return False


# Use `from services.shared import storage` instead.
