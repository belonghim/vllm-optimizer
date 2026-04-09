"""
Pydantic models for SLA management and evaluation

This module defines all data models for SLA profiles, evaluation, and verdicts.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class SlaThresholds(BaseModel):
    """SLA threshold constraints"""

    availability_min: float | None = Field(default=None, description="최소 가용성 (%)", ge=0, le=100)
    p95_latency_max_ms: float | None = Field(default=None, description="P95 latency 최대값 (ms)", gt=0)
    error_rate_max_pct: float | None = Field(default=None, description="최대 오류율 (%)", ge=0, le=100)
    mean_ttft_max_ms: float | None = Field(default=None, description="TTFT 평균 최대값 (ms)", gt=0)
    p95_ttft_max_ms: float | None = Field(default=None, description="TTFT P95 최대값 (ms)", gt=0)
    mean_e2e_latency_max_ms: float | None = Field(default=None, description="Mean E2E Latency 최대값 (ms)", gt=0)
    mean_tpot_max_ms: float | None = Field(default=None, description="Mean TPOT 최대값 (ms)", gt=0)
    p95_tpot_max_ms: float | None = Field(default=None, description="P95 TPOT 최대값 (ms)", gt=0)
    mean_queue_time_max_ms: float | None = Field(default=None, description="Mean Queue Time 최대값 (ms)", gt=0)
    p95_queue_time_max_ms: float | None = Field(default=None, description="P95 Queue Time 최대값 (ms)", gt=0)

    @model_validator(mode="after")
    def at_least_one_threshold(self) -> "SlaThresholds":
        if all(
            v is None
            for v in [
                self.availability_min,
                self.p95_latency_max_ms,
                self.error_rate_max_pct,
                self.mean_ttft_max_ms,
                self.p95_ttft_max_ms,
                self.mean_e2e_latency_max_ms,
                self.mean_tpot_max_ms,
                self.p95_tpot_max_ms,
                self.mean_queue_time_max_ms,
                self.p95_queue_time_max_ms,
            ]
        ):
            raise ValueError("At least one threshold must be set")
        return self


class SlaProfile(BaseModel):
    """SLA profile"""

    id: int | None = None
    name: str
    thresholds: SlaThresholds
    created_at: float | None = None

    model_config = ConfigDict(extra="forbid")


class SlaVerdict(BaseModel):
    """Verdict for a single SLA metric evaluation"""

    metric: str
    value: float | None = None
    threshold: float | None = None
    pass_: bool = Field(alias="pass")
    status: Literal["pass", "fail", "insufficient_data", "skipped"]

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
