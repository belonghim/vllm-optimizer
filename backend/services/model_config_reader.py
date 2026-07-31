import asyncio
import json
import logging
from dataclasses import dataclass

import httpx

logger = logging.getLogger(__name__)


@dataclass
class ModelConfigInfo:
    """Model architecture info derived from config.json / vLLM API / openvino_model.bin."""

    storage_uri: str | None = None
    actual_served_name: str | None = None
    max_position_embeddings: int | None = None
    num_hidden_layers: int | None = None
    num_key_value_heads: int | None = None
    num_attention_heads: int | None = None
    hidden_size: int | None = None
    kv_dtype_bytes: int = 2  # fp16 default
    model_weight_gib: float | None = None

    @property
    def head_dim(self) -> int | None:
        if self.hidden_size and self.num_attention_heads:
            return self.hidden_size // self.num_attention_heads
        return None

    def kv_bytes_per_token_per_layer(self) -> int | None:
        hd = self.head_dim
        if self.num_key_value_heads and hd:
            return 2 * self.num_key_value_heads * hd * self.kv_dtype_bytes
        return None


class ModelConfigReader:
    """Reads model config from vLLM API (primary) or K8s pod exec (fallback).

    Results are cached by storageUri for the lifetime of the tuning session.
    All failures degrade gracefully — None is returned instead of raising.
    """

    def __init__(self) -> None:
        self._cache: dict[str, ModelConfigInfo] = {}

    def invalidate(self, storage_uri: str) -> None:
        """Evict cached info when storageUri changes."""
        self._cache.pop(storage_uri, None)

    async def read(
        self,
        vllm_endpoint: str,
        storage_uri: str | None = None,
        namespace: str | None = None,
        pod_label_selector: str | None = None,
    ) -> ModelConfigInfo | None:
        cache_key = storage_uri or vllm_endpoint
        if cache_key in self._cache:
            return self._cache[cache_key]

        info = ModelConfigInfo(storage_uri=storage_uri)
        found_anything = False

        # Step 1: vLLM /v1/models API — no RBAC risk, always try first.
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{vllm_endpoint.rstrip('/')}/v1/models")
                if resp.status_code == 200:
                    models = resp.json().get("data", [])
                    if models:
                        max_model_len = models[0].get("max_model_len")
                        if isinstance(max_model_len, int) and max_model_len > 0:
                            info.max_position_embeddings = max_model_len
                            found_anything = True
                        model_id = models[0].get("id")
                        if isinstance(model_id, str) and model_id:
                            info.actual_served_name = model_id
        except Exception as e:
            logger.debug("[ModelConfigReader] vLLM API fetch failed: %s", e)

        # Step 2: K8s pod exec for config.json + openvino_model.bin size.
        # Requires pods/exec RBAC — skipped if namespace/selector not provided.
        if namespace and pod_label_selector:
            pod_name = await self._find_running_pod(namespace, pod_label_selector)
            if pod_name:
                config_raw = await self._exec_cat(namespace, pod_name, "/mnt/models/config.json")
                if config_raw:
                    self._parse_config_json(config_raw, info)
                    found_anything = True

                # OpenVINO models use .bin instead of safetensors
                for weight_path in ("/mnt/models/openvino_model.bin", "/mnt/models/model.safetensors"):
                    bin_bytes = await self._exec_file_size(namespace, pod_name, weight_path)
                    if bin_bytes and bin_bytes > 0:
                        info.model_weight_gib = bin_bytes / (1024**3)
                        found_anything = True
                        break

        if found_anything:
            self._cache[cache_key] = info
            return info
        return None

    def _parse_config_json(self, raw: str, info: ModelConfigInfo) -> None:
        try:
            cfg = json.loads(raw)
        except json.JSONDecodeError as e:
            logger.debug("[ModelConfigReader] config.json parse error: %s", e)
            return

        # max_position_embeddings from API already takes precedence (it's the effective limit).
        if not info.max_position_embeddings:
            val = cfg.get("max_position_embeddings")
            if isinstance(val, int) and val > 0:
                info.max_position_embeddings = val

        for attr, key in [
            ("num_hidden_layers", "num_hidden_layers"),
            ("num_key_value_heads", "num_key_value_heads"),
            ("num_attention_heads", "num_attention_heads"),
            ("hidden_size", "hidden_size"),
        ]:
            val = cfg.get(key)
            if isinstance(val, int) and val > 0:
                setattr(info, attr, val)

        dtype = cfg.get("torch_dtype", "float16")
        info.kv_dtype_bytes = 2 if dtype in ("float16", "bfloat16") else 4

    async def _find_running_pod(self, namespace: str, label_selector: str) -> str | None:
        try:
            from kubernetes import client as k8s_client
            from kubernetes import config as k8s_config

            def _find() -> str | None:
                try:
                    k8s_config.load_incluster_config()
                except k8s_config.ConfigException:
                    try:
                        k8s_config.load_kube_config()
                    except k8s_config.ConfigException:
                        return None
                core = k8s_client.CoreV1Api()
                pods = core.list_namespaced_pod(namespace, label_selector=label_selector)
                for pod in pods.items:
                    if pod.status and pod.status.phase == "Running":
                        return pod.metadata.name  # type: ignore[return-value]
                return None

            return await asyncio.to_thread(_find)
        except Exception as e:
            logger.debug("[ModelConfigReader] pod lookup failed (%s): %s", label_selector, e)
            return None

    async def _exec_cat(self, namespace: str, pod_name: str, path: str) -> str | None:
        try:
            from kubernetes import client as k8s_client
            from kubernetes import config as k8s_config
            from kubernetes.stream import stream

            def _exec() -> str | None:
                try:
                    k8s_config.load_incluster_config()
                except k8s_config.ConfigException:
                    try:
                        k8s_config.load_kube_config()
                    except k8s_config.ConfigException:
                        return None
                core = k8s_client.CoreV1Api()
                result = stream(
                    core.connect_get_namespaced_pod_exec,
                    pod_name,
                    namespace,
                    command=["cat", path],
                    stderr=False,
                    stdin=False,
                    stdout=True,
                    tty=False,
                )
                return result if isinstance(result, str) and result.strip() else None

            return await asyncio.to_thread(_exec)
        except Exception as e:
            logger.debug("[ModelConfigReader] exec cat %s on %s failed: %s", path, pod_name, e)
            return None

    async def _exec_file_size(self, namespace: str, pod_name: str, path: str) -> int | None:
        try:
            from kubernetes import client as k8s_client
            from kubernetes import config as k8s_config
            from kubernetes.stream import stream

            def _exec() -> str | None:
                try:
                    k8s_config.load_incluster_config()
                except k8s_config.ConfigException:
                    try:
                        k8s_config.load_kube_config()
                    except k8s_config.ConfigException:
                        return None
                core = k8s_client.CoreV1Api()
                result = stream(
                    core.connect_get_namespaced_pod_exec,
                    pod_name,
                    namespace,
                    command=["stat", "-c", "%s", path],
                    stderr=False,
                    stdin=False,
                    stdout=True,
                    tty=False,
                )
                return result if isinstance(result, str) else None

            raw = await asyncio.to_thread(_exec)
            if raw and raw.strip().isdigit():
                return int(raw.strip())
        except Exception as e:
            logger.debug("[ModelConfigReader] exec stat %s on %s failed: %s", path, pod_name, e)
        return None


_reader = ModelConfigReader()


def get_model_config_reader() -> ModelConfigReader:
    return _reader
