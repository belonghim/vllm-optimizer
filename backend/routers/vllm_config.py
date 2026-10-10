import asyncio
import copy
import logging
from collections.abc import Mapping
from typing import Any, Literal, cast

from fastapi import APIRouter, HTTPException, Query, Request
from kubernetes.client import CustomObjectsApi
from kubernetes.client.exceptions import ApiException as K8sApiException
from models.vllm_config import VllmConfigPatchResponse, VllmConfigResponse
from pydantic import BaseModel
from services.cr_adapter import deep_merge, get_cr_adapter
from services.k8s_operator import get_k8s_namespace, get_vllm_is_name

logger = logging.getLogger(__name__)

router = APIRouter()


ALLOWED_RESOURCE_KEYS = {"cpu", "memory", "nvidia.com/gpu"}

ALLOWED_CONFIG_KEYS = {
    "max_num_seqs",
    "gpu_memory_utilization",
    "max_model_len",
    "max_num_batched_tokens",
}

CrType = Literal["inferenceservice", "llminferenceservice"]

ConfigKey = Literal[
    "max_num_seqs",
    "gpu_memory_utilization",
    "max_model_len",
    "max_num_batched_tokens",
]


async def _validate_and_merge_args(
    adapter,
    custom,
    namespace: str,
    is_name: str,
    request_data: Mapping[ConfigKey, str],
) -> dict[str, Any]:
    is_obj = cast(
        dict[str, Any],
        await asyncio.to_thread(
            custom.get_namespaced_custom_object,
            group=adapter.api_group(),
            version=adapter.api_version(),
            namespace=namespace,
            plural=adapter.api_plural(),
            name=is_name,
        ),
    )
    return adapter.build_args_patch(is_obj.get("spec", {}), dict(request_data))


def _validate_and_merge_resources(
    adapter, request_resources: dict[Literal["requests", "limits"], dict[str, str]]
) -> dict[str, Any] | None:
    # JSON merge patch removes a key only when it is null, so "" becomes None.
    clean_resources: dict[str, Any] = {}
    for _tier, kvs in request_resources.items():
        tier_patch = {k: (v if v != "" else None) for k, v in kvs.items()}
        if tier_patch:
            clean_resources[_tier] = tier_patch
    if clean_resources:
        return adapter.build_resources_patch(clean_resources)
    return None


def _is_named_list(value: Any) -> bool:
    return isinstance(value, list) and bool(value) and all(isinstance(i, dict) and "name" in i for i in value)


def _has_named_list(node: Any) -> bool:
    if isinstance(node, dict):
        return any(_has_named_list(v) for v in node.values())
    return _is_named_list(node)


def _merge_into(base: Any, patch: Any) -> Any:
    """Apply a JSON merge patch to base, merging name-keyed lists (containers, env) instead of replacing."""
    if isinstance(base, dict) and isinstance(patch, dict):
        merged = dict(base)
        for key, value in patch.items():
            if value is None:
                merged.pop(key, None)
            else:
                merged[key] = _merge_into(merged.get(key), value)
        return merged
    if _is_named_list(base) and _is_named_list(patch):
        merged_list = copy.deepcopy(base)
        index_by_name = {item["name"]: i for i, item in enumerate(merged_list)}
        for item in patch:
            i = index_by_name.get(item["name"])
            if i is None:
                merged_list.append(copy.deepcopy(item))
            else:
                merged_list[i] = _merge_into(merged_list[i], item)
        return merged_list
    return copy.deepcopy(patch)


def _expand_named_lists(patch: Any, current: Any) -> Any:
    """Replace name-keyed lists in a merge patch with the merged list so siblings are not dropped."""
    if isinstance(patch, dict):
        return {
            key: _expand_named_lists(value, current.get(key) if isinstance(current, dict) else None)
            for key, value in patch.items()
        }
    if _is_named_list(patch) and _is_named_list(current):
        return _merge_into(current, patch)
    return patch


async def _build_patch_body(
    adapter, custom, namespace: str, is_name: str, sub_patches: list[dict[str, Any]]
) -> dict[str, Any]:
    if not any(_has_named_list(p) for p in sub_patches):
        patch_body: dict[str, Any] = {}
        for sub_patch in sub_patches:
            patch_body = deep_merge(patch_body, sub_patch)
        return patch_body

    current = cast(
        dict[str, Any],
        await asyncio.to_thread(
            custom.get_namespaced_custom_object,
            group=adapter.api_group(),
            version=adapter.api_version(),
            namespace=namespace,
            plural=adapter.api_plural(),
            name=is_name,
        ),
    )
    working: dict[str, Any] = {"spec": copy.deepcopy(current.get("spec", {}))}
    patch_body = {}
    for sub_patch in sub_patches:
        expanded = _expand_named_lists(sub_patch, working)
        patch_body = deep_merge(patch_body, expanded)
        working = _merge_into(working, expanded)
    return patch_body


async def _apply_patch(adapter, custom, namespace: str, is_name: str, patch_body: dict[str, Any]) -> None:
    await asyncio.to_thread(
        custom.patch_namespaced_custom_object,
        group=adapter.api_group(),
        version=adapter.api_version(),
        namespace=namespace,
        plural=adapter.api_plural(),
        name=is_name,
        body=patch_body,
    )


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
        except (OSError, k8s_config.ConfigException):  # intentional: non-critical
            k8s_config.load_kube_config()
        return client.CustomObjectsApi()
    except Exception as e:  # intentional: non-critical
        logger.warning("[VllmConfig] K8s client not available: %s", e)
        return None


@router.get("", response_model=VllmConfigResponse)
async def get_vllm_config(
    request: Request,
    namespace: str | None = Query(default=None),
    is_name: str | None = Query(default=None),
    cr_type: CrType | None = Query(default=None),
) -> dict[str, Any]:
    """Get current vLLM InferenceService configuration."""
    _custom = await asyncio.to_thread(_get_k8s_custom)
    if _custom is None:
        raise HTTPException(status_code=503, detail="Kubernetes not available")
    _api = _custom
    namespace = namespace or get_k8s_namespace()
    is_name = is_name or get_vllm_is_name()
    adapter = get_cr_adapter(cr_type)
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
        extra_args = adapter.read_extra_args(spec)
        resolved_model_name = adapter.resolve_model_name(spec, is_name)
        return {
            "success": True,
            "data": data,
            "storageUri": storage_uri,
            "resources": resources,
            "extraArgs": extra_args,
            "modelName": resolved_model_name,
            "resolvedModelName": resolved_model_name,
        }
    except K8sApiException as e:
        logger.error("[VllmConfig] Failed to read InferenceService: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.patch("", response_model=VllmConfigPatchResponse)
async def patch_vllm_config(
    request: Request,
    config: VllmConfigPatchRequest,
    namespace: str | None = Query(default=None),
    is_name: str | None = Query(default=None),
    cr_type: CrType | None = Query(default=None),
) -> dict[str, Any]:
    """Update vLLM configuration (args, resources, model URI)."""
    invalid_keys = {str(k) for k in config.data} - ALLOWED_CONFIG_KEYS
    if invalid_keys:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid config keys: {sorted(invalid_keys)}. Allowed: {sorted(ALLOWED_CONFIG_KEYS)}",
        )

    if config.resources is not None:
        for _tier, kvs in config.resources.items():
            invalid_res_keys = set(kvs.keys()) - ALLOWED_RESOURCE_KEYS
            if invalid_res_keys:
                raise HTTPException(status_code=422, detail=f"Invalid resource keys: {invalid_res_keys}")
        if config.resources.get("requests", {}).get("nvidia.com/gpu"):
            raise HTTPException(status_code=422, detail="nvidia.com/gpu can only be set in limits")

    if not config.data and config.storageUri is None and config.resources is None:
        return {"success": True, "updated_keys": [], "updated_storageUri": False}

    try:
        from routers.tuner import auto_tuner

        if auto_tuner.is_running:
            raise HTTPException(status_code=409, detail="Tuner is running, cannot modify config")
    except HTTPException:
        raise
    except (ImportError, AttributeError):
        pass

    custom = await asyncio.to_thread(_get_k8s_custom)
    if custom is None:
        raise HTTPException(status_code=503, detail="Kubernetes not available")

    namespace = namespace or get_k8s_namespace()
    is_name = is_name or get_vllm_is_name()
    adapter = get_cr_adapter(cr_type)

    try:
        sub_patches: list[dict[str, Any]] = []

        if config.data:
            sub_patches.append(await _validate_and_merge_args(adapter, custom, namespace, is_name, config.data))

        if config.storageUri is not None:
            sub_patches.append(adapter.build_model_uri_patch(config.storageUri))

        if config.resources is not None:
            res_patch = _validate_and_merge_resources(adapter, config.resources)
            if res_patch:
                sub_patches.append(res_patch)

        patch_body = await _build_patch_body(adapter, custom, namespace, is_name, sub_patches)
        await _apply_patch(adapter, custom, namespace, is_name, patch_body)
        return {
            "success": True,
            "updated_keys": list(config.data.keys()),
            "updated_storageUri": config.storageUri is not None,
        }
    except K8sApiException as e:
        logger.error("[VllmConfig] Failed to patch InferenceService: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e
