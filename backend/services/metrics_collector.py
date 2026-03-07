"""
실시간 메트릭 수집기 — Prometheus + Kubernetes API
vLLM 전용 메트릭: TPS, TTFT, KV Cache, GPU Memory
"""

import logging
import asyncio
import httpx
import os
from collections import deque
from dataclasses import dataclass
from typing import Any, cast
from kubernetes import client, config
from kubernetes.client import V1Deployment
from metrics.prometheus_metrics import update_metrics

PROMETHEUS_URL = os.getenv("PROMETHEUS_URL", "https://thanos-querier.openshift-monitoring.svc.cluster.local:9091")
K8S_NAMESPACE = os.getenv("K8S_NAMESPACE", "default")
K8S_DEPLOYMENT = os.getenv("K8S_DEPLOYMENT_NAME", "vllm-deployment")


@dataclass
class VLLMMetrics:
    timestamp: float
    # 처리량
    tokens_per_second: float = 0
    requests_per_second: float = 0
    # 레이턴시
    mean_ttft_ms: float = 0
    p99_ttft_ms: float = 0
    mean_e2e_latency_ms: float = 0
    p99_e2e_latency_ms: float = 0
    # KV Cache
    kv_cache_usage_pct: float = 0
    kv_cache_hit_rate: float = 0
    # 큐
    running_requests: int = 0
    waiting_requests: int = 0
    # GPU
    gpu_memory_used_gb: float = 0
    gpu_memory_total_gb: float = 0
    gpu_utilization_pct: float = 0
    # Kubernetes
    pod_count: int = 0
    pod_ready: int = 0


# vLLM Prometheus 메트릭 쿼리 매핑
VLLM_QUERIES_BY_VERSION: dict[str, dict[str, str]] = {
    "0.11.x": {
        # Throughput
        "tokens_per_second": 'rate(vllm:generation_tokens_total[1m])',
        "requests_per_second": 'rate(vllm:request_success_total[1m])',
        # Latency
        "mean_ttft_ms": 'histogram_quantile(0.5, rate(vllm:time_to_first_token_seconds_bucket[1m])) * 1000',
        "p99_ttft_ms": 'histogram_quantile(0.99, rate(vllm:time_to_first_token_seconds_bucket[1m])) * 1000',
        "mean_e2e_latency_ms": 'histogram_quantile(0.5, rate(vllm:e2e_request_latency_seconds_bucket[1m])) * 1000',
        "p99_e2e_latency_ms": 'histogram_quantile(0.99, rate(vllm:e2e_request_latency_seconds_bucket[1m])) * 1000',
        # KV Cache
        "kv_cache_usage_pct": 'vllm:gpu_cache_usage_perc * 100',
        "kv_cache_hit_rate": 'vllm:cache_config_info', # This might be missing in 0.11.x, will be handled by logging
        # Queue
        "running_requests": 'vllm:num_requests_running',
        "waiting_requests": 'vllm:num_requests_waiting',
        # GPU Memory
        "gpu_memory_used_gb": 'vllm:gpu_cache_usage_perc * vllm:gpu_memory_total_bytes / 1024^3',
        "gpu_memory_total_gb": 'vllm:gpu_memory_total_bytes / 1024^3',
        # GPU Utilization
        "gpu_utilization_pct": 'vllm:gpu_utilization',
    },
    "0.13.x": {
        # Throughput
        "tokens_per_second": 'sum(rate(vllm:num_generated_tokens[1m]))',
        "requests_per_second": 'sum(rate(vllm:num_requests_finished[1m]))',
        # Latency
        "mean_ttft_ms": 'histogram_quantile(0.5, sum by (le) (rate(vllm:time_to_first_token_seconds_bucket[1m]))) * 1000',
        "p99_ttft_ms": 'histogram_quantile(0.99, sum by (le) (rate(vllm:time_to_first_token_seconds_bucket[1m]))) * 1000',
        "mean_e2e_latency_ms": 'histogram_quantile(0.5, sum by (le) (rate(vllm:e2e_request_latency_seconds_bucket[1m]))) * 1000',
        "p99_e2e_latency_ms": 'histogram_quantile(0.99, sum by (le) (rate(vllm:e2e_request_latency_seconds_bucket[1m]))) * 1000',
        # KV Cache
        "kv_cache_usage_pct": 'vllm:kv_cache_usage_perc * 100',
        "kv_cache_hit_rate": 'vllm:kv_cache_hit_rate',
        # Queue
        "running_requests": 'vllm:num_requests_running',
        "waiting_requests": 'vllm:num_requests_waiting',
        # GPU Memory
        "gpu_memory_used_gb": 'vllm:gpu_memory_usage_bytes / 1024^3',
        "gpu_memory_total_gb": 'vllm:gpu_memory_total_bytes / 1024^3',
        # GPU Utilization
        "gpu_utilization_pct": 'vllm:gpu_utilization_perc * 100',
    }
}


class MetricsCollector:
    _latest: VLLMMetrics | None
    _history: deque[VLLMMetrics]
    _max_history: int = 3600  # 1시간 @ 1초 간격
    _running: bool = False
    _k8s_available: bool = False
    _token: str | None
    _current_queries: dict[str, str] | None # Will be set after version detection
    _version: str = "unknown"
    _missing_metrics: list[str] = []
    _k8s_apps: client.AppsV1Api
    _k8s_core: client.CoreV1Api

    def __init__(self):
        self._latest = None
        self._history = deque(maxlen=self._max_history)
        self._running = False
        self._k8s_available = False
        self._token = self._load_token()
        self._init_k8s()
        self._current_queries = None # Will be set after version detection
        self._version = "unknown"
        self._missing_metrics = []
        self._last_collection_duration: float = 0.0

    async def _post_init(self):
        # This needs to be async, so we call it after __init__
        version = await self._detect_version()
        self._version = version
        self._current_queries = VLLM_QUERIES_BY_VERSION.get(version, VLLM_QUERIES_BY_VERSION["0.11.x"])

    def _load_token(self) -> str | None:
        # Read Kubernetes serviceaccount token if available
        token_path = "/var/run/secrets/kubernetes.io/serviceaccount/token"
        try:
            with open(token_path, "r") as f:
                return f.read().strip()
        except FileNotFoundError:
            return None
        except Exception:
            return None

    def _init_k8s(self):
        try:
            try:
                config.load_incluster_config()
            except Exception:
                config.load_kube_config()
            self._k8s_apps = client.AppsV1Api()
            self._k8s_core = client.CoreV1Api()
            self._k8s_available = True
        except Exception as e:
            logging.error(f"[MetricsCollector] K8s 초기화 실패 (모의 데이터 사용): {e}")

    async def start_collection(self, interval: float = 2.0):
        await self._post_init() # Initialize current_queries after version detection
        self._running = True
        while self._running:
            try:
                await self._collect()
            except Exception as e:
                logging.error(f"[MetricsCollector] 수집 오류: {e}")
            await asyncio.sleep(interval)

    def stop(self):
        self._running = False

    @property
    def latest(self) -> VLLMMetrics | None:
        return self._latest

    @property
    def history(self) -> list[VLLMMetrics]:
        return list(self._history)

    @property
    def last_collection_duration(self) -> float:
        return self._last_collection_duration

    async def _collect(self) -> VLLMMetrics:
        import time
        start = time.monotonic()
        metrics = VLLMMetrics(timestamp=time.time())

        # Prometheus 쿼리
        prom_data = await self._query_prometheus()
        for key, value in prom_data.items():
            if hasattr(metrics, key):
                setattr(metrics, key, value)

        # Kubernetes Pod 상태
        if self._k8s_available:
            k8s_data = self._query_kubernetes()
            metrics.pod_count = k8s_data.get("pod_count", 0)
            metrics.pod_ready = k8s_data.get("pod_ready", 0)

        # Update Prometheus metrics
        update_metrics(metrics)
        
        # Record collection duration
        duration = time.monotonic() - start
        self._last_collection_duration = duration
        try:
            from metrics.prometheus_metrics import metrics_collection_duration_metric
            metrics_collection_duration_metric.observe(duration)
        except Exception:
            pass

        self._latest = metrics
        self._history.append(metrics)
        return metrics

    async def _fetch_prometheus_metric(self, client: httpx.AsyncClient, metric_name: str, query: str) -> tuple[str, float | None]:
        try:
            resp = await client.get(
                f"{PROMETHEUS_URL}/api/v1/query",
                params={"query": query},
            )
            data = resp.json()
            if data["status"] == "success" and data["data"]["result"]:
                value = float(data["data"]["result"][0]["value"][1])
                return metric_name, round(value, 3)
        except Exception:
            pass
        return metric_name, None

    async def _query_prometheus(self) -> dict[str, float]:
        headers = {}
        if getattr(self, "_token", None):
            headers["Authorization"] = f"Bearer {self._token}"

        # CA certificate path for in-cluster TLS verification
        ca_path = "/var/run/secrets/kubernetes.io/serviceaccount/ca.crt"
        verify = ca_path if os.path.exists(ca_path) else True

        async with httpx.AsyncClient(timeout=5, verify=verify, headers=headers) as client:
            tasks = []
            if self._current_queries is not None: # Added check
                tasks = [self._fetch_prometheus_metric(client, name, query) for name, query in self._current_queries.items()]
            responses = await asyncio.gather(*tasks)

        result: dict[str, float] = {}
        missing_metrics: list[str] = []
        for name, value in responses:
            if value is not None:
                result[name] = value
            else:
                missing_metrics.append(name)
        
        if missing_metrics:
            logging.warning(f"[MetricsCollector] Metrics not available: {', '.join(missing_metrics)}")
        
        self._missing_metrics = missing_metrics
        return result

    async def _detect_version(self) -> str:
        headers = {}
        if getattr(self, "_token", None):
            headers["Authorization"] = f"Bearer {self._token}"

        ca_path = "/var/run/secrets/kubernetes.io/serviceaccount/ca.crt"
        verify = ca_path if os.path.exists(ca_path) else True

        async with httpx.AsyncClient(timeout=5, verify=verify, headers=headers) as client:
            try:
                resp = await client.get(
                    f"{PROMETHEUS_URL}/api/v1/query",
                    params={"query": "vllm:kv_cache_usage_perc"},
                )
                data = resp.json()
                if data["status"] == "success" and data["data"]["result"]:
                    logging.info("[MetricsCollector] Detected vLLM version: 0.13.x")
                    return "0.13.x"
            except Exception as e:
                logging.warning(f"[MetricsCollector] Failed to query for vLLM 0.13.x specific metric, falling back to 0.11.x: {e}")
        logging.info("[MetricsCollector] Detected vLLM version: 0.11.x (fallback)")
        return "0.11.x"

    def _query_kubernetes(self) -> dict[str, int]:
        try:
            deployment = cast(V1Deployment, self._k8s_apps.read_namespaced_deployment(
                name=K8S_DEPLOYMENT,
                namespace=K8S_NAMESPACE,
            ))
            pods = self._k8s_core.list_namespaced_pod(
                namespace=K8S_NAMESPACE,
                label_selector=f"app={K8S_DEPLOYMENT}",
            )
            ready = sum(
                1 for p in pods.items
                if p.status.phase == "Running" and
                all(c.ready for c in (p.status.container_statuses or []))
            )
            # Safely extract replicas, guarding against None attributes
            dep_spec = getattr(deployment, "spec", None)
            replicas = getattr(dep_spec, "replicas", None) if dep_spec is not None else None
            pod_count = replicas if replicas is not None else 0
            return {
                "pod_count": pod_count,
                "pod_ready": ready,
            }
        except Exception:
            return {}

    @property
    def version(self) -> str:
        return self._version

    @property
    def missing_metrics(self) -> list[str]:
        return self._missing_metrics

    def get_history_dict(self, last_n: int = 60, include_metadata: bool = True) -> list[dict[str, Any]]:
        history = list(self._history)[-last_n:]
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
                } if include_metadata else None,
            }
            for m in history
        ]
