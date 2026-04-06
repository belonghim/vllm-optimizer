"""
Pydantic response models for vllm_config and status routers.
"""

from typing import Any

from pydantic import BaseModel, Field


class VllmConfigData(BaseModel):
    """vLLM configuration args as key-value pairs."""

    max_num_seqs: str | None = Field(default=None, description="Max concurrent sequences")
    gpu_memory_utilization: str | None = Field(default=None, description="GPU memory fraction")
    max_model_len: str | None = Field(default=None, description="Max model context length")
    max_num_batched_tokens: str | None = Field(default=None, description="Max batched tokens")
    block_size: str | None = Field(default=None, description="KV cache block size")
    swap_space: str | None = Field(default=None, description="Swap space in GB")
    enable_chunked_prefill: str | None = Field(default=None, description="Enable chunked prefill")
    enable_enforce_eager: str | None = Field(default=None, description="Enforce eager mode")


class VllmConfigResources(BaseModel):
    """vLLM resource requests and limits."""

    requests: dict[str, str] | None = Field(default=None, description="Resource requests")
    limits: dict[str, str] | None = Field(default=None, description="Resource limits")


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


class InterruptedRun(BaseModel):
    """Single interrupted run record."""

    id: int | None = Field(default=None, description="Run ID")
    name: str | None = Field(default=None, description="Run name")
    status: str | None = Field(default=None, description="Run status")
    # Flexible extra fields
    extra: dict[str, Any] = Field(default_factory=dict, description="Additional run data")


class InterruptedRunsResponse(BaseModel):
    """Response model for GET /api/status/interrupted."""

    interrupted_runs: list[dict[str, Any]] = Field(
        default_factory=list,
        description="List of interrupted runs detected at startup",
    )
