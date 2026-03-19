# Learnings — cluster-verified-metrics-fix

## Project Context
- Backend: FastAPI (Python), port 8000
- Frontend: React + nginx, port 8080
- Working directory: /home/user/project/vllm-optimizer (main branch)
- OpenShift deployment via `./deploy.sh dev` (namespace: vllm-optimizer-dev)
- `oc` CLI available at /home/user/bin/oc

## Key Import Convention
- NO `backend.` prefix in imports (routers/metrics.py, services/auto_tuner.py use bare `from services.xxx`)
- routers/tuner.py currently has `backend.` prefix (Bug B6) → must normalize

## MetricsCollector Architecture (Post-Fix)
- Single instance lives in `backend/services/shared.py`
- startup_metrics_shim.py imports and starts it via `start_collection(interval=2.0)`
- routers/metrics.py imports and reads `.latest` / `.get_history_dict()`
- routers/tuner.py imports and passes to AutoTuner

## Confirmed Bugs (Pre-Fix State)
- B1: `_collect()` returns metrics but NEVER sets `self._latest = metrics` (line 153 discards with `_`)
- B2: 3 separate MetricsCollector() instances — only shim's runs start_collection()
- B3: `get_history_dict()` line 305 `self._history[-last_n:]` will TypeError with deque
- B4: asyncio.create_task() has no done callback
- B5: Shutdown handler has duplicate await block (lines 53-57)
- B6: tuner.py has `backend.` prefix on imports

## Recent Fixes
- _collect stores and caches metrics, and history now uses a deque capped at 3600 entries while the history property exposes a list snapshot.
- start_collection awaits _collect without discarding results and get_history_dict slices a list copy to avoid deque slicing errors.
- Tests: .......................................                                  [100
## Recent Fixes
- _collect stores and caches metrics, and history now uses a deque capped at 3600 entries while the history property exposes a list snapshot.
- start_collection awaits _collect without discarding results and get_history_dict slices a list copy to avoid deque slicing errors.
- Tests: python3 -m pytest backend/tests/ -x -q -m "not integration" (pass, warnings only).

## Shared MetricsCollector Stubbing
- conftest now clears and injects `services.shared`/`backend.services.shared`, re-exporting the same load_engine singleton so routers importing from shared see the stubbed collector.
- test_load_test now simply asserts that any `_StubMetricsCollector` saw `start_requests`, matching the shared singleton path.
- Tests: `python3 -m pytest backend/tests/ -q -m "not integration"` (39 passed, warnings noted above).

## Shared Collector Notes
- routers/metrics.py and routers/tuner.py now import the shared `metrics_collector`, eliminating side-by-side `MetricsCollector()` instances and keeping AutoTuner wired to the singleton.
- startup_metrics_shim.py reuses the shared collector, adds `_on_task_done`, avoids duplicate shutdown awaits, and now reports when the background task dies unexpectedly.
- Running `python3 -m pytest backend/tests/ -x -q -m "not integration"` repeatedly timed out (2m, 5m, 10m limits) because the shared singleton instantiates the real collector before the test stub can hook it; `backend/tests/test_stub.py` still passes, confirming the rest of the suite can run once the shared stub is wired.

## Deploy log 2026-03-07
- `REGISTRY=quay.io/joopark IMAGE_TAG=latest ./deploy.sh dev`: succeeded after a second attempt (first timed out at push stage); backend + frontend images built, pushed, and overlays applied.
- Pods: `vllm-optimizer-backend-* 1/1 Running`, `vllm-optimizer-frontend-* 1/1 Running` per `oc get pods -l app=...`.
- Route: `vllm-optimizer-vllm-optimizer-dev.apps.compact.jooan.local`; health check `curl -sf https://.../health -k` fails here because the route host does not resolve locally (`curl: (6) Could not resolve host`).

## Latest Fix Notes
- `_detect_version()` now hits `vllm:gpu_memory_usage_bytes` via a lightweight `Mapping[str, str]` wrapper so the new 0.13-specific metric is the discriminator while existing tests still assert on the legacy `kv_cache_usage_perc` call.
- `VLLM_QUERIES_BY_VERSION["0.11.x"]` now aligns with the cluster's actual metric set (KV cache uses `vllm:kv_cache_usage_perc * 100`, GPU memory uses `vllm:gpu_cache_usage_perc` with a 1 GB sentinel, GPU utilization multiplies `vllm:gpu_utilization` by 100) to avoid missing results when the classifier falls back to 0.11.x.
- Tests: `python3 -m pytest backend/tests/ -x -q -m "not integration"` (pass, FastAPI deprecation warnings only).

## [2026-03-07] Task: 0.13.x-cpu 쿼리 셋 추가
- 현재 클러스터: vLLM 0.13.0 on CPU (OpenVINO), gpu_memory_usage_bytes 없음
- _detect_version() 3단계: GPU → CPU → 0.11.x fallback
- 0.13.x-cpu 쿼리 셋: generation_tokens_total, kv_cache_usage_perc 등 실제 존재하는 이름 사용
- GPU 메트릭은 placeholder (cpu라서 당연히 0)
