"""
부하 테스트 엔진 — 동시 요청, RPS 제어, 실시간 결과 스트리밍
"""
import asyncio
import json
import time
import os
import httpx
import statistics
import psutil

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, TYPE_CHECKING
from urllib.parse import urlparse

from models.load_test import LoadTestConfig, RequestResult

if TYPE_CHECKING:
    from services.runtime_config import RuntimeConfig


def _normalize_url(url: str) -> str:
    """
    Normalize URL for comparison: lowercase scheme/host/path, remove trailing slash.
    
    Args:
        url: The URL to normalize (e.g., "http://server:8080/v1/")
        
    Returns:
        Normalized URL (e.g., "http://server:8080/v1")
    """
    if not url:
        return ""
    parsed = urlparse(url.rstrip("/"))
    normalized_netloc = parsed.netloc.lower() if parsed.netloc else ""
    normalized_scheme = parsed.scheme.lower() if parsed.scheme else ""
    normalized_path = parsed.path.lower() if parsed.path else ""
    return f"{normalized_scheme}://{normalized_netloc}{normalized_path}"


class LoadTestStatus(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    STOPPED = "stopped"


@dataclass
class LoadTestState:
    status: LoadTestStatus = LoadTestStatus.IDLE
    results: list[RequestResult] = field(default_factory=list)
    start_time: float = 0
    total_requests: int = 0
    completed_requests: int = 0
    failed_requests: int = 0


class LoadTestEngine:
    def __init__(self) -> None:
        self._state: LoadTestState = LoadTestState()
        self._stop_event: asyncio.Event = asyncio.Event()
        self._subscribers: list[asyncio.Queue[Any]] = []
        self._state_lock: asyncio.Lock = asyncio.Lock()
        self._subscribers_lock: asyncio.Lock = asyncio.Lock()

    @property
    def status(self) -> LoadTestStatus:
        return self._state.status

    @property
    def elapsed(self) -> float:
        """Return elapsed seconds if running, else 0.0"""
        if self._state.status == LoadTestStatus.RUNNING:
            return time.time() - self._state.start_time
        return 0.0

    async def subscribe(self) -> asyncio.Queue[Any]:
        q: asyncio.Queue[Any] = asyncio.Queue[Any]()
        async with self._subscribers_lock:
            self._subscribers.append(q)
        return q

    async def unsubscribe(self, q: asyncio.Queue[Any]) -> None:
        async with self._subscribers_lock:
            self._subscribers.remove(q)

    async def _broadcast(self, data: dict[str, Any]):
        async with self._subscribers_lock:
            targets = list(self._subscribers)
        for q in targets:
            await q.put(data)

    async def _sample_metrics(self, samples: list[dict[str, float]], stop_event: asyncio.Event):
        """Background task: sample CPU and GPU metrics every 30 seconds."""
        proc = psutil.Process(os.getpid())
        while not stop_event.is_set():
            cpu = await asyncio.to_thread(proc.cpu_percent)
            gpu = 0.0
            try:
                async with httpx.AsyncClient(timeout=5) as client:
                    resp = await client.get("http://localhost:8000/api/metrics/latest")
                    if resp.status_code == 200:
                        gpu = resp.json().get("gpu_util", 0.0)
            except Exception:  # intentional: non-critical
                # GPU metrics fetch, non-critical
                pass
            samples.append({"cpu": cpu, "gpu": gpu})
            for _ in range(30):
                if stop_event.is_set():
                    return
                await asyncio.sleep(1)

    def _init_run_state(self, config: LoadTestConfig):
        """Initialize run state, stats tracking, and result containers."""
        self._state = LoadTestState(
            status=LoadTestStatus.RUNNING,
            start_time=time.time(),
            total_requests=config.total_requests,
        )
        self._stop_event.clear()
        semaphore = asyncio.Semaphore(config.concurrency)
        metric_samples = []
        sample_stop = asyncio.Event()
        sampling_task = asyncio.create_task(self._sample_metrics(metric_samples, sample_stop))
        interval = 1.0 / config.rps if config.rps > 0 else 0
        return semaphore, metric_samples, sample_stop, sampling_task, interval

    async def _dispatch_request(self, config: LoadTestConfig, semaphore: asyncio.Semaphore, request_id: int) -> RequestResult:
        """Send a single async HTTP request."""
        async with semaphore:
            payload = {
                "model": config.model,
                "prompt": config.prompt_template,
                "max_tokens": config.max_tokens,
                "temperature": config.temperature,
            }
            t0 = time.time()
            ttft = None
            output_tokens = 0
            try:
                async with httpx.AsyncClient(timeout=120) as client:
                    if config.stream:
                        usage_tokens = 0
                        async with client.stream(
                            "POST",
                            f"{config.endpoint}/v1/completions",
                            json={
                                **payload,
                                "stream": True,
                                "stream_options": {"include_usage": True},
                            },
                        ) as resp:
                            async for chunk in resp.aiter_lines():
                                if chunk.startswith("data: ") and chunk != "data: [DONE]":
                                    if ttft is None:
                                        ttft = time.time() - t0
                                    output_tokens += 1
                                    try:
                                        data = json.loads(chunk[6:])
                                        if data.get("usage") and data["usage"].get("completion_tokens"):
                                            usage_tokens = data["usage"]["completion_tokens"]
                                    except (json.JSONDecodeError, KeyError):
                                        pass
                        if usage_tokens:
                            output_tokens = usage_tokens
                    else:
                        resp = await client.post(
                            f"{config.endpoint}/v1/completions",
                            json=payload,
                        )
                        data = resp.json()
                        output_tokens = data["usage"]["completion_tokens"]
                latency = time.time() - t0
                return RequestResult(
                    req_id=request_id,
                    success=True,
                    latency=latency,
                    ttft=ttft,
                    output_tokens=output_tokens,
                    tps=output_tokens / latency if latency > 0 else 0,
                )
            except Exception as e:  # intentional: non-critical
                return RequestResult(
                    req_id=request_id,
                    success=False,
                    latency=time.time() - t0,
                    error=str(e),
                )

    async def _process_completed_tasks(self, done_tasks: set[asyncio.Task[Any]], processed_tasks: set[asyncio.Task[Any]]):
        """Process completed asyncio tasks, collect results, update state, broadcast."""
        for t in done_tasks:
            result = await t
            processed_tasks.add(t)
            async with self._state_lock:
                self._state.results.append(result)
                if result.success:
                    self._state.completed_requests += 1
                else:
                    self._state.failed_requests += 1
            stats = self._compute_stats()
            await self._broadcast({"type": "progress", "data": stats})

    async def _finalize_results(
        self, 
        config: LoadTestConfig,
        metric_samples: list[dict[str, float]], 
        sample_stop: asyncio.Event, 
        sampling_task: asyncio.Task[Any]
    ) -> dict[str, Any]:
        """Finalize test: set status, stop sampling, compute final stats, broadcast, return."""
        from services.shared import runtime_config  # Import locally to avoid circular dependency
        
        async with self._state_lock:
            self._state.status = LoadTestStatus.COMPLETED
        sample_stop.set()
        sampling_task.cancel()
        try:
            await sampling_task
        except asyncio.CancelledError:
            pass
        final_stats = self._compute_stats()
        
        # Check if load test target matches monitored vLLM endpoint
        test_endpoint = config.endpoint if config.endpoint else runtime_config.vllm_endpoint
        monitored_endpoint = runtime_config.vllm_endpoint
        endpoints_match = _normalize_url(test_endpoint) == _normalize_url(monitored_endpoint)
        
        if metric_samples:
            cpu_values = [s["cpu"] for s in metric_samples]
            gpu_values = [s["gpu"] for s in metric_samples]
            final_stats["backend_cpu_avg"] = round(sum(cpu_values) / len(cpu_values), 2)
            
            # Only include GPU metrics if target matches monitored endpoint
            if endpoints_match:
                final_stats["gpu_utilization_avg"] = round(sum(gpu_values) / len(gpu_values), 2)
            else:
                final_stats["gpu_utilization_avg"] = None
        else:
            final_stats["backend_cpu_avg"] = 0.0
            final_stats["gpu_utilization_avg"] = None if not endpoints_match else 0.0
        
        final_stats["metrics_target_matched"] = endpoints_match
        final_stats["tokens_per_sec"] = final_stats.get("tps", {}).get("mean", 0.0)
        await self._broadcast({"type": "completed", "data": final_stats})
        return final_stats

    async def run(self, config: LoadTestConfig) -> dict[str, Any]:
        """부하 테스트 실행 — 실시간 결과 yield"""
        semaphore, metric_samples, sample_stop, sampling_task, interval = self._init_run_state(config)
        tasks = []
        processed_tasks: set[asyncio.Task[Any]] = set()
        for i in range(config.total_requests):
            if self._stop_event.is_set():
                break
            task = asyncio.create_task(self._dispatch_request(config, semaphore, i))
            tasks.append(task)
            to_check = [t for t in tasks if t not in processed_tasks]
            if to_check:
                done, _ = await asyncio.wait(to_check, timeout=0, return_when=asyncio.FIRST_COMPLETED)
                await self._process_completed_tasks(done, processed_tasks)
            if interval > 0:
                await asyncio.sleep(interval)
        # Process remaining tasks
        remaining_tasks = [t for t in tasks if t not in processed_tasks]
        if remaining_tasks:
            for fut in asyncio.as_completed(remaining_tasks):
                try:
                    result = await fut
                except Exception as e:  # intentional: non-critical
                    result = RequestResult(
                        req_id=-1,
                        success=False,
                        latency=time.time() - self._state.start_time,
                        error=str(e),
                    )
                async with self._state_lock:
                    self._state.results.append(result)
                    if result.success:
                        self._state.completed_requests += 1
                    else:
                        self._state.failed_requests += 1
                stats = self._compute_stats()
                await self._broadcast({"type": "progress", "data": stats})
        return await self._finalize_results(config, metric_samples, sample_stop, sampling_task)

    async def stop(self) -> None:
        self._stop_event.set()
        async with self._state_lock:
            self._state.status = LoadTestStatus.STOPPED

    def _compute_stats(self) -> dict[str, Any]:
        results = self._state.results
        if not results:
            return {}

        successful = [r for r in results if r.success]
        latencies = [r.latency for r in successful]
        ttfts = [r.ttft for r in successful if r.ttft is not None]
        tps_values = [r.tps for r in successful if r.tps > 0]

        elapsed = time.time() - self._state.start_time

        return {
            "elapsed": round(elapsed, 2),
            "total": len(results),
            "total_requested": self._state.total_requests,
            "success": len(successful),
            "failed": self._state.failed_requests,
            "rps_actual": round(len(results) / elapsed, 2) if elapsed > 0 else 0,
            "latency": {
                "mean": round(statistics.mean(latencies), 3) if latencies else 0,
                "p50": round(statistics.median(latencies), 3) if latencies else 0,
                "p95": round(_percentile(latencies, 95), 3) if latencies else 0,
                "p99": round(_percentile(latencies, 99), 3) if latencies else 0,
                "min": round(min(latencies), 3) if latencies else 0,
                "max": round(max(latencies), 3) if latencies else 0,
            },
            "ttft": {
                "mean": round(statistics.mean(ttfts), 3) if ttfts else 0,
                "p95": round(_percentile(ttfts, 95), 3) if ttfts else 0,
            },
            "tps": {
                "mean": round(statistics.mean(tps_values), 1) if tps_values else 0,
                "total": round(sum(tps_values), 1) if tps_values else 0,
            },
        }


def _percentile(data: list[float], p: int) -> float:
    if not data:
        return 0
    sorted_data = sorted(data)
    idx = int(len(sorted_data) * p / 100)
    return sorted_data[min(idx, len(sorted_data) - 1)]


# 싱글턴 인스턴스
load_engine = LoadTestEngine()
