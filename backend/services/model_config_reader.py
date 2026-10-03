import asyncio
import json
import logging
import time

import httpx
from services.model_analysis import ModelAnalysis, analyze_config

logger = logging.getLogger(__name__)

_MODEL_DIR = "/mnt/models"
_SECTION = "__VLLM_OPTIMIZER_SECTION__"
# One exec round-trip: config.json, optional openvino_config.json, total weight file bytes.
_READ_SCRIPT = (
    f"cat {_MODEL_DIR}/config.json; echo; echo {_SECTION}; "
    f"cat {_MODEL_DIR}/openvino_config.json 2>/dev/null; echo; echo {_SECTION}; "
    f"du -cbL {_MODEL_DIR}/*.safetensors {_MODEL_DIR}/*.bin {_MODEL_DIR}/*.gguf 2>/dev/null | tail -1"
)


def _parse_json(raw: str) -> dict | None:
    raw = raw.strip()
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as e:
        logger.debug("[ModelConfigReader] JSON parse error: %s", e)
        return None
    return parsed if isinstance(parsed, dict) else None


def parse_read_output(raw: str) -> tuple[dict | None, dict | None, int | None]:
    parts = raw.split(_SECTION)
    cfg = _parse_json(parts[0]) if parts else None
    ov_cfg = _parse_json(parts[1]) if len(parts) > 1 else None
    weight_bytes: int | None = None
    if len(parts) > 2:
        first = parts[2].strip().split()
        if first and first[0].isdigit() and int(first[0]) > 0:
            weight_bytes = int(first[0])
    return cfg, ov_cfg, weight_bytes


class ModelConfigReader:
    """Reads the target model's config.json via pod exec and analyzes it deterministically.

    Results are cached per (storageUri, kv-cache-dtype). Failures degrade to None — never raise.
    """

    _CACHE_TTL = 3600.0

    def __init__(self) -> None:
        self._cache: dict[str, ModelAnalysis] = {}
        self._cache_times: dict[str, float] = {}

    def invalidate(self, storage_uri: str | None = None) -> None:
        if storage_uri is None:
            self._cache.clear()
            self._cache_times.clear()
            return
        for key in [k for k in self._cache if k.startswith(f"{storage_uri}|")]:
            self._cache.pop(key, None)
            self._cache_times.pop(key, None)

    async def read(
        self,
        vllm_endpoint: str,
        storage_uri: str | None = None,
        namespace: str | None = None,
        pod_label_selector: str | None = None,
        container: str | None = None,
        kv_cache_dtype: str | None = None,
    ) -> ModelAnalysis | None:
        cache_key = f"{storage_uri or vllm_endpoint}|{kv_cache_dtype or 'auto'}"
        cached = self._cache.get(cache_key)
        if cached is not None and time.time() - self._cache_times.get(cache_key, 0.0) < self._CACHE_TTL:
            return cached

        served_name, served_max_len = await self._read_served_model(vllm_endpoint)

        cfg = ov_cfg = None
        weight_bytes: int | None = None
        if namespace and pod_label_selector:
            pod_name = await self._find_running_pod(namespace, pod_label_selector)
            if pod_name:
                raw = await self._exec(namespace, pod_name, container, ["sh", "-c", _READ_SCRIPT])
                if raw:
                    cfg, ov_cfg, weight_bytes = parse_read_output(raw)

        if cfg is None and served_name is None:
            return None

        analysis = analyze_config(cfg or {}, kv_cache_dtype=kv_cache_dtype, openvino_cfg=ov_cfg)
        if cfg is None:
            analysis.warnings.insert(0, "config.json을 읽지 못함 — pods/exec 권한 또는 파드 상태 확인")
        analysis.served_model_name = served_name
        analysis.served_max_model_len = served_max_len
        if weight_bytes:
            analysis.model_weight_gib = weight_bytes / (1024**3)

        if cfg is not None:
            self._cache[cache_key] = analysis
            self._cache_times[cache_key] = time.time()
        return analysis

    async def _read_served_model(self, vllm_endpoint: str) -> tuple[str | None, int | None]:
        from services.shared import get_internal_client

        try:
            resp = await get_internal_client().get(f"{vllm_endpoint.rstrip('/')}/v1/models", timeout=5.0)
            if resp.status_code != 200:
                return None, None
            models = resp.json().get("data", [])
            if not models:
                return None, None
            model_id = models[0].get("id")
            max_len = models[0].get("max_model_len")
            return (
                model_id if isinstance(model_id, str) and model_id else None,
                max_len if isinstance(max_len, int) and max_len > 0 else None,
            )
        except (httpx.HTTPError, ValueError, AttributeError) as e:
            logger.debug("[ModelConfigReader] vLLM API fetch failed: %s", e)
            return None, None

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

    async def _exec(self, namespace: str, pod_name: str, container: str | None, command: list[str]) -> str | None:
        try:
            from kubernetes import client as k8s_client
            from kubernetes import config as k8s_config
            from kubernetes.stream import stream

            def _run() -> str | None:
                try:
                    k8s_config.load_incluster_config()
                except k8s_config.ConfigException:
                    try:
                        k8s_config.load_kube_config()
                    except k8s_config.ConfigException:
                        return None
                core = k8s_client.CoreV1Api()
                kwargs = {"container": container} if container else {}
                result = stream(
                    core.connect_get_namespaced_pod_exec,
                    pod_name,
                    namespace,
                    command=command,
                    stderr=False,
                    stdin=False,
                    stdout=True,
                    tty=False,
                    **kwargs,
                )
                return result if isinstance(result, str) and result.strip() else None

            return await asyncio.to_thread(_run)
        except Exception as e:
            logger.debug("[ModelConfigReader] exec %s on %s failed: %s", command, pod_name, e)
            return None


_reader = ModelConfigReader()


def get_model_config_reader() -> ModelConfigReader:
    return _reader
