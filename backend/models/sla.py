"""
Pydantic models for SLA management and evaluation

This module defines all data models for SLA profiles, evaluation, and verdicts.
"""
from pydantic import BaseModel, Field, ConfigDict
from typing import Optional


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


class SlaProfile(BaseModel):
    """SLA profile for a model"""
    id: Optional[int] = None
    name: str
    model: str = Field(description="대상 모델명 (SLA 매칭에 사용)")
    thresholds: SlaThresholds
    created_at: Optional[float] = None


class SlaVerdict(BaseModel):
    """Verdict for a single SLA metric evaluation"""
    metric: str
    value: Optional[float] = None
    threshold: Optional[float] = None
    pass_: bool = Field(alias="pass")
    status: str  # "pass" | "fail" | "insufficient_data"

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
