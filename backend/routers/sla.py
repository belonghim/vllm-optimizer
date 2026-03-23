import logging

from fastapi import APIRouter, HTTPException

from models.load_test import Benchmark
from models.sla import SlaEvaluateResponse, SlaEvaluationResult, SlaProfile, SlaVerdict
from services.shared import storage

router = APIRouter()
logger = logging.getLogger(__name__)


def evaluate_benchmarks_against_sla(
    profile: SlaProfile,
    benchmarks: list[Benchmark],
) -> list[SlaEvaluationResult]:
    results: list[SlaEvaluationResult] = []

    for benchmark in benchmarks:
        verdicts: list[SlaVerdict] = []
        thresholds = profile.thresholds
        total = benchmark.result.success + benchmark.result.failed

        metric_thresholds: list[tuple[str, float]] = []
        if thresholds.availability_min is not None:
            metric_thresholds.append(("availability", thresholds.availability_min))
        if thresholds.p95_latency_max_ms is not None:
            metric_thresholds.append(("p95_latency", thresholds.p95_latency_max_ms))
        if thresholds.error_rate_max_pct is not None:
            metric_thresholds.append(("error_rate", thresholds.error_rate_max_pct))
        if thresholds.min_tps is not None:
            metric_thresholds.append(("min_tps", thresholds.min_tps))

        if total == 0:
            for metric, threshold in metric_thresholds:
                verdicts.append(
                    SlaVerdict.model_validate(
                        {"metric": metric, "value": None, "threshold": threshold, "pass": False, "status": "insufficient_data"}
                    )
                )
        else:
            for metric, threshold in metric_thresholds:
                if metric == "availability":
                    value = benchmark.result.success / total * 100
                    pass_bool = value >= threshold
                elif metric == "p95_latency":
                    value = benchmark.result.latency.p95 * 1000
                    pass_bool = value <= threshold
                elif metric == "error_rate":
                    value = benchmark.result.failed / total * 100
                    pass_bool = value <= threshold
                else:
                    value = benchmark.result.tps.mean
                    pass_bool = value >= threshold

                verdicts.append(
                    SlaVerdict.model_validate(
                        {"metric": metric, "value": value, "threshold": threshold, "pass": pass_bool, "status": "pass" if pass_bool else "fail"}
                    )
                )

        overall_pass = len(verdicts) > 0 and all(v.pass_ for v in verdicts)
        results.append(
            SlaEvaluationResult(
                benchmark_id=benchmark.id if benchmark.id is not None else 0,
                benchmark_name=benchmark.name,
                timestamp=benchmark.timestamp if benchmark.timestamp is not None else 0.0,
                verdicts=verdicts,
                overall_pass=overall_pass,
            )
        )

    return results


@router.get("/profiles", response_model=list[SlaProfile])
async def list_profiles() -> list[SlaProfile]:
    return await storage.list_sla_profiles()


@router.post("/profiles", response_model=SlaProfile, status_code=201)
async def create_profile(profile: SlaProfile) -> SlaProfile:
    return await storage.save_sla_profile(profile)


@router.get("/profiles/{profile_id}", response_model=SlaProfile)
async def get_profile(profile_id: int) -> SlaProfile:
    profile = await storage.get_sla_profile(profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail=f"SLA profile {profile_id} not found")
    return profile


@router.put("/profiles/{profile_id}", response_model=SlaProfile)
async def update_profile(profile_id: int, profile: SlaProfile) -> SlaProfile:
    updated = await storage.update_sla_profile(profile_id, profile)
    if updated is None:
        raise HTTPException(status_code=404, detail=f"SLA profile {profile_id} not found")
    return updated


@router.delete("/profiles/{profile_id}")
async def delete_profile(profile_id: int) -> dict[str, bool]:
    deleted = await storage.delete_sla_profile(profile_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"SLA profile {profile_id} not found")
    return {"deleted": True}


@router.get("/evaluate/{profile_id}", response_model=SlaEvaluateResponse)
async def evaluate_profile(
    profile_id: int,
) -> SlaEvaluateResponse:
    profile = await storage.get_sla_profile(profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail=f"SLA profile {profile_id} not found")

    benchmarks = await storage.get_benchmarks_by_ids(profile.benchmark_ids)

    found_ids = {b.id for b in benchmarks if b.id is not None}
    missing_ids = [bid for bid in profile.benchmark_ids if bid not in found_ids]
    warnings = [f"Benchmark {bid} not found (may have been deleted)" for bid in missing_ids]

    results = evaluate_benchmarks_against_sla(profile, benchmarks)
    return SlaEvaluateResponse(profile=profile, results=results, warnings=warnings)
