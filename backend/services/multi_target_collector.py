# pyright: reportImportCycles=false
import asyncio
import logging
import math
import os
import re
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, cast

import httpx
from kubernetes import client, config
from metrics.prometheus_metrics import update_metrics
from services.cr_adapter import CRAdapter, get_cr_adapter
from services.retry_helper import with_retry as _with_retry
from services.runtime_config_instance import runtime_config

logger = logging.getLogger(__name__)


PROMETHEUS_URL = os.getenv(
    "PROMETHEUS_URL",
    "https://thanos-querier.openshift-monitoring.svc.cluster.local:9091",
)


@dataclass
class VLLMMetrics:
    timestamp: float
    tokens_per_second: float = 0
    requests_per_second: float = 0
    mean_ttft_ms: float = 0
    p99_ttft_ms: float = 0
    mean_e2e_latency_ms: float = 0
    p99_e2e_latency_ms: float = 0
    kv_cache_usage_pct: float = 0
    kv_cache_hit_rate: float = 0
    running_requests: int = 0
    waiting_requests: int = 0
    gpu_memory_used_gb: float = 0
    gpu_memory_total_gb: float = 0
    gpu_utilization_pct: float = 0
    pod_count: int = 0
    pod_ready: int = 0


@dataclass
class TargetCache:
    key: str
    namespace: str
    is_name: str
    latest: VLLMMetrics | None = None
    history: deque[VLLMMetrics] = field(default_factory=lambda: deque(maxlen=3600))
    last_accessed: float = field(default_factory=time.time)
    is_active: bool = True
    has_monitoring_label: bool | None = None
    is_default: bool = False
    last_label_check: float = field(default_factory=time.time)
    cr_type: str = ""
    model_name: str = ""
    prev_counters: dict[str, dict[str, float]] = field(default_factory=dict)


class MultiTargetMetricsCollector:
    MAX_TARGETS: int = 5
    INACTIVE_TIMEOUT: int = 300
    COLLECT_INTERVAL: float = 5.0

    def __init__(self) -> None:
        self._targets: dict[str, TargetCache] = {}
        self._running: bool = False
        self._collect_task: asyncio.Task[None] | None = None
        self._cleanup_task: asyncio.Task[None] | None = None
        self._lock: asyncio.Lock = asyncio.Lock()
        self._version: str = "multi-target"
        self._missing_metrics: list[str] = []
        self._start_requests: list[float] = []
        self._collect_interval: float = self.COLLECT_INTERVAL

        self._token: str | None = self._load_token()
        self._k8s_available: bool = False
        self._k8s_core: client.CoreV1Api | None = None
        self._k8s_custom: client.CustomObjectsApi | None = None
        self._default_namespace = os.getenv("VLLM_NAMESPACE", "vllm-lab-dev")
        self._default_is_name = os.getenv("VLLM_DEPLOYMENT_NAME", "llm-ov")
        self._init_k8s()
        self._register_default_target()

    def _adapter_for(self, target: TargetCache) -> CRAdapter:
        return get_cr_adapter(target.cr_type)

    def _register_default_target(self) -> None:
        cr_type = os.getenv("VLLM_CR_TYPE", "inferenceservice")
        key = self.build_target_key(self._default_namespace, self._default_is_name, cr_type)
        self._targets[key] = TargetCache(
            key=key,
            namespace=self._default_namespace,
            is_name=self._default_is_name,
            is_default=True,
            has_monitoring_label=None,
            cr_type=cr_type,
            model_name=self._default_is_name,
        )

    async def _resolve_model_name(self, namespace: str, is_name: str, cr_type: str) -> str:
        if not self._k8s_available or self._k8s_custom is None:
            return is_name

        adapter = get_cr_adapter(cr_type)
        try:
            cr_obj = cast(
                dict[str, Any],
                await asyncio.to_thread(
                    self._k8s_custom.get_namespaced_custom_object,
                    group=adapter.api_group(),
                    version=adapter.api_version(),
                    namespace=namespace,
                    plural=adapter.api_plural(),
                    name=is_name,
                ),
            )
        except client.ApiException:
            return is_name
        except OSError as exc:
            logger.warning(
                "[MultiTargetMetricsCollector] model name resolve failed (%s/%s): %s",
                namespace,
                is_name,
                exc,
            )
            return is_name

        spec = cr_obj.get("spec", {}) if isinstance(cr_obj, dict) else {}
        return adapter.resolve_model_name(spec, is_name)

    def _compute_rates(
        self,
        pod_ip: str,
        target: TargetCache,
        raw_counters: dict[str, float],
        now: float,
    ) -> dict[str, float]:
        rates: dict[str, float] = {}
        if pod_ip not in target.prev_counters:
            target.prev_counters[pod_ip] = {}
        prev = target.prev_counters[pod_ip]
        for metric_name, current_value in raw_counters.items():
            ts_key = metric_name + "_ts"
            if metric_name not in prev:
                prev[metric_name] = current_value
                prev[ts_key] = now
                rates[metric_name] = 0.0
            else:
                prev_val = prev[metric_name]
                prev_ts = prev[ts_key]
                elapsed = now - prev_ts
                if elapsed <= 0:
                    rates[metric_name] = 0.0
                    continue
                delta = current_value - prev_val
                if delta < 0:
                    prev[metric_name] = current_value
                    prev[ts_key] = now
                    rates[metric_name] = 0.0
                    continue
                prev[metric_name] = current_value
                prev[ts_key] = now
                rates[metric_name] = delta / elapsed
        return rates

    def _compute_histogram_stats(self, raw_histograms: dict[str, float]) -> dict[str, float]:
        ttft_sum = raw_histograms.get("ttft_sum", 0.0)
        ttft_count = raw_histograms.get("ttft_count", 0.0)
        latency_sum = raw_histograms.get("latency_sum", 0.0)
        latency_count = raw_histograms.get("latency_count", 0.0)
        mean_ttft_ms = (ttft_sum / ttft_count) * 1000 if ttft_count > 0 else 0.0
        mean_e2e_latency_ms = (latency_sum / latency_count) * 1000 if latency_count > 0 else 0.0
        return {"mean_ttft_ms": mean_ttft_ms, "mean_e2e_latency_ms": mean_e2e_latency_ms}

    def _get_default_target(self) -> TargetCache | None:
        if not self._targets:
            return None
        for target in self._targets.values():
            if target.is_default:
                return target
        return next(iter(self._targets.values()))

    def _is_default_target(self, namespace: str, is_name: str) -> bool:
        default_target = self._get_default_target()
        if default_target is None:
            return False
        return default_target.namespace == namespace and default_target.is_name == is_name

    @property
    def latest(self) -> VLLMMetrics | None:
        default_target = self._get_default_target()
        return default_target.latest if default_target else None

    @property
    def history(self) -> list[VLLMMetrics]:
        default_target = self._get_default_target()
        if default_target is None:
            return []
        return list(default_target.history)

    @property
    def version(self) -> str:
        return self._version

    @property
    def missing_metrics(self) -> list[str]:
        return self._missing_metrics

    def get_target(self, namespace: str, is_name: str, cr_type: str | None = None) -> "TargetCache | None":
        """Resolve target cache entry using the canonical key format."""
        key = self.build_target_key(namespace, is_name, cr_type)
        result = self._targets.get(key)
        if result is None:
            logger.warning("Target not found: key=%s (registered: %s)", key, list(self._targets.keys()))
        return result

    def record_start_request(self, interval: float) -> None:
        self._start_requests.append(interval)

    async def start_collection(self, interval: float = 2.0) -> None:
        self.record_start_request(interval)
        self._collect_interval = interval
        await self._ensure_collect_loop()
        try:
            while self._running:
                await asyncio.sleep(0.2)
        except asyncio.CancelledError:
            self.stop()
            raise

    def stop(self) -> None:
        self._running = False
        if self._collect_task is not None and not self._collect_task.done():
            _ = self._collect_task.cancel()
        if self._cleanup_task is not None and not self._cleanup_task.done():
            _ = self._cleanup_task.cancel()

    def set_default_target(self, namespace: str | None = None, is_name: str | None = None) -> None:
        default_target = self._get_default_target()
        if default_target is None:
            return

        old_key = default_target.key
        new_namespace = namespace if namespace is not None else default_target.namespace
        new_is_name = is_name if is_name is not None else default_target.is_name
        new_key = self.build_target_key(new_namespace, new_is_name, default_target.cr_type)

        default_target.namespace = new_namespace
        default_target.is_name = new_is_name
        default_target.key = new_key

        if old_key != new_key:
            _ = self._targets.pop(old_key, None)
            self._targets[new_key] = default_target

        self._default_namespace = new_namespace
        self._default_is_name = new_is_name

    def get_history_dict(self, last_n: int = 60, include_metadata: bool = True) -> list[dict[str, Any]]:
        default_target = self._get_default_target()
        if default_target is None:
            return []
        history = list(default_target.history)[-last_n:]
        return [
            {
                "timestamp": m.timestamp,
                "tps": m.tokens_per_second,
                "rps": m.requests_per_second,
                "ttft_mean": m.mean_ttft_ms,
                "ttft_p99": m.p99_ttft_ms,
                "latency_mean": m.mean_e2e_latency_ms,
                "latency_p99": m.p99_e2e_latency_ms,
                "kv_cache": m.kv_cache_usage_pct,
                "kv_hit_rate": m.kv_cache_hit_rate,
                "running": m.running_requests,
                "waiting": m.waiting_requests,
                "gpu_mem_used": m.gpu_memory_used_gb,
                "gpu_mem_total": m.gpu_memory_total_gb,
                "gpu_util": m.gpu_utilization_pct,
                "pods": m.pod_count,
                "pods_ready": m.pod_ready,
                "_metadata": {
                    "vllm_version": self._version,
                    "missing_metrics": self._missing_metrics,
                }
                if include_metadata
                else None,
            }
            for m in history
        ]

    async def get_metrics(self, namespace: str, is_name: str, cr_type: str | None = None) -> VLLMMetrics | None:
        key = self.build_target_key(namespace, is_name, cr_type)
        async with self._lock:
            target = self._targets.get(key)
            if target is None:
                return None
            target.last_accessed = time.time()
            target.is_active = True
            latest = target.latest

        await self._ensure_collect_loop()
        return latest

    async def register_target(self, namespace: str, is_name: str, cr_type: str | None = None) -> bool:
        if cr_type is None:
            cr_type = runtime_config.cr_type
        key = self.build_target_key(namespace, is_name, cr_type)
        async with self._lock:
            existing = self._targets.get(key)
            if existing is not None:
                existing.last_accessed = time.time()
                existing.is_active = True
                # Refresh monitoring label periodically (every 5 minutes)
                if time.time() - existing.last_label_check > 300:
                    existing.has_monitoring_label = await self.check_namespace_monitoring_label(namespace)
                    existing.model_name = await self._resolve_model_name(namespace, is_name, existing.cr_type)
                    existing.last_label_check = time.time()
            else:
                if len(self._targets) >= self.MAX_TARGETS:
                    return False

                has_monitoring_label = await self.check_namespace_monitoring_label(namespace)
                model_name = await self._resolve_model_name(namespace, is_name, cr_type)
                is_first = not self._targets
                self._targets[key] = TargetCache(
                    key=key,
                    namespace=namespace,
                    is_name=is_name,
                    has_monitoring_label=has_monitoring_label,
                    is_default=is_first,
                    cr_type=cr_type,
                    model_name=model_name,
                )

        await self._ensure_collect_loop()
        return True

    async def remove_target(self, namespace: str, is_name: str, cr_type: str | None = None) -> bool:
        key = self.build_target_key(namespace, is_name, cr_type)
        async with self._lock:
            removed = self._targets.pop(key, None)
            should_stop = not self._targets

        if should_stop:
            self._running = False
            if self._collect_task and not self._collect_task.done():
                _ = self._collect_task.cancel()

        return removed is not None

    async def _ensure_collect_loop(self) -> None:
        if self._collect_task is not None and not self._collect_task.done():
            return
        self._running = True
        self._collect_task = asyncio.create_task(self._collect_loop())
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())

    async def _collect_loop(self) -> None:
        try:
            while self._running:
                now = time.time()
                async with self._lock:
                    targets = list(self._targets.values())

                active_targets: list[TargetCache] = []
                for target in targets:
                    target.is_active = (now - target.last_accessed) <= self.INACTIVE_TIMEOUT
                    if target.is_active:
                        active_targets.append(target)

                if active_targets:
                    results = await asyncio.gather(
                        *(self._collect_target(target) for target in active_targets),
                        return_exceptions=True,
                    )
                    for target, result in zip(active_targets, results, strict=False):
                        if isinstance(result, Exception):
                            logger.warning(
                                "[MultiTargetMetricsCollector] target=%s collect failed: %s",
                                target.key,
                                result,
                            )

                await asyncio.sleep(self._collect_interval)
        except asyncio.CancelledError:
            logger.debug("[MultiTargetMetricsCollector] collection loop cancelled")
            raise

    async def _cleanup_loop(self) -> None:
        CLEANUP_INTERVAL = 60.0
        try:
            while self._running:
                await asyncio.sleep(CLEANUP_INTERVAL)
                async with self._lock:
                    now = time.time()
                    keys_to_remove = [
                        key
                        for key, target in self._targets.items()
                        if not target.is_default and (now - target.last_accessed) > self.INACTIVE_TIMEOUT
                    ]
                    for key in keys_to_remove:
                        target = self._targets[key]
                        logger.info(
                            "[MultiTargetMetricsCollector] Removing inactive target: %s/%s",
                            target.namespace,
                            target.is_name,
                        )
                        del self._targets[key]
        except asyncio.CancelledError:
            logger.debug("[MultiTargetMetricsCollector] cleanup loop cancelled")
            raise

    def _build_target_queries(self, namespace: str, is_name: str, cr_type: str | None = None) -> dict[str, str]:
        if cr_type is None:
            cr_type = runtime_config.cr_type
        adapter = get_cr_adapter(cr_type)
        prefix = adapter.metric_prefix()
        selector = f'namespace="{namespace}", job="{adapter.prometheus_job(is_name, namespace)}"'
        dcgm_selector = f'exported_namespace="{namespace}", exported_pod=~"{adapter.dcgm_pod_pattern(is_name)}"'
        return {
            "tokens_per_second": (
                f"sum(rate({prefix}num_generated_tokens{{{selector}}}[1m])) "
                f"or sum(rate({prefix}generation_tokens_total{{{selector}}}[1m]))"
            ),
            "requests_per_second": (
                f"sum(rate({prefix}num_requests_finished{{{selector}}}[1m])) "
                f"or sum(rate({prefix}request_success_total{{{selector}}}[1m]))"
            ),
            "mean_ttft_ms": (
                f"histogram_quantile(0.5, sum by (le) "
                f"(rate({prefix}time_to_first_token_seconds_bucket{{{selector}}}[1m]))) * 1000"
            ),
            "p99_ttft_ms": (
                f"histogram_quantile(0.99, sum by (le) "
                f"(rate({prefix}time_to_first_token_seconds_bucket{{{selector}}}[1m]))) * 1000"
            ),
            "mean_e2e_latency_ms": (
                f"histogram_quantile(0.5, sum by (le) "
                f"(rate({prefix}e2e_request_latency_seconds_bucket{{{selector}}}[1m]))) * 1000"
            ),
            "p99_e2e_latency_ms": (
                f"histogram_quantile(0.99, sum by (le) "
                f"(rate({prefix}e2e_request_latency_seconds_bucket{{{selector}}}[1m]))) * 1000"
            ),
            "kv_cache_usage_pct": f"avg({prefix}kv_cache_usage_perc{{{selector}}}) * 100",
            "kv_cache_hit_rate": (
                f"avg({prefix}kv_cache_hit_rate{{{selector}}}) or avg({prefix}cache_config_info{{{selector}}})"
            ),
            "running_requests": f"sum({prefix}num_requests_running{{{selector}}})",
            "waiting_requests": f"sum({prefix}num_requests_waiting{{{selector}}})",
            "gpu_memory_used_gb": (
                f"(sum({prefix}gpu_memory_usage_bytes{{{selector}}}) / 1024^3) "
                f"or {prefix}gpu_cache_usage_perc{{{selector}}} "
                f"or (sum(DCGM_FI_DEV_FB_USED{{{dcgm_selector}}}) / 1024)"
            ),
            "gpu_memory_total_gb": (
                f"(sum({prefix}gpu_memory_total_bytes{{{selector}}}) / 1024^3) "
                f"or ({prefix}gpu_cache_usage_perc{{{selector}}} * 0 + 1) "
                f"or (sum(DCGM_FI_DEV_FB_USED{{{dcgm_selector}}} + DCGM_FI_DEV_FB_FREE{{{dcgm_selector}}} + DCGM_FI_DEV_FB_RESERVED{{{dcgm_selector}}}) / 1024)"
            ),
            "gpu_utilization_pct": (
                f"(avg({prefix}gpu_utilization_perc{{{selector}}}) * 100) "
                f"or (avg({prefix}gpu_utilization{{{selector}}}) * 100) "
                f"or sum(DCGM_FI_DEV_GPU_UTIL{{{dcgm_selector}}})"
            ),
        }

    def _build_pod_queries(self, namespace: str, is_name: str, cr_type: str | None = None) -> dict[str, str]:
        if cr_type is None:
            cr_type = runtime_config.cr_type
        adapter = get_cr_adapter(cr_type)
        prefix = adapter.metric_prefix()
        selector = f'namespace="{namespace}", job="{adapter.prometheus_job(is_name, namespace)}"'
        dcgm_selector = f'exported_namespace="{namespace}", exported_pod=~"{adapter.dcgm_pod_pattern(is_name)}"'
        return {
            "tokens_per_second": (
                f"rate({prefix}num_generated_tokens{{{selector}}}[1m]) "
                f"or rate({prefix}generation_tokens_total{{{selector}}}[1m])"
            ),
            "requests_per_second": (
                f"rate({prefix}num_requests_finished{{{selector}}}[1m]) "
                f"or rate({prefix}request_success_total{{{selector}}}[1m])"
            ),
            "mean_ttft_ms": (
                f"histogram_quantile(0.5, rate({prefix}time_to_first_token_seconds_bucket{{{selector}}}[1m])) * 1000"
            ),
            "p99_ttft_ms": (
                f"histogram_quantile(0.99, rate({prefix}time_to_first_token_seconds_bucket{{{selector}}}[1m])) * 1000"
            ),
            "mean_e2e_latency_ms": (
                f"histogram_quantile(0.5, rate({prefix}e2e_request_latency_seconds_bucket{{{selector}}}[1m])) * 1000"
            ),
            "p99_e2e_latency_ms": (
                f"histogram_quantile(0.99, rate({prefix}e2e_request_latency_seconds_bucket{{{selector}}}[1m])) * 1000"
            ),
            "kv_cache_usage_pct": f"{prefix}kv_cache_usage_perc{{{selector}}} * 100",
            "kv_cache_hit_rate": (
                f"{prefix}kv_cache_hit_rate{{{selector}}} or {prefix}cache_config_info{{{selector}}}"
            ),
            "running_requests": f"{prefix}num_requests_running{{{selector}}}",
            "waiting_requests": f"{prefix}num_requests_waiting{{{selector}}}",
            "gpu_memory_used_gb": (
                f"({prefix}gpu_memory_usage_bytes{{{selector}}} / 1024^3) "
                f"or {prefix}gpu_cache_usage_perc{{{selector}}} "
                f"or (DCGM_FI_DEV_FB_USED{{{dcgm_selector}}} / 1024)"
            ),
            "gpu_memory_total_gb": (
                f"({prefix}gpu_memory_total_bytes{{{selector}}} / 1024^3) "
                f"or ({prefix}gpu_cache_usage_perc{{{selector}}} * 0 + 1) "
                f"or ((DCGM_FI_DEV_FB_USED{{{dcgm_selector}}} + DCGM_FI_DEV_FB_FREE{{{dcgm_selector}}} + DCGM_FI_DEV_FB_RESERVED{{{dcgm_selector}}}) / 1024)"
            ),
            "gpu_utilization_pct": (
                f"({prefix}gpu_utilization_perc{{{selector}}} * 100) "
                f"or ({prefix}gpu_utilization{{{selector}}} * 100) "
                f"or DCGM_FI_DEV_GPU_UTIL{{{dcgm_selector}}}"
            ),
        }

    async def check_namespace_monitoring_label(self, namespace: str) -> bool:
        if not self._k8s_available or self._k8s_core is None:
            return False
        try:
            ns_obj = await asyncio.to_thread(self._k8s_core.read_namespace, name=namespace)
        except client.ApiException as exc:
            logger.warning(
                "[MultiTargetMetricsCollector] namespace label check failed (%s): %s",
                namespace,
                exc,
            )
            return False
        except Exception as exc:  # intentional: any k8s error → return False conservatively
            logger.warning(
                "[MultiTargetMetricsCollector] namespace label check error (%s): %s",
                namespace,
                exc,
            )
            return False

        metadata = getattr(ns_obj, "metadata", None)
        labels_obj = getattr(metadata, "labels", {}) if metadata is not None else {}
        if not isinstance(labels_obj, dict):
            return False
        return labels_obj.get("openshift.io/cluster-monitoring") == "true"

    async def _collect_target(self, target: TargetCache) -> None:
        if os.getenv("METRICS_SOURCE", "thanos") == "direct":
            await self._collect_target_direct(target)
        else:
            await self._collect_target_thanos(target)

    async def _collect_target_thanos(self, target: TargetCache) -> None:
        metrics = VLLMMetrics(timestamp=time.time())

        prom_data = await self._query_prometheus(target.namespace, target.is_name, target.cr_type)
        for key, value in prom_data.items():
            if hasattr(metrics, key):
                setattr(metrics, key, value)

        k8s_data = await self._query_kubernetes_pods(target.namespace, target.is_name, target.cr_type)
        metrics.pod_count = k8s_data.get("pod_count", 0)
        metrics.pod_ready = k8s_data.get("pod_ready", 0)

        if target.is_default:
            update_metrics(metrics)

        target.latest = metrics
        target.history.append(metrics)

    async def _collect_target_direct(self, target: TargetCache) -> None:
        from services.metrics_constants import COUNTER_METRIC_MAP

        adapter = self._adapter_for(target)

        if not self._k8s_available or self._k8s_core is None:
            return

        try:
            pods = cast(
                client.V1PodList,
                await asyncio.to_thread(
                    self._k8s_core.list_namespaced_pod,
                    namespace=target.namespace,
                    label_selector=adapter.pod_label_selector(target.is_name),
                ),
            )
        except Exception as exc:
            logger.warning(
                "[MultiTargetMetricsCollector] direct scrape pod list failed (%s): %s",
                target.key,
                exc,
            )
            return

        items = pods.items or []
        running_pods = [pod for pod in items if pod.status and pod.status.phase == "Running" and pod.status.pod_ip]

        if not running_pods:
            return

        port = adapter.metrics_port()
        now = time.time()

        scrape_results = await asyncio.gather(
            *(self._scrape_pod_metrics(pod.status.pod_ip, port) for pod in running_pods),
            return_exceptions=True,
        )

        counter_fields = {v for v in COUNTER_METRIC_MAP.values() if not v.startswith("_")}
        agg_gauges: dict[str, list[float]] = {}
        agg_hist: dict[str, float] = {}
        all_counter_raws: dict[str, dict[str, float]] = {}

        for pod, result in zip(running_pods, scrape_results, strict=False):
            if isinstance(result, Exception) or not result:
                continue
            pod_ip: str = pod.status.pod_ip
            pod_counters: dict[str, float] = {}
            for k, v in cast(dict[str, float], result).items():
                if k in counter_fields:
                    pod_counters[k] = v
                elif k in (
                    "running_requests",
                    "waiting_requests",
                    "kv_cache_usage_pct",
                    "gpu_utilization_pct",
                    "gpu_memory_used_gb",
                ):
                    agg_gauges.setdefault(k, []).append(v)
                elif k.endswith(("_sum", "_count")):
                    agg_hist[k] = agg_hist.get(k, 0.0) + v
            all_counter_raws[pod_ip] = pod_counters

        metrics = VLLMMetrics(timestamp=now)
        metrics.pod_count = len(items)
        metrics.pod_ready = sum(
            1
            for pod in items
            if pod.status
            and pod.status.phase == "Running"
            and pod.status.container_statuses
            and all(cs.ready for cs in (pod.status.container_statuses or []))
        )

        tps = 0.0
        rps = 0.0
        for pod_ip, counter_raws in all_counter_raws.items():
            rates = self._compute_rates(pod_ip, target, counter_raws, now)
            tps += rates.get("tokens_per_second", 0.0)
            rps += rates.get("requests_per_second", 0.0)
        metrics.tokens_per_second = tps
        metrics.requests_per_second = rps

        if "running_requests" in agg_gauges:
            metrics.running_requests = int(sum(agg_gauges["running_requests"]))
        if "waiting_requests" in agg_gauges:
            metrics.waiting_requests = int(sum(agg_gauges["waiting_requests"]))
        if "kv_cache_usage_pct" in agg_gauges:
            vals = agg_gauges["kv_cache_usage_pct"]
            metrics.kv_cache_usage_pct = (sum(vals) / len(vals)) * 100
        if "gpu_utilization_pct" in agg_gauges:
            vals = agg_gauges["gpu_utilization_pct"]
            metrics.gpu_utilization_pct = sum(vals) / len(vals)
        if "gpu_memory_used_gb" in agg_gauges:
            metrics.gpu_memory_used_gb = sum(agg_gauges["gpu_memory_used_gb"])

        hist_stats = self._compute_histogram_stats(agg_hist)
        metrics.mean_ttft_ms = hist_stats.get("mean_ttft_ms", 0.0)
        metrics.mean_e2e_latency_ms = hist_stats.get("mean_e2e_latency_ms", 0.0)

        if target.is_default:
            update_metrics(metrics)

        target.latest = metrics
        target.history.append(metrics)

    async def _query_prometheus(self, namespace: str, is_name: str, cr_type: str | None = None) -> dict[str, float]:
        from services.shared import internal_client

        if cr_type is None:
            cr_type = runtime_config.cr_type
        queries = self._build_target_queries(namespace, is_name, cr_type)
        headers: dict[str, str] = {}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"

        if not internal_client:
            return {}

        responses = await asyncio.gather(
            *(self._fetch_prometheus_metric(headers, metric_name, query) for metric_name, query in queries.items())
        )

        result: dict[str, float] = {}
        missing_metrics: list[str] = []
        for metric_name, value in responses:
            if value is not None:
                result[metric_name] = value
            else:
                missing_metrics.append(metric_name)

        if self._is_default_target(namespace, is_name):
            self._missing_metrics = missing_metrics

        return result

    async def _fetch_prometheus_metric(
        self,
        headers: dict[str, str],
        metric_name: str,
        query: str,
    ) -> tuple[str, float | None]:
        from services.shared import get_internal_client

        async def _do_fetch():
            internal_client = get_internal_client()
            resp = await internal_client.get(
                f"{PROMETHEUS_URL}/api/v1/query",
                params={"query": query},
                headers=headers,
                timeout=5,
            )
            resp.raise_for_status()
            return resp

        try:
            response = await _with_retry(_do_fetch)
            data = cast(dict[str, Any], response.json())
            payload = cast(dict[str, Any], data.get("data", {}))
            results = cast(list[dict[str, Any]], payload.get("result", []))
            if data.get("status") == "success" and results:
                # For aggregated queries (sum/avg), Prometheus returns exactly ONE result
                # because the aggregation function reduces all matching series into a single value.
                # e.g., sum(rate(vllm:requests_total[5m])) aggregates across all pods → single result
                if len(results) > 1:
                    logger.warning(
                        f"Unexpected multiple results for aggregated query '{metric_name}': "
                        f"{len(results)} results. Using first result."
                    )
                value = float(cast(list[Any], results[0].get("value", []))[1])
                if math.isnan(value) or math.isinf(value):
                    return metric_name, None
                return metric_name, round(value, 3)
        except (httpx.HTTPError, ValueError, AttributeError, TypeError):
            pass
        return metric_name, None

    async def _fetch_prometheus_multi_result(
        self,
        headers: dict[str, str],
        query: str,
        pod_name_pattern: str | None = None,
    ) -> dict[str, float]:
        """
        Fetch multiple results from Prometheus, returning a dict mapping pod names to metric values.

        Unlike _fetch_prometheus_metric() which handles aggregated queries (single result),
        this method parses ALL results from the Prometheus response, extracting the 'pod' label
        from each result to create a pod->value mapping.

        Args:
            headers: HTTP headers for Prometheus request
            query: Prometheus query string (should return per-pod results)

        Returns:
            Dict mapping pod names to float values. If 'pod' label is missing from a result,
            uses "pod_0", "pod_1", etc. as fallback keys.
        """
        from services.shared import get_internal_client

        async def _do_fetch():
            internal_client = get_internal_client()
            resp = await internal_client.get(
                f"{PROMETHEUS_URL}/api/v1/query",
                params={"query": query},
                headers=headers,
                timeout=5,
            )
            resp.raise_for_status()
            return resp

        result: dict[str, float] = {}
        try:
            response = await _with_retry(_do_fetch)
            data = cast(dict[str, Any], response.json())
            payload = cast(dict[str, Any], data.get("data", {}))
            results = cast(list[dict[str, Any]], payload.get("result", []))
            if data.get("status") == "success" and results:
                logger.info(f"Multi-result query returned {len(results)} results")
                for i, item in enumerate(results):
                    labels = cast(dict[str, Any], item.get("metric", {}))
                    value_list = cast(list[Any], item.get("value", []))
                    if not value_list or len(value_list) < 2:
                        continue
                    value = float(value_list[1])
                    if math.isnan(value) or math.isinf(value):
                        continue
                    # Extract pod label, fallback to pod_0, pod_1, etc. if missing
                    pod_name = labels.get("pod", f"pod_{i}")
                    if pod_name_pattern and not re.search(pod_name_pattern, pod_name):
                        continue
                    result[pod_name] = round(value, 3)
        except (httpx.HTTPError, ValueError, AttributeError, TypeError):
            pass
        return result

    async def _query_kubernetes_pods(self, namespace: str, is_name: str, cr_type: str | None = None) -> dict[str, int]:
        if cr_type is None:
            cr_type = runtime_config.cr_type
        if not self._k8s_available or self._k8s_core is None:
            return {}
        try:
            pods = cast(
                client.V1PodList,
                await asyncio.to_thread(
                    self._k8s_core.list_namespaced_pod,
                    namespace=namespace,
                    label_selector=get_cr_adapter(cr_type).pod_label_selector(is_name),
                ),
            )
        except client.ApiException:
            return {}
        except OSError as exc:
            logger.warning(
                "[MultiTargetMetricsCollector] pod list failed (%s/%s): %s",
                namespace,
                is_name,
                exc,
            )
            return {}

        items = pods.items or []
        pod_pattern_str = get_cr_adapter(cr_type).dcgm_pod_pattern(is_name)
        if pod_pattern_str:
            pod_pattern = re.compile(pod_pattern_str)
            items = [p for p in items if pod_pattern.match(p.metadata.name or "")]
        ready = sum(
            1
            for pod in items
            if pod.status.phase == "Running"
            and pod.status.container_statuses
            and all(cs.ready for cs in pod.status.container_statuses)
        )
        return {
            "pod_count": len(items),
            "pod_ready": ready,
        }

    def get_has_monitoring_label(self, namespace: str, is_name: str, cr_type: str | None = None) -> bool:
        key = self.build_target_key(namespace, is_name, cr_type)
        target = self._targets.get(key)
        return target.has_monitoring_label is not None and target.has_monitoring_label if target else False

    def build_target_key(self, namespace: str, is_name: str, cr_type: str | None = None) -> str:
        if cr_type is None:
            cr_type = runtime_config.cr_type
        return f"{namespace}/{is_name}/{cr_type}"

    def _load_token(self) -> str | None:
        token_path = "/var/run/secrets/kubernetes.io/serviceaccount/token"
        try:
            with open(token_path, encoding="utf-8") as file_obj:
                return file_obj.read().strip()
        except (FileNotFoundError, OSError):
            return None

    def _init_k8s(self) -> None:
        try:
            try:
                config.load_incluster_config()
            except config.ConfigException:
                config.load_kube_config()
            self._k8s_core = client.CoreV1Api()
            self._k8s_custom = client.CustomObjectsApi()
            self._k8s_available = True
        except Exception as exc:  # intentional: k8s init is optional, service runs without it
            logger.warning(
                "[MultiTargetMetricsCollector] K8s init failed (monitoring label/pods disabled): %s",
                exc,
            )

    async def _scrape_pod_metrics(self, pod_ip: str, port: int) -> dict[str, float]:
        import asyncio

        from services.metrics_constants import (
            COUNTER_METRIC_MAP,
            GAUGE_METRIC_MAP,
            HISTOGRAM_METRIC_MAP,
            normalize_metric_name,
        )

        text: str | None = None
        for attempt in range(2):
            try:
                async with httpx.AsyncClient(verify=False, timeout=5) as http:
                    resp = await http.get(f"http://{pod_ip}:{port}/metrics")
                    resp.raise_for_status()
                    text = resp.text
                break
            except (httpx.ConnectError, httpx.TimeoutException) as exc:
                if attempt == 0:
                    logger.debug(
                        "[MultiTargetMetricsCollector] pod scrape transient error (%s:%d), retrying: %s",
                        pod_ip,
                        port,
                        exc,
                    )
                    await asyncio.sleep(0.5)
                else:
                    logger.warning("[MultiTargetMetricsCollector] pod scrape failed (%s:%d): %s", pod_ip, port, exc)
                    return {}
            except httpx.HTTPError as exc:
                logger.warning("[MultiTargetMetricsCollector] pod scrape failed (%s:%d): %s", pod_ip, port, exc)
                return {}

        if text is None:
            return {}

        hist_suffixes: dict[str, tuple[str, str]] = {}
        for base, alias in HISTOGRAM_METRIC_MAP.items():
            hist_suffixes[f"{base}_sum"] = (alias, "sum")
            hist_suffixes[f"{base}_count"] = (alias, "count")

        gauge_acc: dict[str, float] = {}
        counter_acc: dict[str, float] = {}
        hist_acc: dict[str, float] = {}

        for line in text.splitlines():
            if not line or line.startswith("#"):
                continue

            brace_pos = line.find("{")
            if brace_pos != -1:
                metric_name = normalize_metric_name(line[:brace_pos])
                rest = line[line.rfind("}") + 1 :].strip()
            else:
                parts = line.split(None, 1)
                if len(parts) < 2:
                    continue
                metric_name, rest = normalize_metric_name(parts[0]), parts[1]

            value_str = rest.split()[0] if rest else ""
            if not value_str:
                continue
            try:
                value = float(value_str)
            except ValueError:
                continue
            if math.isnan(value) or math.isinf(value):
                continue

            if metric_name in GAUGE_METRIC_MAP:
                gauge_acc[metric_name] = gauge_acc.get(metric_name, 0.0) + value
            elif metric_name.endswith("_created"):
                pass
            elif metric_name in COUNTER_METRIC_MAP:
                counter_acc[metric_name] = counter_acc.get(metric_name, 0.0) + value
            elif metric_name in hist_suffixes:
                alias, suffix = hist_suffixes[metric_name]
                key = f"{alias}_{suffix}"
                hist_acc[key] = hist_acc.get(key, 0.0) + value

        result: dict[str, float] = {}
        for metric_name, field_name in GAUGE_METRIC_MAP.items():
            if metric_name in gauge_acc:
                result[field_name] = result.get(field_name, 0.0) + gauge_acc[metric_name]
        for metric_name, field_name in COUNTER_METRIC_MAP.items():
            if metric_name in counter_acc:
                result[field_name] = result.get(field_name, 0.0) + counter_acc[metric_name]
        result.update(hist_acc)

        return result
