import asyncio
import logging

def register(app):
    try:
        from services.metrics_collector import MetricsCollector
    except Exception:
        return

    collector = MetricsCollector()
    task_holder = {"task": None}

    @app.on_event("startup")
    async def _start_metrics_collector():
        task_holder["task"] = asyncio.create_task(collector.start_collection(interval=2.0))
        logging.info("[StartupShim] MetricsCollector started (background)")

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
