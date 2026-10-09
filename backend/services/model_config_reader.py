import asyncio
import json
import logging
import re
import time
from typing import Any

import httpx
from services.model_analysis import ModelAnalysis, ModelArtifacts, analyze_config

logger = logging.getLogger(__name__)

_MODEL_DIR = "/mnt/models"
_SECTION = "__VLLM_OPTIMIZER_SECTION__"
# Upper bound per auxiliary file so a pathological tokenizer_config cannot flood the exec stream.
_MAX_AUX_BYTES = 4 * 1024 * 1024
# One exec round-trip. Sections: config.json, openvino_config.json, weight bytes, generation_config.json,
# tokenizer_config.json, chat_template.jinja, custom-code *.py names.
_READ_SCRIPT = (
    f"cat {_MODEL_DIR}/config.json; echo; echo {_SECTION}; "
    f"cat {_MODEL_DIR}/openvino_config.json 2>/dev/null; echo; echo {_SECTION}; "
    f"du -cbL {_MODEL_DIR}/*.safetensors {_MODEL_DIR}/*.bin {_MODEL_DIR}/*.gguf 2>/dev/null | tail -1; "
    f"echo {_SECTION}; head -c {_MAX_AUX_BYTES} {_MODEL_DIR}/generation_config.json 2>/dev/null; echo; echo {_SECTION}; "
    f"head -c {_MAX_AUX_BYTES} {_MODEL_DIR}/tokenizer_config.json 2>/dev/null; echo; echo {_SECTION}; "
    f"head -c {_MAX_AUX_BYTES} {_MODEL_DIR}/chat_template.jinja 2>/dev/null; echo; echo {_SECTION}; "
    f"ls {_MODEL_DIR}/*.py 2>/dev/null"
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


_LABEL_RE = re.compile(r'(\w+)="([^"]*)"')


def _label_int(value: str | None) -> int | None:
    try:
        return int(float(value)) if value not in (None, "", "None") else None
    except ValueError:
        return None


def _label_float(value: str | None) -> float | None:
    try:
        return float(value) if value not in (None, "", "None") else None
    except ValueError:
        return None


def parse_cache_config_info(text: str) -> dict[str, Any] | None:
    """Extract vLLM's allocated KV pool from the ``vllm:cache_config_info`` gauge labels.

    Newer vLLM exposes ``kv_cache_size_tokens``/``kv_cache_max_concurrency``; older releases only
    ``num_gpu_blocks`` × ``block_size``. Works for both the ``vllm:`` and ``kserve_vllm:`` prefixes.
    """
    for line in text.splitlines():
        name, brace, rest = line.partition("{")
        if not brace or not name.endswith("vllm:cache_config_info"):
            continue
        labels = dict(_LABEL_RE.findall(rest))
        block_size = _label_int(labels.get("block_size"))
        tokens = _label_int(labels.get("kv_cache_size_tokens"))
        if tokens is None:
            blocks = _label_int(labels.get("num_gpu_blocks"))
            tokens = blocks * block_size if blocks and block_size else None
        if not tokens:
            return None
        return {
            "kv_cache_size_tokens": tokens,
            "max_concurrency": _label_float(labels.get("kv_cache_max_concurrency")),
            "block_size": block_size,
            "gpu_memory_utilization": _label_float(labels.get("gpu_memory_utilization")),
            "prefix_caching": labels.get("enable_prefix_caching") == "True",
            "cache_dtype": labels.get("cache_dtype"),
            "num_gpu_blocks": _label_int(labels.get("num_gpu_blocks")),
            "mamba_cache_mode": labels.get("mamba_cache_mode"),
        }
    return None


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


def parse_read_artifacts(raw: str) -> ModelArtifacts | None:
    """Auxiliary files from the sections after the weight bytes; None when the exec output predates them."""
    parts = raw.split(_SECTION)
    if len(parts) < 7:
        return None
    template = parts[5].strip("\n")
    return ModelArtifacts(
        generation_config=_parse_json(parts[3]),
        tokenizer_config=_parse_json(parts[4]),
        chat_template=template if template.strip() else None,
        custom_code_files=sorted(p.rsplit("/", 1)[-1] for p in parts[6].split() if p.endswith(".py")),
    )


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
        artifacts: ModelArtifacts | None = None
        weight_bytes: int | None = None
        if namespace and pod_label_selector:
            pod_name, _pod_ip = await self._find_running_pod(namespace, pod_label_selector)
            if pod_name:
                raw = await self._exec(namespace, pod_name, container, ["sh", "-c", _READ_SCRIPT])
                if raw:
                    cfg, ov_cfg, weight_bytes = parse_read_output(raw)
                    artifacts = parse_read_artifacts(raw) if cfg is not None else None

        if cfg is None and served_name is None:
            return None

        analysis = analyze_config(cfg or {}, kv_cache_dtype=kv_cache_dtype, openvino_cfg=ov_cfg, artifacts=artifacts)
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

    async def read_observed_kv(
        self, namespace: str, pod_label_selector: str, port: int, scheme: str
    ) -> dict[str, Any] | None:
        """vLLM's measured KV pool from a running target pod's /metrics (needs only pods list)."""
        pod_name, pod_ip = await self._find_running_pod(namespace, pod_label_selector)
        if not pod_ip:
            return None
        try:
            async with httpx.AsyncClient(verify=False, timeout=5.0) as http:
                resp = await http.get(f"{scheme}://{pod_ip}:{port}/metrics")
                resp.raise_for_status()
        except httpx.HTTPError as e:
            logger.debug("[ModelConfigReader] metrics scrape of %s failed: %s", pod_name, e)
            return None
        observed = parse_cache_config_info(resp.text)
        if observed is not None:
            observed["pod"] = pod_name
        return observed

    async def _find_running_pod(self, namespace: str, label_selector: str) -> tuple[str | None, str | None]:
        try:
            from kubernetes import client as k8s_client
            from kubernetes import config as k8s_config

            def _find() -> tuple[str | None, str | None]:
                try:
                    k8s_config.load_incluster_config()
                except k8s_config.ConfigException:
                    try:
                        k8s_config.load_kube_config()
                    except k8s_config.ConfigException:
                        return None, None
                core = k8s_client.CoreV1Api()
                pods = core.list_namespaced_pod(namespace, label_selector=label_selector)
                for pod in pods.items:
                    if pod.status and pod.status.phase == "Running":
                        return pod.metadata.name, pod.status.pod_ip
                return None, None

            return await asyncio.to_thread(_find)
        except Exception as e:
            logger.debug("[ModelConfigReader] pod lookup failed (%s): %s", label_selector, e)
            return None, None

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
