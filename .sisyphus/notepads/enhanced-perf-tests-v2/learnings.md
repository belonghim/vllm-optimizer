# Learnings — enhanced-perf-tests-v2

## [2026-03-07] Session ses_3395bdedaffe2CeuD0guO8P23T — Initial Analysis

### Project Conventions
- **Worktree**: `/home/user/project/vllm-optimizer-perf-tests` (branch: `enhanced-perf-tests-v2`)
- **pyproject.toml**: Only has `pythonpath = ["backend"]` and `asyncio_mode = "auto"` — needs `addopts` and `markers`
- **Test location**: `backend/tests/` (13 existing tests), no `integration/` subdir yet
- **Backend**: FastAPI with async patterns, Pydantic v2
- **Python imports**: `from models.load_test import ...` (pythonpath is `backend/`)

### Key File Paths
- `backend/services/load_engine.py` — `LoadTestEngine.run()` returns dict (NOT LoadTestResult model)
- `backend/services/auto_tuner.py` — has `_wait_for_ready()` with `asyncio.sleep(interval)` loop
- `backend/services/metrics_collector.py` — `_collect()` method exists, needs timing wrapper
- `backend/metrics/prometheus_metrics.py` — custom `_registry`, uses `CollectorRegistry`
- `backend/models/load_test.py` — `LoadTestResult` model (Pydantic), `_compute_stats()` returns plain dict
- `backend/routers/tuner.py` — `TunerStatusResponse` Pydantic model, `get_tuner_status()` endpoint

### Gotchas
- `load_engine.run()` returns a plain `dict`, NOT a `LoadTestResult` instance
- `_compute_stats()` returns a plain dict with keys: elapsed, total, success, failed, rps_actual, latency, ttft, tps
- `MetricsCollector._collect()` stores to `self._latest` implicitly via `update_metrics()` call; need to also store it in `self._latest = metrics` (check if it already does)
- Actually looking at `_collect()`, it doesn't set `self._latest`! It just calls `update_metrics(metrics)` and returns `metrics`. Bug or intended?
- Wait, looking again at `start_collection()`: it calls `_ = await self._collect()` but doesn't assign to `self._latest`. This seems like a bug but I should not change behavior.
- `auto_tuner.py` uses `asyncio.sleep(interval)` in `_wait_for_ready()` - this is where we add wait timing
- `TunerStatusResponse` does NOT have `wait_metrics` field yet
- docs directory: `docs/integration_test_guide.md` exists
- `backend/routers/tuner.py` imports `TuningConfig` from `models.load_test` but the start endpoint takes `TuningStartRequest` with `config: TuningConfig`
- The test `test_auto_tuner.py` calls `http_client.post("/api/tuner/start", json={"n_trials": 2, ...})` directly but the actual router expects `{"config": {...}, "vllm_endpoint": "..."}` - this is a discrepancy in the plan

### Architecture
- OpenShift-specific: UBI9 images, non-root, port 8000/8080
- No Kubernetes Ingress, use OpenShift Route
- Monitoring: Thanos Querier (not Prometheus directly)

## [2026-03-07] Session ses_33952b456ffeDsVOD2Thev1ZAy — Wait metrics tracking
- AutoTuner now records readiness wait durations and poll counts, and exposes them via the `wait_metrics` property.
- `/api/tuner/status` now carries `wait_metrics` so clients can inspect total wait seconds per trial.
- Running `python3 -m pytest backend/tests/test_tuner.py -v --tb=short` required installing `psutil`.
