import asyncio
import logging
import math
import os
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, cast

import httpx
from kubernetes import client, config

from services.metrics_collector import VLLMMetrics

logger = logging.getLogger(__name__)

PROMETHEUS_URL = os.getenv(
    "PROMETHEUS_URL",
    "https://thanos-querier.openshift-monitoring.svc.cluster.local:9091",
)


@dataclass
class TargetCache:
    key: str
    namespace: str
    is_name: str
    latest: VLLMMetrics | None = None
    history: deque[VLLMMetrics] = field(default_factory=lambda: deque(maxlen=3600))
    last_accessed: float = field(default_factory=time.time)
    is_active: bool = True
    has_monitoring_label: bool = False
    is_default: bool = False
    last_label_check: float = field(default_factory=time.time)


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

        self._token: str | None = self._load_token()
        self._k8s_available: bool = False
        self._k8s_core: client.CoreV1Api | None = None
        self._init_k8s()

    async def get_metrics(self, namespace: str, is_name: str) -> VLLMMetrics | None:
        key = self._target_key(namespace, is_name)
        async with self._lock:
            target = self._targets.get(key)
            if target is None:
                return None
            target.last_accessed = time.time()
            target.is_active = True
            latest = target.latest

        await self._ensure_collect_loop()
        return latest

    async def register_target(self, namespace: str, is_name: str) -> bool:
        key = self._target_key(namespace, is_name)
        async with self._lock:
            existing = self._targets.get(key)
            if existing is not None:
                existing.last_accessed = time.time()
                existing.is_active = True
                # Refresh monitoring label periodically (every 5 minutes)
                if time.time() - existing.last_label_check > 300:
                    existing.has_monitoring_label = await self.check_namespace_monitoring_label(namespace)
                    existing.last_label_check = time.time()
            else:
                if len(self._targets) >= self.MAX_TARGETS:
                    return False

                has_monitoring_label = await self.check_namespace_monitoring_label(namespace)
                is_first = not self._targets
                self._targets[key] = TargetCache(
                    key=key,
                    namespace=namespace,
                    is_name=is_name,
                    has_monitoring_label=has_monitoring_label,
                    is_default=is_first,
                )

        await self._ensure_collect_loop()
        return True

    async def remove_target(self, namespace: str, is_name: str) -> bool:
        key = self._target_key(namespace, is_name)
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
                    for target, result in zip(active_targets, results):
                        if isinstance(result, Exception):
                            logger.warning(
                                "[MultiTargetMetricsCollector] target=%s collect failed: %s",
                                target.key,
                                result,
                            )

                await asyncio.sleep(self.COLLECT_INTERVAL)
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
                        if not target.is_default
                        and (now - target.last_accessed) > self.INACTIVE_TIMEOUT
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

    def _build_target_queries(self, namespace: str, is_name: str) -> dict[str, str]:
        selector = f'namespace="{namespace}", job="{is_name}-metrics"'
        return {
            "tokens_per_second": (
                f'sum(rate(vllm:num_generated_tokens{{{selector}}}[1m])) '
                f'or sum(rate(vllm:generation_tokens_total{{{selector}}}[1m]))'
            ),
            "requests_per_second": (
                f'sum(rate(vllm:num_requests_finished{{{selector}}}[1m])) '
                f'or sum(rate(vllm:request_success_total{{{selector}}}[1m]))'
            ),
            "mean_ttft_ms": (
                f'histogram_quantile(0.5, sum by (le) '
                f'(rate(vllm:time_to_first_token_seconds_bucket{{{selector}}}[1m]))) * 1000'
            ),
            "p99_ttft_ms": (
                f'histogram_quantile(0.99, sum by (le) '
                f'(rate(vllm:time_to_first_token_seconds_bucket{{{selector}}}[1m]))) * 1000'
            ),
            "mean_e2e_latency_ms": (
                f'histogram_quantile(0.5, sum by (le) '
                f'(rate(vllm:e2e_request_latency_seconds_bucket{{{selector}}}[1m]))) * 1000'
            ),
            "p99_e2e_latency_ms": (
                f'histogram_quantile(0.99, sum by (le) '
                f'(rate(vllm:e2e_request_latency_seconds_bucket{{{selector}}}[1m]))) * 1000'
            ),
            "kv_cache_usage_pct": f'vllm:kv_cache_usage_perc{{{selector}}} * 100',
            "kv_cache_hit_rate": (
                f'vllm:kv_cache_hit_rate{{{selector}}} or vllm:cache_config_info{{{selector}}}'
            ),
            "running_requests": f'vllm:num_requests_running{{{selector}}}',
            "waiting_requests": f'vllm:num_requests_waiting{{{selector}}}',
            "gpu_memory_used_gb": (
                f'(vllm:gpu_memory_usage_bytes{{{selector}}} / 1024^3) '
                f'or vllm:gpu_cache_usage_perc{{{selector}}}'
            ),
            "gpu_memory_total_gb": (
                f'(vllm:gpu_memory_total_bytes{{{selector}}} / 1024^3) '
                f'or (vllm:gpu_cache_usage_perc{{{selector}}} * 0 + 1)'
            ),
            "gpu_utilization_pct": (
                f'(vllm:gpu_utilization_perc{{{selector}}} * 100) '
                f'or (vllm:gpu_utilization{{{selector}}} * 100)'
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
        except Exception as exc:
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
        metrics = VLLMMetrics(timestamp=time.time())

        prom_data = await self._query_prometheus(target.namespace, target.is_name)
        for key, value in prom_data.items():
            if hasattr(metrics, key):
                setattr(metrics, key, value)

        k8s_data = await self._query_kubernetes_pods(target.namespace, target.is_name)
        metrics.pod_count = k8s_data.get("pod_count", 0)
        metrics.pod_ready = k8s_data.get("pod_ready", 0)

        target.latest = metrics
        target.history.append(metrics)

    async def _query_prometheus(self, namespace: str, is_name: str) -> dict[str, float]:
        queries = self._build_target_queries(namespace, is_name)
        headers: dict[str, str] = {}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"

        async with httpx.AsyncClient(timeout=5, verify=False, headers=headers) as client:
            responses = await asyncio.gather(
                *(
                    self._fetch_prometheus_metric(client, metric_name, query)
                    for metric_name, query in queries.items()
                )
            )

        result: dict[str, float] = {}
        for metric_name, value in responses:
            if value is not None:
                result[metric_name] = value
        return result

    async def _fetch_prometheus_metric(
        self,
        client_instance: httpx.AsyncClient,
        metric_name: str,
        query: str,
    ) -> tuple[str, float | None]:
        try:
            response = await client_instance.get(
                f"{PROMETHEUS_URL}/api/v1/query",
                params={"query": query},
            )
            _ = response.raise_for_status()
            data = cast(dict[str, Any], response.json())
            payload = cast(dict[str, Any], data.get("data", {}))
            results = cast(list[dict[str, Any]], payload.get("result", []))
            if data.get("status") == "success" and results:
                value = float(cast(list[Any], results[0].get("value", []))[1])
                if math.isnan(value) or math.isinf(value):
                    return metric_name, None
                return metric_name, round(value, 3)
        except Exception:
            pass
        return metric_name, None

    async def _query_kubernetes_pods(self, namespace: str, is_name: str) -> dict[str, int]:
        if not self._k8s_available or self._k8s_core is None:
            return {}
        try:
            pods = cast(
                client.V1PodList,
                await asyncio.to_thread(
                    self._k8s_core.list_namespaced_pod,
                    namespace=namespace,
                    label_selector=f"serving.kserve.io/inferenceservice={is_name}",
                ),
            )
        except client.ApiException:
            return {}
        except Exception as exc:
            logger.warning(
                "[MultiTargetMetricsCollector] pod list failed (%s/%s): %s",
                namespace,
                is_name,
                exc,
            )
            return {}

        items = pods.items or []
        ready = sum(
            1
            for pod in items
            if pod.status.phase == "Running"
            and all(container.ready for container in (pod.status.container_statuses or []))
        )
        return {
            "pod_count": len(items),
            "pod_ready": ready,
        }

    def get_has_monitoring_label(self, namespace: str, is_name: str) -> bool:
        key = self._target_key(namespace, is_name)
        target = self._targets.get(key)
        return target.has_monitoring_label if target else False

    def _target_key(self, namespace: str, is_name: str) -> str:
        return f"{namespace}/{is_name}"

    def _load_token(self) -> str | None:
        token_path = "/var/run/secrets/kubernetes.io/serviceaccount/token"
        try:
            with open(token_path, "r", encoding="utf-8") as file_obj:
                return file_obj.read().strip()
        except (FileNotFoundError, OSError):
            return None

    def _init_k8s(self) -> None:
        try:
            try:
                config.load_incluster_config()
            except Exception:
                config.load_kube_config()
            self._k8s_core = client.CoreV1Api()
            self._k8s_available = True
        except Exception as exc:
            logger.warning(
                "[MultiTargetMetricsCollector] K8s init failed (monitoring label/pods disabled): %s",
                exc,
            )
