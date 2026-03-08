import asyncio
import logging

logger = logging.getLogger(__name__)


def register(app):
    try:
        from services.shared import metrics_collector as collector
    except Exception:
        return

    task_holder = {"task": None}

    def _on_task_done(task: asyncio.Task) -> None:
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
    async def _start_metrics_collector():
        _ensure_metrics_task()

    @app.post("/startup_metrics", tags=["startup_metrics"])
    async def _startup_metrics_endpoint():
        started = _ensure_metrics_task()
        task = task_holder["task"]
        running = task is not None and not task.done()
        return {
            "status": "started" if started else "already_running",
            "running": running,
            "collector_version": collector.version,
        }

    @app.on_event("shutdown")
    async def _shutdown_metrics_collector():
        try:
            collector.stop()
        except Exception:
            pass
        if task_holder["task"] is not None:
            try:
                await task_holder["task"]
            except Exception:
                pass
