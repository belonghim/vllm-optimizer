import asyncio
import logging
import time
from contextlib import suppress
from typing import Any

logger = logging.getLogger(__name__)

_metrics_available: bool = False
tuner_trials_total: Any = None
tuner_best_score: Any = None
tuner_trial_duration_seconds: Any = None
try:
    from metrics.prometheus_metrics import (  # pyright: ignore[reportImplicitRelativeImport]
        tuner_best_score,  # type: ignore[assignment]
        tuner_trial_duration_seconds,  # type: ignore[assignment]
        tuner_trials_total,  # type: ignore[assignment]
    )

    _metrics_available = True
except ImportError:
    pass


class EventBroadcaster:
    def __init__(self) -> None:
        self._subscribers: list[asyncio.Queue[Any]] = []
        self._subscribers_lock: asyncio.Lock = asyncio.Lock()
        self._persistence_warning_sent: bool = False

    async def subscribe(self) -> asyncio.Queue[Any]:
        q: asyncio.Queue[Any] = asyncio.Queue()
        async with self._subscribers_lock:
            self._subscribers.append(q)
        return q

    async def unsubscribe(self, q: asyncio.Queue[Any]) -> None:
        async with self._subscribers_lock:
            with suppress(ValueError):
                self._subscribers.remove(q)

    async def broadcast(self, data: dict[str, Any]) -> None:
        async with self._subscribers_lock:
            targets = list(self._subscribers)
        for q in targets:
            await q.put(data)

    async def broadcast_persistence_warning_once(self) -> None:
        if self._persistence_warning_sent:
            return
        self._persistence_warning_sent = True
        await self.broadcast(
            {
                "type": "tuning_warning",
                "data": {
                    "message": "트라이얼 저장에 실패했지만 튜닝은 계속 진행합니다",
                },
            }
        )

    def reset_persistence_warning(self) -> None:
        self._persistence_warning_sent = False

    async def emit_trial_metrics(self, trial_start: float, status: str, best_trial: Any, config: Any) -> None:
        try:
            if _metrics_available:
                tuner_trial_duration_seconds.observe(time.monotonic() - trial_start)
                tuner_trials_total.labels(status=status).inc()
                if status == "completed" and best_trial is not None:
                    assert config is not None
                    tuner_best_score.labels(objective=config.objective).set(best_trial.score)
        except Exception as _e:
            logger.debug("[AutoTuner] Metrics emit failed (non-critical): %s", _e)
