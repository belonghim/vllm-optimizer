# Improve Frontend Quality

## TL;DR

> **Quick Summary**: 3가지 영역 개선. ① LoadTestPage useEffect 중복 제거로 기존 4개 실패 테스트 해소, ② SSE 재연결 중 UI 배너 추가(UX), ③ 테스트 커버리지 보강(TunerPage/MonitorPage 신규, BenchmarkPage 강화).
>
> **Deliverables**:
> - `frontend/src/pages/LoadTestPage.jsx` — useEffect 2개 → 1개 병합 (T1) + isReconnecting 배너 (T2)
> - `frontend/src/pages/LoadTestPage.test.jsx` — SSE 재연결 테스트 +2개 (T2)
> - `frontend/src/pages/TunerPage.test.jsx` — 신규, 6개 (T3)
> - `frontend/src/pages/BenchmarkPage.test.jsx` — 기존 2개 → 의미있는 5개 (T4a)
> - `frontend/src/pages/MonitorPage.test.jsx` — 신규, 4개 (T4b)
>
> **Estimated Effort**: Medium (5 tasks, focused changes)
> **Parallel Execution**: YES — Wave 1에서 T1/T3/T4a/T4b 병렬, Wave 2에서 T2
> **Critical Path**: T1 → T2 → T5 → F1-F4

---

## Context

### Original Request
3가지 개선:
1. Save as Benchmark 테스트 수정 (4개 실패)
2. SSE 안정성 추가 개선
3. 프론트엔드 전반 품질 개선

### Research Findings
- **T1 근본 원인**: `LoadTestPage.jsx` lines 147-167에 `/api/config`를 호출하는 `useEffect`가 2개 있음 (endpoint용, model용). 4개 실패 테스트는 fetch mock을 3개만 준비하는데 실제론 4번 호출됨. 수정 방향: 두 useEffect를 하나로 병합 → 테스트 변경 0건으로 모든 4개 실패 해소.
- **T2 SSE 재연결**: `onerror` 핸들러에서 CONNECTING 상태 시 조용히 재시도 중인데 UI 피드백 없음. 사용자가 재연결 시도를 인지 불가.
- **테스트 현황** (33개 중 29개 통과): TunerPage.test.jsx/MonitorPage.test.jsx 없음, BenchmarkPage.test.jsx는 column header 2개만 확인하는 trivial tests.

### Metis Review Key Directives
- T1은 컴포넌트 수정(useEffect 병합)이 테스트 수정보다 우월 — 중복 네트워크 요청 제거 + 테스트 0건 변경으로 4개 실패 해소
- T2: `isReconnecting: boolean` 단순 상태 (전체 FSM 금지), TDD 순서 필수 (테스트 먼저 → 구현)
- T3/T4: `isMockEnabled: true` 활용으로 복잡한 mock 불필요
- T4를 T4a(BenchmarkPage), T4b(MonitorPage)로 분리

---

## Work Objectives

### Core Objective
프론트엔드 테스트 스위트가 33/33 통과하고(기존 4개 실패 해소), SSE 재연결 시 사용자에게 시각적 피드백이 제공되며, 미커버 컴포넌트(TunerPage, MonitorPage)의 기본 테스트가 존재하도록 한다.

### Concrete Deliverables
- `frontend/src/pages/LoadTestPage.jsx` — useEffect 병합 + isReconnecting 배너
- `frontend/src/pages/LoadTestPage.test.jsx` — SSE 재연결 테스트 2개 추가
- `frontend/src/pages/TunerPage.test.jsx` — 신규 6개 테스트
- `frontend/src/pages/BenchmarkPage.test.jsx` — 기존 2개 + 3개 추가 = 5개
- `frontend/src/pages/MonitorPage.test.jsx` — 신규 4개 테스트

### Definition of Done
- [x] `cd frontend && npx vitest run` → **0 failures** — 45/45 통과 (기존 33→45)
- [x] 새 SSE 재연결 배너 — CONNECTING 상태 시 "↺ SSE 재연결 중..." 텍스트 표시
- [x] TunerPage 기본 테스트 6개 통과
- [x] BenchmarkPage 테스트 5개 통과 (기존 2 + 신규 3)
- [x] MonitorPage 기본 테스트 4개 통과

### Must Have
- LoadTestPage.jsx: 두 `/api/config` useEffect가 단일 useEffect로 병합, `vllm_endpoint`와 `resolved_model_name` 모두 하나의 `.then()` 체인에서 처리
- LoadTestPage.jsx: `isReconnecting: boolean` 상태, CONNECTING onerror 시 `true`, onmessage 수신 시 `false`, 최대 재시도 초과 시 `false`(에러 표시로 전환)
- LoadTestPage.test.jsx: TDD 순서 — T2에서 테스트 먼저 작성 후 구현
- TunerPage.test.jsx: `isMockEnabled: true` 모킹 전략, 6개 테스트
- BenchmarkPage.test.jsx: 빈 상태 메시지, 행 데이터 렌더링, 에러 배너 테스트 추가
- MonitorPage.test.jsx: `isMockEnabled: true` 모킹 전략, 4개 테스트

### Must NOT Have (Guardrails)
- `isReconnecting`을 문자열 FSM(`connectionStatus = "reconnecting"`)으로 확장 금지 — boolean만 사용
- T2에서 `setError(...)` 사용하여 재연결 상태 표시 금지 — `error` 상태는 스트림이 죽었을 때만 사용
- T3에서 TunerPage SSE 스트리밍 테스트 금지 — 통합 테스트 영역
- T3에서 폼 인터랙션(advanced settings, checkboxes) 테스트 금지
- T4b에서 `setInterval` 폴링 동작 테스트 금지
- Chart 내부 렌더링 assertion 금지 (Recharts는 brittle)
- T1에서 테스트 파일 수정 금지 — 컴포넌트 수정만으로 0 테스트 변경이 목표

---

## Verification Strategy

### Test Decision
- **Infrastructure**: vitest + @testing-library/react (이미 설정됨)
- **TDD**: T2는 RED → GREEN → REFACTOR 순서 필수
- **기준**: `npx vitest run --reporter=verbose` 에서 0 failures

### QA Policy
- Backend 변경 없음 — backend 테스트 제외
- Evidence: `.sisyphus/evidence/task-{N}-*.txt`

---

## Execution Strategy

### Parallel Execution Waves

```
Wave 1 (Start Immediately — 4 tasks, MAX PARALLEL):
├── T1: useEffect 병합 (LoadTestPage.jsx 컴포넌트 수정)       [quick]
├── T3: TunerPage.test.jsx 신규 6개 테스트                   [quick]
├── T4a: BenchmarkPage.test.jsx +3개 의미있는 테스트          [quick]
└── T4b: MonitorPage.test.jsx 신규 4개 테스트                [quick]

Wave 2 (After T1 — T2가 LoadTestPage.jsx 추가 수정):
└── T2: SSE 재연결 UI 배너 + 테스트 2개 (TDD)                [visual-engineering]

Wave 3 (After All — regression):
└── T5: 전체 테스트 regression 검증                          [quick]

Wave FINAL (4 parallel reviews):
├── F1: Plan Compliance Audit  [oracle]
├── F2: Code Quality Review    [unspecified-high]
├── F3: Manual QA              [unspecified-high]
└── F4: Scope Fidelity Check   [deep]
```

### Dependency Matrix

| Task | Depends On | Blocks |
|------|-----------|--------|
| T1 | — | T2, T5 |
| T3 | — | T5 |
| T4a | — | T5 |
| T4b | — | T5 |
| T2 | T1 | T5 |
| T5 | T1, T2, T3, T4a, T4b | F1-F4 |
| F1-F4 | T5 | — |

---

## TODOs

- [x] 1. [T1] LoadTestPage useEffect 2개 → 1개 병합 (기존 4개 실패 테스트 해소)

  **What to do**:
  `frontend/src/pages/LoadTestPage.jsx` lines 147-167에 `/api/config`를 중복 호출하는 useEffect 2개를 1개로 병합한다.

  **현재 코드 (수정 전)**:
  ```jsx
  useEffect(() => {
    fetch(`${API}/config`)
      .then(r => r.json())
      .then(data => {
        if (data.vllm_endpoint) {
          setConfig(c => ({ ...c, endpoint: c.endpoint || data.vllm_endpoint }));
        }
      })
      .catch(() => {});
  }, []);

  useEffect(() => {
    fetch(`${API}/config`)
      .then(r => r.json())
      .then(data => {
        if (data.resolved_model_name && data.resolved_model_name !== "auto") {
          setConfig(c => ({ ...c, model: c.model === "auto" ? data.resolved_model_name : c.model }));
        }
      })
      .catch(() => {});
  }, []);
  ```

  **수정 후 (단일 useEffect)**:
  ```jsx
  useEffect(() => {
    fetch(`${API}/config`)
      .then(r => r.json())
      .then(data => {
        setConfig(c => ({
          ...c,
          ...(data.vllm_endpoint ? { endpoint: c.endpoint || data.vllm_endpoint } : {}),
          ...(data.resolved_model_name && data.resolved_model_name !== "auto"
            ? { model: c.model === "auto" ? data.resolved_model_name : c.model }
            : {}),
        }));
      })
      .catch(() => {});
  }, []);
  ```

  **검증 (테스트 변경 없이 4개 실패 해소 확인)**:
  ```bash
  cd frontend && npx vitest run src/pages/LoadTestPage.test.jsx --reporter=verbose
  # 기대: 기존 4개 failing tests 모두 PASS
  ```

  **Recommended Agent Profile**:
  - **Category**: `quick` (단순 컴포넌트 수정)

  **Parallelization**:
  - Wave 1, T3/T4a/T4b와 병렬 (서로 다른 파일)
  - T2의 prerequisite

  **References**:
  - `frontend/src/pages/LoadTestPage.jsx:147-167` — 수정 대상

  **Acceptance Criteria**:
  - [x] `LoadTestPage.jsx`에 `/api/config` fetch가 단 1개의 useEffect에서만 호출됨
  - [x] `cd frontend && npx vitest run src/pages/LoadTestPage.test.jsx` → **0 failures** (기존 4개 포함 전체 통과)
  - [x] 테스트 파일 변경 0건

  **QA Scenarios (MANDATORY):**
  ```
  Scenario: 기존 4개 failing tests 해소 확인
    Steps:
      1. cd frontend && npx vitest run src/pages/LoadTestPage.test.jsx --reporter=verbose
      2. "shows success feedback after save", "shows error feedback", "disables button during save", "disables button after successful save" 모두 ✓
    Expected: 4개 모두 PASS
    Evidence: .sisyphus/evidence/task-1-save-test-fix.txt
  ```

  **Commit**: YES
  - Message: `fix(frontend): merge duplicate /api/config useEffects — fixes save-as-benchmark tests`
  - Files: `frontend/src/pages/LoadTestPage.jsx`

- [x] 2. [T2] SSE 재연결 배너 + 테스트 2개 (TDD 순서)

  **What to do** (TDD — 테스트 먼저):

  ### Step 1: 실패하는 테스트 먼저 작성 (RED)

  `frontend/src/pages/LoadTestPage.test.jsx` 파일의 "SSE onerror reconnect behavior" describe 블록 마지막에 **2개 테스트 추가**:

  ```jsx
  it("shows reconnecting banner when onerror fires in CONNECTING state", async () => {
    render(<LoadTestPage />);
    await act(async () => { fireEvent.click(screen.getByText("▶ Run Load Test")); });
    await waitFor(() => expect(mockEsInstance).not.toBeNull());

    mockEsInstance.readyState = 0;
    act(() => { mockEsInstance.onerror(); });

    expect(screen.getByText(/재연결 중/)).toBeInTheDocument();
    expect(screen.queryByText(/SSE 연결 실패/)).not.toBeInTheDocument();
  });

  it("clears reconnecting banner when valid message received", async () => {
    render(<LoadTestPage />);
    await act(async () => { fireEvent.click(screen.getByText("▶ Run Load Test")); });
    await waitFor(() => expect(mockEsInstance).not.toBeNull());

    mockEsInstance.readyState = 0;
    act(() => { mockEsInstance.onerror(); });
    expect(screen.getByText(/재연결 중/)).toBeInTheDocument();

    act(() => {
      mockEsInstance.onmessage({
        data: JSON.stringify({ type: "progress", data: { total: 1, total_requested: 10 } }),
      });
    });

    expect(screen.queryByText(/재연결 중/)).not.toBeInTheDocument();
  });
  ```

  또한 **기존 테스트** `"does not close EventSource when readyState is CONNECTING (transient error)"` 에 배너 assertion 추가:
  ```jsx
  // 기존 assertions 이후에 추가:
  expect(screen.getByText(/재연결 중/)).toBeInTheDocument();
  ```

  ### Step 2: 테스트 실패 확인 (RED 검증)
  ```bash
  cd frontend && npx vitest run src/pages/LoadTestPage.test.jsx --reporter=verbose 2>&1 | grep "재연결"
  # 기대: 2개 FAIL (테스트가 올바르게 실패함을 확인)
  ```

  ### Step 3: 구현 (GREEN)

  `frontend/src/pages/LoadTestPage.jsx` 수정:

  1. **상태 추가** (line 32 근처):
  ```jsx
  const [isReconnecting, setIsReconnecting] = useState(false);
  ```

  2. **onmessage에 리셋 추가** (line 64 `retryCountRef.current = 0;` 바로 다음):
  ```jsx
  setIsReconnecting(false);
  ```

  3. **onerror 핸들러 수정** (CONNECTING 분기 내 return 직전):
  ```jsx
  if (es.readyState === EventSource.CONNECTING) {
    retryCountRef.current += 1;
    if (retryCountRef.current <= 3) {
      setIsReconnecting(true);   // ← 추가
      return;
    }
  }
  setIsReconnecting(false);     // ← 추가 (최대 재시도 초과 시 배너 제거 후 에러 표시)
  setError(`SSE 연결 실패: ...`);
  ```

  4. **JSX 배너 추가** (에러 배너 위, `{error && ...}` 블록 바로 위에 추가):
  ```jsx
  {isReconnecting && status === "running" && (
    <div style={{
      background: "rgba(255,180,0,0.08)",
      border: "1px solid rgba(255,180,0,0.4)",
      color: "#ffb400",
      padding: "10px 16px",
      fontSize: 12,
      fontFamily: font,
    }}>
      ↺ SSE 재연결 중... ({retryCountRef.current}/3회 시도)
    </div>
  )}
  ```

  ### Step 4: 테스트 통과 확인 (GREEN 검증)
  ```bash
  cd frontend && npx vitest run src/pages/LoadTestPage.test.jsx --reporter=verbose
  # 기대: 전체 통과 (기존 SSE 4개 + 신규 2개 + 수정된 기존 1개)
  ```

  **Recommended Agent Profile**:
  - **Category**: `visual-engineering` (JSX UI + 테스트 TDD)

  **Parallelization**:
  - Wave 2, T1 완료 후 시작 (LoadTestPage.jsx 파일 충돌 방지)

  **References**:
  - `frontend/src/pages/LoadTestPage.jsx:27-107` — 상태/핸들러 수정 영역
  - `frontend/src/pages/LoadTestPage.test.jsx:346-432` — 기존 SSE onerror 테스트 (확장 대상)
  - `frontend/src/App.jsx` — COLORS 패턴 참조 (amber/warning 색상)
  - `frontend/src/constants.js` — `font` 상수 참조

  **Acceptance Criteria**:
  - [x] 테스트 먼저 작성 → FAIL 확인 → 구현 → PASS 순서 준수
  - [x] `isReconnecting: boolean` 상태 (string 아님)
  - [x] `setError`는 재연결 상태에서 사용하지 않음
  - [x] CONNECTING onerror 시 amber 배너 "↺ SSE 재연결 중..." 표시
  - [x] onmessage 수신 시 배너 즉시 사라짐
  - [x] 최대 재시도 초과 시 배너 사라지고 빨간 에러 배너 표시
  - [x] `cd frontend && npx vitest run src/pages/LoadTestPage.test.jsx` → 전체 통과

  **QA Scenarios (MANDATORY):**
  ```
  Scenario: TDD Red phase 확인
    Steps:
      1. 테스트 2개 추가 후 npx vitest run src/pages/LoadTestPage.test.jsx
      2. 새 2개 테스트 FAIL 확인 (나머지는 통과)
    Evidence: .sisyphus/evidence/task-2-tdd-red.txt

  Scenario: TDD Green phase 확인
    Steps:
      1. 구현 후 npx vitest run src/pages/LoadTestPage.test.jsx
      2. 전체 통과 확인
    Evidence: .sisyphus/evidence/task-2-tdd-green.txt
  ```

  **Commit**: YES
  - Message: `feat(frontend): add SSE reconnecting status banner`
  - Files: `frontend/src/pages/LoadTestPage.jsx`, `frontend/src/pages/LoadTestPage.test.jsx`
  - Pre-commit: `cd frontend && npx vitest run src/pages/LoadTestPage.test.jsx`

- [x] 3. [T3] TunerPage 기본 테스트 신규 작성 (6개)

  **What to do**:
  `frontend/src/pages/TunerPage.test.jsx` 신규 파일 생성. `isMockEnabled: true` 전략으로 복잡한 SSE/polling/fetch 모킹 없이 기본 동작 검증.

  ### 파일 구조
  ```jsx
  import { render, screen, fireEvent, act, waitFor } from "@testing-library/react";
  import { vi, describe, it, expect, beforeEach, afterEach } from "vitest";
  import TunerPage from "./TunerPage";

  vi.mock("../contexts/MockDataContext", () => ({
    useMockData: () => ({ isMockEnabled: true }),
  }));

  beforeEach(() => {
    global.ResizeObserver = class { observe(){} unobserve(){} disconnect(){} };
    // isMockEnabled: true여도 /api/config는 항상 호출됨 (guard 없음)
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => ({}) }));
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.clearAllMocks();
  });

  describe("TunerPage", () => {
    it("renders without crashing", () => { ... });
    it("shows Start Tuning button enabled", () => { ... });
    it("shows Stop button disabled initially", () => { ... });
    it("shows IDLE status tag", () => { ... });
    it("shows trials counter with 0 completed", () => { ... });
    it("shows error banner when /api/config fetch fails", async () => { ... }); // isMockEnabled: false로 오버라이드
  });
  ```

  ### 6개 테스트 상세 스펙

  **Test 1: renders without crashing**
  - `render(<TunerPage />)` 후 예외 없이 렌더링됨
  - `screen.getByText(/Start Tuning|자동 파라미터/)` 등 최소 1개 요소 존재

  **Test 2: "▶ Start Tuning" button present and enabled**
  - `screen.getByText("▶ Start Tuning")` 존재
  - `expect(button).not.toBeDisabled()`

  **Test 3: "■ Stop" button present and disabled**
  - `screen.getByText(/Stop/)` 존재 (영문 텍스트 확인 후 조정)
  - `expect(button).toBeDisabled()`

  **Test 4: status tag shows IDLE or 유사 상태**
  - `screen.getByText(/IDLE|대기/)` 존재

  **Test 5: trials counter shows "0 / N"**
  - `screen.getByText(/0 \/ \d+/)` 패턴 존재

  **Test 6: error banner when fetch fails** (mock override)
  - `vi.mock`을 `isMockEnabled: false`로 로컬 오버라이드, fetch reject 설정
  - 에러 메시지 배너 렌더링 확인

  **중요**: 실제 TunerPage.jsx를 반드시 먼저 읽고 정확한 버튼 텍스트/레이블 확인 후 테스트 작성

  **Scope 명시적 제외 (파일 내 주석으로 기록)**:
  ```
  // OUT OF SCOPE: SSE 스트리밍, 폼 인터랙션, 차트 렌더링, 폴링 interval
  ```

  **Recommended Agent Profile**:
  - **Category**: `quick`

  **Parallelization**:
  - Wave 1, T1/T4a/T4b와 병렬 (신규 파일, 충돌 없음)

  **References**:
  - `frontend/src/pages/TunerPage.jsx` — **반드시 먼저 읽어 정확한 텍스트 확인**
  - `frontend/src/pages/LoadTestPage.test.jsx:1-50` — 테스트 파일 setup 패턴 참조

  **Acceptance Criteria**:
  - [x] `frontend/src/pages/TunerPage.test.jsx` 신규 파일 생성
  - [x] 6개 테스트 모두 PASS
  - [x] `cd frontend && npx vitest run src/pages/TunerPage.test.jsx` → 6 passed, 0 failed

  **QA Scenarios (MANDATORY):**
  ```
  Scenario: TunerPage 테스트 6개 통과
    Steps:
      1. cd frontend && npx vitest run src/pages/TunerPage.test.jsx --reporter=verbose
    Expected: 6 passed, 0 failed
    Evidence: .sisyphus/evidence/task-3-tuner-tests.txt
  ```

  **Commit**: YES
  - Message: `test(tuner): add basic render and initial-state coverage`
  - Files: `frontend/src/pages/TunerPage.test.jsx`

- [x] 4. [T4a] BenchmarkPage 테스트 보강 (+3개 의미있는 테스트)

  **What to do**:
  `frontend/src/pages/BenchmarkPage.test.jsx`에 기존 2개(column header) 외 3개의 실질적 테스트 추가.

  ### 현재 파일 상태 먼저 읽기
  `frontend/src/pages/BenchmarkPage.test.jsx` 전체 읽기 후, `frontend/src/pages/BenchmarkPage.jsx` 읽기.

  ### 추가할 3개 테스트

  **Test 3: 빈 상태 메시지**
  - 데이터 없을 때 "부하 테스트 결과를 저장하면 여기 나타납니다." (또는 유사) 메시지 렌더링
  - `isMockEnabled: false`이고 fetch가 빈 배열을 반환하는 경우

  **Test 4: 벤치마크 행 데이터 렌더링**
  - `isMockEnabled: true` 사용 — 목 데이터가 표시됨
  - 테이블에 최소 1개 행이 있고 의미있는 데이터(모델명, latency 값 등)가 표시됨

  **Test 5: fetch 실패 시 에러 배너**
  - fetch reject 시 에러 상태 표시 확인

  **중요**: 실제 BenchmarkPage.jsx를 먼저 읽어 정확한 구조 파악 후 구현.

  **Recommended Agent Profile**:
  - **Category**: `quick`

  **Parallelization**:
  - Wave 1, T1/T3/T4b와 병렬

  **References**:
  - `frontend/src/pages/BenchmarkPage.jsx` — 반드시 먼저 읽기
  - `frontend/src/pages/BenchmarkPage.test.jsx` — 기존 설정 패턴 확인

  **Acceptance Criteria**:
  - [x] BenchmarkPage.test.jsx에 3개 추가 → 총 5개 테스트
  - [x] `cd frontend && npx vitest run src/pages/BenchmarkPage.test.jsx` → 5 passed, 0 failed

  **QA Scenarios (MANDATORY):**
  ```
  Scenario: BenchmarkPage 5개 테스트 통과
    Steps:
      1. cd frontend && npx vitest run src/pages/BenchmarkPage.test.jsx --reporter=verbose
    Expected: 5 passed, 0 failed
    Evidence: .sisyphus/evidence/task-4a-benchmark-tests.txt
  ```

  **Commit**: YES
  - Message: `test(benchmark): strengthen coverage beyond column headers`
  - Files: `frontend/src/pages/BenchmarkPage.test.jsx`

- [x] 5. [T4b] MonitorPage 기본 테스트 신규 작성 (4개)

  **What to do**:
  `frontend/src/pages/MonitorPage.test.jsx` 신규 파일 생성. `isMockEnabled: true` 전략으로 복잡한 polling 모킹 없이 기본 동작 검증.

  ### 4개 테스트 스펙

  **Test 1: renders without crashing**

  **Test 2: metric cards present (isMockEnabled: true)**
  - 목 데이터로 MetricCard 컴포넌트들이 렌더링됨
  - e.g. TPS, Latency, 요청수 카드 존재

  **Test 3: error banner when fetch fails**
  - `isMockEnabled: false` + fetch reject
  - 에러 상태 표시

  **Test 4: CONNECTED 상태 표시 또는 초기 로딩 상태**
  - 컴포넌트가 초기 상태를 올바르게 표시

  **중요**: MonitorPage.jsx 먼저 읽어 정확한 구조 파악.

  **Recommended Agent Profile**:
  - **Category**: `quick`

  **Parallelization**:
  - Wave 1, T1/T3/T4a와 병렬

  **References**:
  - `frontend/src/pages/MonitorPage.jsx` — 반드시 먼저 읽기
  - `frontend/src/pages/LoadTestPage.test.jsx:1-50` — setup 패턴 참조

  **Acceptance Criteria**:
  - [x] `frontend/src/pages/MonitorPage.test.jsx` 신규 파일 생성
  - [x] 4개 테스트 모두 PASS
  - [x] `cd frontend && npx vitest run src/pages/MonitorPage.test.jsx` → 4 passed, 0 failed

  **QA Scenarios (MANDATORY):**
  ```
  Scenario: MonitorPage 4개 테스트 통과
    Steps:
      1. cd frontend && npx vitest run src/pages/MonitorPage.test.jsx --reporter=verbose
    Expected: 4 passed, 0 failed
    Evidence: .sisyphus/evidence/task-4b-monitor-tests.txt
  ```

  **Commit**: YES
  - Message: `test(monitor): add initial render and metric display coverage`
  - Files: `frontend/src/pages/MonitorPage.test.jsx`

- [x] 6. [T5] 전체 테스트 regression 검증

  **What to do**:
  T1-T4b 완료 후 전체 테스트 스위트 실행. 기존 29개 + 신규 테스트 전체 통과 확인.

  **검증 명령어**:
  ```bash
  cd frontend && npx vitest run --reporter=verbose 2>&1
  ```

  **기대 결과**:
  - 기존 실패 4개 → 0개
  - 신규 테스트: T2 +2, T3 +6, T4a +3, T4b +4 = +15개 추가
  - 전체: 33 + 15 = 48개 이상 통과, 0 failures

  **Recommended Agent Profile**:
  - **Category**: `quick`

  **Acceptance Criteria**:
  - [x] `cd frontend && npx vitest run` → **0 failures**

  **Commit**: NO

---

## Final Verification Wave (MANDATORY)

- [x] F1. **Plan Compliance Audit** — `oracle`
  Must Have 전부 존재, Must NOT Have 전부 없음, 6개 태스크 체크박스 완료 확인.
  Output: `Must Have [N/N] | Must NOT Have [N/N] | VERDICT: APPROVE/REJECT`

- [x] F2. **Code Quality Review** — `unspecified-high`
  `cd frontend && npx vitest run` 실행. 변경된 파일의 빈 catch, 미사용 변수, console.log 확인.
  Output: `Tests [PASS/FAIL] | Files [N clean] | VERDICT`

- [x] F3. **Real Manual QA** — `unspecified-high`
  모든 QA Scenario 직접 실행, evidence 저장.
  Output: `Scenarios [N/N pass] | VERDICT`

- [x] F4. **Scope Fidelity Check** — `deep`
  git diff 검토. 각 태스크 스펙과 실제 변경 1:1 대조.
  Output: `Tasks [N/N compliant] | Unaccounted [CLEAN] | VERDICT`

---

## Commit Strategy

| Task | Commit Message | Files |
|------|---------------|-------|
| T1 | `fix(frontend): merge duplicate /api/config useEffects — fixes save-as-benchmark tests` | LoadTestPage.jsx |
| T2 | `feat(frontend): add SSE reconnecting status banner` | LoadTestPage.jsx, LoadTestPage.test.jsx |
| T3 | `test(tuner): add basic render and initial-state coverage` | TunerPage.test.jsx |
| T4a | `test(benchmark): strengthen coverage beyond column headers` | BenchmarkPage.test.jsx |
| T4b | `test(monitor): add initial render and metric display coverage` | MonitorPage.test.jsx |

---

## Success Criteria

```bash
# 전체 프론트엔드 테스트 — 0 failures
cd frontend && npx vitest run

# 파일별 검증
cd frontend && npx vitest run src/pages/LoadTestPage.test.jsx   # 0 failures (기존 4개 포함)
cd frontend && npx vitest run src/pages/TunerPage.test.jsx      # 6 passed
cd frontend && npx vitest run src/pages/BenchmarkPage.test.jsx  # 5 passed
cd frontend && npx vitest run src/pages/MonitorPage.test.jsx    # 4 passed
```

### Final Checklist
- [x] 기존 4개 failing tests 해소 (0 failures in LoadTestPage.test.jsx)
- [x] SSE 재연결 시 amber 배너 표시 (isReconnecting boolean)
- [x] TunerPage 기본 테스트 존재
- [x] BenchmarkPage 의미있는 테스트 5개
- [x] MonitorPage 기본 테스트 존재
- [x] 전체 0 failures
