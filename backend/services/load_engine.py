"""
부하 테스트 엔진 — 동시 요청, RPS 제어, 실시간 결과 스트리밍
"""
import asyncio
import time
import httpx
import statistics

from dataclasses import dataclass, field
from enum import Enum
import json

from models.load_test import LoadTestConfig, LoadTestResult, RequestResult


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
    def __init__(self):
        self._state = LoadTestState()
        self._stop_event = asyncio.Event()
        self._subscribers: list[asyncio.Queue] = []
        self._state_lock = asyncio.Lock()
        self._subscribers_lock = asyncio.Lock()

    @property
    def status(self) -> LoadTestStatus:
        return self._state.status

    @property
    def elapsed(self) -> float:
        """Return elapsed seconds if running, else 0.0"""
        if self._state.status == LoadTestStatus.RUNNING:
            return time.time() - self._state.start_time
        return 0.0

    async def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        async with self._subscribers_lock:
            self._subscribers.append(q)
        return q

    async def unsubscribe(self, q: asyncio.Queue):
        async with self._subscribers_lock:
            self._subscribers.remove(q)

    async def _broadcast(self, data: dict):
        async with self._subscribers_lock:
            targets = list(self._subscribers)
        for q in targets:
            await q.put(data)

    async def run(self, config: LoadTestConfig) -> dict:
        """부하 테스트 실행 — 실시간 결과 yield"""
        self._state = LoadTestState(
            status=LoadTestStatus.RUNNING,
            start_time=time.time(),
        )
        self._stop_event.clear()

        semaphore = asyncio.Semaphore(config.concurrency)
        tasks = []

        # RPS 제어를 위한 토큰 버킷
        interval = 1.0 / config.rps if config.rps > 0 else 0

        async def single_request(req_id: int) -> RequestResult:
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
                            # Streaming — TTFT 측정
                            async with client.stream(
                                "POST",
                                f"{config.endpoint}/v1/completions",
                                json={**payload, "stream": True},
                            ) as resp:
                                async for chunk in resp.aiter_lines():
                                    if chunk.startswith("data: ") and chunk != "data: [DONE]":
                                        if ttft is None:
                                            ttft = time.time() - t0
                                        output_tokens += 1
                        else:
                            resp = await client.post(
                                f"{config.endpoint}/v1/completions",
                                json=payload,
                            )
                            data = resp.json()
                            output_tokens = data["usage"]["completion_tokens"]

                    latency = time.time() - t0
                    return RequestResult(
                        req_id=req_id,
                        success=True,
                        latency=latency,
                        ttft=ttft,
                        output_tokens=output_tokens,
                        tps=output_tokens / latency if latency > 0 else 0,
                    )

                except Exception as e:
                    return RequestResult(
                        req_id=req_id,
                        success=False,
                        latency=time.time() - t0,
                        error=str(e),
                    )

        # 요청 생성 루프
        for i in range(config.total_requests):
            if self._stop_event.is_set():
                break

            task = asyncio.create_task(single_request(i))
            tasks.append(task)

            # 완료된 태스크 처리
            done, _ = await asyncio.wait(
                [t for t in tasks if not t.done()],
                timeout=0,
                return_when=asyncio.FIRST_COMPLETED,
            )
            for t in done:
                result = await t
                async with self._state_lock:
                    self._state.results.append(result)
                    if result.success:
                        self._state.completed_requests += 1
                    else:
                        self._state.failed_requests += 1

                # 실시간 통계 계산
                stats = self._compute_stats()
                await self._broadcast({
                    "type": "progress",
                    "data": stats,
                })

            if interval > 0:
                await asyncio.sleep(interval)

        # 남은 태스크 완료 대기
        if tasks:
            remaining = await asyncio.gather(
                *[t for t in tasks if not t.done()],
                return_exceptions=True,
            )
            for result in remaining:
                if isinstance(result, RequestResult):
                    async with self._state_lock:
                        self._state.results.append(result)

        async with self._state_lock:
            self._state.status = LoadTestStatus.COMPLETED
        final_stats = self._compute_stats()
        await self._broadcast({"type": "completed", "data": final_stats})
        return final_stats

    async def stop(self):
        self._stop_event.set()
        async with self._state_lock:
            self._state.status = LoadTestStatus.STOPPED

    def _compute_stats(self) -> dict:
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
