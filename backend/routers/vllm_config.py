import asyncio
import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Any, Dict, Optional, cast, Literal
from kubernetes.client import CustomObjectsApi
from kubernetes.client.exceptions import ApiException as K8sApiException
from services.shared import runtime_config

logger = logging.getLogger(__name__)

router = APIRouter()


def _get_k8s_namespace() -> str:
    namespace = runtime_config.vllm_namespace
    return namespace if namespace else "default"


def _get_vllm_is_name() -> str:
    return runtime_config.vllm_is_name or "llm-ov"

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

# IS args에서 파싱할 key 매핑 (CLI flag → config key)
_ARG_TO_KEY = {
    "--max-num-seqs": "max_num_seqs",
    "--gpu-memory-utilization": "gpu_memory_utilization",
    "--max-model-len": "max_model_len",
    "--max-num-batched-tokens": "max_num_batched_tokens",
    "--block-size": "block_size",
    "--swap-space": "swap_space",
    "--enable-chunked-prefill": "enable_chunked_prefill",
    "--enforce-eager": "enable_enforce_eager",
}
_KEY_TO_ARG = {v: k for k, v in _ARG_TO_KEY.items()}

# 튜닝 arg 접두사 (정적 args 필터링용)
_TUNING_ARG_PREFIXES = tuple(_ARG_TO_KEY.keys())


def _args_to_config_dict(args: list[str]) -> dict[str, Any]:
    """IS args list → key-value config dict"""
    result = {}
    for arg in args:
        for cli_flag, config_key in _ARG_TO_KEY.items():
            if arg == cli_flag:  # boolean flag (예: --enable-chunked-prefill)
                result[config_key] = "true"
                break
            elif arg.startswith(cli_flag + "="):  # key=value flag
                result[config_key] = arg.split("=", 1)[1]
                break
    return result


def _config_dict_to_tuning_args(config: dict[str, Any]) -> list[str]:
    """key-value config dict → IS tuning args list"""
    result = []
    for key, value in config.items():
        cli_flag = _KEY_TO_ARG.get(key)
        if cli_flag is None:
            continue
        # boolean flags (enable_chunked_prefill, enforce_eager)
        if key in ("enable_chunked_prefill", "enable_enforce_eager"):
            if str(value).lower() in ("true", "1", "yes"):
                result.append(cli_flag)
            # false/empty → 생략
        else:
            if value is not None and str(value):
                result.append(f"{cli_flag}={str(value)}")
    return result


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
    storageUri: Optional[str] = None


def _get_k8s_custom() -> Optional[CustomObjectsApi]:
    try:
        from kubernetes import client, config as k8s_config
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
    try:
        is_obj = cast(dict[str, Any], await asyncio.to_thread(
            _api.get_namespaced_custom_object,
            group="serving.kserve.io",
            version="v1beta1",
            namespace=namespace,
            plural="inferenceservices",
            name=is_name,
        ))
        model_spec: dict[str, Any] = is_obj.get("spec", {}).get("predictor", {}).get("model", {})  # type: ignore[index]
        args = model_spec.get("args") or []
        storage_uri = model_spec.get("storageUri")
        resources = model_spec.get("resources", {})
        return {"success": True, "data": _args_to_config_dict(args), "storageUri": storage_uri, "resources": resources}
    except K8sApiException as e:
        logger.error("[VllmConfig] Failed to read InferenceService: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("")
async def patch_vllm_config(request: VllmConfigPatchRequest) -> dict[str, Any]:
    # 키 유효성 검증
    invalid_keys = set(request.data.keys()) - ALLOWED_CONFIG_KEYS
    if invalid_keys:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid config keys: {sorted(invalid_keys)}. Allowed: {sorted(ALLOWED_CONFIG_KEYS)}",
        )

    if not request.data and request.storageUri is None:
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
    try:
        model_patch: dict[str, Any] = {}

        if request.data:
            is_obj = cast(dict[str, Any], await asyncio.to_thread(
                _api.get_namespaced_custom_object,
                group="serving.kserve.io",
                version="v1beta1",
                namespace=namespace,
                plural="inferenceservices",
                name=is_name,
            ))
            current_args: list[str] = (is_obj.get("spec", {}).get("predictor", {})  # type: ignore[index]
                            .get("model", {}).get("args") or [])

            # 정적 args (튜닝 파라미터 아닌 것) 보존
            static_args = [a for a in current_args
                           if not a.startswith(_TUNING_ARG_PREFIXES)]

            new_tuning_args = _config_dict_to_tuning_args(request.data)
            model_patch["args"] = static_args + new_tuning_args

        if request.storageUri is not None:
            model_patch["storageUri"] = request.storageUri

        patch_body = {"spec": {"predictor": {"model": model_patch}}}
        await asyncio.to_thread(
            _api.patch_namespaced_custom_object,
            group="serving.kserve.io",
            version="v1beta1",
            namespace=namespace,
            plural="inferenceservices",
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
        raise HTTPException(status_code=500, detail=str(e))
