import os
import asyncio
import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Dict

logger = logging.getLogger(__name__)

router = APIRouter()

K8S_NAMESPACE = os.getenv("K8S_NAMESPACE", "default")
K8S_CONFIGMAP = os.getenv("K8S_CONFIGMAP_NAME", "vllm-config")

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


class VllmConfigPatchRequest(BaseModel):
    data: Dict[str, str]


def _get_k8s_core():
    try:
        from kubernetes import client, config as k8s_config
        try:
            k8s_config.load_incluster_config()
        except Exception:
            k8s_config.load_kube_config()
        return client.CoreV1Api()
    except Exception as e:
        logger.warning("[VllmConfig] K8s client not available: %s", e)
        return None


@router.get("")
async def get_vllm_config():
    core = await asyncio.to_thread(_get_k8s_core)
    if core is None:
        raise HTTPException(status_code=503, detail="Kubernetes not available")
    try:
        cm = await asyncio.to_thread(
            core.read_namespaced_config_map,
            name=K8S_CONFIGMAP,
            namespace=K8S_NAMESPACE,
        )
        return {"success": True, "data": cm.data or {}}
    except Exception as e:
        logger.error("[VllmConfig] Failed to read ConfigMap: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("")
async def patch_vllm_config(request: VllmConfigPatchRequest):
    # 키 유효성 검증
    invalid_keys = set(request.data.keys()) - ALLOWED_CONFIG_KEYS
    if invalid_keys:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid config keys: {sorted(invalid_keys)}. Allowed: {sorted(ALLOWED_CONFIG_KEYS)}",
        )

    # 튜너 실행 중 체크
    try:
        from services.shared import load_engine as _le  # noqa
        from routers.tuner import auto_tuner
        if auto_tuner.is_running:
            raise HTTPException(status_code=409, detail="Tuner is running, cannot modify config")
    except HTTPException:
        raise
    except Exception:
        pass  # auto_tuner 접근 불가 시 진행

    core = await asyncio.to_thread(_get_k8s_core)
    if core is None:
        raise HTTPException(status_code=503, detail="Kubernetes not available")

    try:
        patch_body = {"data": request.data}
        await asyncio.to_thread(
            core.patch_namespaced_config_map,
            name=K8S_CONFIGMAP,
            namespace=K8S_NAMESPACE,
            body=patch_body,
        )
        return {"success": True, "updated_keys": list(request.data.keys())}
    except Exception as e:
        logger.error("[VllmConfig] Failed to patch ConfigMap: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
