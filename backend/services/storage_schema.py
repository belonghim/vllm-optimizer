"""SQLite DDL extracted from Storage.

Module-level async functions taking the aiosqlite connection as first argument.
Storage._create_* methods delegate here; tests call the methods, not these functions.
"""

import logging
import sqlite3

import aiosqlite

logger = logging.getLogger(__name__)


async def _create_benchmark_tables(db: aiosqlite.Connection) -> None:
    await db.execute("""
        CREATE TABLE IF NOT EXISTS benchmarks (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            timestamp REAL NOT NULL,
            config_json TEXT NOT NULL,
            result_json TEXT NOT NULL
        )
    """)
    try:
        await db.execute("ALTER TABLE benchmarks ADD COLUMN metadata_json TEXT DEFAULT NULL")
        await db.commit()
    except sqlite3.OperationalError:  # intentional: column already exists → migration is a no-op
        pass


async def _create_load_test_tables(db: aiosqlite.Connection) -> None:
    await db.execute("""
        CREATE TABLE IF NOT EXISTS load_test_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            test_id TEXT NOT NULL,
            config_json TEXT NOT NULL,
            result_json TEXT NOT NULL,
            timestamp REAL NOT NULL
        )
    """)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS running_state (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_type TEXT NOT NULL,
            started_at REAL NOT NULL,
            cleared_at REAL
        )
    """)


async def _create_sla_tables(db: aiosqlite.Connection) -> None:
    await db.execute("""
        CREATE TABLE IF NOT EXISTS sla_profiles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            thresholds_json TEXT NOT NULL,
            created_at REAL NOT NULL
        )
    """)
    # Migration: remove legacy 'model' column from sla_profiles
    try:
        cursor = await db.execute("PRAGMA table_info(sla_profiles)")
        cols = [row[1] for row in await cursor.fetchall()]
        await cursor.close()  # close before DDL to release read lock
        if "model" in cols:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS sla_profiles_v2 (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    benchmark_ids_json TEXT NOT NULL DEFAULT '[]',
                    thresholds_json TEXT NOT NULL,
                    created_at REAL NOT NULL
                )
            """)
            await db.execute("""
                INSERT INTO sla_profiles_v2 (id, name, benchmark_ids_json, thresholds_json, created_at)
                SELECT id, name, COALESCE(benchmark_ids_json, '[]'), thresholds_json, created_at
                FROM sla_profiles
            """)
            await db.execute("DROP TABLE sla_profiles")
            await db.execute("ALTER TABLE sla_profiles_v2 RENAME TO sla_profiles")
            await db.commit()
            logger.info("[Storage] Migrated sla_profiles: removed legacy 'model' column")
    except sqlite3.OperationalError as e:  # intentional: fail-open, schema migration must not block app start
        logger.warning("[Storage] sla_profiles model column migration failed: %s", e)

    try:
        cursor = await db.execute("PRAGMA table_info(sla_profiles)")
        cols = [row[1] for row in await cursor.fetchall()]
        await cursor.close()  # close before DDL to release read lock
        if "benchmark_ids_json" in cols:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS sla_profiles_v2 (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    thresholds_json TEXT NOT NULL,
                    created_at REAL NOT NULL
                )
            """)
            await db.execute("""
                INSERT INTO sla_profiles_v2 (id, name, thresholds_json, created_at)
                SELECT id, name, thresholds_json, created_at FROM sla_profiles
            """)
            await db.execute("DROP TABLE sla_profiles")
            await db.execute("ALTER TABLE sla_profiles_v2 RENAME TO sla_profiles")
            await db.commit()
            logger.info("[Storage] Migrated sla_profiles: removed benchmark_ids_json column")
    except sqlite3.OperationalError as e:  # intentional: fail-open, schema migration must not block app start
        logger.warning("[Storage] sla_profiles benchmark_ids_json migration failed: %s", e)


async def _create_tuner_tables(db: aiosqlite.Connection) -> None:
    await db.execute("""
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
    try:
        await db.execute("ALTER TABLE tuner_trials ADD COLUMN failure_json TEXT DEFAULT NULL")
        await db.commit()
    except sqlite3.OperationalError:  # intentional: column already exists → migration is a no-op
        pass
    await db.execute("""
        CREATE TABLE IF NOT EXISTS tuning_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp REAL NOT NULL,
            objective TEXT NOT NULL,
            n_trials INTEGER NOT NULL,
            best_tps REAL,
            best_p99 REAL,
            best_score REAL,
            trials_json TEXT NOT NULL,
            importance_json TEXT NOT NULL,
            best_params_json TEXT DEFAULT ''
        )
    """)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS sweep_history (
            sweep_id TEXT PRIMARY KEY,
            timestamp REAL NOT NULL,
            config_json TEXT NOT NULL,
            result_json TEXT NOT NULL
        )
    """)


async def _create_target_tables(db: aiosqlite.Connection) -> None:
    await db.execute("""
        CREATE TABLE IF NOT EXISTS target_saved (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            targets_json TEXT NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
