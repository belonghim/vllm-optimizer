import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Any, Optional
from weakref import WeakKeyDictionary

logger = logging.getLogger(__name__)

_app_state: WeakKeyDictionary[Any, dict[str, Any]] = WeakKeyDictionary()


def _build_state() -> Optional[dict[str, Any]]:
    try:
        from services.shared import metrics_collector as collector
    except Exception:  # intentional: fail-open
        return None

    task_holder: dict[str, Optional[asyncio.Task[Any]]] = {"task": None}

    def _on_task_done(task: asyncio.Task[Any]) -> None:
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

    return {
        "collector": collector,
        "task_holder": task_holder,
        "ensure": _ensure_metrics_task,
    }


def create_lifespan(app):
    state = _app_state.get(app)
    if state is None:
        state = _build_state()
        if state is not None:
            _app_state[app] = state

    if state is None:
        @asynccontextmanager
        async def _noop_lifespan(app):
            yield

        return _noop_lifespan

    collector = state["collector"]
    task_holder = state["task_holder"]
    _ensure_metrics_task = state["ensure"]

    @asynccontextmanager
    async def lifespan(app):
        _ensure_metrics_task()
        yield
        try:
            collector.stop()
        except Exception as e:  # intentional: non-critical
            logger.debug("[StartupShim] Ignoring exception during shutdown: %s", e)
        if task_holder["task"] is not None:
            try:
                _pending = task_holder["task"]
                await _pending
            except Exception as e:  # intentional: non-critical
                logger.debug("[StartupShim] Ignoring exception while awaiting task: %s", e)

    setattr(lifespan, "_collector", collector)
    setattr(lifespan, "_task_holder", task_holder)
    setattr(lifespan, "_ensure_metrics_task", _ensure_metrics_task)
    return lifespan


def register(app) -> None:
    shim_lifespan = create_lifespan(app)
    collector = getattr(shim_lifespan, "_collector", None)
    task_holder = getattr(shim_lifespan, "_task_holder", None)
    _ensure_metrics_task = getattr(shim_lifespan, "_ensure_metrics_task", None)
    if collector is None or task_holder is None or _ensure_metrics_task is None:
        return

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
