# Plan: Backend Code Quality — Critical Bug Fixes & Cleanup

**Created**: 2026-03-06
**Status**: Ready for execution
**Estimated Tasks**: 3 (2 parallel + 1 sequential)
**Scope**: `backend/` only — no frontend, no OpenShift manifests

---

## TL;DR

탐색 중 발견된 **4개의 치명적 async/await 런타임 버그** 수정 + 코드 품질 개선.
현재 부하 테스트 시작/중지/스트리밍이 모두 조용히 실패하는 상태.

## Problem Statement

`backend/routers/load_test.py`에서 `load_engine`의 async 메서드들을 호출할 때 `await`를 누락하거나,
async generator가 아닌 함수에 `async for`를 사용하여 **모든 부하 테스트 기능이 런타임에 실패**합니다.
테스트는 mock으로 우회되어 통과하지만 실제 실행 시 작동하지 않습니다.

추가로: `print()` 사용, 115줄 데드코드, 미사용 import, `/history` 미구현 등 품질 문제 존재.

## Scope

### IN
- `backend/routers/load_test.py` — 4개 await 버그 수정, import 정리, logging 도입
- `backend/services/load_engine.py` — 리턴 타입 어노테이션 수정, 미사용 import 제거
- `backend/main.py` — 115줄 데드코드 제거, 미사용 import 정리, print→logging
- `backend/services/metrics_collector.py` — 디버그 print + 미사용 sys import 제거
- `backend/startup_metrics_shim.py` — print→logging
- `backend/tests/test_load_test.py` — 새 테스트 추가

### OUT
- `frontend/` — 변경 없음
- `openshift/` — 변경 없음
- `backend/routers/metrics.py`, `benchmark.py`, `tuner.py` — 변경 없음
- `backend/services/auto_tuner.py` — 이미 `await load_engine.run()` 올바르게 사용 중
- 디스크 기반 히스토리 저장소 — 범위 밖 (인메모리 deque만)

## Architecture Decision

- `/history` 저장: `collections.deque(maxlen=100)` — 모듈 레벨 인메모리
- `/status` elapsed: `is_running=True`일 때만 실제 경과 시간, 아닐 때 `0.0` (기존 테스트 호환)
- `run()` 함수: 현재처럼 regular async coroutine 유지 (AsyncGenerator로 변경 안함)
- 로깅: `import logging` 패턴 — services/에서 이미 사용 중인 패턴 따름

## Dependency Graph

```
Wave 1 (병렬 실행):
├── Task 1: Fix 4 critical async/await bugs + return type annotation
└── Task 2: Code quality — print→logging, dead code removal, import cleanup

Wave 2 (Wave 1 완료 후):
└── Task 3: Wire /status elapsed + /history store + new tests
```

## Commit Strategy

- Commit 1 (Task 1): `fix: resolve 4 critical async/await bugs in load test router`
- Commit 2 (Task 2): `refactor: replace print() with logging, remove dead fallback code from main.py`
- Commit 3 (Task 3): `feat: wire /status elapsed time and /history in-memory store with tests`

---

## Wave 1 — Parallel (No Dependencies)

### Task 1: Fix 4 Critical Async/Await Bugs + Return Type

**Category**: `quick`
**Skills**: `[]`
**Files**: `backend/routers/load_test.py`, `backend/services/load_engine.py`
**Depends**: None
**Blocks**: Task 3

#### What to do

**File: `backend/routers/load_test.py`**

1. **Line 72** — `async for result in await load_engine.run(config): pass`

   `run()`은 `async def`이지만 `yield`를 사용하지 않는 일반 코루틴입니다.
   `await`하면 dict를 반환하고, `async for`는 dict에 대해 TypeError를 발생시킵니다.
   이 에러는 `except Exception`에 잡혀 print되고 무시됩니다.

   **변경**:
   ```python
   # BEFORE (line 69-78)
   async def run_test():
       global _active_test_task
       try:
           async for result in await load_engine.run(config):
               # Results are broadcasted via subscribe()
               pass
       except Exception as e:
           print(f"[LoadTest] Error: {e}")
       finally:
           _active_test_task = None

   # AFTER
   async def run_test():
       global _active_test_task
       try:
           await load_engine.run(config)
       except Exception as e:
           logging.error("[LoadTest] Error: %s", e)
       finally:
           _active_test_task = None
   ```

2. **Line 104** — `load_engine.stop()` → `await load_engine.stop()`

   `stop()`은 `async def`입니다. `await` 없이 호출하면 코루틴 객체만 생성되고 실행되지 않습니다.

   **변경**:
   ```python
   # BEFORE
   load_engine.stop()

   # AFTER
   await load_engine.stop()
   ```

3. **Line 154** — `queue = load_engine.subscribe()` → `queue = await load_engine.subscribe()`

   `subscribe()`는 `async def`입니다. `await` 없이 호출하면 Queue 대신 코루틴 객체가 반환됩니다.

   **변경**:
   ```python
   # BEFORE
   queue = load_engine.subscribe()

   # AFTER
   queue = await load_engine.subscribe()
   ```

4. **Line 165** — `load_engine.unsubscribe(queue)` → `await load_engine.unsubscribe(queue)`

   **변경**:
   ```python
   # BEFORE
   load_engine.unsubscribe(queue)

   # AFTER
   await load_engine.unsubscribe(queue)
   ```

5. **Line 8** — 미사용 `AsyncGenerator` import 제거

   **변경**:
   ```python
   # BEFORE
   from typing import Optional, Dict, Any, AsyncGenerator

   # AFTER
   from typing import Optional, Dict, Any
   ```

6. **파일 상단에 `import logging` 추가** (line 76의 print 교체 포함)

**File: `backend/services/load_engine.py`**

7. **Line 62** — 리턴 타입 어노테이션 수정

   `run()`은 `yield`를 사용하지 않으므로 AsyncGenerator가 아닙니다.

   **변경**:
   ```python
   # BEFORE
   async def run(self, config: LoadTestConfig) -> AsyncGenerator[dict, None]:

   # AFTER
   async def run(self, config: LoadTestConfig) -> dict:
   ```

8. **Line 8** — 미사용 `AsyncGenerator` import 제거

   **변경**:
   ```python
   # BEFORE
   from typing import AsyncGenerator

   # AFTER (line 삭제)
   ```

#### ⚠️ 주의사항

- `backend/services/auto_tuner.py:259`도 `await self._load_engine.run(test_config)` 호출함 — 이 파일은 이미 올바르게 `await`를 사용하므로 **수정하지 말 것**
- `run()` 함수를 실제 AsyncGenerator(yield 사용)로 변경하면 `auto_tuner.py`가 깨짐 — **하지 말 것**

#### QA (필수 실행)

- [ ] `python3 -m pytest backend/tests/ -v` — 37개 전체 통과
- [ ] `grep -n 'AsyncGenerator' backend/routers/load_test.py backend/services/load_engine.py` — 매치 없음
- [ ] `grep -n 'await load_engine\.' backend/routers/load_test.py` — run, stop, subscribe, unsubscribe 모두 await 사용 확인
- [ ] `grep -n 'load_engine\.\(run\|stop\|subscribe\|unsubscribe\)' backend/routers/load_test.py | grep -v await` — 매치 없음 (await 없는 호출 없음)

---

### Task 2: Code Quality — print→logging, Dead Code Removal, Import Cleanup

**Category**: `quick`
**Skills**: `[]`
**Files**: `backend/main.py`, `backend/services/metrics_collector.py`, `backend/startup_metrics_shim.py`
**Depends**: None
**Blocks**: Task 3

#### What to do

**File: `backend/services/metrics_collector.py`**

1. **Line 5-6** — 디버그 print + sys import 제거

   이 print는 **모든 import 시마다** 실행되어 stderr를 오염시킵니다.
   `sys`는 이 print 외에 다른 곳에서 사용되지 않습니다.

   **변경**:
   ```python
   # BEFORE (lines 5-6)
   import sys
   print(f"[DEBUG] Loading services/metrics_collector: __name__={__name__}, __file__={__file__}", file=sys.stderr)

   # AFTER (두 줄 모두 삭제)
   ```

**File: `backend/main.py`**

2. **Line 69** — print→logging

   **변경**:
   ```python
   # BEFORE
   print("Startup shim not loaded:", e)

   # AFTER
   logging.debug("Startup shim not loaded: %s", e)
   ```

3. **Lines 85-203** — 데드코드 제거

   `routers/__init__.py`가 라우터 객체를 올바르게 re-export하므로 (`from routers.load_test import router as load_test` 등),
   `except ImportError` 블록 전체(115줄)는 절대 실행되지 않는 데드코드입니다.

   **변경**:
   ```python
   # BEFORE (lines 85-203)
   # Placeholder router imports
   # These will be implemented in subsequent tasks (T6-T9)
   try:
       from routers import load_test, metrics, benchmark, tuner
   except ImportError:
       # ... 115줄의 플레이스홀더 코드 ...
       ...

   # AFTER (2줄)
   # Router imports
   from routers import load_test, metrics, benchmark, tuner
   ```

4. **미사용 import 제거** — 데드코드에서만 사용되던 import들:

   ```python
   # 삭제할 import들:
   import uuid                  # line 12 — 데드코드에서만 사용
   from typing import Optional  # line 11 — 데드코드에서만 사용

   from models.load_test import LoadTestConfig, LoadTestResult, LatencyStats, TpsStats, TuningConfig, Benchmark
   # line 23 — 데드코드에서만 사용 → 전체 줄 삭제
   ```

   **잔류 확인**: 삭제 전 `LoadTestConfig` 등이 데드코드 외에 사용되지 않는지 확인 완료.
   - `uuid`: line 106, 194 (모두 데드코드) → 삭제 가능
   - `Optional`: line 113 (데드코드) → 삭제 가능
   - `LoadTestConfig` 등: line 104 (데드코드) → 삭제 가능

5. **`import logging` 추가** — 파일 상단

6. **`from fastapi import APIRouter` (line 92)** — 데드코드 안에 있으므로 자동 제거됨

**File: `backend/startup_metrics_shim.py`**

7. **Line 15** — print→logging

   **변경**:
   ```python
   # BEFORE
   print("[StartupShim] MetricsCollector started (background)")

   # AFTER
   logging.info("[StartupShim] MetricsCollector started (background)")
   ```

   **`import logging` 추가** 필요

#### ⚠️ 주의사항

- `main.py`에서 `from fastapi.responses import JSONResponse, PlainTextResponse`는 유지 — 데드코드 밖(health check, metrics endpoint)에서 사용됨
- `main.py`에서 `from kubernetes import config, client`는 유지 — health check에서 사용됨
- `main.py`에서 `import time`, `import os`는 유지 — health check에서 사용됨
- `metrics_collector.py`의 `logging` import (line 7)는 이미 존재 — 추가 불필요

#### QA (필수 실행)

- [ ] `python3 -m pytest backend/tests/ -v` — 37개 전체 통과
- [ ] `grep -rn 'print(' backend/ --include='*.py' | grep -v tests/ | grep -v __pycache__` — 출력 없음 (0개 print)
- [ ] `wc -l backend/main.py` — 약 150줄 이하 (원래 267줄)
- [ ] `python3 -c "import ast; tree = ast.parse(open('backend/main.py').read()); print('OK')"` — 유효한 Python 구문 확인

---

## Wave 2 — Sequential (Depends on Wave 1)

### Task 3: Wire /status Elapsed Time + /history In-Memory Store + New Tests

**Category**: `quick`
**Skills**: `[]`
**Files**: `backend/routers/load_test.py`, `backend/services/load_engine.py`, `backend/tests/test_load_test.py`
**Depends**: Task 1, Task 2
**Blocks**: None

#### What to do

**File: `backend/services/load_engine.py`**

1. **`elapsed` 프로퍼티 추가** — `LoadTestEngine` 클래스에:

   ```python
   @property
   def elapsed(self) -> float:
       """Return elapsed seconds if running, else 0.0"""
       if self._state.status == LoadTestStatus.RUNNING:
           return time.time() - self._state.start_time
       return 0.0
   ```

**File: `backend/routers/load_test.py`**

2. **`/status` 엔드포인트 개선** — 실제 경과 시간 반환

   **변경**:
   ```python
   # BEFORE
   return {
       "test_id": test_id,
       "running": is_running,
       "config": _current_config,
       "current_result": None,
       "elapsed": 0.0,  # Could compute from engine state if needed
   }

   # AFTER
   return {
       "test_id": test_id,
       "running": is_running,
       "config": _current_config,
       "current_result": None,
       "elapsed": load_engine.elapsed,
   }
   ```

   **중요**: `is_running=False`일 때 `load_engine.elapsed`는 `0.0`을 반환하므로
   기존 테스트 `test_load_test_status_endpoint_defaults`의 `assert data.get("elapsed") == 0.0`이 유지됨.

3. **`/history` 인메모리 저장소 구현**

   파일 상단에 추가:
   ```python
   from collections import deque
   import time as time_module

   # In-memory history store (max 100 entries, no persistence)
   _test_history: deque = deque(maxlen=100)
   ```

   `run_test()` 내 `await load_engine.run(config)` 완료 후 히스토리에 저장:
   ```python
   async def run_test():
       global _active_test_task
       try:
           result = await load_engine.run(config)
           # Store completed test in history
           _test_history.appendleft({
               "test_id": test_id,
               "config": config.model_dump(),
               "result": result,
               "timestamp": time_module.time(),
           })
       except Exception as e:
           logging.error("[LoadTest] Error: %s", e)
       finally:
           _active_test_task = None
   ```

   `/history` 엔드포인트 변경:
   ```python
   @router.get("/history")
   async def get_load_test_history(limit: int = 10):
       """Get list of recent load test runs and their final results."""
       return list(_test_history)[:limit]
   ```

4. **TODO 주석 제거** — line 179의 `# TODO: Implement history retrieval from storage in T7-T9`

**File: `backend/tests/test_load_test.py`**

5. **새 테스트 추가**:

   ```python
   def test_load_test_stop_endpoint(client):
       """Test that POST /stop returns correct response"""
       response = client.post("/api/load_test/stop?test_id=test-123")
       assert response.status_code == 200
       data = response.json()
       assert data.get("status") == "stopped"
       assert data.get("test_id") == "test-123"
   ```

   **기존 테스트 수정 불필요** — `/status`의 `elapsed == 0.0` 어설션은 테스트 미실행 상태에서 여전히 유효.

#### ⚠️ 주의사항

- `time` 모듈은 `load_test.py`에 이미 import 가능하지만, `time.time()` vs `time_module.time()` 네이밍 충돌 주의 — 기존 코드에서 `time` import 여부 확인 후 결정
- `deque`의 `maxlen=100` — 이는 인메모리이므로 프로세스 재시작 시 초기화됨 (의도적)
- `_test_history.appendleft()` 사용 — 최신이 앞에 오도록 (limit 적용 시 최신 N개 반환)

#### QA (필수 실행)

- [ ] `python3 -m pytest backend/tests/ -v` — 모든 테스트 통과 (37개 + 새 테스트)
- [ ] `grep -n 'elapsed.*0\.0' backend/routers/load_test.py` — 하드코딩된 0.0 없음
- [ ] `grep -n 'TODO' backend/routers/load_test.py` — TODO 없음
- [ ] `grep -n 'deque\|_test_history' backend/routers/load_test.py` — 히스토리 스토어 존재 확인

---

## Final Verification Wave

모든 Task 완료 후 최종 검증:

```bash
# 1. 전체 테스트 통과
python3 -m pytest backend/tests/ -v

# 2. print() 호출 제거 확인
grep -rn 'print(' backend/ --include='*.py' | grep -v tests/ | grep -v __pycache__

# 3. AsyncGenerator import 제거 확인
grep -rn 'AsyncGenerator' backend/routers/load_test.py backend/services/load_engine.py

# 4. main.py 사이즈 감소 확인
wc -l backend/main.py

# 5. 모든 load_engine 호출에 await 사용 확인
grep -n 'load_engine\.\(run\|stop\|subscribe\|unsubscribe\)' backend/routers/load_test.py | grep -v await

# 6. TODO 제거 확인
grep -rn 'TODO' backend/routers/load_test.py
```

## Definition of Done

- [ ] 4개 치명적 async/await 버그 수정 완료
- [ ] `load_engine.run()` 리턴 타입 `dict`로 수정
- [ ] 모든 `print()` 호출이 `logging`으로 교체 (또는 제거)
- [ ] `main.py` 데드코드 115줄 제거 (267줄 → ~150줄)
- [ ] 미사용 import 정리 (`AsyncGenerator`, `uuid`, `Optional`, 모델 imports)
- [ ] `/status` 엔드포인트에서 실제 경과 시간 반환
- [ ] `/history` 엔드포인트에서 인메모리 테스트 히스토리 반환
- [ ] 기존 37개 테스트 전부 통과
- [ ] 새 테스트 추가 및 통과
