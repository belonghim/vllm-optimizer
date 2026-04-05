from __future__ import annotations

import asyncio
import logging
import time
from contextlib import suppress
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from models.load_test import TuningConfig, TuningTrial
    from prometheus_client import Counter, Gauge, Histogram

logger = logging.getLogger(__name__)

_metrics_available: bool = False
tuner_trials_total: Counter | None = None
tuner_best_score: Gauge | None = None
tuner_trial_duration_seconds: Histogram | None = None
try:
    from metrics.prometheus_metrics import (  # pyright: ignore[reportImplicitRelativeImport]  # backend/ added to sys.path at runtime
        tuner_best_score,  # type: ignore[assignment]  # module-level declares Counter|Gauge|Histogram|null, import is non-null
        tuner_trial_duration_seconds,  # type: ignore[assignment]  # module-level declares Counter|Gauge|Histogram|null, import is non-null
        tuner_trials_total,  # type: ignore[assignment]  # module-level declares Counter|Gauge|Histogram|null, import is non-null
    )

    _metrics_available = True
except ImportError:
    pass


class EventBroadcaster:
    def __init__(self) -> None:
        self._subscribers: list[asyncio.Queue[dict[str, Any]]] = []
        self._subscribers_lock: asyncio.Lock = asyncio.Lock()
        self._persistence_warning_sent: bool = False

    async def subscribe(self) -> asyncio.Queue[dict[str, Any]]:
        q: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        async with self._subscribers_lock:
            self._subscribers.append(q)
        return q

    async def unsubscribe(self, q: asyncio.Queue[dict[str, Any]]) -> None:
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

    async def emit_trial_metrics(
        self, trial_start: float, status: str, best_trial: TuningTrial | None, config: TuningConfig | None
    ) -> None:
        try:
            if _metrics_available:
                tuner_trial_duration_seconds.observe(time.monotonic() - trial_start)
                tuner_trials_total.labels(status=status).inc()
                if status == "completed" and best_trial is not None:
                    assert config is not None
                    tuner_best_score.labels(objective=config.objective).set(best_trial.score)
        except Exception as _e:  # intentional: non-critical metrics
            logger.debug("[AutoTuner] Metrics emit failed (non-critical): %s", _e)
