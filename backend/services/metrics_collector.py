"""
실시간 메트릭 수집기 — Prometheus + Kubernetes API
vLLM 전용 메트릭: TPS, TTFT, KV Cache, GPU Memory
"""
import asyncio
import httpx
import os
from dataclasses import dataclass
from typing import Optional
from kubernetes import client as k8s_client, config as k8s_config
from ..metrics.prometheus_metrics import update_metrics

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
VLLM_QUERIES = {
    "tokens_per_second": 'rate(vllm:generation_tokens_total[1m])',
    "requests_per_second": 'rate(vllm:request_success_total[1m])',
    "mean_ttft_ms": 'histogram_quantile(0.5, rate(vllm:time_to_first_token_seconds_bucket[1m])) * 1000',
    "p99_ttft_ms": 'histogram_quantile(0.99, rate(vllm:time_to_first_token_seconds_bucket[1m])) * 1000',
    "mean_e2e_latency_ms": 'histogram_quantile(0.5, rate(vllm:e2e_request_latency_seconds_bucket[1m])) * 1000',
    "p99_e2e_latency_ms": 'histogram_quantile(0.99, rate(vllm:e2e_request_latency_seconds_bucket[1m])) * 1000',
    "kv_cache_usage_pct": 'vllm:gpu_cache_usage_perc * 100',
    "kv_cache_hit_rate": 'vllm:cache_config_info',
    "running_requests": 'vllm:num_requests_running',
    "waiting_requests": 'vllm:num_requests_waiting',
    "gpu_memory_used_gb": 'vllm:gpu_cache_usage_perc * vllm:gpu_memory_total_bytes / 1024^3',
}


class MetricsCollector:
    def __init__(self):
        self._latest: Optional[VLLMMetrics] = None
        self._history: list[VLLMMetrics] = []
        self._max_history = 300  # 5분 @ 1초 간격
        self._running = False
        self._k8s_available = False
        self._token = self._load_token()
        self._init_k8s()

    def _load_token(self) -> Optional[str]:
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
                k8s_config.load_incluster_config()  # Pod 내부에서 실행 시
            except Exception:
                k8s_config.load_kube_config()  # 로컬 개발 시
            self._k8s_apps = k8s_client.AppsV1Api()
            self._k8s_core = k8s_client.CoreV1Api()
            self._k8s_available = True
        except Exception as e:
            print(f"[MetricsCollector] K8s 초기화 실패 (모의 데이터 사용): {e}")

    async def start_collection(self, interval: float = 2.0):
        self._running = True
        while self._running:
            try:
                metrics = await self._collect()
                self._latest = metrics
                self._history.append(metrics)
                if len(self._history) > self._max_history:
                    self._history.pop(0)
            except Exception as e:
                print(f"[MetricsCollector] 수집 오류: {e}")
            await asyncio.sleep(interval)

    def stop(self):
        self._running = False

    @property
    def latest(self) -> Optional[VLLMMetrics]:
        return self._latest

    @property
    def history(self) -> list[VLLMMetrics]:
        return self._history

    async def _collect(self) -> VLLMMetrics:
        import time
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

        return metrics

    async def _query_prometheus(self) -> dict:
        results = {}
        # Prepare headers with optional Bearer token
        headers = {}
        if getattr(self, "_token", None):
            headers["Authorization"] = f"Bearer {self._token}"
        async with httpx.AsyncClient(timeout=5, verify=False, headers=headers) as client:
            for metric_name, query in VLLM_QUERIES.items():
                try:
                    resp = await client.get(
                        f"{PROMETHEUS_URL}/api/v1/query",
                        params={"query": query},
                    )
                    data = resp.json()
                    if data["status"] == "success" and data["data"]["result"]:
                        value = float(data["data"]["result"][0]["value"][1])
                        results[metric_name] = round(value, 3)
                except Exception:
                    pass
        return results

    def _query_kubernetes(self) -> dict:
        try:
            deployment = self._k8s_apps.read_namespaced_deployment(
                name=K8S_DEPLOYMENT,
                namespace=K8S_NAMESPACE,
            )
            pods = self._k8s_core.list_namespaced_pod(
                namespace=K8S_NAMESPACE,
                label_selector=f"app={K8S_DEPLOYMENT}",
            )
            ready = sum(
                1 for p in pods.items
                if p.status.phase == "Running" and
                all(c.ready for c in (p.status.container_statuses or []))
            )
            return {
                "pod_count": deployment.spec.replicas,
                "pod_ready": ready,
            }
        except Exception:
            return {}

    def get_history_dict(self, last_n: int = 60) -> list[dict]:
        history = self._history[-last_n:]
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
            }
            for m in history
        ]
