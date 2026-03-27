"""
부하 테스트 엔진 — 동시 요청, RPS 제어, 실시간 결과 스트리밍
"""

import asyncio
import contextlib
import importlib
import json
import logging
import os
import statistics
import time
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any
from urllib.parse import urlparse

import httpx
import psutil
from models.load_test import LoadTestConfig, RequestResult, SweepConfig, SweepStepResult, SweepResult

logger = logging.getLogger(__name__)


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


class LoadTestStatus(StrEnum):
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
            except Exception as e:  # intentional: non-critical
                logger.debug("[LoadEngine] GPU metrics unavailable: %s", e)
            samples.append({"cpu": cpu, "gpu": gpu})
            for _ in range(30):
                if stop_event.is_set():
                    return
                await asyncio.sleep(1)

    def _init_run_state(self, config: LoadTestConfig):
        """Initialize run state, stats tracking, and result containers."""
        self._stop_event.clear()
        semaphore = asyncio.Semaphore(config.concurrency)
        metric_samples = []
        sample_stop = asyncio.Event()
        sampling_task = asyncio.create_task(self._sample_metrics(metric_samples, sample_stop))
        interval = 1.0 / config.rps if config.rps > 0 else 0
        return semaphore, metric_samples, sample_stop, sampling_task, interval

    async def _preflight_check(self, config: "LoadTestConfig") -> dict[str, Any]:
        if config.total_requests < 1:
            return {
                "success": False,
                "error": "total_requests는 1 이상이어야 합니다",
                "error_type": "validation",
            }
        if config.concurrency < 1:
            return {
                "success": False,
                "error": "concurrency는 1 이상이어야 합니다",
                "error_type": "validation",
            }

        endpoint = (config.endpoint or "").rstrip("/")
        models_url = f"{endpoint}/v1/models"

        try:
            async with httpx.AsyncClient(timeout=5.0, verify=False) as client:
                response = await client.get(models_url)
        except httpx.ConnectError as e:
            return {
                "success": False,
                "error": f"vLLM 엔드포인트 연결 실패: {models_url} ({e})",
                "error_type": "connection",
            }
        except httpx.TimeoutException as e:
            return {
                "success": False,
                "error": f"vLLM 엔드포인트 응답 시간 초과: {models_url} ({e})",
                "error_type": "timeout",
            }
        except httpx.RequestError as e:
            return {
                "success": False,
                "error": f"vLLM 엔드포인트 요청 실패: {models_url} ({e})",
                "error_type": "connection",
            }

        if response.status_code >= 400:
            logger.warning(
                "[LoadTest] Preflight endpoint reachable but returned HTTP %s for %s",
                response.status_code,
                models_url,
            )
            return {"success": True}

        if config.model == "auto":
            return {"success": True}

        try:
            model_data = response.json().get("data", [])
        except (ValueError, AttributeError) as e:
            logger.warning("[LoadTest] Failed to parse /v1/models response in preflight: %s", e)
            return {"success": True}

        available_models = [str(item.get("id")) for item in model_data if isinstance(item, dict) and item.get("id")]
        if config.model not in available_models:
            available = ", ".join(available_models) if available_models else "없음"
            return {
                "success": False,
                "error": f"모델 '{config.model}'을(를) 찾을 수 없습니다. 사용 가능한 모델: {available}",
                "error_type": "model_not_found",
            }

        return {"success": True}

    async def _dispatch_request(
        self, config: LoadTestConfig, semaphore: asyncio.Semaphore, request_id: int
    ) -> RequestResult:
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
            token_timestamps: list[float] | None = None
            itl_mean: float | None = None
            itl_p95: float | None = None
            itl_p99: float | None = None
            try:
                async with httpx.AsyncClient(timeout=120) as client:
                    if config.stream:
                        usage_tokens = 0
                        token_timestamps = []
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
                                    token_timestamps.append(time.time())
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
                        if len(token_timestamps) >= 2:
                            deltas = [
                                token_timestamps[i + 1] - token_timestamps[i] for i in range(len(token_timestamps) - 1)
                            ]
                            itl_mean = sum(deltas) / len(deltas)
                            itl_p95 = sorted(deltas)[int(len(deltas) * 0.95)]
                            itl_p99 = sorted(deltas)[int(len(deltas) * 0.99)]
                        else:
                            itl_mean = itl_p95 = itl_p99 = None
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
                    token_timestamps=token_timestamps,
                    itl_mean=itl_mean,
                    itl_p95=itl_p95,
                    itl_p99=itl_p99,
                )
            except Exception as e:  # intentional: non-critical
                return RequestResult(
                    req_id=request_id,
                    success=False,
                    latency=time.time() - t0,
                    error=str(e),
                )

    async def _process_completed_tasks(
        self,
        done_tasks: set[asyncio.Task[Any]],
        processed_tasks: set[asyncio.Task[Any]],
    ) -> list[RequestResult]:
        """Process completed asyncio tasks, collect results, update state, broadcast."""
        processed_results: list[RequestResult] = []
        for t in done_tasks:
            result = await t
            processed_tasks.add(t)
            processed_results.append(result)
            async with self._state_lock:
                self._state.results.append(result)
                if len(self._state.results) > 1000:
                    self._state.results = self._state.results[-1000:]
                if result.success:
                    self._state.completed_requests += 1
                else:
                    self._state.failed_requests += 1
            stats = self._compute_stats()
            await self._broadcast({"type": "progress", "data": stats})
        return processed_results

    async def _fail_run(
        self,
        error_data: dict[str, Any],
        sample_stop: asyncio.Event,
        sampling_task: asyncio.Task[Any],
        pending_tasks: list[asyncio.Task[Any]],
    ) -> dict[str, Any]:
        error = str(error_data.get("error", "부하 테스트 실패"))
        error_type = str(error_data.get("error_type", "unknown"))
        await self._broadcast(
            {
                "type": "error",
                "data": {
                    "error": error,
                    "error_type": error_type,
                },
            }
        )
        self._stop_event.set()
        for task in pending_tasks:
            if not task.done():
                task.cancel()
        if pending_tasks:
            await asyncio.gather(*pending_tasks, return_exceptions=True)
        sample_stop.set()
        sampling_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await sampling_task
        async with self._state_lock:
            self._state.status = LoadTestStatus.FAILED
        return {
            "success": False,
            "error": error,
            "error_type": error_type,
        }

    async def _finalize_results(
        self,
        config: LoadTestConfig,
        metric_samples: list[dict[str, float]],
        sample_stop: asyncio.Event,
        sampling_task: asyncio.Task[Any],
    ) -> dict[str, Any]:
        """Finalize test: set status, stop sampling, compute final stats, broadcast, return."""
        shared_module = importlib.import_module("services.shared")
        runtime_config = shared_module.runtime_config

        async with self._state_lock:
            self._state.status = LoadTestStatus.COMPLETED
        sample_stop.set()
        sampling_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await sampling_task
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
        try:
            storage = shared_module.storage
            import time as _time

            await storage.save_load_test(
                {
                    "test_id": f"run-{int(_time.time())}",
                    "config": config.model_dump(),
                    "result": final_stats,
                    "timestamp": _time.time(),
                }
            )
        except Exception as _e:
            import logging as _logging

            _logging.getLogger(__name__).warning("Failed to persist load test result: %s", _e)
        return final_stats

    async def run(self, config: LoadTestConfig, skip_preflight: bool = False) -> dict[str, Any]:
        """부하 테스트 실행 — 실시간 결과 yield"""
        async with self._state_lock:
            if self._state.status == LoadTestStatus.RUNNING:
                return {
                    "error": "이미 부하 테스트가 실행 중입니다.",
                    "error_type": "already_running",
                }
            self._state = LoadTestState(
                status=LoadTestStatus.RUNNING,
                start_time=time.time(),
                total_requests=config.total_requests,
            )

        _running_row_id: int | None = None
        try:
            try:
                shared_module = importlib.import_module("services.shared")
                _storage = shared_module.storage

                _running_row_id = await _storage.set_running("loadtest")
            except Exception as e:
                logger.warning("[LoadEngine] Failed to record running state: %s", e)

            semaphore, metric_samples, sample_stop, sampling_task, interval = self._init_run_state(config)
            if not skip_preflight:
                preflight = await self._preflight_check(config)
                if not preflight.get("success"):
                    return await self._fail_run(preflight, sample_stop, sampling_task, [])

            first_batch_size = min(5, config.total_requests)
            first_batch_results: dict[int, RequestResult] = {}
            first_batch_checked = False

            def _check_consecutive_failures(new_results: list[RequestResult]) -> dict[str, str] | None:
                nonlocal first_batch_checked
                if first_batch_checked or first_batch_size <= 0:
                    return None
                for result in new_results:
                    if 0 <= result.req_id < first_batch_size:
                        first_batch_results[result.req_id] = result
                if len(first_batch_results) < first_batch_size:
                    return None
                first_batch_checked = True
                if all(not result.success for result in first_batch_results.values()):
                    errors = {r.error for r in first_batch_results.values() if not r.success and r.error}
                    if len(errors) != 1:
                        return None
                    common_error = errors.pop()
                    return {
                        "error": f"연속 {first_batch_size}개 요청 실패. 테스트를 중단합니다: {common_error}",
                        "error_type": "consecutive_failure",
                    }
                return None

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
                    processed_results = await self._process_completed_tasks(done, processed_tasks)
                    consecutive_failure = _check_consecutive_failures(processed_results)
                    if consecutive_failure:
                        return await self._fail_run(consecutive_failure, sample_stop, sampling_task, tasks)
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
                        if len(self._state.results) > 1000:
                            self._state.results = self._state.results[-1000:]
                        if result.success:
                            self._state.completed_requests += 1
                        else:
                            self._state.failed_requests += 1
                    stats = self._compute_stats()
                    await self._broadcast({"type": "progress", "data": stats})
                    consecutive_failure = _check_consecutive_failures([result])
                    if consecutive_failure:
                        return await self._fail_run(consecutive_failure, sample_stop, sampling_task, remaining_tasks)
            return await self._finalize_results(config, metric_samples, sample_stop, sampling_task)
        finally:
            if _running_row_id is not None:
                try:
                    shared_module = importlib.import_module("services.shared")
                    _storage = shared_module.storage

                    await _storage.clear_running(_running_row_id)
                except Exception as e:
                    logger.warning("[LoadEngine] Failed to clear running state: %s", e)

    async def stop(self) -> None:
        self._stop_event.set()
        async with self._state_lock:
            self._state.status = LoadTestStatus.STOPPED

    async def run_sweep(self, config: SweepConfig) -> SweepResult:
        async with self._state_lock:
            if self._state.status == LoadTestStatus.RUNNING:
                return SweepResult(
                    config=config,
                    steps=[],
                    total_duration=0.0,
                )

        sweep_start = time.time()
        steps: list[SweepStepResult] = []
        step1_p99: float | None = None
        consecutive_100pct_failures = 0

        rps_range = range(config.rps_start, config.rps_end + 1, config.rps_step)
        for step_num, rps in enumerate(rps_range, start=1):
            if self._state.status == LoadTestStatus.STOPPED:
                break

            self._stop_event.clear()

            step_config = LoadTestConfig(
                endpoint=config.endpoint,
                model=config.model,
                prompt_template=config.prompt,
                total_requests=config.requests_per_step,
                concurrency=config.concurrency,
                rps=rps,
                max_tokens=config.max_tokens,
                temperature=0.7,
                stream=config.stream,
            )

            step_result_raw = await self.run(step_config, skip_preflight=True)

            if self._state.status == LoadTestStatus.STOPPED:
                break

            total_in_step = step_result_raw.get("total", 0)
            failed_in_step = step_result_raw.get("failed", 0)

            if total_in_step > 0 and failed_in_step == total_in_step:
                consecutive_100pct_failures += 1
            else:
                consecutive_100pct_failures = 0
            if consecutive_100pct_failures >= 3:
                break

            error_rate = failed_in_step / max(total_in_step, 1)
            p99_latency = step_result_raw.get("latency", {}).get("p99", 0.0) or 0.0

            if step_num == 1:
                step1_p99 = p99_latency

            saturated = False
            saturation_reason: str | None = None

            if error_rate > config.saturation_error_rate:
                saturated = True
                saturation_reason = f"Error rate {error_rate:.1%} exceeded threshold {config.saturation_error_rate:.1%}"
            elif step1_p99 and step1_p99 > 0 and p99_latency > step1_p99 * config.saturation_latency_factor:
                saturated = True
                saturation_reason = (
                    f"P99 latency {p99_latency:.3f}s > step1 {step1_p99:.3f}s × {config.saturation_latency_factor}"
                )

            step_obj = SweepStepResult(
                step=step_num,
                rps=float(rps),
                stats=step_result_raw,
                saturated=saturated,
                saturation_reason=saturation_reason,
            )
            steps.append(step_obj)

            await self._broadcast({"type": "sweep_step", "data": step_obj.model_dump()})

            if saturated:
                break

        saturation_point: float | None = None
        optimal_rps: float | None = None
        saturated_steps = [s for s in steps if s.saturated]
        if saturated_steps:
            saturation_point = saturated_steps[0].rps
            non_saturated = [s for s in steps if not s.saturated]
            if non_saturated:
                optimal_rps = non_saturated[-1].rps

        return SweepResult(
            config=config,
            steps=steps,
            saturation_point=saturation_point,
            optimal_rps=optimal_rps,
            total_duration=round(time.time() - sweep_start, 2),
        )

    def _compute_stats(self) -> dict[str, Any]:
        results = self._state.results
        if not results:
            return {}

        successful = [r for r in results if r.success]
        latencies = [r.latency for r in successful]
        ttfts = [r.ttft for r in successful if r.ttft is not None]
        tps_values = [r.tps for r in successful if r.tps > 0]
        itl_means = [r.itl_mean for r in successful if r.itl_mean is not None]

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
            "itl": {
                "mean": round(statistics.mean(itl_means), 4) if itl_means else None,
                "p95": round(_percentile(itl_means, 95), 4) if itl_means else None,
                "p99": round(_percentile(itl_means, 99), 4) if itl_means else None,
            }
            if itl_means
            else None,
        }


def _percentile(data: list[float], p: int) -> float:
    if not data:
        return 0
    sorted_data = sorted(data)
    idx = int(len(sorted_data) * p / 100)
    return sorted_data[min(idx, len(sorted_data) - 1)]


# 싱글턴 인스턴스
load_engine = LoadTestEngine()
