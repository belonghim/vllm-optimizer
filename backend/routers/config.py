from fastapi import APIRouter
from pydantic import BaseModel
from services.model_resolver import resolve_model_name
from services.shared import runtime_config

router = APIRouter(prefix="/api/config", tags=["config"])


class ConfigResponse(BaseModel):
    vllm_endpoint: str
    vllm_namespace: str
    vllm_is_name: str
    vllm_model_name: str
    resolved_model_name: str


class ConfigPatch(BaseModel):
    vllm_endpoint: str | None = None
    vllm_namespace: str | None = None
    vllm_is_name: str | None = None


@router.get("", response_model=ConfigResponse)
async def get_config() -> ConfigResponse:
    import os

    endpoint = runtime_config.vllm_endpoint
    model_name = os.getenv("VLLM_MODEL", "auto")
    try:
        resolved = await resolve_model_name(endpoint)
    except Exception:
        resolved = model_name
    return ConfigResponse(
        vllm_endpoint=endpoint,
        vllm_namespace=runtime_config.vllm_namespace,
        vllm_is_name=runtime_config.vllm_is_name,
        vllm_model_name=model_name,
        resolved_model_name=resolved,
    )


@router.patch("", response_model=ConfigResponse)
async def patch_config(patch: ConfigPatch) -> ConfigResponse:
    if patch.vllm_endpoint is not None:
        runtime_config.set_vllm_endpoint(patch.vllm_endpoint)
    if patch.vllm_namespace is not None:
        runtime_config.set_vllm_namespace(patch.vllm_namespace)
    if patch.vllm_is_name is not None:
        runtime_config.set_vllm_is_name(patch.vllm_is_name)
    return await get_config()
