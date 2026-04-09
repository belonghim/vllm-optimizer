import asyncio
from collections.abc import AsyncIterator, Callable
from typing import cast

import pytest
from models.load_test import Benchmark, LatencyStats, LoadTestConfig, LoadTestResult, TpsStats
from models.sla import SlaEvaluationResult, SlaProfile, SlaThresholds, SlaVerdict
from pydantic import ValidationError
from services.storage import Storage


@pytest.fixture
async def storage() -> AsyncIterator[Storage]:
    s = Storage(":memory:")
    await s.initialize()
    yield s
    await s.close()


def _make_benchmark(
    *,
    benchmark_id: int = 1,
    name: str = "benchmark-1",
    timestamp: float = 1700000000.0,
    success: int = 990,
    failed: int = 10,
    p95_seconds: float = 0.4,
    tps_mean: float = 20.0,
) -> Benchmark:
    total = success + failed
    return Benchmark(
        id=benchmark_id,
        name=name,
        timestamp=timestamp,
        config=LoadTestConfig(
            endpoint="http://localhost:8000",
            model="OpenVINO/Phi-4-mini-instruct-int4-ov",
            total_requests=max(total, 1),
            concurrency=1,
        ),
        result=LoadTestResult(
            elapsed=1.0,
            total=total,
            total_requested=total,
            success=success,
            failed=failed,
            rps_actual=0.0,
            latency=LatencyStats(
                mean=p95_seconds, p50=p95_seconds, p95=p95_seconds, p99=p95_seconds, min=p95_seconds, max=p95_seconds
            ),
            ttft=LatencyStats(),
            tps=TpsStats(mean=tps_mean, total=tps_mean * max(total, 1)),
        ),
    )


def _evaluate(profile: SlaProfile, benchmarks: list[Benchmark]) -> list[SlaEvaluationResult]:
    from routers.sla import (
        evaluate_benchmarks_against_sla,  # pyright: ignore[reportMissingImports, reportUnknownVariableType]  # test env: backend/ added to sys.path at runtime
    )

    evaluate_fn = cast(
        Callable[[SlaProfile, list[Benchmark]], list[SlaEvaluationResult]],
        evaluate_benchmarks_against_sla,
    )
    return evaluate_fn(profile, benchmarks)


def _verdict_by_metric(result: SlaEvaluationResult, metric: str) -> SlaVerdict:
    return next(v for v in result.verdicts if v.metric == metric)


@pytest.mark.asyncio
async def test_evaluate_all_pass(storage: Storage) -> None:
    profile = SlaProfile(
        name="strict",
        thresholds=SlaThresholds(
            availability_min=99.0,
            p95_latency_max_ms=500.0,
            error_rate_max_pct=1.0,
        ),
    )
    benchmark = _make_benchmark(success=990, failed=10, p95_seconds=0.4, tps_mean=20.0)

    results = _evaluate(profile, [benchmark])

    assert len(results) == 1
    assert results[0].overall_pass is True
    assert all(v.status == "pass" for v in results[0].verdicts)
    assert all(v.pass_ is True for v in results[0].verdicts)


@pytest.mark.asyncio
async def test_evaluate_latency_fail(storage: Storage) -> None:
    profile = SlaProfile(
        name="latency-only",
        thresholds=SlaThresholds(p95_latency_max_ms=500.0),
    )
    benchmark = _make_benchmark(p95_seconds=0.6)

    results = _evaluate(profile, [benchmark])

    assert len(results) == 1
    assert results[0].overall_pass is False
    latency_verdict = _verdict_by_metric(results[0], "p95_latency")
    assert latency_verdict.status == "fail"
    assert latency_verdict.pass_ is False


@pytest.mark.asyncio
async def test_evaluate_availability_fail(storage: Storage) -> None:
    profile = SlaProfile(
        name="avail-only",
        thresholds=SlaThresholds(availability_min=99.9),
    )
    benchmark = _make_benchmark(success=950, failed=50)

    results = _evaluate(profile, [benchmark])

    assert len(results) == 1
    assert results[0].overall_pass is False
    availability_verdict = _verdict_by_metric(results[0], "availability")
    assert availability_verdict.status == "fail"
    assert availability_verdict.pass_ is False


@pytest.mark.asyncio
async def test_evaluate_error_rate_fail(storage: Storage) -> None:
    profile = SlaProfile(
        name="error-only",
        thresholds=SlaThresholds(error_rate_max_pct=0.1),
    )
    benchmark = _make_benchmark(success=990, failed=10)

    results = _evaluate(profile, [benchmark])

    assert len(results) == 1
    assert results[0].overall_pass is False
    error_verdict = _verdict_by_metric(results[0], "error_rate")
    assert error_verdict.status == "fail"
    assert error_verdict.pass_ is False


@pytest.mark.asyncio
async def test_evaluate_mean_e2e_latency_pass(storage: Storage) -> None:
    profile = SlaProfile(
        name="e2e-latency-pass",
        thresholds=SlaThresholds(mean_e2e_latency_max_ms=500.0),
    )
    benchmark = _make_benchmark(p95_seconds=0.3)
    benchmark.result.latency = LatencyStats(mean=0.3, p50=0.3, p95=0.3, p99=0.3, min=0.3, max=0.3)

    results = _evaluate(profile, [benchmark])

    assert len(results) == 1
    assert results[0].overall_pass is True
    e2e_verdict = _verdict_by_metric(results[0], "mean_e2e_latency")
    assert e2e_verdict.status == "pass"
    assert e2e_verdict.pass_ is True
    assert e2e_verdict.value == pytest.approx(300.0)


@pytest.mark.asyncio
async def test_evaluate_mean_e2e_latency_fail(storage: Storage) -> None:
    profile = SlaProfile(
        name="e2e-latency-fail",
        thresholds=SlaThresholds(mean_e2e_latency_max_ms=200.0),
    )
    benchmark = _make_benchmark(p95_seconds=0.3)
    benchmark.result.latency = LatencyStats(mean=0.3, p50=0.3, p95=0.3, p99=0.3, min=0.3, max=0.3)

    results = _evaluate(profile, [benchmark])

    assert len(results) == 1
    assert results[0].overall_pass is False
    e2e_verdict = _verdict_by_metric(results[0], "mean_e2e_latency")
    assert e2e_verdict.status == "fail"
    assert e2e_verdict.pass_ is False
    assert e2e_verdict.value == pytest.approx(300.0)


@pytest.mark.asyncio
async def test_evaluate_zero_requests(storage: Storage) -> None:
    profile = SlaProfile(
        name="zero-requests",
        thresholds=SlaThresholds(availability_min=99.9, p95_latency_max_ms=500.0),
    )
    benchmark = _make_benchmark(success=0, failed=0, p95_seconds=0.0)

    results = _evaluate(profile, [benchmark])

    assert len(results) == 1
    assert results[0].overall_pass is False
    assert len(results[0].verdicts) == 2
    assert all(v.status == "insufficient_data" for v in results[0].verdicts)
    assert all(v.pass_ is False for v in results[0].verdicts)


@pytest.mark.asyncio
async def test_evaluate_partial_thresholds(storage: Storage) -> None:
    profile = SlaProfile(
        name="partial",
        thresholds=SlaThresholds(p95_latency_max_ms=500.0),
    )
    benchmark = _make_benchmark(p95_seconds=0.3)

    results = _evaluate(profile, [benchmark])

    assert len(results) == 1
    assert len(results[0].verdicts) == 1
    assert results[0].verdicts[0].metric == "p95_latency"
    assert results[0].verdicts[0].status == "pass"
    assert results[0].overall_pass is True


@pytest.mark.asyncio
async def test_evaluate_no_benchmarks(storage: Storage) -> None:
    profile = SlaProfile(
        name="empty",
        thresholds=SlaThresholds(availability_min=99.0),
    )

    results = _evaluate(profile, [])

    assert results == []


@pytest.mark.asyncio
async def test_sla_profile_crud(storage: Storage) -> None:
    profile = SlaProfile(
        name="prod-sla",
        thresholds=SlaThresholds(
            availability_min=99.9,
            p95_latency_max_ms=500.0,
            error_rate_max_pct=0.5,
            mean_e2e_latency_max_ms=300.0,
        ),
    )

    saved = await storage.save_sla_profile(profile)
    assert saved.id is not None

    loaded = await storage.get_sla_profile(saved.id)
    assert loaded is not None
    assert loaded.id == saved.id
    assert loaded.name == "prod-sla"
    assert loaded.thresholds.availability_min == 99.9
    assert loaded.thresholds.p95_latency_max_ms == 500.0
    assert loaded.thresholds.error_rate_max_pct == 0.5
    assert loaded.thresholds.mean_e2e_latency_max_ms == 300.0


@pytest.mark.asyncio
async def test_thresholds_all_none_rejected(storage: Storage) -> None:
    with pytest.raises(ValidationError):
        SlaThresholds()


@pytest.mark.asyncio
async def test_thresholds_at_least_one_valid(storage: Storage) -> None:
    t = SlaThresholds(mean_e2e_latency_max_ms=300.0)
    assert t.mean_e2e_latency_max_ms == 300.0


@pytest.mark.asyncio
async def test_verdict_invalid_status_rejected(storage: Storage) -> None:
    with pytest.raises(ValidationError):
        SlaVerdict.model_validate({"metric": "x", "pass": True, "status": "invalid"})


@pytest.mark.asyncio
async def test_verdict_valid_statuses(storage: Storage) -> None:
    for status in ["pass", "fail", "insufficient_data", "skipped"]:
        v = SlaVerdict.model_validate({"metric": "x", "pass": status == "pass", "status": status})
        assert v.status == status


@pytest.mark.asyncio
async def test_evaluate_boundary_exact_threshold(storage: Storage) -> None:
    profile = SlaProfile(
        name="boundary",
        thresholds=SlaThresholds(availability_min=99.0),
    )
    benchmark = _make_benchmark(success=990, failed=10)
    results = _evaluate(profile, [benchmark])
    assert results[0].overall_pass is True
    assert _verdict_by_metric(results[0], "availability").status == "pass"


@pytest.mark.asyncio
async def test_evaluate_multi_benchmark_mixed(storage: Storage) -> None:
    profile = SlaProfile(
        name="multi",
        thresholds=SlaThresholds(p95_latency_max_ms=500.0),
    )
    b_pass1 = _make_benchmark(benchmark_id=1, name="b1", p95_seconds=0.3)
    b_pass2 = _make_benchmark(benchmark_id=2, name="b2", p95_seconds=0.4)
    b_fail = _make_benchmark(benchmark_id=3, name="b3", p95_seconds=0.6)
    results = _evaluate(profile, [b_pass1, b_pass2, b_fail])
    assert len(results) == 3
    assert results[0].overall_pass is True
    assert results[1].overall_pass is True
    assert results[2].overall_pass is False


@pytest.mark.asyncio
async def test_evaluate_benchmark_ids_excluded_when_not_passed(storage: Storage) -> None:
    profile = SlaProfile(
        name="excl",
        thresholds=SlaThresholds(p95_latency_max_ms=500.0),
    )
    results = _evaluate(profile, [])
    assert results == []


@pytest.mark.asyncio
async def test_sla_profile_update(storage: Storage) -> None:
    profile = SlaProfile(
        name="original",
        thresholds=SlaThresholds(availability_min=99.0),
    )
    saved = await storage.save_sla_profile(profile)
    assert saved.id is not None

    updated_profile = SlaProfile(
        name="updated",
        thresholds=SlaThresholds(availability_min=95.0, mean_e2e_latency_max_ms=300.0),
    )
    updated = await storage.update_sla_profile(saved.id, updated_profile)
    assert updated is not None
    assert updated.name == "updated"
    assert updated.thresholds.availability_min == 95.0
    assert updated.thresholds.mean_e2e_latency_max_ms == 300.0

    loaded = await storage.get_sla_profile(saved.id)
    assert loaded is not None
    assert loaded.name == "updated"


@pytest.mark.asyncio
async def test_sla_profile_delete(storage: Storage) -> None:
    profile = SlaProfile(
        name="to-delete",
        thresholds=SlaThresholds(mean_e2e_latency_max_ms=300.0),
    )
    saved = await storage.save_sla_profile(profile)
    assert saved.id is not None

    deleted = await storage.delete_sla_profile(saved.id)
    assert deleted is True

    loaded = await storage.get_sla_profile(saved.id)
    assert loaded is None


@pytest.mark.asyncio
async def test_sla_profile_list(storage: Storage) -> None:
    profiles = []
    for i in range(3):
        p = SlaProfile(
            name=f"profile-{i}",
            thresholds=SlaThresholds(mean_e2e_latency_max_ms=float(100 + i * 50)),
        )
        saved = await storage.save_sla_profile(p)
        profiles.append(saved)
        await asyncio.sleep(0.01)

    listed = await storage.list_sla_profiles()
    assert len(listed) >= 3
    our_profiles = [p for p in listed if p.name.startswith("profile-")]
    assert len(our_profiles) == 3
    timestamps = [p.created_at for p in our_profiles]
    assert timestamps == sorted(timestamps, reverse=True)


@pytest.mark.asyncio
async def test_create_profile_http_201(storage: Storage, monkeypatch: pytest.MonkeyPatch) -> None:
    from unittest.mock import patch

    from fastapi import FastAPI
    from routers.sla import router
    from starlette.testclient import TestClient

    with patch("routers.sla.storage", storage):
        app = FastAPI()
        app.include_router(router, prefix="/api/sla")
        client = TestClient(app)

        body = {
            "name": "Test Profile",
            "thresholds": {
                "availability_min": 99.9,
                "p95_latency_max_ms": None,
                "error_rate_max_pct": None,
                "mean_e2e_latency_max_ms": None,
            },
        }
        resp = client.post("/api/sla/profiles", json=body)
        assert resp.status_code == 201
        data = resp.json()
        assert data["id"] is not None
        assert data["name"] == "Test Profile"


@pytest.mark.asyncio
async def test_create_profile_http_422_no_thresholds(storage: Storage, monkeypatch: pytest.MonkeyPatch) -> None:
    from unittest.mock import patch

    from fastapi import FastAPI
    from routers.sla import router
    from starlette.testclient import TestClient

    with patch("routers.sla.storage", storage):
        app = FastAPI()
        app.include_router(router, prefix="/api/sla")
        client = TestClient(app)

        body = {
            "name": "Test Profile",
            "thresholds": {
                "availability_min": None,
                "p95_latency_max_ms": None,
                "error_rate_max_pct": None,
                "mean_e2e_latency_max_ms": None,
            },
        }
        resp = client.post("/api/sla/profiles", json=body)
        assert resp.status_code == 422


@pytest.mark.asyncio
async def test_evaluate_with_missing_benchmarks(storage: Storage, monkeypatch: pytest.MonkeyPatch) -> None:
    from unittest.mock import patch

    from fastapi import FastAPI
    from routers.sla import router
    from starlette.testclient import TestClient

    b = _make_benchmark(benchmark_id=1)
    saved_b = await storage.save_benchmark(b)
    real_id = saved_b.id

    missing_id = 9999
    profile = SlaProfile(
        name="missing-bench",
        thresholds=SlaThresholds(availability_min=99.0),
    )
    saved_profile = await storage.save_sla_profile(profile)

    with patch("routers.sla.storage", storage):
        app = FastAPI()
        app.include_router(router, prefix="/api/sla")
        client = TestClient(app)

        resp = client.post(
            "/api/sla/evaluate", json={"profile_id": saved_profile.id, "benchmark_ids": [real_id, missing_id]}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["warnings"]) == 1
        assert str(missing_id) in data["warnings"][0]


@pytest.mark.asyncio
async def test_evaluate_warnings_field_in_response(storage: Storage, monkeypatch: pytest.MonkeyPatch) -> None:
    from unittest.mock import patch

    from fastapi import FastAPI
    from routers.sla import router
    from starlette.testclient import TestClient

    b = _make_benchmark(benchmark_id=1)
    saved_b = await storage.save_benchmark(b)
    real_id = saved_b.id

    profile = SlaProfile(
        name="all-found",
        thresholds=SlaThresholds(availability_min=99.0),
    )
    saved_profile = await storage.save_sla_profile(profile)

    with patch("routers.sla.storage", storage):
        app = FastAPI()
        app.include_router(router, prefix="/api/sla")
        client = TestClient(app)

        resp = client.post("/api/sla/evaluate", json={"profile_id": saved_profile.id, "benchmark_ids": [real_id]})
        assert resp.status_code == 200
        data = resp.json()
        assert "warnings" in data
        assert data["warnings"] == []


@pytest.mark.asyncio
async def test_evaluate_profile_empty_benchmarks(storage: Storage, monkeypatch: pytest.MonkeyPatch) -> None:
    from unittest.mock import patch

    from fastapi import FastAPI
    from routers.sla import router
    from starlette.testclient import TestClient

    profile = SlaProfile(
        name="empty-benchmarks-eval",
        thresholds=SlaThresholds(availability_min=99.0),
    )
    saved_profile = await storage.save_sla_profile(profile)

    with patch("routers.sla.storage", storage):
        app = FastAPI()
        app.include_router(router, prefix="/api/sla")
        client = TestClient(app)

        resp = client.post("/api/sla/evaluate", json={"profile_id": saved_profile.id, "benchmark_ids": []})
        assert resp.status_code == 200
        data = resp.json()
        assert data["results"] == []
        assert data["warnings"] == []


@pytest.mark.asyncio
async def test_evaluate_mean_ttft_pass(storage: Storage) -> None:
    profile = SlaProfile(
        name="ttft-mean-pass",
        thresholds=SlaThresholds(mean_ttft_max_ms=500.0),
    )
    benchmark = _make_benchmark(success=990, failed=10, p95_seconds=0.4, tps_mean=20.0)
    benchmark.result.ttft = LatencyStats(mean=0.3, p50=0.3, p95=0.3, p99=0.3, min=0.3, max=0.3)

    results = _evaluate(profile, [benchmark])

    assert len(results) == 1
    assert results[0].overall_pass is True
    ttft_verdict = _verdict_by_metric(results[0], "ttft_mean")
    assert ttft_verdict.status == "pass"
    assert ttft_verdict.pass_ is True


@pytest.mark.asyncio
async def test_evaluate_mean_ttft_fail(storage: Storage) -> None:
    profile = SlaProfile(
        name="ttft-mean-fail",
        thresholds=SlaThresholds(mean_ttft_max_ms=200.0),
    )
    benchmark = _make_benchmark(success=990, failed=10, p95_seconds=0.4, tps_mean=20.0)
    benchmark.result.ttft = LatencyStats(mean=0.3, p50=0.3, p95=0.3, p99=0.3, min=0.3, max=0.3)

    results = _evaluate(profile, [benchmark])

    assert len(results) == 1
    assert results[0].overall_pass is False
    ttft_verdict = _verdict_by_metric(results[0], "ttft_mean")
    assert ttft_verdict.status == "fail"
    assert ttft_verdict.pass_ is False
    assert ttft_verdict.value == pytest.approx(300.0)


@pytest.mark.asyncio
async def test_evaluate_p95_ttft_pass(storage: Storage) -> None:
    profile = SlaProfile(
        name="ttft-p95-pass",
        thresholds=SlaThresholds(p95_ttft_max_ms=1000.0),
    )
    benchmark = _make_benchmark(success=990, failed=10, p95_seconds=0.4, tps_mean=20.0)
    benchmark.result.ttft = LatencyStats(mean=0.5, p50=0.5, p95=0.8, p99=0.9, min=0.5, max=0.9)

    results = _evaluate(profile, [benchmark])

    assert len(results) == 1
    assert results[0].overall_pass is True
    ttft_verdict = _verdict_by_metric(results[0], "ttft_p95")
    assert ttft_verdict.status == "pass"
    assert ttft_verdict.pass_ is True


@pytest.mark.asyncio
async def test_evaluate_p95_ttft_fail(storage: Storage) -> None:
    profile = SlaProfile(
        name="ttft-p95-fail",
        thresholds=SlaThresholds(p95_ttft_max_ms=500.0),
    )
    benchmark = _make_benchmark(success=990, failed=10, p95_seconds=0.4, tps_mean=20.0)
    benchmark.result.ttft = LatencyStats(mean=0.5, p50=0.5, p95=0.8, p99=0.9, min=0.5, max=0.9)

    results = _evaluate(profile, [benchmark])

    assert len(results) == 1
    assert results[0].overall_pass is False
    ttft_verdict = _verdict_by_metric(results[0], "ttft_p95")
    assert ttft_verdict.status == "fail"
    assert ttft_verdict.pass_ is False
    assert ttft_verdict.value == pytest.approx(800.0)


@pytest.mark.asyncio
async def test_ttft_zero_produces_skipped_verdict(storage: Storage) -> None:
    profile = SlaProfile(
        name="ttft-zero-skipped-verdict",
        thresholds=SlaThresholds(mean_ttft_max_ms=100.0, p95_ttft_max_ms=200.0),
    )
    benchmark = _make_benchmark(success=990, failed=10, p95_seconds=0.4, tps_mean=20.0)
    benchmark.result.ttft = LatencyStats(mean=0.0, p50=0.0, p95=0.0, p99=0.0, min=0.0, max=0.0)

    results = _evaluate(profile, [benchmark])

    assert len(results) == 1
    assert results[0].overall_pass is True
    ttft_mean_verdict = _verdict_by_metric(results[0], "ttft_mean")
    ttft_p95_verdict = _verdict_by_metric(results[0], "ttft_p95")
    assert ttft_mean_verdict.status == "skipped"
    assert ttft_mean_verdict.pass_ is True
    assert ttft_mean_verdict.value == 0
    assert ttft_p95_verdict.status == "skipped"
    assert ttft_p95_verdict.pass_ is True
    assert ttft_p95_verdict.value == 0


@pytest.mark.asyncio
async def test_overall_pass_ignores_skipped(storage: Storage) -> None:
    profile = SlaProfile(
        name="ttft-zero-overall-pass",
        thresholds=SlaThresholds(mean_ttft_max_ms=100.0),
    )
    benchmark = _make_benchmark(success=990, failed=10, p95_seconds=0.4, tps_mean=20.0)
    benchmark.result.ttft = LatencyStats(mean=0.0, p50=0.0, p95=0.0, p99=0.0, min=0.0, max=0.0)

    results = _evaluate(profile, [benchmark])

    assert len(results) == 1
    assert results[0].overall_pass is True
    assert len(results[0].verdicts) == 1
    assert results[0].verdicts[0].metric == "ttft_mean"
    assert results[0].verdicts[0].status == "skipped"
    assert results[0].verdicts[0].pass_ is True


@pytest.mark.asyncio
async def test_evaluate_tpot_mean_pass(storage: Storage) -> None:
    profile = SlaProfile(
        name="tpot-mean-pass",
        thresholds=SlaThresholds(mean_tpot_max_ms=50.0),
    )
    benchmark = _make_benchmark(success=990, failed=10, p95_seconds=0.4, tps_mean=20.0)
    benchmark.result.tpot = LatencyStats(mean=0.03, p50=0.03, p95=0.04, p99=0.05, min=0.02, max=0.05)

    results = _evaluate(profile, [benchmark])

    assert len(results) == 1
    assert results[0].overall_pass is True
    tpot_verdict = _verdict_by_metric(results[0], "tpot_mean")
    assert tpot_verdict.status == "pass"
    assert tpot_verdict.pass_ is True
    assert tpot_verdict.value == pytest.approx(30.0)


@pytest.mark.asyncio
async def test_evaluate_tpot_mean_fail(storage: Storage) -> None:
    profile = SlaProfile(
        name="tpot-mean-fail",
        thresholds=SlaThresholds(mean_tpot_max_ms=20.0),
    )
    benchmark = _make_benchmark(success=990, failed=10, p95_seconds=0.4, tps_mean=20.0)
    benchmark.result.tpot = LatencyStats(mean=0.03, p50=0.03, p95=0.04, p99=0.05, min=0.02, max=0.05)

    results = _evaluate(profile, [benchmark])

    assert len(results) == 1
    assert results[0].overall_pass is False
    tpot_verdict = _verdict_by_metric(results[0], "tpot_mean")
    assert tpot_verdict.status == "fail"
    assert tpot_verdict.pass_ is False
    assert tpot_verdict.value == pytest.approx(30.0)


@pytest.mark.asyncio
async def test_evaluate_tpot_mean_skipped_when_none(storage: Storage) -> None:
    profile = SlaProfile(
        name="tpot-mean-skipped",
        thresholds=SlaThresholds(mean_tpot_max_ms=50.0),
    )
    benchmark = _make_benchmark(success=990, failed=10, p95_seconds=0.4, tps_mean=20.0)
    benchmark.result.tpot = None

    results = _evaluate(profile, [benchmark])

    assert len(results) == 1
    assert results[0].overall_pass is True
    tpot_verdict = _verdict_by_metric(results[0], "tpot_mean")
    assert tpot_verdict.status == "skipped"
    assert tpot_verdict.pass_ is True


@pytest.mark.asyncio
async def test_evaluate_tpot_mean_skipped_when_zero(storage: Storage) -> None:
    profile = SlaProfile(
        name="tpot-mean-zero-skipped",
        thresholds=SlaThresholds(mean_tpot_max_ms=50.0),
    )
    benchmark = _make_benchmark(success=990, failed=10, p95_seconds=0.4, tps_mean=20.0)
    benchmark.result.tpot = LatencyStats(mean=0.0, p50=0.0, p95=0.0, p99=0.0, min=0.0, max=0.0)

    results = _evaluate(profile, [benchmark])

    assert len(results) == 1
    assert results[0].overall_pass is True
    tpot_verdict = _verdict_by_metric(results[0], "tpot_mean")
    assert tpot_verdict.status == "skipped"
    assert tpot_verdict.pass_ is True
    assert tpot_verdict.value == 0.0


@pytest.mark.asyncio
async def test_evaluate_tpot_p95_pass(storage: Storage) -> None:
    profile = SlaProfile(
        name="tpot-p95-pass",
        thresholds=SlaThresholds(p95_tpot_max_ms=100.0),
    )
    benchmark = _make_benchmark(success=990, failed=10, p95_seconds=0.4, tps_mean=20.0)
    benchmark.result.tpot = LatencyStats(mean=0.03, p50=0.03, p95=0.04, p99=0.05, min=0.02, max=0.05)

    results = _evaluate(profile, [benchmark])

    assert len(results) == 1
    assert results[0].overall_pass is True
    tpot_verdict = _verdict_by_metric(results[0], "tpot_p95")
    assert tpot_verdict.status == "pass"
    assert tpot_verdict.pass_ is True
    assert tpot_verdict.value == pytest.approx(40.0)


@pytest.mark.asyncio
async def test_evaluate_tpot_p95_fail(storage: Storage) -> None:
    profile = SlaProfile(
        name="tpot-p95-fail",
        thresholds=SlaThresholds(p95_tpot_max_ms=30.0),
    )
    benchmark = _make_benchmark(success=990, failed=10, p95_seconds=0.4, tps_mean=20.0)
    benchmark.result.tpot = LatencyStats(mean=0.03, p50=0.03, p95=0.04, p99=0.05, min=0.02, max=0.05)

    results = _evaluate(profile, [benchmark])

    assert len(results) == 1
    assert results[0].overall_pass is False
    tpot_verdict = _verdict_by_metric(results[0], "tpot_p95")
    assert tpot_verdict.status == "fail"
    assert tpot_verdict.pass_ is False
    assert tpot_verdict.value == pytest.approx(40.0)


@pytest.mark.asyncio
async def test_evaluate_tpot_p95_skipped_when_none(storage: Storage) -> None:
    profile = SlaProfile(
        name="tpot-p95-skipped",
        thresholds=SlaThresholds(p95_tpot_max_ms=50.0),
    )
    benchmark = _make_benchmark(success=990, failed=10, p95_seconds=0.4, tps_mean=20.0)
    benchmark.result.tpot = None

    results = _evaluate(profile, [benchmark])

    assert len(results) == 1
    assert results[0].overall_pass is True
    tpot_verdict = _verdict_by_metric(results[0], "tpot_p95")
    assert tpot_verdict.status == "skipped"
    assert tpot_verdict.pass_ is True


@pytest.mark.asyncio
async def test_evaluate_queue_time_mean_pass(storage: Storage) -> None:
    profile = SlaProfile(
        name="queue-time-mean-pass",
        thresholds=SlaThresholds(mean_queue_time_max_ms=100.0),
    )
    benchmark = _make_benchmark(success=990, failed=10, p95_seconds=0.4, tps_mean=20.0)
    benchmark.result.queue_time = LatencyStats(mean=0.05, p50=0.05, p95=0.08, p99=0.1, min=0.01, max=0.1)

    results = _evaluate(profile, [benchmark])

    assert len(results) == 1
    assert results[0].overall_pass is True
    queue_verdict = _verdict_by_metric(results[0], "queue_time_mean")
    assert queue_verdict.status == "pass"
    assert queue_verdict.pass_ is True
    assert queue_verdict.value == pytest.approx(50.0)


@pytest.mark.asyncio
async def test_evaluate_queue_time_mean_fail(storage: Storage) -> None:
    profile = SlaProfile(
        name="queue-time-mean-fail",
        thresholds=SlaThresholds(mean_queue_time_max_ms=30.0),
    )
    benchmark = _make_benchmark(success=990, failed=10, p95_seconds=0.4, tps_mean=20.0)
    benchmark.result.queue_time = LatencyStats(mean=0.05, p50=0.05, p95=0.08, p99=0.1, min=0.01, max=0.1)

    results = _evaluate(profile, [benchmark])

    assert len(results) == 1
    assert results[0].overall_pass is False
    queue_verdict = _verdict_by_metric(results[0], "queue_time_mean")
    assert queue_verdict.status == "fail"
    assert queue_verdict.pass_ is False
    assert queue_verdict.value == pytest.approx(50.0)


@pytest.mark.asyncio
async def test_evaluate_queue_time_mean_skipped_when_none(storage: Storage) -> None:
    profile = SlaProfile(
        name="queue-time-mean-skipped",
        thresholds=SlaThresholds(mean_queue_time_max_ms=100.0),
    )
    benchmark = _make_benchmark(success=990, failed=10, p95_seconds=0.4, tps_mean=20.0)
    benchmark.result.queue_time = None

    results = _evaluate(profile, [benchmark])

    assert len(results) == 1
    assert results[0].overall_pass is True
    queue_verdict = _verdict_by_metric(results[0], "queue_time_mean")
    assert queue_verdict.status == "skipped"
    assert queue_verdict.pass_ is True


@pytest.mark.asyncio
async def test_evaluate_queue_time_mean_skipped_when_zero(storage: Storage) -> None:
    profile = SlaProfile(
        name="queue-time-mean-zero-skipped",
        thresholds=SlaThresholds(mean_queue_time_max_ms=100.0),
    )
    benchmark = _make_benchmark(success=990, failed=10, p95_seconds=0.4, tps_mean=20.0)
    benchmark.result.queue_time = LatencyStats(mean=0.0, p50=0.0, p95=0.0, p99=0.0, min=0.0, max=0.0)

    results = _evaluate(profile, [benchmark])

    assert len(results) == 1
    assert results[0].overall_pass is True
    queue_verdict = _verdict_by_metric(results[0], "queue_time_mean")
    assert queue_verdict.status == "skipped"
    assert queue_verdict.pass_ is True
    assert queue_verdict.value == 0.0


@pytest.mark.asyncio
async def test_evaluate_queue_time_p95_pass(storage: Storage) -> None:
    profile = SlaProfile(
        name="queue-time-p95-pass",
        thresholds=SlaThresholds(p95_queue_time_max_ms=200.0),
    )
    benchmark = _make_benchmark(success=990, failed=10, p95_seconds=0.4, tps_mean=20.0)
    benchmark.result.queue_time = LatencyStats(mean=0.05, p50=0.05, p95=0.08, p99=0.1, min=0.01, max=0.1)

    results = _evaluate(profile, [benchmark])

    assert len(results) == 1
    assert results[0].overall_pass is True
    queue_verdict = _verdict_by_metric(results[0], "queue_time_p95")
    assert queue_verdict.status == "pass"
    assert queue_verdict.pass_ is True
    assert queue_verdict.value == pytest.approx(80.0)


@pytest.mark.asyncio
async def test_evaluate_queue_time_p95_fail(storage: Storage) -> None:
    profile = SlaProfile(
        name="queue-time-p95-fail",
        thresholds=SlaThresholds(p95_queue_time_max_ms=50.0),
    )
    benchmark = _make_benchmark(success=990, failed=10, p95_seconds=0.4, tps_mean=20.0)
    benchmark.result.queue_time = LatencyStats(mean=0.05, p50=0.05, p95=0.08, p99=0.1, min=0.01, max=0.1)

    results = _evaluate(profile, [benchmark])

    assert len(results) == 1
    assert results[0].overall_pass is False
    queue_verdict = _verdict_by_metric(results[0], "queue_time_p95")
    assert queue_verdict.status == "fail"
    assert queue_verdict.pass_ is False
    assert queue_verdict.value == pytest.approx(80.0)


@pytest.mark.asyncio
async def test_evaluate_queue_time_p95_skipped_when_none(storage: Storage) -> None:
    profile = SlaProfile(
        name="queue-time-p95-skipped",
        thresholds=SlaThresholds(p95_queue_time_max_ms=100.0),
    )
    benchmark = _make_benchmark(success=990, failed=10, p95_seconds=0.4, tps_mean=20.0)
    benchmark.result.queue_time = None

    results = _evaluate(profile, [benchmark])

    assert len(results) == 1
    assert results[0].overall_pass is True
    queue_verdict = _verdict_by_metric(results[0], "queue_time_p95")
    assert queue_verdict.status == "skipped"
    assert queue_verdict.pass_ is True
