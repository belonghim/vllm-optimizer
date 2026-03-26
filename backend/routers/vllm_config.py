import asyncio
import logging
from typing import Any, Literal, cast

from fastapi import APIRouter, HTTPException
from kubernetes.client import CustomObjectsApi
from kubernetes.client.exceptions import ApiException as K8sApiException
from pydantic import BaseModel
from services.shared import runtime_config
from services.cr_adapter import deep_merge, get_cr_adapter

logger = logging.getLogger(__name__)

router = APIRouter()


def _get_k8s_namespace() -> str:
    namespace = runtime_config.vllm_namespace
    return namespace if namespace else "default"


def _get_vllm_is_name() -> str:
    return runtime_config.vllm_is_name or "llm-ov"


ALLOWED_RESOURCE_KEYS = {"cpu", "memory", "nvidia.com/gpu"}

ALLOWED_CONFIG_KEYS = {
    "max_num_seqs",
    "gpu_memory_utilization",
    "max_model_len",
    "max_num_batched_tokens",
    "block_size",
    "swap_space",
    "enable_chunked_prefill",
    "enable_enforce_eager",
}


ConfigKey = Literal[
    "max_num_seqs",
    "gpu_memory_utilization",
    "max_model_len",
    "max_num_batched_tokens",
    "block_size",
    "swap_space",
    "enable_chunked_prefill",
    "enable_enforce_eager",
]


class VllmConfigPatchRequest(BaseModel):
    data: dict[ConfigKey, str] = {}
    storageUri: str | None = None
    resources: dict[Literal["requests", "limits"], dict[str, str]] | None = None


def _get_k8s_custom() -> CustomObjectsApi | None:
    try:
        from kubernetes import client
        from kubernetes import config as k8s_config

        try:
            k8s_config.load_incluster_config()
        except Exception:  # intentional: non-critical
            k8s_config.load_kube_config()
        return client.CustomObjectsApi()
    except Exception as e:  # intentional: non-critical
        logger.warning("[VllmConfig] K8s client not available: %s", e)
        return None


@router.get("")
async def get_vllm_config() -> dict[str, Any]:
    _custom = await asyncio.to_thread(_get_k8s_custom)
    if _custom is None:
        raise HTTPException(status_code=503, detail="Kubernetes not available")
    _api = _custom
    namespace = _get_k8s_namespace()
    is_name = _get_vllm_is_name()
    adapter = get_cr_adapter()
    try:
        is_obj = cast(
            dict[str, Any],
            await asyncio.to_thread(
                _api.get_namespaced_custom_object,
                group=adapter.api_group(),
                version=adapter.api_version(),
                namespace=namespace,
                plural=adapter.api_plural(),
                name=is_name,
            ),
        )
        spec = is_obj.get("spec", {})
        data = adapter.read_args(spec)
        storage_uri = adapter.read_model_uri(spec)
        resources = adapter.read_resources(spec)
        return {"success": True, "data": data, "storageUri": storage_uri, "resources": resources}
    except K8sApiException as e:
        logger.error("[VllmConfig] Failed to read InferenceService: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.patch("")
async def patch_vllm_config(request: VllmConfigPatchRequest) -> dict[str, Any]:
    # 키 유효성 검증
    invalid_keys = {str(k) for k in request.data} - ALLOWED_CONFIG_KEYS
    if invalid_keys:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid config keys: {sorted(invalid_keys)}. Allowed: {sorted(ALLOWED_CONFIG_KEYS)}",
        )

    if request.resources is not None:
        for _tier, kvs in request.resources.items():
            invalid_res_keys = set(kvs.keys()) - ALLOWED_RESOURCE_KEYS
            if invalid_res_keys:
                raise HTTPException(status_code=422, detail=f"Invalid resource keys: {invalid_res_keys}")

    if not request.data and request.storageUri is None and request.resources is None:
        return {"success": True, "updated_keys": [], "updated_storageUri": False}

    # 튜너 실행 중 체크
    try:
        from services.shared import load_engine as _le  # noqa
        from routers.tuner import auto_tuner

        if auto_tuner.is_running:
            raise HTTPException(status_code=409, detail="Tuner is running, cannot modify config")
    except HTTPException:
        raise
    except Exception:  # intentional: non-critical
        pass  # auto_tuner 접근 불가 시 진행

    custom = await asyncio.to_thread(_get_k8s_custom)
    if custom is None:
        raise HTTPException(status_code=503, detail="Kubernetes not available")
    _api = custom
    namespace = _get_k8s_namespace()
    is_name = _get_vllm_is_name()
    adapter = get_cr_adapter()
    try:
        patch_body: dict[str, Any] = {}

        if request.data:
            is_obj = cast(
                dict[str, Any],
                await asyncio.to_thread(
                    _api.get_namespaced_custom_object,
                    group=adapter.api_group(),
                    version=adapter.api_version(),
                    namespace=namespace,
                    plural=adapter.api_plural(),
                    name=is_name,
                ),
            )
            args_patch = adapter.build_args_patch(is_obj.get("spec", {}), dict(request.data))
            patch_body = deep_merge(patch_body, args_patch)

        if request.storageUri is not None:
            uri_patch = adapter.build_model_uri_patch(request.storageUri)
            patch_body = deep_merge(patch_body, uri_patch)

        if request.resources is not None:
            clean_resources: dict[str, Any] = {}
            for _tier, kvs in request.resources.items():
                cleaned = {k: v for k, v in kvs.items() if v != ""}
                if cleaned:
                    clean_resources[_tier] = cleaned
            if clean_resources:
                res_patch = adapter.build_resources_patch(clean_resources)
                patch_body = deep_merge(patch_body, res_patch)

        await asyncio.to_thread(
            _api.patch_namespaced_custom_object,
            group=adapter.api_group(),
            version=adapter.api_version(),
            namespace=namespace,
            plural=adapter.api_plural(),
            name=is_name,
            body=patch_body,
        )
        return {
            "success": True,
            "updated_keys": list(request.data.keys()),
            "updated_storageUri": request.storageUri is not None,
        }
    except K8sApiException as e:
        logger.error("[VllmConfig] Failed to patch InferenceService: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e
