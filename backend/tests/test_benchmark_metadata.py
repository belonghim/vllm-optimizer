import os
import tempfile

import aiosqlite
import pytest

from models.load_test import (
    Benchmark,
    BenchmarkMetadata,
    LatencyStats,
    LoadTestConfig,
    LoadTestResult,
    TpsStats,
)
from services.storage import Storage


@pytest.fixture
async def storage():
    s = Storage(":memory:")
    await s.initialize()
    yield s
    await s.close()


def _make_benchmark(*, metadata: BenchmarkMetadata | None = None) -> Benchmark:
    return Benchmark(
        name="benchmark-with-metadata",
        config=LoadTestConfig(
            endpoint="http://localhost:8000",
            model="test-model",
            total_requests=10,
            concurrency=2,
        ),
        result=LoadTestResult(
            elapsed=1.0,
            total=10,
            success=10,
            failed=0,
            rps_actual=10.0,
            latency=LatencyStats(mean=0.1, p50=0.1, p95=0.2, p99=0.3, min=0.05, max=0.5),
            ttft=LatencyStats(mean=0.05, p50=0.05, p95=0.08, p99=0.1, min=0.01, max=0.2),
            tps=TpsStats(mean=100.0, total=1000.0),
        ),
        metadata=metadata,
    )


def test_metadata_model_all_optional():
    metadata = BenchmarkMetadata()

    assert metadata.model_identifier is None
    assert metadata.hardware_type is None
    assert metadata.runtime is None
    assert metadata.vllm_version is None
    assert metadata.replica_count is None
    assert metadata.notes is None
    assert metadata.extra == {}


def test_metadata_model_with_values():
    metadata = BenchmarkMetadata(
        model_identifier="llm-ov",
        hardware_type="CPU",
        runtime="OpenVINO",
        vllm_version="0.8.0",
        replica_count=2,
        notes="baseline run",
        extra={"cluster": "dev", "owner": "qa"},
    )

    payload = metadata.model_dump_json()
    parsed = BenchmarkMetadata.model_validate_json(payload)

    assert parsed.model_identifier == "llm-ov"
    assert parsed.hardware_type == "CPU"
    assert parsed.runtime == "OpenVINO"
    assert parsed.vllm_version == "0.8.0"
    assert parsed.replica_count == 2
    assert parsed.notes == "baseline run"
    assert parsed.extra == {"cluster": "dev", "owner": "qa"}


@pytest.mark.asyncio
async def test_benchmark_with_metadata_roundtrip(storage):
    source = _make_benchmark(
        metadata=BenchmarkMetadata(
            model_identifier="llm-ov",
            hardware_type="CPU",
            runtime="OpenVINO",
            vllm_version="0.8.0",
            replica_count=1,
            notes="first save",
            extra={"env": "dev"},
        )
    )

    saved = await storage.save_benchmark(source)
    assert saved.id is not None

    loaded = await storage.get_benchmark(saved.id)
    assert loaded is not None
    assert loaded.metadata is not None
    assert loaded.metadata.model_identifier == "llm-ov"
    assert loaded.metadata.runtime == "OpenVINO"
    assert loaded.metadata.extra == {"env": "dev"}


@pytest.mark.asyncio
async def test_benchmark_without_metadata_backward_compat(storage):
    source = _make_benchmark(metadata=None)
    saved = await storage.save_benchmark(source)
    assert saved.id is not None

    loaded = await storage.get_benchmark(saved.id)
    assert loaded is not None
    assert loaded.metadata is None


@pytest.mark.asyncio
async def test_schema_migration_adds_column():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        conn = await aiosqlite.connect(db_path)
        await conn.execute(
            """
            CREATE TABLE benchmarks (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                timestamp REAL NOT NULL,
                config_json TEXT NOT NULL,
                result_json TEXT NOT NULL
            )
            """
        )
        await conn.commit()
        await conn.close()

        storage = Storage(db_path)
        await storage.initialize()

        assert storage._conn is not None
        cursor = await storage._conn.execute("PRAGMA table_info(benchmarks)")
        rows = await cursor.fetchall()
        columns = [row[1] for row in rows]
        assert "metadata_json" in columns

        await storage.close()
    finally:
        for suffix in ["", "-wal", "-shm"]:
            path = db_path + suffix
            if os.path.exists(path):
                os.unlink(path)


@pytest.mark.asyncio
async def test_metadata_json_parse_failure_fallback(storage):
    assert storage._conn is not None

    source = _make_benchmark(metadata=None)
    config_json = source.config.model_dump_json()
    result_json = source.result.model_dump_json()

    await storage._conn.execute(
        """
        INSERT INTO benchmarks (id, name, timestamp, config_json, result_json, metadata_json)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (123, source.name, 1000.0, config_json, result_json, "{invalid-json"),
    )
    await storage._conn.commit()

    loaded = await storage.get_benchmark(123)
    assert loaded is not None
    assert loaded.metadata is None

    listed = await storage.list_benchmarks()
    assert len(listed) == 1
    assert listed[0].metadata is None
