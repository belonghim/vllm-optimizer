# Fix Load Test Bugs: Total Requests Display + Save as Benchmark

## TL;DR

> **Quick Summary**: 부하 테스트 페이지의 두 가지 버그 수정 — (1) Total Requests가 실제 설정값보다 적게 표시되는 문제, (2) 완료된 부하 테스트를 벤치마크로 저장하는 기능 부재.
> 
> **Deliverables**:
> - `_compute_stats()`에 `total_requested` 필드 추가 (설정된 요청 수 표시)
> - 프론트엔드 테이블에서 정확한 Total Requests 표시
> - "Save as Benchmark" 버튼 추가 (완료 상태에서만 표시)
> - 인라인 성공/실패 피드백 UI
> - 테스트 파일 신규 생성 (`LoadTestPage.test.jsx`) + 백엔드 테스트 추가
> 
> **Estimated Effort**: Short (3 tasks, 2 waves)
> **Parallel Execution**: YES - 2 waves
> **Critical Path**: Task 1 → Task 2 → Task 3

---

## Context

### Original Request
"부하테스트 페이지에서 Run load test를 실행하면, RPS 만큼 Total requests가 나와야 할텐데. 실제로는 더 적게 수행한 것으로 표시돼. 그리고 저장된 벤치마크에 들어가지도 않아."

### Interview Summary
**Key Discussions**:
- 이전 model-comparison 기능 구현 중 두 버그 발견 및 근본 원인 분석 완료
- Bug 1: `_compute_stats()`가 `len(results)` (수집된 결과 수)를 반환 → 설정된 `total_requests`가 아닌 완료된 요청 수만 표시
- Bug 2: LoadTestPage에 "Save as Benchmark" 버튼 자체가 없음 → POST /api/benchmark/save 백엔드 엔드포인트는 이미 존재

**Research Findings**:
- `LoadTestState` dataclass에 `total_requests: int = 0` 필드가 이미 존재하나 `run()`에서 설정되지 않음
- `LoadTestResult` Pydantic 모델에 `total_requested` 필드가 없어 벤치마크 저장 시 유실됨
- 프론트엔드 `completed` 이벤트 핸들러에서 `setProgress(100)` 호출 누락 (상태 정합성 문제)
- 프론트엔드 config 상태에 `model: "auto"`가 유지됨 → 벤치마크 저장 시 해석된 모델명 대신 "auto" 저장 → start 응답에서 해석된 모델명 캡처 필요
- Progress 계산 시 `data.data = {}` (결과 없음) → `NaN%` 표시 가능 (엣지 케이스)

### Metis Review
**Identified Gaps** (addressed):
- 테이블 행 `["Total Requests", result.total]` 수정이 계획에서 누락됨 → Task 2에 포함
- `LoadTestResult` 스키마에 `total_requested` 필드 추가 여부 미결정 → 추가하기로 결정 (벤치마크 영속성)
- Progress bar가 `status === "running"`일 때만 렌더링 → `setProgress(100)`은 시각적 효과 없음 (상태 정합성만)
- `config.model` 해석값 미캡처 → start 응답에서 해석된 모델명 업데이트 포함
- Mock 모드에서 Save 버튼 동작 미정의 → Mock 모드에서 숨김 처리
- 이중 저장 방지 미정의 → `isSaving` 상태 + 저장 후 비활성화
- NaN 가드 미포함 → 프론트엔드에 방어 코드 추가
- `LoadTestPage.test.jsx` 미존재 → 신규 생성 필요 (EventSource 모킹 포함)

---

## Work Objectives

### Core Objective
부하 테스트 페이지의 Total Requests 표시를 정확하게 수정하고, 완료된 테스트 결과를 벤치마크로 저장할 수 있는 기능을 추가한다.

### Concrete Deliverables
- `backend/services/load_engine.py` — `_compute_stats()`에 `total_requested` 필드 추가, `run()`에서 `LoadTestState.total_requests` 설정
- `backend/models/load_test.py` — `LoadTestResult`에 `total_requested: int = 0` 필드 추가
- `frontend/src/pages/LoadTestPage.jsx` — 테이블 행 수정, `setProgress(100)`, NaN 가드, Save as Benchmark 버튼, 해석된 모델명 캡처
- `frontend/src/pages/LoadTestPage.test.jsx` — 신규 테스트 파일 (10+ 테스트 케이스)
- `backend/tests/test_load_test.py` — `_compute_stats()` 단위 테스트 2+ 케이스 추가

### Definition of Done
- [x] `python3 -m pytest backend/tests/ -m "not integration" -q` → ≥54 passed, 0 failed
- [x] `cd frontend && npx vitest run` → ≥27 passed, 0 failed
- [x] 테이블 "Total Requests" 행이 `config.total_requests` 값 표시
- [x] "Save as Benchmark" 버튼이 완료 상태에서만 표시
- [x] 벤치마크 저장 시 해석된 모델명 포함

### Must Have
- `total_requested` 필드가 progress/completed 이벤트 모두에 포함
- Save 버튼은 `status === "completed" && result !== null && !isMockEnabled` 조건에서만 렌더링
- 이중 저장 방지 (`isSaving` 상태)
- 인라인 성공/실패 피드백 (기존 `COLORS` 사용)
- 기존 52 backend + 17 frontend 테스트 무회귀

### Must NOT Have (Guardrails)
- **새로운 npm/pip 패키지 추가 금지** — 모달, 토스트 라이브러리 등
- **새로운 페이지/탭 추가 금지**
- **`BenchmarkPage.jsx` 수정 금지** — 이 계획의 범위 밖
- **`asyncio.gather()` 남은 태스크 블록의 `failed_requests` 미카운트 버그 수정 금지** — 별도 이슈 (lines 197-206)
- **SSE 이벤트 envelope 형식 변경 금지** (`type`/`data` 구조 유지)
- **크로스 컴포넌트 상태 관리 추가 금지** — Redux, Context 등
- **`_compute_stats()` 시그니처 변경 금지** — 파라미터 추가하지 않음
- **Progress bar 가시성 조건 변경 금지** — `status === "running"` 유지 (`setProgress(100)`은 상태 정합성만)
- **Mock 모드에서 Save 버튼 표시 금지** — 실제 API 필요
- **벤치마크 자동 리프레시 금지** — BenchmarkPage 탭 이동 시 자연 갱신

---

## Verification Strategy

> **ZERO HUMAN INTERVENTION** — ALL verification is agent-executed. No exceptions.

### Test Decision
- **Infrastructure exists**: YES (backend: pytest, frontend: vitest + @testing-library/react)
- **Automated tests**: YES (Tests-after — 각 구현 변경에 대응하는 테스트 포함)
- **Framework**: Backend: `pytest`, Frontend: `vitest` + RTL
- **Strategy**: 각 Task에 구현 + 테스트가 함께 포함됨

### QA Policy
Every task MUST include agent-executed QA scenarios.
Evidence saved to `.sisyphus/evidence/task-{N}-{scenario-slug}.{ext}`.

- **Backend**: Use Bash — `pytest` 실행, `grep` 검증
- **Frontend**: Use Bash — `vitest run` 실행, 출력 확인

---

## Execution Strategy

### Parallel Execution Waves

```
Wave 1 (Start Immediately — backend fix):
└── Task 1: Backend _compute_stats() total_requested fix + tests [quick]

Wave 2 (After Wave 1 — frontend fixes, SEQUENTIAL within wave):
├── Task 2: Frontend progress/table display fix + LoadTestPage.test.jsx [deep]
└── Task 3: Frontend Save as Benchmark button + tests (depends: Task 2) [deep]

Wave FINAL (After ALL tasks):
├── F1: Plan compliance audit [oracle]
├── F2: Code quality review [unspecified-high]
├── F3: Real manual QA [unspecified-high]
└── F4: Scope fidelity check [deep]

Critical Path: Task 1 → Task 2 → Task 3 → Final Wave
Parallel Speedup: ~30% faster than pure sequential (Wave 2 tasks are sequential due to same-file edits, Final Wave is 4-way parallel)
Max Concurrent: 4 (Final Wave)
```

### Dependency Matrix

| Task | Depends On | Blocks |
|------|-----------|--------|
| 1 | — | 2, 3 |
| 2 | 1 | 3 |
| 3 | 1, 2 | — |
| F1-F4 | 1, 2, 3 | — |

### Agent Dispatch Summary

- **Wave 1**: 1 task — T1 → `quick`
- **Wave 2**: 2 tasks — T2 → `deep` + `frontend-ui-ux`, T3 → `deep` + `frontend-ui-ux`
- **FINAL**: 4 tasks — F1 → `oracle`, F2 → `unspecified-high`, F3 → `unspecified-high`, F4 → `deep`

---

## TODOs

- [x] 1. Backend: `_compute_stats()` total_requested 필드 추가 + 테스트

  **What to do**:
  - `backend/services/load_engine.py` line 93-96: `LoadTestState` 초기화에 `total_requests=config.total_requests` 추가
    ```python
    self._state = LoadTestState(
        status=LoadTestStatus.RUNNING,
        start_time=time.time(),
        total_requests=config.total_requests,  # ← 추가
    )
    ```
  - `backend/services/load_engine.py` `_compute_stats()` return dict에 `"total_requested"` 필드 추가 (line 253 부근):
    ```python
    return {
        "elapsed": ...,
        "total": len(results),
        "total_requested": self._state.total_requests,  # ← 추가
        ...
    }
    ```
  - `backend/models/load_test.py` `LoadTestResult` 모델에 필드 추가:
    ```python
    class LoadTestResult(BaseModel):
        ...
        total_requested: int = 0  # ← 추가 (total 필드 바로 아래)
        ...
    ```
  - `backend/tests/test_load_test.py`에 단위 테스트 2개 추가:
    - `test_compute_stats_includes_total_requested`: `LoadTestState.total_requests=200` 설정 후 `_compute_stats()` 호출 → `stats["total_requested"] == 200` 확인
    - `test_compute_stats_total_requested_defaults_to_zero`: 기본 상태에서 `_compute_stats()` → `stats["total_requested"] == 0` 확인
  - 기존 52개 테스트 무회귀 확인

  **Must NOT do**:
  - `_compute_stats()` 메서드 시그니처 변경 (파라미터 추가 금지)
  - `asyncio.gather()` 남은 태스크 블록 수정 (lines 197-206)
  - SSE 이벤트 envelope 형식 변경

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: 3개 파일에 각각 1-3줄 변경 + 테스트 2개 추가. 단순 수정.
  - **Skills**: []
    - No skills needed — pure backend Python changes
  - **Skills Evaluated but Omitted**:
    - `playwright`: 브라우저 관련 작업 없음
    - `frontend-ui-ux`: 백엔드 전용 작업

  **Parallelization**:
  - **Can Run In Parallel**: NO (Wave 1 단독)
  - **Parallel Group**: Wave 1
  - **Blocks**: Task 2, Task 3
  - **Blocked By**: None (즉시 시작 가능)

  **References** (CRITICAL):

  **Pattern References**:
  - `backend/services/load_engine.py:26-33` — `LoadTestState` dataclass: `total_requests: int = 0` 필드가 이미 존재하나 `run()`에서 설정하지 않음
  - `backend/services/load_engine.py:91-96` — `run()` 메서드의 `LoadTestState` 초기화 코드: 여기에 `total_requests=config.total_requests` 추가
  - `backend/services/load_engine.py:239-273` — `_compute_stats()` 메서드: `"total": len(results)` 다음에 `"total_requested"` 필드 추가 위치
  - `backend/tests/test_load_test.py` — 기존 테스트 패턴 참조 (isolated_client 픽스처 사용)

  **API/Type References**:
  - `backend/models/load_test.py:54-68` — `LoadTestResult` 모델: `total: int = 0` 바로 아래에 `total_requested: int = 0` 추가
  - `backend/models/load_test.py:27-35` — `RequestResult` 모델: `_compute_stats()` 테스트에서 사용할 모델

  **WHY Each Reference Matters**:
  - `LoadTestState.total_requests` 필드가 이미 존재하므로 새 필드를 추가할 필요 없이 초기화만 추가하면 됨
  - `_compute_stats()`는 `self._state`에 접근하므로 `self._state.total_requests` 직접 참조 가능
  - `LoadTestResult`에 `total_requested` 추가는 벤치마크 저장 시 필드 유지를 위함 (Pydantic 기본값 0으로 하위 호환)

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: _compute_stats()에 total_requested 필드 포함 확인
    Tool: Bash (pytest)
    Preconditions: backend/tests/ 디렉토리에서 실행
    Steps:
      1. python3 -m pytest backend/tests/test_load_test.py::test_compute_stats_includes_total_requested -v
      2. 출력에 "PASSED" 포함 확인
    Expected Result: 테스트 PASSED
    Failure Indicators: "FAILED" 또는 "AssertionError" 포함
    Evidence: .sisyphus/evidence/task-1-compute-stats-total-requested.txt

  Scenario: 전체 백엔드 테스트 무회귀
    Tool: Bash (pytest)
    Preconditions: 프로젝트 루트에서 실행
    Steps:
      1. python3 -m pytest backend/tests/ -m "not integration" -q
      2. 출력에 "passed" 포함, "failed" 미포함 확인
      3. passed 수 ≥ 54 확인
    Expected Result: ≥54 passed, 0 failed
    Failure Indicators: "failed" 포함 또는 passed < 54
    Evidence: .sisyphus/evidence/task-1-backend-regression.txt

  Scenario: LoadTestResult 모델에 total_requested 필드 존재 확인
    Tool: Bash (grep)
    Preconditions: None
    Steps:
      1. grep -n "total_requested" backend/models/load_test.py
      2. 결과에 LoadTestResult 클래스 내 필드 정의 포함 확인
    Expected Result: "total_requested: int = 0" 라인 출력
    Failure Indicators: 출력 없음
    Evidence: .sisyphus/evidence/task-1-model-field.txt
  ```

  **Commit**: YES
  - Message: `feat(engine): emit total_requested in load test stats`
  - Files: `backend/services/load_engine.py`, `backend/models/load_test.py`, `backend/tests/test_load_test.py`
  - Pre-commit: `python3 -m pytest backend/tests/ -m "not integration" -q`

---

- [x] 2. Frontend: LoadTestPage 진행률/테이블 표시 수정 + 테스트 파일 생성

  **What to do**:
  - `frontend/src/pages/LoadTestPage.test.jsx` 신규 생성:
    - `vi.stubGlobal('EventSource', MockEventSource)` — jsdom에 EventSource 없음
    - `vi.stubGlobal('fetch', vi.fn())` — fetch 모킹
    - `vi.mock('../contexts/MockDataContext', () => ({ useMockData: () => ({ isMockEnabled: false }) }))` — MockData 모킹
    - 테스트 케이스:
      - `renders "Total Requests" as total_requested when available` — `result={total:150, total_requested:200}` → 테이블에 "200" 표시 확인
      - `renders "Total Requests" as total (fallback) when no total_requested` — `result={total:150}` → "150" 표시
      - `does not display NaN progress` — `data.data={}` 시 NaN 방지 확인
  - `frontend/src/pages/LoadTestPage.jsx` 수정:
    - **Line 62-70** (progress 핸들러): NaN 가드 추가
      ```jsx
      if (data.type === "progress" && data.data) {
        const d = data.data;
        if (d.total != null) {  // ← NaN 방지
          setProgress(Math.round((d.total / config.total_requests) * 100));
        }
        // ... 나머지 동일
      }
      ```
    - **Line 72-77** (completed 핸들러): `setProgress(100)` 추가 (상태 정합성)
      ```jsx
      if (data.type === "completed") {
        setStatus("completed");
        setProgress(100);  // ← 추가
        es.close();
        esRef.current = null;
        setResult(data.data);
      }
      ```
    - **Line 212** (테이블 행): `result.total` → `result.total_requested ?? result.total`
      ```jsx
      ["Total Requests", result.total_requested ?? result.total],
      ```
    - **Line 44-50** (start 함수): POST /start 응답에서 해석된 모델명 캡처
      ```jsx
      const resp = await fetch(`${API}/load_test/start`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(config),
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const startData = await resp.json();
      if (startData.config?.model) {
        setConfig(c => ({ ...c, model: startData.config.model }));
      }
      ```
  - 기존 17개 프론트엔드 테스트 무회귀 확인

  **Must NOT do**:
  - Progress bar 가시성 조건 변경 금지 (`status === "running"` 유지)
  - SSE 핸들링 패턴 리팩토링 금지
  - `BenchmarkPage.jsx` 수정 금지

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: 신규 테스트 파일 생성 (EventSource 모킹 전략), 여러 JSX 변경, 엣지 케이스 핸들링
  - **Skills**: [`frontend-ui-ux`]
    - `frontend-ui-ux`: React 컴포넌트 테스트 패턴 및 UI 일관성 보장
  - **Skills Evaluated but Omitted**:
    - `playwright`: jsdom 기반 유닛 테스트만 수행
    - `dev-browser`: 브라우저 자동화 불필요

  **Parallelization**:
  - **Can Run In Parallel**: NO (Task 3이 이 테스트 파일 사용)
  - **Parallel Group**: Wave 2 (순차)
  - **Blocks**: Task 3
  - **Blocked By**: Task 1

  **References** (CRITICAL):

  **Pattern References**:
  - `frontend/src/pages/BenchmarkPage.test.jsx` — 컴포넌트 테스트 구조: `vi.mock('../contexts/MockDataContext')` 패턴
  - `frontend/src/components/MetricCard.test.jsx` — 최소 렌더 테스트 패턴
  - `frontend/src/pages/LoadTestPage.jsx:30-89` — `start()` 함수 전체: POST /start → EventSource 연결 흐름
  - `frontend/src/pages/LoadTestPage.jsx:62-77` — SSE 메시지 핸들러: progress + completed 이벤트 처리
  - `frontend/src/pages/LoadTestPage.jsx:210-228` — 결과 테이블: `["Total Requests", result.total]` 수정 대상

  **API/Type References**:
  - `backend/routers/load_test.py:99-104` — POST /start 응답 shape: `{test_id, status, message, config}` — `config.model`에 해석된 모델명 포함
  - `backend/services/load_engine.py:251-253` — `_compute_stats()` 반환 shape: `{total, total_requested, ...}`

  **External References**:
  - vitest `vi.stubGlobal()` 문서: EventSource와 fetch를 jsdom에서 모킹하기 위해 필요

  **WHY Each Reference Matters**:
  - `BenchmarkPage.test.jsx`는 MockDataContext 모킹 패턴의 정확한 참조 — 동일 방식 사용
  - `LoadTestPage.jsx:62-77`은 수정 대상 코드 — NaN 가드와 setProgress(100) 삽입 위치
  - POST /start 응답에서 `config.model`을 읽어 프론트엔드 상태 업데이트 — 벤치마크 저장 시 "auto" 대신 실제 모델명 사용

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Total Requests 테이블 행이 total_requested 표시
    Tool: Bash (vitest)
    Preconditions: frontend/ 디렉토리에서 실행
    Steps:
      1. cd frontend && npx vitest run src/pages/LoadTestPage.test.jsx --reporter=verbose
      2. "Total Requests" 관련 테스트가 PASS 확인
    Expected Result: 모든 LoadTestPage 테스트 PASS
    Failure Indicators: "FAIL" 포함
    Evidence: .sisyphus/evidence/task-2-loadtest-table.txt

  Scenario: 전체 프론트엔드 테스트 무회귀
    Tool: Bash (vitest)
    Preconditions: frontend/ 디렉토리에서 실행
    Steps:
      1. cd frontend && npx vitest run
      2. 출력에 "Tests" 라인 확인, failed 수 = 0
      3. passed 수 ≥ 20 확인 (17 기존 + ≥3 신규)
    Expected Result: ≥20 passed, 0 failed
    Failure Indicators: "failed" > 0
    Evidence: .sisyphus/evidence/task-2-frontend-regression.txt

  Scenario: NaN 가드 적용 확인
    Tool: Bash (grep)
    Preconditions: None
    Steps:
      1. grep -n "total != null\|total !== undefined" frontend/src/pages/LoadTestPage.jsx
      2. progress 핸들러 내 가드 코드 존재 확인
    Expected Result: NaN 방지 조건문 라인 출력
    Failure Indicators: 출력 없음
    Evidence: .sisyphus/evidence/task-2-nan-guard.txt

  Scenario: setProgress(100) completed 핸들러 포함 확인
    Tool: Bash (grep)
    Preconditions: None
    Steps:
      1. grep -A5 "completed" frontend/src/pages/LoadTestPage.jsx | grep "setProgress(100)"
      2. completed 블록 내 setProgress(100) 존재 확인
    Expected Result: setProgress(100) 라인 출력
    Failure Indicators: 출력 없음
    Evidence: .sisyphus/evidence/task-2-progress-100.txt
  ```

  **Commit**: YES (Task 3과 함께 그룹)
  - Message: `fix(load-test): show configured total and add Save as Benchmark`
  - Files: `frontend/src/pages/LoadTestPage.jsx`, `frontend/src/pages/LoadTestPage.test.jsx`
  - Pre-commit: `cd frontend && npx vitest run`

---

- [x] 3. Frontend: Save as Benchmark 버튼 + 테스트

  **What to do**:
  - `frontend/src/pages/LoadTestPage.jsx`에 상태 추가:
    ```jsx
    const [isSaving, setIsSaving] = useState(false);
    const [saveStatus, setSaveStatus] = useState(null); // null | "ok" | "error"
    ```
  - `saveAsBenchmark` 핸들러 추가:
    ```jsx
    const saveAsBenchmark = async () => {
      if (isSaving || !result) return;
      setIsSaving(true);
      setSaveStatus(null);
      const name = `${config.model} @ ${new Date().toLocaleDateString()}`;
      try {
        const resp = await fetch(`${API}/benchmark/save`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ name, config, result }),
        });
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        setSaveStatus("ok");
      } catch {
        setSaveStatus("error");
      } finally {
        setIsSaving(false);
      }
    };
    ```
  - 결과 섹션 하단에 Save 버튼 JSX 추가 (latencyData 차트 뒤, `</>` 종료 전):
    ```jsx
    {status === "completed" && result && !isMockEnabled && (
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 12 }}>
        <button className="btn btn-primary" onClick={saveAsBenchmark}
          disabled={isSaving || saveStatus === "ok"}>
          {saveStatus === "ok" ? "✓ Saved" : isSaving ? "Saving..." : "⬆ Save as Benchmark"}
        </button>
        {saveStatus === "error" && (
          <span style={{ color: COLORS.red, fontSize: 11, fontFamily: font.mono }}>
            ✗ Save failed
          </span>
        )}
      </div>
    )}
    ```
  - `frontend/src/pages/LoadTestPage.test.jsx`에 테스트 추가:
    - `Save as Benchmark button absent when status is idle` — idle 상태에서 버튼 없음
    - `Save as Benchmark button absent when status is running` — running 상태에서 버튼 없음
    - `Save as Benchmark button present when status is completed and result exists` — completed + result 존재 시 버튼 표시
    - `Save as Benchmark calls POST /api/benchmark/save with correct payload` — fetch 호출 검증 (name, config, result 포함)
    - `Save as Benchmark shows success feedback after 200 response` — "✓ Saved" 텍스트 DOM 확인
    - `Save as Benchmark shows error feedback after failed fetch` — "✗ Save failed" 텍스트 DOM 확인
    - `Save as Benchmark button hidden in mock mode` — `isMockEnabled=true` 시 버튼 없음
  - `status`, `result` 초기화 시 `saveStatus` 리셋: `start()` 함수 내 `setSaveStatus(null)` 추가

  **Must NOT do**:
  - 새로운 npm 패키지 추가 금지 (모달, 토스트 라이브러리)
  - `window.prompt()` 사용 금지 (이름 자동 생성)
  - BenchmarkPage 자동 리프레시 금지
  - 크로스 컴포넌트 상태 관리 추가 금지

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: async 핸들러, fetch 모킹, 상태 머신 (idle/saving/saved/error), 7개 테스트 케이스
  - **Skills**: [`frontend-ui-ux`]
    - `frontend-ui-ux`: 버튼/피드백 UI가 다크 테마에 시각적으로 맞아야 함
  - **Skills Evaluated but Omitted**:
    - `playwright`: jsdom 유닛 테스트만 수행
    - `git-master`: git 작업 없음

  **Parallelization**:
  - **Can Run In Parallel**: NO (Task 2와 동일 파일 수정)
  - **Parallel Group**: Wave 2 (Task 2 이후 순차)
  - **Blocks**: None
  - **Blocked By**: Task 1, Task 2

  **References** (CRITICAL):

  **Pattern References**:
  - `frontend/src/pages/LoadTestPage.jsx:151-158` — 기존 버튼 스타일: `className="btn btn-primary"`, `className="btn btn-danger"` 패턴
  - `frontend/src/pages/LoadTestPage.jsx:162-174` — 기존 에러 메시지 스타일: `COLORS.red`, `fontSize: 11`, `fontFamily` 패턴 — Save 실패 피드백 동일 패턴 사용
  - `frontend/src/pages/BenchmarkPage.test.jsx` — 컴포넌트 테스트 패턴: `vi.mock('../contexts/MockDataContext')`, `render()`, `screen.getByText()`
  - `frontend/src/mockData.js:78-96` — `simulateLoadTest()`: mock 모드에서 `setStatus("completed")` 호출 — mock 완료 시에도 Save 버튼이 표시되지 않아야 함 (`!isMockEnabled` 가드)

  **API/Type References**:
  - `backend/routers/benchmark.py:22-28` — `POST /api/benchmark/save` 엔드포인트: `Benchmark` 모델 수신 → `{name: str, config: LoadTestConfig, result: LoadTestResult}` shape
  - `backend/models/load_test.py:123-129` — `Benchmark` 모델: `id` (optional, 서버 생성), `name` (필수), `timestamp` (서버 생성), `config`, `result`
  - `frontend/src/constants.js:2` — `API = "/api"` — fetch URL: `${API}/benchmark/save`

  **WHY Each Reference Matters**:
  - 기존 버튼 `className` 패턴을 따라야 UI 일관성 유지
  - `POST /api/benchmark/save`의 정확한 payload shape를 알아야 올바른 fetch body 구성
  - `Benchmark` 모델의 `id`/`timestamp`는 서버가 생성하므로 프론트엔드에서 보내지 않음
  - Mock 모드에서 `simulateLoadTest()`가 `setStatus("completed")` 호출 → `!isMockEnabled` 가드 필수

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Save as Benchmark 버튼 완료 상태에서만 표시
    Tool: Bash (vitest)
    Preconditions: frontend/ 디렉토리에서 실행
    Steps:
      1. cd frontend && npx vitest run src/pages/LoadTestPage.test.jsx --reporter=verbose
      2. Save 관련 테스트 7개 모두 PASS 확인
    Expected Result: 모든 Save 관련 테스트 PASS
    Failure Indicators: "FAIL" 포함
    Evidence: .sisyphus/evidence/task-3-save-button-tests.txt

  Scenario: 전체 프론트엔드 테스트 무회귀
    Tool: Bash (vitest)
    Preconditions: frontend/ 디렉토리에서 실행
    Steps:
      1. cd frontend && npx vitest run
      2. passed 수 ≥ 27 확인 (17 기존 + ≥10 신규 LoadTestPage 테스트)
      3. failed 수 = 0
    Expected Result: ≥27 passed, 0 failed
    Failure Indicators: failed > 0 또는 passed < 27
    Evidence: .sisyphus/evidence/task-3-frontend-full.txt

  Scenario: Save 버튼 클릭 시 올바른 API 호출 확인 (코드 검증)
    Tool: Bash (grep)
    Preconditions: None
    Steps:
      1. grep -n "benchmark/save" frontend/src/pages/LoadTestPage.jsx
      2. fetch 호출에 "/api/benchmark/save" 포함 확인
      3. grep -n "JSON.stringify" frontend/src/pages/LoadTestPage.jsx | grep -i "benchmark\|save"
      4. payload에 name, config, result 포함 확인
    Expected Result: fetch URL과 payload 구조 확인
    Failure Indicators: URL 불일치 또는 payload 필드 누락
    Evidence: .sisyphus/evidence/task-3-api-call.txt

  Scenario: Mock 모드에서 Save 버튼 숨김 확인 (코드 검증)
    Tool: Bash (grep)
    Preconditions: None
    Steps:
      1. grep -n "isMockEnabled" frontend/src/pages/LoadTestPage.jsx
      2. Save 버튼 렌더링 조건에 "!isMockEnabled" 포함 확인
    Expected Result: Save 버튼 조건에 mock 가드 포함
    Failure Indicators: isMockEnabled 가드 없음
    Evidence: .sisyphus/evidence/task-3-mock-guard.txt

  Scenario: 백엔드 테스트 무회귀
    Tool: Bash (pytest)
    Preconditions: 프로젝트 루트에서 실행
    Steps:
      1. python3 -m pytest backend/tests/ -m "not integration" -q
      2. passed 수 ≥ 54, failed = 0
    Expected Result: ≥54 passed, 0 failed
    Failure Indicators: failed > 0
    Evidence: .sisyphus/evidence/task-3-backend-regression.txt
  ```

  **Commit**: YES (Task 2와 함께 그룹)
  - Message: `fix(load-test): show configured total and add Save as Benchmark`
  - Files: `frontend/src/pages/LoadTestPage.jsx`, `frontend/src/pages/LoadTestPage.test.jsx`
  - Pre-commit: `cd frontend && npx vitest run`

---

## Final Verification Wave (MANDATORY — after ALL implementation tasks)

> 4 review agents run in PARALLEL. ALL must APPROVE. Rejection → fix → re-run.

- [x] F1. **Plan Compliance Audit** — `oracle`
  Read the plan end-to-end. For each "Must Have": verify implementation exists (read file, run command). For each "Must NOT Have": search codebase for forbidden patterns — reject with file:line if found. Check evidence files exist in .sisyphus/evidence/. Compare deliverables against plan.
  Output: `Must Have [N/N] | Must NOT Have [N/N] | Tasks [N/N] | VERDICT: APPROVE/REJECT`

- [x] F2. **Code Quality Review** — `unspecified-high`
  Run `python3 -m pytest backend/tests/ -m "not integration" -q` + `cd frontend && npx vitest run`. Review all changed files for: `as any`/`@ts-ignore`, empty catches, console.log in prod, commented-out code, unused imports. Check AI slop: excessive comments, over-abstraction, generic names.
  Output: `Build [PASS/FAIL] | Tests [N pass/N fail] | Files [N clean/N issues] | VERDICT`

- [x] F3. **Real Manual QA** — `unspecified-high` (+ `playwright` skill if applicable)
  Start from clean state. Verify: (1) `_compute_stats()` returns `total_requested` field; (2) Table row shows correct value; (3) Save button appears only on completion; (4) Save creates benchmark entry; (5) Mock mode hides Save button. Save evidence to `.sisyphus/evidence/final-qa/`.
  Output: `Scenarios [N/N pass] | VERDICT`

- [x] F4. **Scope Fidelity Check** — `deep`
  For each task: read "What to do", read actual diff (`git diff`). Verify 1:1 — everything in spec was built (no missing), nothing beyond spec was built (no creep). Check "Must NOT do" compliance. Flag unaccounted changes.
  Output: `Tasks [N/N compliant] | Unaccounted [CLEAN/N files] | VERDICT`

---

## Commit Strategy

- **Commit 1** (after Task 1): `feat(engine): emit total_requested in load test stats` — `backend/services/load_engine.py`, `backend/models/load_test.py`, `backend/tests/test_load_test.py`
- **Commit 2** (after Task 2+3): `fix(load-test): show configured total and add Save as Benchmark` — `frontend/src/pages/LoadTestPage.jsx`, `frontend/src/pages/LoadTestPage.test.jsx`

---

## Success Criteria

### Verification Commands
```bash
python3 -m pytest backend/tests/ -m "not integration" -q  # Expected: ≥54 passed, 0 failed
cd frontend && npx vitest run                              # Expected: ≥27 passed, 0 failed
```

### Final Checklist
- [x] All "Must Have" present
- [x] All "Must NOT Have" absent
- [x] Backend tests: ≥54 passed (52 prior + ≥2 new)
- [x] Frontend tests: ≥27 passed (17 prior + ≥10 new)
- [x] "Total Requests" table row shows `config.total_requests` (not completed count)
- [x] "Save as Benchmark" button visible only on completion
- [x] Benchmark save creates entry retrievable via `GET /api/benchmark/list`
