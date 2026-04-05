import time
from collections.abc import Callable

from fastapi import APIRouter, Request
from models.sla import SlaProfile
from pydantic import BaseModel
from services.rate_limiter import limiter
from services.shared import multi_target_collector, storage

router = APIRouter()
metrics_collector = multi_target_collector


class ViolatedMetric(BaseModel):
    metric: str
    threshold: float
    actual: float
    severity: str = "critical"


class SlaProfileViolation(BaseModel):
    profile_id: int
    profile_name: str
    violated_metrics: list[ViolatedMetric]


class SlaViolationsResponse(BaseModel):
    violations: list[SlaProfileViolation]
    has_violations: bool
    checked_at: float


def _collect_profile_violations(profile: SlaProfile, latest_metrics: object) -> list[ViolatedMetric]:
    thresholds = profile.thresholds
    violations: list[ViolatedMetric] = []

    def add_if_violated(
        metric: str,
        threshold: float | None,
        actual: float | None,
        is_violated: Callable[[float, float], bool],
    ) -> None:
        if threshold is None or actual is None:
            return
        if is_violated(actual, threshold):
            violations.append(
                ViolatedMetric(
                    metric=metric,
                    threshold=float(threshold),
                    actual=float(actual),
                    severity="critical",
                )
            )

    add_if_violated(
        "p99_latency_ms",
        thresholds.p95_latency_max_ms,
        getattr(latest_metrics, "p99_e2e_latency_ms", None),
        lambda actual, threshold: actual > threshold,
    )
    add_if_violated(
        "min_tps",
        thresholds.min_tps,
        getattr(latest_metrics, "tokens_per_second", None),
        lambda actual, threshold: actual < threshold,
    )

    max_error_rate = getattr(thresholds, "max_error_rate", None)
    if max_error_rate is None:
        max_error_rate = getattr(thresholds, "error_rate_max_pct", None)
    actual_error_rate = getattr(latest_metrics, "error_rate_pct", None)
    if actual_error_rate is None:
        actual_error_rate = getattr(latest_metrics, "error_rate", None)
    add_if_violated(
        "max_error_rate",
        max_error_rate,
        actual_error_rate,
        lambda actual, threshold: actual > threshold,
    )

    max_ttft_ms = getattr(thresholds, "max_ttft_ms", None)
    add_if_violated(
        "max_ttft_ms",
        max_ttft_ms,
        getattr(latest_metrics, "p99_ttft_ms", None),
        lambda actual, threshold: actual > threshold,
    )

    return violations


@router.get("/sla-violations", response_model=SlaViolationsResponse)
@limiter.limit("60/minute")
async def get_sla_violations(request: Request) -> SlaViolationsResponse:
    profiles = await storage.list_sla_profiles()
    latest_metrics = metrics_collector.latest

    if latest_metrics is None or not profiles:
        return SlaViolationsResponse(violations=[], has_violations=False, checked_at=time.time())

    violations: list[SlaProfileViolation] = []
    for profile in profiles:
        violated_metrics = _collect_profile_violations(profile, latest_metrics)
        if violated_metrics:
            violations.append(
                SlaProfileViolation(
                    profile_id=profile.id or 0,
                    profile_name=profile.name,
                    violated_metrics=violated_metrics,
                )
            )

    return SlaViolationsResponse(
        violations=violations,
        has_violations=len(violations) > 0,
        checked_at=time.time(),
    )
