import logging

from fastapi import APIRouter, HTTPException, Query, Request, Response
from models.load_test import Benchmark
from models.sla import SlaEvaluateResponse, SlaEvaluationResult, SlaProfile, SlaVerdict
from pydantic import BaseModel
from services.rate_limiter import limiter
from services.shared import storage

router = APIRouter()
logger = logging.getLogger(__name__)


class SlaEvaluateRequest(BaseModel):
    profile_id: int
    benchmark_ids: list[int] = []


def evaluate_benchmarks_against_sla(
    profile: SlaProfile,
    benchmarks: list[Benchmark],
) -> list[SlaEvaluationResult]:
    """Evaluate saved benchmarks against the given SLA profile and return judgment results."""
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
        if thresholds.mean_ttft_max_ms is not None:
            metric_thresholds.append(("ttft_mean", thresholds.mean_ttft_max_ms))
        if thresholds.p95_ttft_max_ms is not None:
            metric_thresholds.append(("ttft_p95", thresholds.p95_ttft_max_ms))

        if total == 0:
            for metric, threshold in metric_thresholds:
                verdicts.append(
                    SlaVerdict.model_validate(
                        {
                            "metric": metric,
                            "value": None,
                            "threshold": threshold,
                            "pass": False,
                            "status": "insufficient_data",
                        }
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
                elif metric == "ttft_mean":
                    value = benchmark.result.ttft.mean * 1000
                    if value == 0:
                        verdicts.append(
                            SlaVerdict.model_validate(
                                {
                                    "metric": metric,
                                    "value": 0.0,
                                    "threshold": threshold,
                                    "pass": True,
                                    "status": "skipped",
                                }
                            )
                        )
                        continue
                    pass_bool = value <= threshold
                elif metric == "ttft_p95":
                    value = benchmark.result.ttft.p95 * 1000
                    if value == 0:
                        verdicts.append(
                            SlaVerdict.model_validate(
                                {
                                    "metric": metric,
                                    "value": 0.0,
                                    "threshold": threshold,
                                    "pass": True,
                                    "status": "skipped",
                                }
                            )
                        )
                        continue
                    pass_bool = value <= threshold
                else:
                    value = benchmark.result.tps.mean
                    pass_bool = value >= threshold

                verdicts.append(
                    SlaVerdict.model_validate(
                        {
                            "metric": metric,
                            "value": value,
                            "threshold": threshold,
                            "pass": pass_bool,
                            "status": "pass" if pass_bool else "fail",
                        }
                    )
                )

        active = [v for v in verdicts if v.status != "skipped"]
        overall_pass = len(active) == 0 or all(v.pass_ for v in active)
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
@limiter.limit("60/minute")
async def list_profiles(
    request: Request,
    limit: int = Query(default=50, ge=1),
    offset: int = Query(default=0, ge=0),
    response: Response = None,
) -> list[SlaProfile]:
    """List all SLA profiles with pagination."""
    total = await storage.count_sla_profiles()
    profiles = await storage.list_sla_profiles(limit=limit, offset=offset)
    if response is not None:
        response.headers["X-Total-Count"] = str(total)
    return profiles


@router.post("/profiles", response_model=SlaProfile, status_code=201)
@limiter.limit("60/minute")
async def create_profile(request: Request, profile: SlaProfile) -> SlaProfile:
    """Create a new SLA profile."""
    return await storage.save_sla_profile(profile)


@router.get("/profiles/{profile_id}", response_model=SlaProfile)
@limiter.limit("60/minute")
async def get_profile(request: Request, profile_id: int) -> SlaProfile:
    """Retrieve an SLA profile by ID."""
    profile = await storage.get_sla_profile(profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail=f"SLA profile {profile_id} not found")
    return profile


@router.put("/profiles/{profile_id}", response_model=SlaProfile)
@limiter.limit("60/minute")
async def update_profile(request: Request, profile_id: int, profile: SlaProfile) -> SlaProfile:
    """Update an existing SLA profile."""
    updated = await storage.update_sla_profile(profile_id, profile)
    if updated is None:
        raise HTTPException(status_code=404, detail=f"SLA profile {profile_id} not found")
    return updated


@router.delete("/profiles/{profile_id}")
@limiter.limit("60/minute")
async def delete_profile(request: Request, profile_id: int) -> dict[str, bool]:
    """Delete an SLA profile by ID."""
    deleted = await storage.delete_sla_profile(profile_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"SLA profile {profile_id} not found")
    return {"deleted": True}


@router.post("/evaluate", response_model=SlaEvaluateResponse)
@limiter.limit("60/minute")
async def evaluate_profile(request: Request, eval_request: SlaEvaluateRequest) -> SlaEvaluateResponse:
    """Evaluate benchmarks against an SLA profile."""
    profile = await storage.get_sla_profile(eval_request.profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail=f"SLA profile {eval_request.profile_id} not found")

    benchmarks = await storage.get_benchmarks_by_ids(eval_request.benchmark_ids)

    found_ids = {b.id for b in benchmarks if b.id is not None}
    missing_ids = [bid for bid in eval_request.benchmark_ids if bid not in found_ids]
    warnings = [f"Benchmark {bid} not found (may have been deleted)" for bid in missing_ids]

    results = evaluate_benchmarks_against_sla(profile, benchmarks)
    return SlaEvaluateResponse(profile=profile, results=results, warnings=warnings)
