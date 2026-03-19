# Issues — enhanced-perf-tests-v2

## [2026-03-07] Known Discrepancies to Watch

1. **TunerStartRequest format**: Plan's `test_auto_tuner.py` uses `http_client.post("/api/tuner/start", json={"n_trials": 2, ...})` but actual router expects `{"config": TuningConfig, "vllm_endpoint": str}`. The test needs to match the router's schema.

2. **MetricsCollector._latest**: The `_collect()` method doesn't set `self._latest`. Check if `start_collection()` sets it elsewhere.

3. **load_engine.run()**: Returns plain dict, not a LoadTestResult Pydantic model. Fields backend_cpu_avg, gpu_utilization_avg, tokens_per_sec need to be added to the dict, not the model.

## [2026-03-07] psutil dependency for tuner tests
- `backend/tests/test_tuner.py` fails with `ModuleNotFoundError: psutil` until `psutil` is installed in the environment.
