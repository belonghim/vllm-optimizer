from collections.abc import AsyncIterator, Callable
from typing import cast

import pytest
from pydantic import ValidationError

from models.load_test import Benchmark, LatencyStats, LoadTestConfig, LoadTestResult, TpsStats
from models.sla import SlaEvaluationResult, SlaProfile, SlaThresholds, SlaVerdict
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
            model="llm-ov",
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
            latency=LatencyStats(mean=p95_seconds, p50=p95_seconds, p95=p95_seconds, p99=p95_seconds, min=p95_seconds, max=p95_seconds),
            ttft=LatencyStats(),
            tps=TpsStats(mean=tps_mean, total=tps_mean * max(total, 1)),
        ),
    )


def _evaluate(profile: SlaProfile, benchmarks: list[Benchmark]) -> list[SlaEvaluationResult]:
    from routers.sla import evaluate_benchmarks_against_sla  # pyright: ignore[reportMissingImports, reportUnknownVariableType]

    evaluate_fn = cast(
        Callable[[SlaProfile, list[Benchmark]], list[SlaEvaluationResult]],
        evaluate_benchmarks_against_sla,
    )
    return evaluate_fn(profile, benchmarks)


def _verdict_by_metric(result: SlaEvaluationResult, metric: str) -> SlaVerdict:
    return next(v for v in result.verdicts if v.metric == metric)


@pytest.mark.asyncio
async def test_evaluate_all_pass(storage: Storage) -> None:
    assert storage is not None
    profile = SlaProfile(
        name="strict",
        model="llm-ov",
        thresholds=SlaThresholds(
            availability_min=99.0,
            p95_latency_max_ms=500.0,
            error_rate_max_pct=1.0,
            min_tps=10.0,
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
    assert storage is not None
    profile = SlaProfile(
        name="latency-only",
        model="llm-ov",
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
    assert storage is not None
    profile = SlaProfile(
        name="avail-only",
        model="llm-ov",
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
    assert storage is not None
    profile = SlaProfile(
        name="error-only",
        model="llm-ov",
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
async def test_evaluate_tps_fail(storage: Storage) -> None:
    assert storage is not None
    profile = SlaProfile(
        name="tps-only",
        model="llm-ov",
        thresholds=SlaThresholds(min_tps=50.0),
    )
    benchmark = _make_benchmark(tps_mean=30.0)

    results = _evaluate(profile, [benchmark])

    assert len(results) == 1
    assert results[0].overall_pass is False
    tps_verdict = _verdict_by_metric(results[0], "min_tps")
    assert tps_verdict.status == "fail"
    assert tps_verdict.pass_ is False


@pytest.mark.asyncio
async def test_evaluate_zero_requests(storage: Storage) -> None:
    assert storage is not None
    profile = SlaProfile(
        name="zero-requests",
        model="llm-ov",
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
    assert storage is not None
    profile = SlaProfile(
        name="partial",
        model="llm-ov",
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
    assert storage is not None
    profile = SlaProfile(
        name="empty",
        model="llm-ov",
        thresholds=SlaThresholds(availability_min=99.0),
    )

    results = _evaluate(profile, [])

    assert results == []


@pytest.mark.asyncio
async def test_sla_profile_crud(storage: Storage) -> None:
    profile = SlaProfile(
        name="prod-sla",
        model="llm-ov",
        thresholds=SlaThresholds(
            availability_min=99.9,
            p95_latency_max_ms=500.0,
            error_rate_max_pct=0.5,
            min_tps=20.0,
        ),
    )

    saved = await storage.save_sla_profile(profile)
    assert saved.id is not None

    loaded = await storage.get_sla_profile(saved.id)
    assert loaded is not None
    assert loaded.id == saved.id
    assert loaded.name == "prod-sla"
    assert loaded.model == "llm-ov"
    assert loaded.thresholds.availability_min == 99.9
    assert loaded.thresholds.p95_latency_max_ms == 500.0
    assert loaded.thresholds.error_rate_max_pct == 0.5
    assert loaded.thresholds.min_tps == 20.0


@pytest.mark.asyncio
async def test_thresholds_all_none_rejected(storage: Storage) -> None:
    """SlaThresholds()는 최소 1개 threshold 필수 — ValidationError 발생해야 함 (RED)"""
    with pytest.raises(ValidationError):
        SlaThresholds()


@pytest.mark.asyncio
async def test_thresholds_at_least_one_valid(storage: Storage) -> None:
    """최소 1개 threshold 설정 시 정상 생성"""
    t = SlaThresholds(min_tps=10.0)
    assert t.min_tps == 10.0


@pytest.mark.asyncio
async def test_verdict_invalid_status_rejected(storage: Storage) -> None:
    """SlaVerdict.status가 Literal 외 값이면 ValidationError (RED)"""
    with pytest.raises(ValidationError):
        SlaVerdict.model_validate({"metric": "x", "pass": True, "status": "invalid"})


@pytest.mark.asyncio
async def test_verdict_valid_statuses(storage: Storage) -> None:
    """pass, fail, insufficient_data 세 값 모두 정상"""
    for status in ["pass", "fail", "insufficient_data"]:
        v = SlaVerdict.model_validate({"metric": "x", "pass": status == "pass", "status": status})
        assert v.status == status


@pytest.mark.asyncio
async def test_evaluate_boundary_exact_threshold(storage: Storage) -> None:
    """가용성 정확히 threshold와 동일 → >= 이므로 PASS"""
    profile = SlaProfile(
        name="boundary",
        model="llm-ov",
        thresholds=SlaThresholds(availability_min=99.0),
    )
    # 990 success / 1000 total = 99.0% — 정확히 threshold
    benchmark = _make_benchmark(success=990, failed=10)
    results = _evaluate(profile, [benchmark])
    assert results[0].overall_pass is True
    assert _verdict_by_metric(results[0], "availability").status == "pass"
