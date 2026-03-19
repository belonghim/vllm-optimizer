# Fix 'Start Tuning' Button — API Contract Alignment

## TL;DR

> **Quick Summary**: 'Start Tuning' 버튼이 동작하지 않는 원인은 프론트엔드-백엔드 API 응답 형식 불일치. 버튼 클릭은 되지만 `/tuner/status`와 `/tuner/trials` 응답 형식이 프론트엔드 기대와 다르고, `start()` 함수에 에러 핸들링이 없어 실패가 무시됨.
>
> **Deliverables**:
> - 백엔드 `/tuner/status` 응답 형식 수정 (running, trials_completed, best 필드)
> - 백엔드 `/tuner/trials` 응답 형식 수정 (id, tps, p99_latency, params 필드)
> - 프론트엔드 `start()` 에러 핸들링 추가
> - 기존 테스트 업데이트 + 새 응답 형식 테스트 추가
>
> **Estimated Effort**: Short
> **Parallel Execution**: YES - 2 waves
> **Critical Path**: Task 1 → Task 3 → Task 4

---

## Context

### Original Request
"'Start tuning' 버튼이 동작하지 않아."

### Root Cause Analysis

**3가지 API 계약 불일치**가 원인:

1. **`/tuner/status` 응답 불일치** (치명적):
   - Frontend expects: `{ running: boolean, trials_completed: number, best: { params, tps, p99_latency } }`
   - Backend returns: `{ status: "idle"/"running", current_trial: int|null, best_metric: float|null }`
   - `status.running` → 항상 `undefined` → 버튼 disable 안 됨, 상태 항상 "IDLE", best params 표시 불가

2. **`/tuner/trials` 응답 불일치**:
   - Frontend expects: `{ id, tps, p99_latency, params }`
   - Backend returns: `{ trial_number, parameters, metrics: { tps, p99_latency, score }, status }`
   - 스캐터 차트 데이터 전부 `undefined` → 차트 렌더링 안 됨

3. **`start()` 에러 핸들링 부재**:
   - `fetch()` 실패 시 try/catch 없음
   - HTTP 4xx/5xx도 `fetch()`는 throw하지 않음 → 에러 무시
   - `success: false` 응답도 확인 안 함

4. **p99_latency 단위 불일치** (Metis 발견):
   - `TuningTrial.p99_latency`는 **초(seconds)** 단위 (models/load_test.py:99 문서화)
   - Frontend MetricCard는 `unit="ms"` → 0.52초가 "1 ms"로 표시됨
   - 백엔드 응답에서 ms로 변환 필요

### Metis Review
**Identified Gaps** (addressed):
- `trials_completed: null` 렌더링 → Pydantic 모델에서 기본값 0으로 강제
- `fetch()` 4xx/5xx 미포착 → `!res.ok` 체크 추가
- `test_tuner_start_endpoint` 잘못된 request body → 함께 수정
- `applyBest()` 거짓 성공 알림 → 범위 외 (별도 작업)
- `stop()/applyBest()` 에러 핸들링 → 범위 외

---

## Work Objectives

### Core Objective
백엔드 API 응답 형식을 프론트엔드가 기대하는 형식에 맞춰 'Start Tuning' 버튼과 전체 Tuner 탭이 정상 동작하도록 수정.

### Concrete Deliverables
- `backend/routers/tuner.py`: 새 Pydantic 응답 모델 + 엔드포인트 수정
- `frontend/src/pages/TunerPage.jsx`: `start()` 에러 핸들링
- `backend/tests/test_tuner.py`: 새 응답 형식 테스트 + 기존 테스트 업데이트

### Definition of Done
- [x] `curl /api/tuner/status` → `running`, `trials_completed`, `best` 필드 포함
- [x] `curl /api/tuner/trials` → 각 항목에 `id`, `tps`, `p99_latency`, `params` 필드 포함
- [x] `python3 -m pytest backend/tests/ -x -q -m "not integration"` → 전체 PASS
- [x] Start 버튼 클릭 시 에러 발생하면 UI에 에러 메시지 표시

### Must Have
- `/tuner/status`에 `running: bool`, `trials_completed: int = 0`, `best: Optional[BestTrialInfo]` 필드
- `/tuner/trials` 각 항목에 `id`, `tps`, `p99_latency`, `params`, `score`, `status` 필드 (최상위)
- `p99_latency`는 ms 단위로 반환 (초 → ms 변환)
- `start()` 함수에 try/catch + `!res.ok` 체크 + `!data.success` 체크

### Must NOT Have (Guardrails)
- `auto_tuner.py` 서비스 로직 변경 금지
- `/tuner/start` 요청 파싱 로직 (`TuningStartRequest`) 변경 금지
- `stop()` 또는 `applyBest()` 에러 핸들링 추가 금지
- `applyBest()` UI 동작 (alert) 변경 금지
- 새 엔드포인트 추가 금지
- `fetchStatus` try/catch 변경 금지 (이미 정상 동작)
- 스캐터 차트 "best trial" 하이라이트 점 추가 금지
- `importance` 엔드포인트 stub → 실제 Optuna 연동 금지
- UI에 `elapsed_seconds`/`message` 표시 추가 금지

---

## Verification Strategy

> **ZERO HUMAN INTERVENTION** — ALL verification is agent-executed. No exceptions.

### Test Decision
- **Infrastructure exists**: YES (pytest)
- **Automated tests**: YES (Tests-after — 기존 테스트 업데이트 + 새 테스트 추가)
- **Framework**: pytest with FastAPI TestClient
- **Test command**: `cd backend && python3 -m pytest tests/ -x -q -m "not integration"`

### QA Policy
Every task MUST include agent-executed QA scenarios.
Evidence saved to `.sisyphus/evidence/task-{N}-{scenario-slug}.{ext}`.

- **Backend API**: Bash (curl) — Send requests, assert status + response fields
- **Frontend**: Code inspection + build verification
- **Tests**: Bash (pytest) — Run test suite, verify all pass

---

## Execution Strategy

### Parallel Execution Waves

```
Wave 1 (Start Immediately — independent changes):
├── Task 1: Backend — 새 응답 모델 + 엔드포인트 수정 [quick]
├── Task 2: Frontend — start() 에러 핸들링 추가 [quick]
└── Task 3: Tests — 새 응답 형식 테스트 + 기존 테스트 업데이트 [quick]

Wave 2 (After Wave 1 — verification):
└── Task 4: 전체 테스트 실행 + 통합 검증 [quick]

Wave FINAL (After ALL tasks — independent review):
├── Task F1: Plan compliance audit [oracle]
├── Task F2: Code quality review [unspecified-high]
└── Task F3: Scope fidelity check [deep]

Critical Path: Task 1 → Task 3 → Task 4
Parallel Speedup: Task 1 + Task 2 동시 실행
Max Concurrent: 2 (Wave 1)
```

### Dependency Matrix

| Task | Depends On | Blocks |
|------|-----------|--------|
| 1    | —         | 3, 4   |
| 2    | —         | 4      |
| 3    | 1         | 4      |
| 4    | 1, 2, 3   | F1-F3  |

### Agent Dispatch Summary

- **Wave 1**: **3 tasks** — T1 → `quick`, T2 → `quick`, T3 → `quick` (T1, T2 parallel; T3 after T1)
- **Wave 2**: **1 task** — T4 → `quick`
- **FINAL**: **3 tasks** — F1 → `oracle`, F2 → `unspecified-high`, F3 → `deep`

---

## TODOs

- [x] 1. Backend — 새 Pydantic 응답 모델 정의 + 엔드포인트 수정

  **What to do**:
  - `backend/routers/tuner.py`에 새 Pydantic 응답 모델 추가:
    - `BestTrialInfo(BaseModel)`: `params: dict[str, Any]`, `tps: float`, `p99_latency: float` (ms 단위)
    - `TunerStatusFrontendResponse(BaseModel)`: `running: bool`, `trials_completed: int = 0`, `best: Optional[BestTrialInfo] = None`
    - `TrialFrontendInfo(BaseModel)`: `id: int`, `tps: float`, `p99_latency: float` (ms 단위), `params: dict[str, Any]`, `score: float`, `status: str`
  - `/status` 엔드포인트 수정:
    - `response_model`을 `TunerStatusFrontendResponse`로 변경
    - `running: auto_tuner.is_running` (bool)
    - `trials_completed: len(auto_tuner.trials)` (항상 int, None 불가)
    - `best`: `auto_tuner.best`가 None이면 None, 아니면 `BestTrialInfo(params=best.params, tps=best.tps, p99_latency=best.p99_latency * 1000)` — 초 → ms 변환
  - `/trials` 엔드포인트 수정:
    - `response_model`을 `list[TrialFrontendInfo]`로 변경
    - 각 `TuningTrial`을 `TrialFrontendInfo(id=t.trial_id, tps=t.tps, p99_latency=t.p99_latency * 1000, params=t.params, score=t.score, status=t.status)`로 변환
  - 기존 `TunerStatusResponse` 모델은 삭제하지 말고 유지 (다른 곳에서 참조 가능)
  - 기존 `TrialInfo` 모델도 삭제하지 말고 유지

  **Must NOT do**:
  - `auto_tuner.py` 서비스 로직 변경
  - `TuningStartRequest` 변경
  - 새 엔드포인트 추가
  - `/tuner/start`, `/tuner/stop`, `/tuner/apply-best`, `/tuner/importance` 엔드포인트 변경

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: 단일 파일 수정, 기존 패턴 따르기, Pydantic 모델 추가
  - **Skills**: []
    - 별도 스킬 불필요

  **Parallelization**:
  - **Can Run In Parallel**: YES (Task 2와 동시 실행 가능)
  - **Parallel Group**: Wave 1 (with Task 2)
  - **Blocks**: Task 3, Task 4
  - **Blocked By**: None (can start immediately)

  **References**:

  **Pattern References**:
  - `backend/routers/tuner.py:20-44` — 기존 Pydantic 응답 모델 패턴 (`TunerStatusResponse`, `TrialInfo`). 동일한 파일/패턴으로 새 모델 정의
  - `backend/routers/tuner.py:99-112` — 현재 `/status` 엔드포인트. `auto_tuner.is_running`, `auto_tuner.best`, `auto_tuner.trials` 접근 패턴 참고
  - `backend/routers/tuner.py:115-127` — 현재 `/trials` 엔드포인트. `TuningTrial` → 응답 변환 패턴 참고

  **API/Type References**:
  - `backend/models/load_test.py:94-101` — `TuningTrial` 모델. `trial_id`, `params`, `tps`, `p99_latency`(초 단위), `score`, `status` 필드
  - `backend/services/auto_tuner.py:100-111` — `AutoTuner` properties: `trials` (List[TuningTrial]), `best` (Optional[TuningTrial]), `is_running` (bool)

  **WHY Each Reference Matters**:
  - `tuner.py:20-44`: 새 모델을 이 패턴과 동일하게 정의해야 FastAPI 자동 문서화와 validation이 작동
  - `load_test.py:99`: `p99_latency: float = Field(description="P99 latency in seconds")` — **초 단위**임을 확인. 응답에서 `* 1000`으로 ms 변환 필수
  - `auto_tuner.py:100-111`: `best` property가 None일 수 있음 → Optional 처리 필수

  **Acceptance Criteria**:

  - [x] `TunerStatusFrontendResponse`, `BestTrialInfo`, `TrialFrontendInfo` 모델이 `tuner.py`에 정의됨
  - [x] `/tuner/status` 응답에 `running` (bool), `trials_completed` (int), `best` (null 또는 object) 필드 존재
  - [x] `/tuner/trials` 응답의 각 항목에 `id`, `tps`, `p99_latency`, `params`, `score`, `status` 필드 존재
  - [x] `p99_latency` 값이 ms 단위 (초 × 1000)

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: /tuner/status returns correct shape when idle
    Tool: Bash (curl + python3)
    Preconditions: Backend running, no tuning in progress
    Steps:
      1. curl -s http://localhost:8000/api/tuner/status
      2. Parse JSON, assert 'running' is False (bool)
      3. Assert 'trials_completed' is 0 (int, not None)
      4. Assert 'best' is null
    Expected Result: All assertions pass
    Failure Indicators: KeyError on 'running', 'trials_completed' is null, 'best' key missing
    Evidence: .sisyphus/evidence/task-1-status-idle.json

  Scenario: /tuner/trials returns empty list when idle
    Tool: Bash (curl)
    Preconditions: Backend running, no tuning in progress
    Steps:
      1. curl -s http://localhost:8000/api/tuner/trials
      2. Parse JSON, assert result is empty list []
    Expected Result: Response is []
    Failure Indicators: Non-empty list, 500 error
    Evidence: .sisyphus/evidence/task-1-trials-empty.json
  ```

  **Commit**: YES
  - Message: `fix(backend/tuner): reshape /status and /trials responses to match frontend contract`
  - Files: `backend/routers/tuner.py`
  - Pre-commit: `cd backend && python3 -m pytest tests/test_tuner.py -x -q -m "not integration"`

- [x] 2. Frontend — start() 에러 핸들링 추가

  **What to do**:
  - `frontend/src/pages/TunerPage.jsx`의 `start()` 함수 (line 60-66) 수정:
    1. 함수 시작에 `setError(null)` 추가 (이전 에러 클리어)
    2. 전체 fetch 호출을 `try/catch`로 감싸기
    3. `const res = await fetch(...)` 후 `if (!res.ok) throw new Error(...)` 체크
    4. `const data = await res.json()` 후 `if (!data.success) { setError(data.message || '튜닝 시작 실패'); return; }` 체크
    5. `catch` 블록에서 `setError(\`튜닝 시작 실패: ${err.message}\`)` 호출

  **Must NOT do**:
  - `stop()` 또는 `applyBest()` 함수 수정
  - `fetchStatus()` 함수 수정
  - UI 레이아웃/스타일 변경
  - 다른 페이지 파일 수정

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: 단일 함수 5줄 수정, 명확한 패턴
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES (Task 1과 동시 실행 가능 — 다른 파일)
  - **Parallel Group**: Wave 1 (with Task 1)
  - **Blocks**: Task 4
  - **Blocked By**: None (can start immediately)

  **References**:

  **Pattern References**:
  - `frontend/src/pages/TunerPage.jsx:60-66` — 현재 `start()` 함수. 이 코드를 수정
  - `frontend/src/pages/TunerPage.jsx:24-41` — `fetchStatus()` 함수의 try/catch + setError 패턴. 동일한 에러 처리 패턴 따르기

  **WHY Each Reference Matters**:
  - `TunerPage.jsx:60-66`: 정확히 이 코드를 수정해야 함
  - `TunerPage.jsx:24-41`: `setError(\`튜너 조회 실패: ${err.message}\`)` 패턴 — 동일한 에러 메시지 스타일 따르기

  **Acceptance Criteria**:

  - [x] `start()` 함수에 try/catch 블록 존재
  - [x] `!res.ok` 체크 존재
  - [x] `!data.success` 체크 존재
  - [x] 에러 시 `setError()` 호출

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: start() function has error handling (code inspection)
    Tool: Bash (grep)
    Preconditions: TunerPage.jsx 수정 완료
    Steps:
      1. grep -c "try {" frontend/src/pages/TunerPage.jsx — start 함수 내 try 블록 확인
      2. grep -c "res.ok" frontend/src/pages/TunerPage.jsx — HTTP 에러 체크 확인
      3. grep -c "data.success" frontend/src/pages/TunerPage.jsx — 비즈니스 에러 체크 확인
      4. grep -c "setError" frontend/src/pages/TunerPage.jsx — 에러 표시 호출 확인 (기존 1개 + 새로 2개 = 3개 이상)
    Expected Result: 모든 grep 카운트가 1 이상
    Failure Indicators: grep 카운트 0
    Evidence: .sisyphus/evidence/task-2-error-handling.txt

  Scenario: Frontend builds without errors
    Tool: Bash (npm/vite)
    Preconditions: 소스 수정 완료
    Steps:
      1. cd frontend && npm run build
    Expected Result: Build succeeds with exit code 0
    Failure Indicators: Build fails, syntax errors
    Evidence: .sisyphus/evidence/task-2-build.txt
  ```

  **Commit**: YES
  - Message: `fix(frontend): add error handling to TunerPage start()`
  - Files: `frontend/src/pages/TunerPage.jsx`

- [x] 3. Tests — 새 응답 형식 테스트 추가 + 기존 테스트 업데이트

  **What to do**:
  - `backend/tests/test_tuner.py` 수정:
  
  **새 테스트 추가:**
  - `test_tuner_status_has_running_field`: GET `/api/tuner/status` → `data['running']`이 `False` (bool 타입)
  - `test_tuner_status_has_trials_completed`: GET `/api/tuner/status` → `data['trials_completed']`이 `0` (int 타입)
  - `test_tuner_status_best_is_null_when_idle`: GET `/api/tuner/status` → `data['best']`이 `None`
  - `test_tuner_trials_item_shape_with_data`: `auto_tuner._trials`에 TuningTrial 하나 주입 후 GET `/api/tuner/trials` → 응답의 첫 항목에 `id`, `tps`, `p99_latency`, `params`, `score`, `status` 키가 있고, `trial_number`, `parameters`, `metrics` 키가 없음. `p99_latency`가 ms 단위 (주입한 초 값 × 1000)

  **기존 테스트 업데이트:**
  - `test_tuner_status_endpoint`: 기존 `data.get("status")` 검증 유지하면서 `running`, `trials_completed` 필드도 추가 검증
  - `test_tuner_start_endpoint`: request body를 프론트엔드와 동일한 flat schema로 수정:
    ```python
    request_data = {
        "objective": "balanced",
        "n_trials": 2,
        "eval_requests": 10,
        "vllm_endpoint": "http://localhost:8000",
        "max_num_seqs_min": 64,
        "max_num_seqs_max": 512,
        "gpu_memory_min": 0.80,
        "gpu_memory_max": 0.95,
    }
    ```

  **Must NOT do**:
  - 기존 async 테스트들 변경 (test_apply_params_*, test_wait_for_ready_*, test_start_reapplies_*)
  - 통합 테스트 변경

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: 단일 테스트 파일, 패턴 명확
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: NO (Task 1 완료 후 실행)
  - **Parallel Group**: Sequential (after Task 1)
  - **Blocks**: Task 4
  - **Blocked By**: Task 1 (새 응답 모델이 적용된 후 테스트해야 함)

  **References**:

  **Pattern References**:
  - `backend/tests/test_tuner.py:45-56` — 기존 status/trials 테스트 패턴. `TestClient` + `resp.json()` 패턴
  - `backend/tests/test_tuner.py:66-79` — 기존 start 테스트. 이 request body를 수정

  **API/Type References**:
  - `backend/routers/tuner.py:48-59` — `TuningStartRequest` flat schema. 테스트 request body가 이 스키마와 일치해야 함
  - `backend/models/load_test.py:94-101` — `TuningTrial` 모델. 테스트에서 trial 주입 시 이 모델 사용

  **WHY Each Reference Matters**:
  - `test_tuner.py:45-56`: 기존 테스트 패턴 따라 일관성 유지
  - `TuningStartRequest:48-59`: 테스트의 request body가 프론트엔드 실제 전송 형식과 일치하도록 수정

  **Acceptance Criteria**:

  - [x] 새 테스트 4개 추가됨
  - [x] 기존 `test_tuner_status_endpoint` 업데이트됨
  - [x] 기존 `test_tuner_start_endpoint` request body 수정됨
  - [x] `python3 -m pytest backend/tests/test_tuner.py -x -v -m "not integration"` → 전체 PASS

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: All tuner tests pass
    Tool: Bash (pytest)
    Preconditions: Task 1 (backend 수정) 완료
    Steps:
      1. cd backend && python3 -m pytest tests/test_tuner.py -x -v -m "not integration"
    Expected Result: All tests PASSED, 0 failures, 0 errors
    Failure Indicators: Any test FAILED or ERROR
    Evidence: .sisyphus/evidence/task-3-tuner-tests.txt

  Scenario: Full backend test suite passes
    Tool: Bash (pytest)
    Preconditions: Task 1 + Task 3 완료
    Steps:
      1. cd backend && python3 -m pytest tests/ -x -q -m "not integration"
    Expected Result: All tests pass, 0 failures
    Failure Indicators: Any test failure
    Evidence: .sisyphus/evidence/task-3-full-tests.txt
  ```

  **Commit**: YES
  - Message: `test(tuner): update tests for new response shape + fix start request body`
  - Files: `backend/tests/test_tuner.py`
  - Pre-commit: `cd backend && python3 -m pytest tests/ -x -q -m "not integration"`

- [x] 4. 통합 검증 — 전체 테스트 + 빌드 확인

  **What to do**:
  - 전체 백엔드 테스트 스위트 실행: `cd backend && python3 -m pytest tests/ -x -v -m "not integration"`
  - 프론트엔드 빌드 확인: `cd frontend && npm run build`
  - 변경된 파일 목록 확인: `git diff --name-only` — `auto_tuner.py` 변경 없음 확인
  - 최종 검증: 변경 파일이 `tuner.py`, `TunerPage.jsx`, `test_tuner.py` 3개뿐인지 확인

  **Must NOT do**:
  - 추가 코드 변경
  - 통합 테스트 실행 (클러스터 필요)

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: 명령어 실행 + 결과 확인만
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Wave 2 (after all Wave 1 tasks)
  - **Blocks**: F1, F2, F3
  - **Blocked By**: Task 1, Task 2, Task 3

  **References**:

  **Pattern References**:
  - `pyproject.toml` — pytest 설정, markers 정의
  - `frontend/package.json` — build script 확인

  **Acceptance Criteria**:

  - [x] `python3 -m pytest backend/tests/ -x -v -m "not integration"` → ALL PASS
  - [x] `cd frontend && npm run build` → exit code 0
  - [x] `git diff --name-only` → `auto_tuner.py` 포함되지 않음
  - [x] 변경 파일: `backend/routers/tuner.py`, `frontend/src/pages/TunerPage.jsx`, `backend/tests/test_tuner.py`

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Full backend test suite green
    Tool: Bash (pytest)
    Preconditions: Task 1, 2, 3 완료
    Steps:
      1. cd backend && python3 -m pytest tests/ -x -v -m "not integration" 2>&1
    Expected Result: All tests PASSED
    Failure Indicators: FAILED or ERROR in output
    Evidence: .sisyphus/evidence/task-4-full-tests.txt

  Scenario: Frontend builds successfully
    Tool: Bash
    Preconditions: Task 2 완료
    Steps:
      1. cd frontend && npm run build 2>&1
    Expected Result: Build completes with exit code 0
    Failure Indicators: Non-zero exit code, syntax errors
    Evidence: .sisyphus/evidence/task-4-frontend-build.txt

  Scenario: No forbidden file changes
    Tool: Bash (git)
    Preconditions: All tasks completed
    Steps:
      1. git diff --name-only
      2. Assert auto_tuner.py is NOT in the list
      3. Assert only expected files are changed
    Expected Result: Only tuner.py, TunerPage.jsx, test_tuner.py changed
    Failure Indicators: auto_tuner.py or unexpected files in diff
    Evidence: .sisyphus/evidence/task-4-scope-check.txt
  ```

  **Commit**: NO (verification only)

---

## Final Verification Wave (MANDATORY — after ALL implementation tasks)

> 3 review agents run in PARALLEL. ALL must APPROVE. Rejection → fix → re-run.

- [x] F1. **Plan Compliance Audit** — `oracle` → APPROVE (Must Have [4/4] | Must NOT Have [6/6])
- [x] F2. **Code Quality Review** — `unspecified-high` → APPROVE (63 pass / 0 fail | ACCEPTABLE)
- [x] F3. **Scope Fidelity Check** — `deep` → APPROVE (Tasks [4/4 compliant] | CLEAN)

---

## Commit Strategy

- **Commit 1**: `fix(backend/tuner): reshape /status and /trials responses to match frontend contract`
  - Files: `backend/routers/tuner.py`
  - Pre-commit: `cd backend && python3 -m pytest tests/test_tuner.py -x -q -m "not integration"`

- **Commit 2**: `fix(frontend): add error handling to TunerPage start()`
  - Files: `frontend/src/pages/TunerPage.jsx`

- **Commit 3**: `test(tuner): update tests for new response shape + fix start request body`
  - Files: `backend/tests/test_tuner.py`
  - Pre-commit: `cd backend && python3 -m pytest tests/ -x -q -m "not integration"`

---

## Success Criteria

### Verification Commands
```bash
# 1. Backend unit tests pass
cd backend && python3 -m pytest tests/ -x -q -m "not integration"
# Expected: all tests pass, 0 failures

# 2. /tuner/status returns correct shape
curl -s http://localhost:8000/api/tuner/status | python3 -c "
import sys, json
d = json.load(sys.stdin)
assert isinstance(d['running'], bool), f'running must be bool, got {type(d[\"running\"])}'
assert isinstance(d['trials_completed'], int), f'trials_completed must be int, got {type(d[\"trials_completed\"])}'
assert d['trials_completed'] == 0
assert d['best'] is None
print('OK: /tuner/status shape correct')
"

# 3. /tuner/trials returns correct shape (empty when idle)
curl -s http://localhost:8000/api/tuner/trials | python3 -c "
import sys, json
d = json.load(sys.stdin)
assert isinstance(d, list)
assert len(d) == 0
print('OK: /tuner/trials empty list when idle')
"
```

### Final Checklist
- [x] All "Must Have" present
- [x] All "Must NOT Have" absent
- [x] All tests pass
- [x] No changes to auto_tuner.py
- [x] No changes to TuningStartRequest
