# Code Quality Improvements — Bug Fixes & Security Hardening

## TL;DR

> **Quick Summary**: 코드 감사에서 발견된 CRITICAL 2건 + HIGH 4건 + MEDIUM 4건 버그/이슈 수정. 스트리밍 토큰 카운팅 오류, 타임아웃 누락, 레이스 컨디션, Prometheus 메트릭 오용, deprecated API, 보안 강화 등.
>
> **Deliverables**:
> - 스트리밍 모드 정확한 토큰 카운팅 (vLLM usage 파싱)
> - resolve_model_name 전체 호출에 타임아웃 적용
> - 튜너 중지 레이스 컨디션 해결
> - Prometheus Counter → Gauge 전환 (rate 메트릭)
> - FastAPI lifespan 마이그레이션
> - psutil async 래핑, nginx CSP 헤더, SCC 강화, 부하 테스트 동시 실행 방지
>
> **Estimated Effort**: Medium
> **Parallel Execution**: YES — 3 waves
> **Critical Path**: T0 → T1 → T7 (backend chain, longest)

---

## Context

### Original Request
이전 코드 품질 감사에서 기술 부채(full-codebase-cleanup, 완료)와 별도로 발견된 실제 버그 및 보안 이슈 10건 수정.

### Interview Summary
**Key Discussions**:
- 사용자가 "전체 (MEDIUM 포함)" 범위 선택
- 기존 테스트 활용, 새 테스트 파일 생성 안 함
- Tekton Buildah security-opt는 rootless buildah 필수 → SKIP

**Research Findings**:
- vLLM SSE: 각 chunk에 `choices[0].text` 포함, 마지막 chunk에 `usage` 필드 (stream_options.include_usage=True 시)
- PrometheusRules에서 `vllm_optimizer_*` 메트릭 미참조 → 이름 변경 안전
- Frontend/Backend 모두 emptyDir 마운트 존재 → readOnlyRootFilesystem 전환 가능

### Metis Review
**Identified Gaps** (addressed):
- 스트리밍 토큰 카운팅 전략: dual approach (usage 파싱 + chunk fallback) 채택
- Counter→Gauge 이름 변경: PrometheusRules 미참조 확인, `_per_second` 이름으로 변경
- load_test resolve 폴백: `os.getenv("VLLM_MODEL")` 패턴 채택 (main.py와 동일)
- auto_tuner 폴백: resolve 실패 시 trial FAIL이 아닌 환경변수 폴백
- lifespan 마이그레이션: `/startup_metrics` POST 라우트 보존 필수
- SCC: Python .pyc 캐시 실패는 silent → 정상 동작

---

## Work Objectives

### Core Objective
코드 감사에서 발견된 10개 실제 버그/보안 이슈를 기존 동작을 보존하면서 수정.

### Concrete Deliverables
- `backend/services/load_engine.py` — 스트리밍 토큰 카운팅 정확도 수정, psutil async 래핑
- `backend/routers/load_test.py` — resolve 타임아웃 추가, 동시 실행 방지 Lock
- `backend/routers/tuner.py` — stop 레이스 컨디션 수정
- `backend/services/auto_tuner.py` — evaluate 내 resolve 타임아웃 추가
- `backend/metrics/prometheus_metrics.py` — Counter → Gauge 전환
- `backend/startup_metrics_shim.py` + `backend/main.py` — lifespan 마이그레이션
- `frontend/nginx.conf` — CSP 헤더 추가
- `openshift/base/01-namespace-rbac.yaml` — readOnlyRootFilesystem: true

### Definition of Done
- [x] `cd backend && python3 -m pytest tests/ -x -q -m "not integration"` — 120 passed, 0 failures
- [x] `oc apply -k openshift/overlays/dev --dry-run=client` — exit 0
- [x] `oc apply -k openshift/overlays/prod --dry-run=client` — exit 0

### Must Have
- 기존 테스트 통과 (120 passed)
- 기존 API 응답 스키마 불변
- 기존 SSE 이벤트 포맷 불변 (프론트엔드 호환)
- OpenShift overlay 빌드 성공

### Must NOT Have (Guardrails)
- **G1**: 비스트리밍 경로 변경 금지 (이미 정확히 동작)
- **G2**: model_resolver.py 내부 수정 금지 (httpx 10초 타임아웃은 별도 관심사)
- **G3**: 새 테스트 파일 생성 금지
- **G4**: 메트릭 히스토그램 변경 금지
- **G5**: main.py 앱 생성 외 구조 변경 금지 (lifespan 파라미터 추가만)
- **G6**: CSP 외 새 보안 헤더 추가 금지
- **G7**: 부하 테스트 큐잉/스케줄링/영속화 금지 (Lock + 409만)
- **G8**: SCC 외 보안 컨텍스트 변경 금지
- **G9**: 포트 8000/8080 파라미터화 금지
- **G10**: 기존 emptyDir 볼륨 제거/변경 금지

---

## Verification Strategy

> **ZERO HUMAN INTERVENTION** — ALL verification is agent-executed.

### Test Decision
- **Infrastructure exists**: YES
- **Automated tests**: 기존 테스트 실행 (새 파일 없음)
- **Backend**: `cd backend && python3 -m pytest tests/ -x -q -m "not integration"`

### QA Policy
Every task MUST include agent-executed QA scenarios.
Evidence saved to `.sisyphus/evidence/cqi-task-{N}-{scenario-slug}.{ext}`.

---

## Execution Strategy

### Parallel Execution Waves

```
Wave 0 (Baseline — must complete first):
└── T0: Capture current baselines [quick]

Wave 1 (Independent fixes — 5 parallel tasks):
├── T1: Fix streaming token counting (depends: T0) [deep]
├── T2: Add resolve_model_name timeouts (depends: T0) [quick]
├── T3: Fix tuner stop race condition (depends: T0) [quick]
├── T5: SCC readOnlyRootFilesystem (depends: T0) [quick]
└── T9: nginx CSP header (depends: T0) [quick]

Wave 2 (Dependent fixes — 4 parallel tasks):
├── T4: Prometheus Counter → Gauge (depends: T0) [unspecified-high]
├── T6: FastAPI lifespan migration (depends: T0) [deep]
├── T7: psutil async wrapping (depends: T1) [quick]
└── T8: Load test concurrent guard (depends: T2) [quick]

Wave FINAL (After ALL tasks — 3 parallel reviews):
├── F1: Plan compliance audit (oracle)
├── F2: Code quality + test verification (unspecified-high)
└── F3: Scope fidelity check (deep)
→ Present results → Get explicit user okay
```

### Dependency Matrix

| Task | Blocked By | Blocks | Wave |
|------|-----------|--------|------|
| T0 | — | T1-T9 | 0 |
| T1 | T0 | T7 | 1 |
| T2 | T0 | T8 | 1 |
| T3 | T0 | — | 1 |
| T4 | T0 | — | 2 |
| T5 | T0 | — | 1 |
| T6 | T0 | — | 2 |
| T7 | T1 | — | 2 |
| T8 | T2 | — | 2 |
| T9 | T0 | — | 1 |

### Agent Dispatch Summary

- **Wave 0**: **1** — T0 → `quick`
- **Wave 1**: **5** — T1 → `deep`, T2,T3,T5,T9 → `quick`
- **Wave 2**: **4** — T4 → `unspecified-high`, T6 → `deep`, T7,T8 → `quick`
- **FINAL**: **3** — F1 → `oracle`, F2 → `unspecified-high`, F3 → `deep`

---

## TODOs

- [ ] 0. Capture Test Baselines

  **What to do**:
  - Run backend unit tests and record pass count
  - Record current Prometheus metric names/types
  - Verify kustomize builds succeed
  - Save all baselines to `.sisyphus/evidence/cqi-task-0-baselines.md`

  **Must NOT do**: Change any code

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Blocks**: T1-T9
  - **Blocked By**: None

  **References**:
  - `backend/services/load_engine.py:126-130` — streaming token counting code
  - `backend/metrics/prometheus_metrics.py:22-30` — Counter metric definitions

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Baselines captured
    Tool: Bash
    Steps:
      1. cd backend && python3 -m pytest tests/ -x -q -m "not integration" 2>&1 | tail -3
      2. grep -n "Counter\|Gauge" backend/metrics/prometheus_metrics.py | head -10
      3. oc apply -k openshift/overlays/dev --dry-run=client 2>&1 | tail -3
    Expected Result: Test count, metric types, kustomize success all recorded
    Evidence: .sisyphus/evidence/cqi-task-0-baselines.md
  ```

  **Evidence to Capture:**
  - [ ] .sisyphus/evidence/cqi-task-0-baselines.md

  **Commit**: NO

---

- [x] 1. Fix Streaming Token Counting

  **What to do**:
  - In `backend/services/load_engine.py`, modify the streaming branch in `_dispatch_request()`:
    - Add `"stream_options": {"include_usage": True}` to the streaming request payload
    - Parse each SSE chunk as JSON: on the final chunk (where `usage` field exists), use `usage["completion_tokens"]` as the authoritative token count
    - Keep `output_tokens += 1` as fallback counter for older vLLM versions without usage support
    - After loop, prefer usage-based count if available: `output_tokens = usage_tokens if usage_tokens else output_tokens`
  - Preserve TTFT measurement logic exactly as-is
  - Preserve non-streaming path exactly as-is (G1)

  **Must NOT do**:
  - Change non-streaming path (G1)
  - Change model_resolver.py (G2)
  - Add external tokenizer library

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with T2, T3, T5, T9)
  - **Blocks**: T7
  - **Blocked By**: T0

  **References**:
  - `backend/services/load_engine.py:110-145` — `_dispatch_request()` full method
  - `backend/services/load_engine.py:126-130` — Streaming token counting to fix
  - `backend/models/load_test.py:RequestResult` — Result dataclass with `output_tokens` field

  **WHY Each Reference Matters**:
  - Lines 110-145 are the target — must understand both paths before modifying streaming
  - RequestResult defines the output schema — `output_tokens` field must contain accurate count

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Streaming request includes stream_options
    Tool: Bash
    Steps:
      1. grep -n "stream_options\|include_usage" backend/services/load_engine.py
    Expected Result: stream_options.include_usage=True in streaming payload
    Evidence: .sisyphus/evidence/cqi-task-1-stream-options.txt

  Scenario: Token counting parses usage from final chunk
    Tool: Bash
    Steps:
      1. grep -n "usage\|completion_tokens" backend/services/load_engine.py | grep -v "^.*:#"
    Expected Result: Both usage parsing and chunk count fallback present
    Evidence: .sisyphus/evidence/cqi-task-1-token-parsing.txt

  Scenario: All load test tests pass
    Tool: Bash
    Steps:
      1. cd backend && python3 -m pytest tests/test_load_test.py -v --tb=short 2>&1
    Expected Result: Same pass count, 0 failures
    Evidence: .sisyphus/evidence/cqi-task-1-tests.txt
  ```

  **Evidence to Capture:**
  - [ ] .sisyphus/evidence/cqi-task-1-stream-options.txt
  - [ ] .sisyphus/evidence/cqi-task-1-token-parsing.txt
  - [ ] .sisyphus/evidence/cqi-task-1-tests.txt

  **Commit**: YES
  - Message: `fix(load-engine): parse actual token count from vLLM SSE streaming response`
  - Files: `backend/services/load_engine.py`
  - Pre-commit: `cd backend && python3 -m pytest tests/test_load_test.py -v --tb=short`

---

- [x] 2. Add resolve_model_name Timeouts

  **What to do**:
  - In `backend/routers/load_test.py:77`, wrap with timeout matching main.py pattern:
    ```python
    try:
        config.model = await asyncio.wait_for(resolve_model_name(config.endpoint), timeout=3.0)
    except asyncio.TimeoutError:
        config.model = os.getenv("VLLM_MODEL", "auto")
    ```
  - In `backend/services/auto_tuner.py:718`, same pattern:
    ```python
    try:
        model_name = await asyncio.wait_for(resolve_model_name(endpoint), timeout=3.0)
    except asyncio.TimeoutError:
        model_name = os.getenv("VLLM_MODEL", "auto")
    ```
  - Add `import os` if not present

  **Must NOT do**: Change model_resolver.py (G2)

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1
  - **Blocks**: T8
  - **Blocked By**: T0

  **References**:
  - `backend/main.py:146-152` — Existing timeout pattern to copy
  - `backend/routers/load_test.py:77` — Missing timeout
  - `backend/services/auto_tuner.py:718` — Missing timeout

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: All resolve_model_name calls have timeouts
    Tool: Bash
    Steps:
      1. grep -rn "resolve_model_name" backend/ --include="*.py" | grep -v test | grep -v __pycache__
      2. For each, verify wait_for wrapping
    Expected Result: All 3 files have wait_for timeout
    Evidence: .sisyphus/evidence/cqi-task-2-timeouts.txt

  Scenario: All tests pass
    Tool: Bash
    Steps:
      1. cd backend && python3 -m pytest tests/ -x -q -m "not integration" 2>&1 | tail -3
    Expected Result: 120 passed
    Evidence: .sisyphus/evidence/cqi-task-2-tests.txt
  ```

  **Evidence to Capture:**
  - [ ] .sisyphus/evidence/cqi-task-2-timeouts.txt
  - [ ] .sisyphus/evidence/cqi-task-2-tests.txt

  **Commit**: YES
  - Message: `fix(backend): add timeout to all resolve_model_name calls`
  - Files: `backend/routers/load_test.py`, `backend/services/auto_tuner.py`
  - Pre-commit: `cd backend && python3 -m pytest tests/ -x -q -m "not integration"`

---

- [x] 3. Fix Tuner Stop Race Condition

  **What to do**:
  - Move `is_running` check inside `auto_tuner.stop()` under lock:
    ```python
    async def stop(self) -> dict[str, Any]:
        async with self._lock:
            if not self._running:
                return {"success": False, "message": "No tuning is currently running."}
            self._running = False
        return {"success": True, "message": "Tuning stopped."}
    ```
  - Simplify router to delegate entirely:
    ```python
    @router.post("/stop")
    async def stop_tuning() -> dict[str, Any]:
        return await auto_tuner.stop()
    ```

  **Must NOT do**: Add new locks (reuse existing `_lock`)

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1
  - **Blocks**: None
  - **Blocked By**: T0

  **References**:
  - `backend/routers/tuner.py:192-198` — Current stop endpoint
  - `backend/services/auto_tuner.py` — stop() method and _lock usage in start()

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: is_running check inside lock
    Tool: Bash
    Steps:
      1. grep -A10 "async def stop" backend/services/auto_tuner.py | head -15
    Expected Result: _lock used, _running check inside lock
    Evidence: .sisyphus/evidence/cqi-task-3-stop-lock.txt

  Scenario: All tuner tests pass
    Tool: Bash
    Steps:
      1. cd backend && python3 -m pytest tests/test_tuner.py -v --tb=short 2>&1
    Expected Result: Same pass count, 0 failures
    Evidence: .sisyphus/evidence/cqi-task-3-tests.txt
  ```

  **Evidence to Capture:**
  - [ ] .sisyphus/evidence/cqi-task-3-stop-lock.txt
  - [ ] .sisyphus/evidence/cqi-task-3-tests.txt

  **Commit**: YES
  - Message: `fix(tuner): protect stop endpoint with lock to prevent race condition`
  - Files: `backend/routers/tuner.py`, `backend/services/auto_tuner.py`
  - Pre-commit: `cd backend && python3 -m pytest tests/test_tuner.py -v --tb=short`

---

- [x] 4. Prometheus Counter → Gauge for Rate Metrics

  **What to do**:
  - In `backend/metrics/prometheus_metrics.py`:
    - `request_success_total_metric = Counter(...)` → `request_rate_metric = Gauge('vllm_optimizer_requests_per_second', ..., registry=_registry)`
    - `generation_tokens_total_metric = Counter(...)` → `token_rate_metric = Gauge('vllm_optimizer_tokens_per_second', ..., registry=_registry)`
    - `.inc()` → `.set()` in update_metrics_from_snapshot
  - Update all import references in other files if variable names changed

  **Must NOT do**: Change histogram metrics (G4)

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2
  - **Blocks**: None
  - **Blocked By**: T0

  **References**:
  - `backend/metrics/prometheus_metrics.py:22-30` — Counter definitions
  - `backend/metrics/prometheus_metrics.py:118-121` — update_metrics with .inc()
  - `backend/tests/test_prometheus_metrics.py` — Tests may reference old names

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Rate metrics are Gauges
    Tool: Bash
    Steps:
      1. grep -n "Gauge.*per_second" backend/metrics/prometheus_metrics.py
      2. Assert ≥ 2 Gauge definitions
    Expected Result: Rate metrics defined as Gauges
    Evidence: .sisyphus/evidence/cqi-task-4-gauge.txt

  Scenario: Backend tests pass
    Tool: Bash
    Steps:
      1. cd backend && python3 -m pytest tests/ -x -q -m "not integration" 2>&1 | tail -5
    Expected Result: All pass
    Evidence: .sisyphus/evidence/cqi-task-4-tests.txt
  ```

  **Evidence to Capture:**
  - [ ] .sisyphus/evidence/cqi-task-4-gauge.txt
  - [ ] .sisyphus/evidence/cqi-task-4-tests.txt

  **Commit**: YES
  - Message: `fix(prometheus): replace Counter with Gauge for rate metrics`
  - Files: `backend/metrics/prometheus_metrics.py`
  - Pre-commit: `cd backend && python3 -m pytest tests/ -x -q -m "not integration"`

---

- [x] 5. SCC readOnlyRootFilesystem

  **What to do**:
  - In `openshift/base/01-namespace-rbac.yaml`, change `readOnlyRootFilesystem: false` → `true`
  - Verify existing emptyDir volumes cover writable paths (already confirmed)

  **Must NOT do**: Change existing emptyDir volumes (G10), change other security contexts (G8)

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1
  - **Blocks**: None
  - **Blocked By**: T0

  **References**:
  - `openshift/base/01-namespace-rbac.yaml:94` — readOnlyRootFilesystem line
  - `openshift/base/03-backend.yaml` — Backend emptyDir at /tmp
  - `openshift/base/04-frontend.yaml` — Frontend emptyDir at /tmp, /var/cache/nginx, /var/run

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: readOnlyRootFilesystem is true
    Tool: Bash
    Steps:
      1. grep "readOnlyRootFilesystem" openshift/base/01-namespace-rbac.yaml
    Expected Result: readOnlyRootFilesystem: true
    Evidence: .sisyphus/evidence/cqi-task-5-scc.txt

  Scenario: Kustomize builds succeed
    Tool: Bash
    Steps:
      1. oc apply -k openshift/overlays/dev --dry-run=client 2>&1 | tail -3
      2. oc apply -k openshift/overlays/prod --dry-run=client 2>&1 | tail -3
    Expected Result: Both succeed
    Evidence: .sisyphus/evidence/cqi-task-5-kustomize.txt
  ```

  **Evidence to Capture:**
  - [ ] .sisyphus/evidence/cqi-task-5-scc.txt
  - [ ] .sisyphus/evidence/cqi-task-5-kustomize.txt

  **Commit**: YES
  - Message: `fix(scc): set readOnlyRootFilesystem to true`
  - Files: `openshift/base/01-namespace-rbac.yaml`
  - Pre-commit: `oc apply -k openshift/overlays/dev --dry-run=client`

---

- [x] 6. FastAPI Lifespan Migration

  **What to do**:
  - In `backend/startup_metrics_shim.py`:
    - Remove `@app.on_event` decorators
    - Create a lifespan factory function that returns an `@asynccontextmanager` lifespan
    - Preserve the `/startup_metrics` POST route registration
  - In `backend/main.py`:
    - Import lifespan from shim
    - Pass `lifespan=` to `FastAPI()` constructor

  **Must NOT do**: Break `/startup_metrics` POST route, change main.py beyond lifespan param (G5)

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2
  - **Blocks**: None
  - **Blocked By**: T0

  **References**:
  - `backend/startup_metrics_shim.py` — Full file to refactor
  - `backend/main.py:25-35` — App creation
  - `backend/tests/conftest.py` — App reload pattern in tests
  - FastAPI lifespan docs: `https://fastapi.tiangolo.com/advanced/events/#lifespan`

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: No deprecated on_event usage
    Tool: Bash
    Steps:
      1. grep -rn "on_event" backend/ --include="*.py" | grep -v test | grep -v __pycache__
    Expected Result: 0 matches
    Evidence: .sisyphus/evidence/cqi-task-6-no-onevent.txt

  Scenario: Lifespan pattern used
    Tool: Bash
    Steps:
      1. grep -n "lifespan\|asynccontextmanager" backend/startup_metrics_shim.py backend/main.py
    Expected Result: Lifespan context manager defined and used
    Evidence: .sisyphus/evidence/cqi-task-6-lifespan.txt

  Scenario: All backend tests pass
    Tool: Bash
    Steps:
      1. cd backend && python3 -m pytest tests/ -x -q -m "not integration" 2>&1 | tail -5
    Expected Result: 120 passed, 0 failures
    Evidence: .sisyphus/evidence/cqi-task-6-tests.txt
  ```

  **Evidence to Capture:**
  - [ ] .sisyphus/evidence/cqi-task-6-no-onevent.txt
  - [ ] .sisyphus/evidence/cqi-task-6-lifespan.txt
  - [ ] .sisyphus/evidence/cqi-task-6-tests.txt

  **Commit**: YES
  - Message: `refactor(shim): migrate from deprecated on_event to lifespan pattern`
  - Files: `backend/startup_metrics_shim.py`, `backend/main.py`
  - Pre-commit: `cd backend && python3 -m pytest tests/ -x -q -m "not integration"`

---

- [x] 7. Wrap psutil Blocking Call

  **What to do**:
  - In `backend/services/load_engine.py`, change `cpu = proc.cpu_percent()` → `cpu = await asyncio.to_thread(proc.cpu_percent)`

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2
  - **Blocks**: None
  - **Blocked By**: T1 (same file)

  **References**:
  - `backend/services/load_engine.py:73-80` — _sample_metrics with psutil

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: psutil wrapped with to_thread
    Tool: Bash
    Steps:
      1. grep -n "to_thread.*cpu_percent" backend/services/load_engine.py
    Expected Result: to_thread wrapping found
    Evidence: .sisyphus/evidence/cqi-task-7-psutil.txt

  Scenario: Tests pass
    Tool: Bash
    Steps:
      1. cd backend && python3 -m pytest tests/test_load_test.py -v --tb=short 2>&1 | tail -10
    Expected Result: All pass
    Evidence: .sisyphus/evidence/cqi-task-7-tests.txt
  ```

  **Evidence to Capture:**
  - [ ] .sisyphus/evidence/cqi-task-7-psutil.txt
  - [ ] .sisyphus/evidence/cqi-task-7-tests.txt

  **Commit**: YES
  - Message: `fix(load-engine): wrap psutil cpu_percent with asyncio.to_thread`
  - Files: `backend/services/load_engine.py`
  - Pre-commit: `cd backend && python3 -m pytest tests/test_load_test.py -v --tb=short`

---

- [x] 8. Add Load Test Concurrent Guard

  **What to do**:
  - In `backend/routers/load_test.py`:
    - Add `_test_lock = asyncio.Lock()` module-level
    - In `start_load_test()`, acquire lock and check:
      ```python
      async with _test_lock:
          if _active_test_task is not None and not _active_test_task.done():
              raise HTTPException(status_code=409, detail="A load test is already running.")
      ```
  - Ensure cleanup in `finally` block of `run_test()`

  **Must NOT do**: Add queue/scheduler/persistence (G7)

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2
  - **Blocks**: None
  - **Blocked By**: T2 (same file)

  **References**:
  - `backend/routers/load_test.py:30-35` — Global state variables
  - `backend/routers/load_test.py:65-95` — start_load_test endpoint

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Lock and 409 response present
    Tool: Bash
    Steps:
      1. grep -n "Lock\|409\|already running" backend/routers/load_test.py
    Expected Result: asyncio.Lock and 409 found
    Evidence: .sisyphus/evidence/cqi-task-8-guard.txt

  Scenario: Tests pass
    Tool: Bash
    Steps:
      1. cd backend && python3 -m pytest tests/test_load_test.py -v --tb=short 2>&1 | tail -10
    Expected Result: All pass
    Evidence: .sisyphus/evidence/cqi-task-8-tests.txt
  ```

  **Evidence to Capture:**
  - [ ] .sisyphus/evidence/cqi-task-8-guard.txt
  - [ ] .sisyphus/evidence/cqi-task-8-tests.txt

  **Commit**: YES
  - Message: `fix(load-test): add concurrent test prevention with asyncio.Lock`
  - Files: `backend/routers/load_test.py`
  - Pre-commit: `cd backend && python3 -m pytest tests/test_load_test.py -v --tb=short`

---

- [x] 9. Add nginx CSP Header

  **What to do**:
  - In `frontend/nginx.conf`, after existing security headers, add:
    ```nginx
    add_header Content-Security-Policy "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; connect-src 'self'; img-src 'self' data:; font-src 'self';" always;
    ```

  **Must NOT do**: Add other headers beyond CSP (G6), modify existing headers

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1
  - **Blocks**: None
  - **Blocked By**: T0

  **References**:
  - `frontend/nginx.conf:19-23` — Existing security headers

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: CSP header present
    Tool: Bash
    Steps:
      1. grep -n "Content-Security-Policy" frontend/nginx.conf
    Expected Result: CSP header found
    Evidence: .sisyphus/evidence/cqi-task-9-csp.txt

  Scenario: Existing headers preserved
    Tool: Bash
    Steps:
      1. grep -c "X-Frame-Options\|X-Content-Type-Options\|Referrer-Policy" frontend/nginx.conf
    Expected Result: 3 existing headers still present
    Evidence: .sisyphus/evidence/cqi-task-9-existing.txt
  ```

  **Evidence to Capture:**
  - [ ] .sisyphus/evidence/cqi-task-9-csp.txt
  - [ ] .sisyphus/evidence/cqi-task-9-existing.txt

  **Commit**: YES
  - Message: `feat(nginx): add Content-Security-Policy header`
  - Files: `frontend/nginx.conf`
  - Pre-commit: none

---

## Final Verification Wave

> 3 review agents run in PARALLEL. ALL must APPROVE.

- [x] F1. **Plan Compliance Audit** — `oracle`
  For each "Must Have": verify implementation. For each guardrail: search for violations. Check evidence files.
  Output: `Must Have [N/N] | Guardrails [10/10] | VERDICT`

- [x] F2. **Code Quality + Test Verification** — `unspecified-high`
  Run full test suite. Run kustomize builds. Verify Prometheus metrics. Check changed files for quality.
  Output: `Tests [PASS/FAIL] | Kustomize [PASS/FAIL] | VERDICT`

- [x] F3. **Scope Fidelity Check** — `deep`
  For each task: compare spec vs diff. Verify guardrails. Flag scope creep.
  Output: `Tasks [N/N] | Guardrails [10/10] | VERDICT`

---

## Commit Strategy

| Task | Message | Files |
|------|---------|-------|
| T1 | `fix(load-engine): parse actual token count from vLLM SSE streaming response` | `load_engine.py` |
| T2 | `fix(backend): add timeout to all resolve_model_name calls` | `load_test.py`, `auto_tuner.py` |
| T3 | `fix(tuner): protect stop endpoint with lock to prevent race condition` | `tuner.py`, `auto_tuner.py` |
| T4 | `fix(prometheus): replace Counter with Gauge for rate metrics` | `prometheus_metrics.py` |
| T5 | `fix(scc): set readOnlyRootFilesystem to true` | `01-namespace-rbac.yaml` |
| T6 | `refactor(shim): migrate from deprecated on_event to lifespan pattern` | `startup_metrics_shim.py`, `main.py` |
| T7 | `fix(load-engine): wrap psutil cpu_percent with asyncio.to_thread` | `load_engine.py` |
| T8 | `fix(load-test): add concurrent test prevention with asyncio.Lock` | `load_test.py` |
| T9 | `feat(nginx): add Content-Security-Policy header` | `nginx.conf` |

---

## Success Criteria

### Verification Commands
```bash
cd backend && python3 -m pytest tests/ -x -q -m "not integration"  # 120 passed
oc apply -k openshift/overlays/dev --dry-run=client                # success
oc apply -k openshift/overlays/prod --dry-run=client               # success
grep "stream_options" backend/services/load_engine.py              # found
grep -rn "resolve_model_name" backend/ --include="*.py" | grep -v test  # all have wait_for
grep "Gauge.*per_second" backend/metrics/prometheus_metrics.py     # ≥2
grep -rn "on_event" backend/ --include="*.py" | grep -v test      # 0
grep "Content-Security-Policy" frontend/nginx.conf                 # found
grep "readOnlyRootFilesystem: true" openshift/base/01-namespace-rbac.yaml  # found
```

### Final Checklist
- [ ] All tests pass (120 passed)
- [ ] Kustomize dev/prod build success
- [ ] All resolve_model_name calls have timeouts
- [ ] Streaming token counting uses vLLM usage field
- [ ] Prometheus rate metrics use Gauge
- [ ] No deprecated on_event in production code
- [ ] CSP header in nginx
- [ ] readOnlyRootFilesystem: true
- [ ] Load test concurrent guard active
- [ ] Tuner stop race condition fixed
