import asyncio
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


def register(app) -> None:
    try:
        from services.shared import metrics_collector as collector
    except Exception:  # intentional: fail-open
        return

    task_holder: dict[str, Optional[asyncio.Task[Any]]] = {"task": None}

    def _on_task_done(task: asyncio.Task[Any]) -> None:
        """Log if the metrics collection task dies unexpectedly."""
        if not task.cancelled() and task.exception():
            logger.error("[StartupShim] Metrics collection task died: %s", task.exception())

    def _ensure_metrics_task() -> bool:
        task = task_holder["task"]
        if task is None or task.done():
            tracker = getattr(collector, "record_start_request", None)
            if callable(tracker):
                tracker(2.0)
            new_task = asyncio.create_task(collector.start_collection(interval=2.0))
            new_task.add_done_callback(_on_task_done)
            task_holder["task"] = new_task
            logger.info("[StartupShim] MetricsCollector started (background)")
            return True
        return False

    @app.on_event("startup")
    async def _start_metrics_collector() -> None:
        _ensure_metrics_task()

    @app.post("/startup_metrics", tags=["startup_metrics"])
    async def _startup_metrics_endpoint() -> dict[str, Any]:
        started = _ensure_metrics_task()
        task = task_holder["task"]
        running = task is not None and not task.done()
        return {
            "status": "started" if started else "already_running",
            "running": running,
            "collector_version": collector.version,
        }

    @app.on_event("shutdown")
    async def _shutdown_metrics_collector() -> None:
        try:
            collector.stop()
        except Exception as e:  # intentional: non-critical
            # intentional: shutdown cleanup
            logger.debug("[StartupShim] Ignoring exception during shutdown: %s", e)
        if task_holder["task"] is not None:
            try:
                _pending = task_holder["task"]
                await _pending
            except Exception as e:  # intentional: non-critical
                # intentional: ignore exceptions while awaiting task completion
                logger.debug("[StartupShim] Ignoring exception while awaiting task: %s", e)
