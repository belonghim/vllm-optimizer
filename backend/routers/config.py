import logging
import os
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from kubernetes import config as k8s_config
from kubernetes.client.exceptions import ApiException
from models.default_targets import DefaultTargetItem, DefaultTargetsPatch, DefaultTargetsResponse
from pydantic import BaseModel
from services.model_resolver import resolve_model_name
from services.rate_limiter import limiter
from services.shared import runtime_config

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/config", tags=["config"])


class ConfigResponse(BaseModel):
    vllm_endpoint: str
    vllm_namespace: str
    vllm_is_name: str
    vllm_model_name: str
    resolved_model_name: str
    cr_type: str
    configmap_updated: bool = True


class ConfigPatch(BaseModel):
    vllm_endpoint: str | None = None
    vllm_namespace: str | None = None
    vllm_is_name: str | None = None
    cr_type: Literal["inferenceservice", "llminferenceservice"] | None = None


@router.get("", response_model=ConfigResponse)
@limiter.limit("60/minute")
async def get_config(request: Request) -> ConfigResponse:
    endpoint = runtime_config.vllm_endpoint
    model_name = os.getenv("VLLM_MODEL", "auto")
    try:
        resolved = await resolve_model_name(endpoint)
    except (RuntimeError, ValueError, OSError):
        resolved = model_name
    return ConfigResponse(
        vllm_endpoint=endpoint,
        vllm_namespace=runtime_config.vllm_namespace,
        vllm_is_name=runtime_config.vllm_is_name,
        vllm_model_name=model_name,
        resolved_model_name=resolved,
        cr_type=runtime_config.cr_type,
        configmap_updated=True,
    )


@router.patch("", response_model=ConfigResponse)
@limiter.limit("60/minute")
async def patch_config(request: Request, patch: ConfigPatch) -> ConfigResponse:
    if patch.cr_type is not None:
        try:
            from routers.tuner import auto_tuner

            if auto_tuner.is_running:
                raise HTTPException(
                    status_code=409,
                    detail="Auto-tuner is running. Cannot change CR type.",
                )
        except HTTPException:
            raise
        except (ImportError, AttributeError, RuntimeError):
            pass

    if patch.vllm_endpoint is not None:
        runtime_config.set_vllm_endpoint(patch.vllm_endpoint)
    if patch.vllm_namespace is not None:
        runtime_config.set_vllm_namespace(patch.vllm_namespace)
    if patch.vllm_is_name is not None:
        runtime_config.set_vllm_is_name(patch.vllm_is_name)

    configmap_updated = True
    if patch.cr_type is not None:
        runtime_config.set_cr_type(patch.cr_type)

        try:
            import asyncio

            from kubernetes import client as k8s_client
            from kubernetes import config as k8s_config

            def _patch_cm():
                try:
                    k8s_config.load_incluster_config()
                except k8s_config.ConfigException:
                    k8s_config.load_kube_config()
                v1 = k8s_client.CoreV1Api()
                namespace = os.getenv("POD_NAMESPACE", "vllm-optimizer-dev")
                v1.patch_namespaced_config_map(
                    name="vllm-optimizer-config",
                    namespace=namespace,
                    body={"data": {"VLLM_CR_TYPE": patch.cr_type}},
                )

            await asyncio.to_thread(_patch_cm)
        except (ApiException, OSError, AttributeError) as e:
            logger.warning("ConfigMap patch failed (in-memory applied): %s", e)
            configmap_updated = False

    base = await get_config(request)
    return ConfigResponse(
        vllm_endpoint=base.vllm_endpoint,
        vllm_namespace=base.vllm_namespace,
        vllm_is_name=base.vllm_is_name,
        vllm_model_name=base.vllm_model_name,
        resolved_model_name=base.resolved_model_name,
        cr_type=base.cr_type,
        configmap_updated=configmap_updated,
    )


@router.get("/default-targets", response_model=DefaultTargetsResponse)
@limiter.limit("60/minute")
async def get_default_targets(request: Request) -> DefaultTargetsResponse:
    import asyncio

    from kubernetes import client as k8s_client

    def _read_cm():
        try:
            k8s_config.load_incluster_config()
        except k8s_config.ConfigException:
            k8s_config.load_kube_config()
        v1 = k8s_client.CoreV1Api()
        namespace = os.getenv("POD_NAMESPACE", "vllm-optimizer-dev")
        cm = v1.read_namespaced_config_map(name="vllm-optimizer-config", namespace=namespace)
        return cm.data if cm.data else {}

    try:
        data = await asyncio.to_thread(_read_cm)
    except (ApiException, OSError, AttributeError) as e:
        logger.warning("ConfigMap read failed: %s", e)
        data = {}

    return DefaultTargetsResponse(
        isvc=DefaultTargetItem(
            name=data.get("DEFAULT_ISVC_NAME", ""),
            namespace=data.get("DEFAULT_ISVC_NAMESPACE", ""),
        ),
        llmisvc=DefaultTargetItem(
            name=data.get("DEFAULT_LLMISVC_NAME", ""),
            namespace=data.get("DEFAULT_LLMISVC_NAMESPACE", ""),
        ),
    )


@router.patch("/default-targets", response_model=DefaultTargetsResponse)
@limiter.limit("60/minute")
async def patch_default_targets(request: Request, patch: DefaultTargetsPatch) -> DefaultTargetsResponse:
    import asyncio

    from kubernetes import client as k8s_client

    patch_data: dict[str, str] = {}
    if patch.isvc is not None:
        patch_data["DEFAULT_ISVC_NAME"] = patch.isvc.name
        patch_data["DEFAULT_ISVC_NAMESPACE"] = patch.isvc.namespace
    if patch.llmisvc is not None:
        patch_data["DEFAULT_LLMISVC_NAME"] = patch.llmisvc.name
        patch_data["DEFAULT_LLMISVC_NAMESPACE"] = patch.llmisvc.namespace

    if not patch_data:
        return await get_default_targets(request)

    def _patch_cm():
        try:
            k8s_config.load_incluster_config()
        except k8s_config.ConfigException:
            k8s_config.load_kube_config()
        v1 = k8s_client.CoreV1Api()
        namespace = os.getenv("POD_NAMESPACE", "vllm-optimizer-dev")
        v1.patch_namespaced_config_map(
            name="vllm-optimizer-config",
            namespace=namespace,
            body={"data": patch_data},
        )

    configmap_updated = True
    try:
        await asyncio.to_thread(_patch_cm)
    except (ApiException, OSError, AttributeError) as e:
        logger.warning("ConfigMap patch failed: %s", e)
        configmap_updated = False

    result = await get_default_targets(request)
    result.configmap_updated = configmap_updated
    return result
