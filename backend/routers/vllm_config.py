import os
import asyncio
import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Dict, Optional
from kubernetes.client.exceptions import ApiException as K8sApiException

logger = logging.getLogger(__name__)

router = APIRouter()

K8S_NAMESPACE = os.getenv("K8S_NAMESPACE", "default")
VLLM_IS_NAME = os.getenv("VLLM_DEPLOYMENT_NAME") or "llm-ov"

ALLOWED_CONFIG_KEYS = {
    "MAX_NUM_SEQS",
    "GPU_MEMORY_UTILIZATION",
    "MAX_MODEL_LEN",
    "MAX_NUM_BATCHED_TOKENS",
    "BLOCK_SIZE",
    "SWAP_SPACE",
    "ENABLE_CHUNKED_PREFILL",
    "ENABLE_ENFORCE_EAGER",
}

# IS args에서 파싱할 key 매핑 (CLI flag → config key)
_ARG_TO_KEY = {
    "--max-num-seqs": "MAX_NUM_SEQS",
    "--gpu-memory-utilization": "GPU_MEMORY_UTILIZATION",
    "--max-model-len": "MAX_MODEL_LEN",
    "--max-num-batched-tokens": "MAX_NUM_BATCHED_TOKENS",
    "--block-size": "BLOCK_SIZE",
    "--swap-space": "SWAP_SPACE",
    "--enable-chunked-prefill": "ENABLE_CHUNKED_PREFILL",
    "--enforce-eager": "ENABLE_ENFORCE_EAGER",
}
_KEY_TO_ARG = {v: k for k, v in _ARG_TO_KEY.items()}

# 튜닝 arg 접두사 (정적 args 필터링용)
_TUNING_ARG_PREFIXES = tuple(_ARG_TO_KEY.keys())


def _args_to_config_dict(args: list) -> dict:
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


def _config_dict_to_tuning_args(config: dict) -> list:
    """key-value config dict → IS tuning args list"""
    result = []
    for key, value in config.items():
        cli_flag = _KEY_TO_ARG.get(key)
        if cli_flag is None:
            continue
        # boolean flags (enable_chunked_prefill, enforce_eager)
        if key in ("ENABLE_CHUNKED_PREFILL", "ENABLE_ENFORCE_EAGER"):
            if value.lower() in ("true", "1", "yes"):
                result.append(cli_flag)
            # false/empty → 생략
        else:
            if value:
                result.append(f"{cli_flag}={value}")
    return result


class VllmConfigPatchRequest(BaseModel):
    data: Dict[str, str] = {}
    storageUri: Optional[str] = None


def _get_k8s_custom() -> Optional[object]:
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
async def get_vllm_config() -> dict:
    custom = await asyncio.to_thread(_get_k8s_custom)
    if custom is None:
        raise HTTPException(status_code=503, detail="Kubernetes not available")
    try:
        is_obj = await asyncio.to_thread(
            custom.get_namespaced_custom_object,
            group="serving.kserve.io",
            version="v1beta1",
            namespace=K8S_NAMESPACE,
            plural="inferenceservices",
            name=VLLM_IS_NAME,
        )
        model_spec = is_obj.get("spec", {}).get("predictor", {}).get("model", {})
        args = model_spec.get("args") or []
        storage_uri = model_spec.get("storageUri")
        return {"success": True, "data": _args_to_config_dict(args), "storageUri": storage_uri}
    except K8sApiException as e:
        logger.error("[VllmConfig] Failed to read InferenceService: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("")
async def patch_vllm_config(request: VllmConfigPatchRequest) -> dict:
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

    try:
        model_patch: dict = {}

        if request.data:
            is_obj = await asyncio.to_thread(
                custom.get_namespaced_custom_object,
                group="serving.kserve.io",
                version="v1beta1",
                namespace=K8S_NAMESPACE,
                plural="inferenceservices",
                name=VLLM_IS_NAME,
            )
            current_args = (is_obj.get("spec", {}).get("predictor", {})
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
            custom.patch_namespaced_custom_object,
            group="serving.kserve.io",
            version="v1beta1",
            namespace=K8S_NAMESPACE,
            plural="inferenceservices",
            name=VLLM_IS_NAME,
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
