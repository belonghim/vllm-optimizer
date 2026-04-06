"""
Pydantic response models for vllm_config and status routers.
"""

from typing import Any

from pydantic import BaseModel, Field


class VllmConfigResponse(BaseModel):
    """Response model for GET /api/vllm-config."""

    success: bool = Field(description="Whether the request succeeded")
    data: dict[str, Any] = Field(description="vLLM args as key-value pairs")
    storageUri: str | None = Field(default=None, description="Model storage URI")
    resources: dict[str, Any] = Field(default_factory=dict, description="Resource requests/limits")
    extraArgs: list[str] = Field(default_factory=list, description="Extra arguments not in known keys")
    modelName: str = Field(description="Model name served by vLLM")
    resolvedModelName: str = Field(description="Resolved model name (same as modelName)")


class VllmConfigPatchResponse(BaseModel):
    """Response model for PATCH /api/vllm-config."""

    success: bool = Field(description="Whether the patch was applied")
    updated_keys: list[str] = Field(default_factory=list, description="Config keys that were updated")
    updated_storageUri: bool = Field(description="Whether storageUri was updated")


class InterruptedRunsResponse(BaseModel):
    """Response model for GET /api/status/interrupted."""

    interrupted_runs: list[dict[str, Any]] = Field(
        default_factory=list,
        description="List of interrupted runs detected at startup",
    )
