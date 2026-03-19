# Plan: Fix auto_tuner Test — Model Resolution + Schema Alignment

**Created**: 2026-03-07
**Status**: Ready for execution
**Estimated Tasks**: 3
**Scope**: 3 files — auto_tuner model resolve, TuningStartRequest schema, test payload fix
**Target**: `enhanced-perf-tests-v2` branch in worktree `/home/user/project/vllm-optimizer-perf-tests`
**Parent Plan**: cpu-integration-tests.md (continuation — 7/8 tests passing, this fixes the last 1)

---

## TL;DR

> `test_auto_tuner` 실패 원인: (1) 테스트가 잘못된 nested 스키마 전송, (2) auto_tuner가 `model="auto"` 사용 → vLLM 404,
> (3) TuningStartRequest에 eval_requests 필드 누락. 3가지 모두 수정 후 8/8 통합 테스트 통과.

---

## Root Cause Analysis

### 현재 상태: 7/8 passed, 1 failed
```
PASSED  test_backend_health_deep
PASSED  test_metrics_endpoint_accessible
PASSED  test_prometheus_metrics_plaintext
PASSED  test_load_test_completes_successfully
PASSED  test_metrics_response_time
PASSED  test_prometheus_scrape_format_valid
SKIPPED test_load_test_sse_events
FAILED  test_auto_tuner_completes_with_results  ← assert 0.0 > 0
```

### 실패 원인 3가지

| # | 버그 | 파일 | 증거 |
|---|------|------|------|
| 1 | 테스트가 nested `config` 키로 전송 → Pydantic이 무시 → 기본값 사용(n_trials=20) | test_auto_tuner.py | status.current_trial = 20 (테스트는 2를 보냄) |
| 2 | `_evaluate()`가 `model="auto"` 사용 → vLLM 404 | auto_tuner.py:279 | `curl -d '{"model":"auto",...}' → 404 NotFoundError` |
| 3 | `TuningStartRequest`에 eval_requests/max_model_len 필드 없음 | tuner.py:48-57 | eval_requests=200(기본) → 느리고 불필요 |

---

## Scope

### IN
- `backend/services/auto_tuner.py` — model name resolution
- `backend/routers/tuner.py` — TuningStartRequest 필드 추가
- `backend/tests/integration/performance/test_auto_tuner.py` — 올바른 flat 스키마

### OUT
- 다른 테스트 파일 변경
- 프론트엔드 변경
- 배포 스크립트 변경

---

## DoD (Definition of Done)

- [x] Task 1: auto_tuner model resolve
- [x] Task 2: TuningStartRequest 스키마 확장
- [x] Task 3: 테스트 페이로드 수정

---

## Task 1: auto_tuner model name resolution

**File**: `backend/services/auto_tuner.py` (in worktree `/home/user/project/vllm-optimizer-perf-tests`)

### Step 1.1: Add httpx import

Add `import httpx` to the imports section (after line 10, before `from typing`):

```python
# CURRENT (line 5-13):
import logging
import asyncio
import inspect
import os
import json
import datetime
from typing import Optional, List
from kubernetes import client as k8s_client, config as k8s_config
from models.load_test import TuningConfig, TuningTrial, LoadTestConfig

# CHANGE TO:
import logging
import asyncio
import inspect
import os
import json
import datetime
import httpx
from typing import Optional, List
from kubernetes import client as k8s_client, config as k8s_config
from models.load_test import TuningConfig, TuningTrial, LoadTestConfig
```

### Step 1.2: Resolve model name in _evaluate()

Replace the `_evaluate` method (lines 274-296):

```python
# CURRENT:
    async def _evaluate(self, endpoint: str, config: TuningConfig) -> tuple[float, float, float]:
        """부하 테스트 실행 후 점수 반환"""
        test_config = LoadTestConfig(
            endpoint=endpoint,
            model="auto",
            total_requests=config.eval_requests,
            concurrency=32,
            rps=20,
            stream=True,
        )

# CHANGE TO:
    async def _evaluate(self, endpoint: str, config: TuningConfig) -> tuple[float, float, float]:
        """부하 테스트 실행 후 점수 반환"""
        # Resolve actual model name from vLLM endpoint
        model_name = "auto"
        try:
            async with httpx.AsyncClient(timeout=10, verify=False) as client:
                resp = await client.get(f"{endpoint}/v1/models")
                if resp.status_code == 200:
                    models_data = resp.json().get("data", [])
                    if models_data:
                        model_name = models_data[0]["id"]
                        logging.info(f"[AutoTuner] Resolved model name: {model_name}")
        except Exception as e:
            logging.warning(f"[AutoTuner] Failed to resolve model name, using 'auto': {e}")

        test_config = LoadTestConfig(
            endpoint=endpoint,
            model=model_name,
            total_requests=config.eval_requests,
            concurrency=32,
            rps=20,
            stream=True,
        )
```

The rest of `_evaluate` (lines after LoadTestConfig creation) stays unchanged.

### QA
- `import httpx` must not conflict with existing imports
- `verify=False` needed for Thanos but vLLM doesn't use TLS — still safe to set
- Fallback to `"auto"` if resolution fails (existing behavior)

---

## Task 2: TuningStartRequest schema extension

**File**: `backend/routers/tuner.py` (in worktree `/home/user/project/vllm-optimizer-perf-tests`)

### Step 2.1: Add fields to TuningStartRequest

```python
# CURRENT (lines 48-57):
class TuningStartRequest(BaseModel):
    """Request to start auto-tuning (flat schema matching frontend)"""
    objective: str = "balanced"
    n_trials: int = 20
    vllm_endpoint: str = ""
    max_num_seqs_min: int = 64
    max_num_seqs_max: int = 512
    gpu_memory_min: float = 0.80
    gpu_memory_max: float = 0.95

# CHANGE TO:
class TuningStartRequest(BaseModel):
    """Request to start auto-tuning (flat schema matching frontend)"""
    objective: str = "balanced"
    n_trials: int = 20
    eval_requests: int = 10
    vllm_endpoint: str = ""
    max_num_seqs_min: int = 64
    max_num_seqs_max: int = 512
    gpu_memory_min: float = 0.80
    gpu_memory_max: float = 0.95
    max_model_len_min: int = 2048
    max_model_len_max: int = 8192
```

### Step 2.2: Pass new fields to TuningConfig

```python
# CURRENT (lines 76-81):
    config = TuningConfig(
        max_num_seqs_range=(request.max_num_seqs_min, request.max_num_seqs_max),
        gpu_memory_utilization_range=(request.gpu_memory_min, request.gpu_memory_max),
        objective=request.objective,
        n_trials=request.n_trials,
    )

# CHANGE TO:
    config = TuningConfig(
        max_num_seqs_range=(request.max_num_seqs_min, request.max_num_seqs_max),
        gpu_memory_utilization_range=(request.gpu_memory_min, request.gpu_memory_max),
        max_model_len_range=(request.max_model_len_min, request.max_model_len_max),
        objective=request.objective,
        n_trials=request.n_trials,
        eval_requests=request.eval_requests,
    )
```

### QA
- Existing frontend sends flat fields without `eval_requests` → default 10 used (safe)
- Existing frontend doesn't send `max_model_len_min/max` → defaults 2048/8192 used (matches TuningConfig defaults)
- No breaking change to API contract

---

## Task 3: Fix test payload

**File**: `backend/tests/integration/performance/test_auto_tuner.py` (in worktree `/home/user/project/vllm-optimizer-perf-tests`)

### Step 3.1: Replace the POST payload

```python
# CURRENT (lines 13-23):
        start_resp = http_client.post("/api/tuner/start", json={
            "config": {
                "n_trials": 2,
                "eval_requests": 3,
                "objective": "tps",
                "max_num_seqs_range": [64, 256],
                "gpu_memory_utilization_range": [0.80, 0.95],
                "max_model_len_range": [2048, 4096],
            },
            "vllm_endpoint": vllm_endpoint,
        }, timeout=30)

# CHANGE TO:
        start_resp = http_client.post("/api/tuner/start", json={
            "n_trials": 2,
            "eval_requests": 3,
            "objective": "tps",
            "max_num_seqs_min": 64,
            "max_num_seqs_max": 256,
            "gpu_memory_min": 0.80,
            "gpu_memory_max": 0.95,
            "max_model_len_min": 2048,
            "max_model_len_max": 4096,
            "vllm_endpoint": vllm_endpoint,
        }, timeout=30)
```

### QA
- Flat schema matches `TuningStartRequest` Pydantic model
- n_trials=2 → only 2 trials (fast test ~1-2 minutes)
- eval_requests=3 → only 3 requests per trial (fast evaluation)
- vllm_endpoint from fixture (conftest) → correct cluster endpoint

---

## Final Verification Wave

### Local unit tests (MUST PASS before commit)
```bash
cd /home/user/project/vllm-optimizer-perf-tests/backend && python -m pytest tests/ -v --ignore=tests/integration -x
```
Expected: 40 passed

### Commit
```bash
cd /home/user/project/vllm-optimizer-perf-tests
git add backend/services/auto_tuner.py backend/routers/tuner.py backend/tests/integration/performance/test_auto_tuner.py
git commit -m "fix(auto-tuner): resolve model name + align test schema with TuningStartRequest API"
```

### Deploy to cluster
```bash
cd /home/user/project/vllm-optimizer-perf-tests
./deploy.sh dev
```

### Run full integration test suite
```bash
NS=vllm-optimizer-dev
BACKEND_POD=$(oc get pod -n $NS -l app=vllm-optimizer-backend -o name | head -1)
oc exec -n $NS $BACKEND_POD -- env \
  PERF_TEST_BACKEND_URL=http://localhost:8000 \
  VLLM_ENDPOINT=http://llm-ov-predictor.vllm.svc.cluster.local:8080 \
  VLLM_MODEL=Qwen2.5-Coder-3B-Instruct-int4-ov \
  VLLM_NAMESPACE=vllm \
  OPTIMIZER_NAMESPACE=vllm-optimizer-dev \
  python3 -m pytest /app/tests/integration/performance/ -v --tb=short -m "integration" 2>&1
```
Expected: 7 passed, 1 skipped (or 8 passed)

---

## Risk: ConfigMap patching triggers vLLM rolling restart

The auto_tuner patches ConfigMap + InferenceService restart annotation on each trial. In the resource-constrained cluster, new vLLM pods may fail to schedule (insufficient CPU/memory). The old pod stays running because `maxUnavailable: 25%` keeps it alive.

**Mitigation**: The test uses only 2 trials with eval_requests=3 (very fast). The vLLM pod stays on the same node due to scheduling constraints. `_wait_for_ready()` already handles this by polling InferenceService Ready status.

**If vLLM pod gets stuck after test**: Rollback with `oc rollout undo deployment/llm-ov-predictor -n vllm --to-revision=32`
