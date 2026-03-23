"""
Pydantic models for SLA management and evaluation

This module defines all data models for SLA profiles, evaluation, and verdicts.
"""
from pydantic import BaseModel, Field, ConfigDict, model_validator
from typing import Optional, Literal


class SlaThresholds(BaseModel):
    """SLA threshold constraints"""
    availability_min: Optional[float] = Field(
        default=None,
        description="최소 가용성 (%)",
        ge=0,
        le=100
    )
    p95_latency_max_ms: Optional[float] = Field(
        default=None,
        description="P95 latency 최대값 (ms)",
        gt=0
    )
    error_rate_max_pct: Optional[float] = Field(
        default=None,
        description="최대 오류율 (%)",
        ge=0,
        le=100
    )
    min_tps: Optional[float] = Field(
        default=None,
        description="최소 TPS",
        gt=0
    )

    @model_validator(mode='after')
    def at_least_one_threshold(self) -> 'SlaThresholds':
        if all(v is None for v in [
            self.availability_min, self.p95_latency_max_ms,
            self.error_rate_max_pct, self.min_tps
        ]):
            raise ValueError("At least one threshold must be set")
        return self


class SlaProfile(BaseModel):
    """SLA profile"""
    id: Optional[int] = None
    name: str
    benchmark_ids: list[int] = Field(description="할당된 벤치마크 ID 목록 (1~5개)")
    thresholds: SlaThresholds
    created_at: Optional[float] = None

    @model_validator(mode='after')
    def validate_benchmark_ids(self) -> 'SlaProfile':
        # 중복 제거 (순서 유지)
        seen = set()
        deduped = [x for x in self.benchmark_ids if x not in seen and not seen.add(x)]
        # 양수만 허용
        if any(x <= 0 for x in deduped):
            raise ValueError("benchmark_ids must contain only positive integers")
        # 최소 1개
        if len(deduped) == 0:
            raise ValueError("benchmark_ids must contain at least one benchmark")
        # 최대 5개
        if len(deduped) > 5:
            raise ValueError("benchmark_ids can contain at most 5 benchmarks")
        self.benchmark_ids = deduped
        return self


class SlaVerdict(BaseModel):
    """Verdict for a single SLA metric evaluation"""
    metric: str
    value: Optional[float] = None
    threshold: Optional[float] = None
    pass_: bool = Field(alias="pass")
    status: Literal["pass", "fail", "insufficient_data"]

    model_config = ConfigDict(populate_by_name=True)


class SlaEvaluationResult(BaseModel):
    """Result of SLA evaluation against a benchmark"""
    benchmark_id: int
    benchmark_name: str
    timestamp: float
    verdicts: list[SlaVerdict]
    overall_pass: bool


class SlaEvaluateResponse(BaseModel):
    """Response for SLA evaluation"""
    profile: SlaProfile
    results: list[SlaEvaluationResult]
    warnings: list[str] = []
