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
    thresholds: SlaThresholds
    created_at: Optional[float] = None

    model_config = ConfigDict(extra="forbid")


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
