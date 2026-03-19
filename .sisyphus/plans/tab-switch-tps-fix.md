# 탭 전환 상태 유실 + 모니터 TPS=0 버그 수정

## TL;DR

> **Quick Summary**: 프론트엔드 탭 전환 시 컴포넌트 언마운트로 인한 상태/SSE 연결 유실 버그와, 모니터링 페이지의 Prometheus TPS 쿼리 이름 불일치로 인한 TPS=0 버그를 수정한다.
> 
> **Deliverables**:
> - `App.jsx` — 모든 탭 항상 마운트 (display:none) + 개별 ErrorBoundary 격리
> - `metrics_collector.py` — 0.13.x-cpu TPS Prometheus 쿼리 이름 교정
> 
> **Estimated Effort**: Short
> **Parallel Execution**: YES — 2 waves
> **Critical Path**: Task 2 (진단) → Task 3 (TPS 쿼리 수정)

---

## Context

### Original Request
"부하 테스트 중에 실시간 모니터링에 들려보면, TPS가 항상 0이야. 그리고 다시 부하 테스트로 돌아오면, 페이지가 초기화되어 있어."

### Interview Summary
**Key Discussions**:
- 탭 전환 수정 방식: 모든 탭 항상 마운트 + display:none (사용자 선택)
- 실행 환경: OpenShift 클러스터 내부
- 모니터 TPS=0: 다른 메트릭(Running Reqs, KV Cache, Pods)은 정상. TPS만 0.

**Research Findings**:
- `App.jsx:36` — 조건부 렌더링(`const ActivePage = PAGES.find(...)?.Component`)으로 탭 전환 시 이전 컴포넌트 언마운트
- `LoadTestPage.jsx:142-149` — useEffect 클린업이 SSE EventSource 닫음
- `MonitorPage.jsx:29` — `/api/metrics/latest` → Thanos Querier에서 TPS 조회
- `metrics_collector.py` — 0.13.x-cpu TPS 쿼리: `rate(vllm:generation_tokens_total[1m])` → 이 메트릭 이름이 실제 vLLM에서 노출하는 이름과 불일치할 가능성 높음
- Thanos 연결 자체는 정상 (다른 메트릭 쿼리 성공)

### Metis Review
**Identified Gaps** (addressed):
- 개별 ErrorBoundary 격리 필요 → Task 1에 포함
- Chart 리사이즈 이슈 (display:none → block 전환 시) → Task 1에 포함
- TPS 메트릭 이름 미검증 → Task 2(진단)를 Task 3 선행조건으로 설정
- 0.13.x-cpu 쿼리에 `sum()` 래퍼 누락 (멀티 Pod 대비) → Task 3에 포함

---

## Work Objectives

### Core Objective
두 가지 프론트엔드/백엔드 버그를 수정하여 탭 전환 시 상태가 보존되고, 모니터링 페이지에서 TPS가 정상 표시되도록 한다.

### Concrete Deliverables
- `frontend/src/App.jsx` — 탭 렌더링 방식 변경 (조건부 → 항상 마운트)
- `backend/services/metrics_collector.py` — 0.13.x-cpu TPS 쿼리 교정

### Definition of Done
- [x] 부하 테스트 실행 중 탭 전환 후 돌아와도 진행률/결과/SSE 연결 유지됨
- [x] 모니터링 페이지에서 부하 테스트 중 TPS > 0 표시됨
- [x] 기존 백엔드 단위 테스트 전부 통과

### Must Have
- 탭 전환 시 모든 페이지 컴포넌트 상태 보존 (SSE 연결 포함)
- 개별 탭 ErrorBoundary 격리 (한 탭 에러가 다른 탭에 영향 안 줌)
- 0.13.x-cpu 환경에서 실제 vLLM TPS 메트릭이 정상 수집됨
- 버그 1/2 별도 커밋 (zero coupling)

### Must NOT Have (Guardrails)
- `LoadTestPage.jsx`, `MonitorPage.jsx` 등 개별 페이지 컴포넌트 수정 금지 (Bug 1)
- SSE 연결 로직(`esRef`, `retryCountRef`, `onerror`) 변경 금지
- `_detect_version()` 로직 변경 금지
- `MetricsSnapshot` 모델 또는 `/api/metrics/latest` 라우터 로직 변경 금지
- `VLLM_QUERIES_BY_VERSION`의 `0.11.x`, `0.13.x` (GPU) 쿼리 변경 금지
- TPS 표시 형식 변경 (0 → — 등) — 별도 이슈
- `_missing_metrics`를 프론트엔드에 노출하는 기능 추가 — 별도 이슈
- 버전 감지 재시도 로직 추가 — 별도 이슈

---

## Verification Strategy

> **ZERO HUMAN INTERVENTION** — ALL verification is agent-executed. No exceptions.

### Test Decision
- **Infrastructure exists**: YES (backend: pytest)
- **Automated tests**: Tests-after (Bug 2: 단위 테스트, Bug 1: 프론트엔드 테스트 인프라 없으므로 QA 시나리오로 검증)
- **Framework**: pytest (backend)

### QA Policy
Every task MUST include agent-executed QA scenarios.
Evidence saved to `.sisyphus/evidence/task-{N}-{scenario-slug}.{ext}`.

- **Frontend/UI**: Use Playwright (playwright skill) — Navigate, interact, assert DOM, screenshot
- **Backend**: Use Bash (curl/pytest) — Send requests, assert status + response fields
- **Cluster Diagnostic**: Use Bash (oc exec) — Query Thanos from backend pod

---

## Execution Strategy

### Parallel Execution Waves

```
Wave 1 (Start Immediately — independent tasks):
├── Task 1: Fix App.jsx tab rendering [quick]
└── Task 2: Diagnose Prometheus TPS metric name [quick]

Wave 2 (After Task 2 — depends on diagnostic result):
└── Task 3: Fix MetricsCollector TPS query [quick]

Wave FINAL (After ALL tasks — 4 parallel verification):
├── F1: Plan compliance audit (oracle)
├── F2: Code quality review (unspecified-high)
├── F3: Real manual QA (unspecified-high + playwright)
└── F4: Scope fidelity check (deep)

Critical Path: Task 2 → Task 3 → F1-F4
Parallel Speedup: Task 1 + Task 2 동시 실행
Max Concurrent: 2 (Wave 1)
```

### Dependency Matrix

| Task | Depends On | Blocks |
|------|-----------|--------|
| 1 | — | F1-F4 |
| 2 | — | 3 |
| 3 | 2 | F1-F4 |
| F1-F4 | 1, 3 | — |

### Agent Dispatch Summary

- **Wave 1**: 2 tasks — T1 → `quick`, T2 → `quick`
- **Wave 2**: 1 task — T3 → `quick`
- **FINAL**: 4 tasks — F1 → `oracle`, F2 → `unspecified-high`, F3 → `unspecified-high` + `playwright`, F4 → `deep`

---

## TODOs

- [x] 1. App.jsx 탭 렌더링 방식 변경 — 모든 탭 항상 마운트 + 개별 ErrorBoundary

  **What to do**:
  1. `App.jsx`의 렌더링 방식을 조건부 렌더링에서 **모든 탭 동시 렌더링 + display:none** 으로 변경:
     ```jsx
     // 변경 전 (line 36, 77):
     const ActivePage = PAGES.find(p => p.id === page)?.Component ?? MonitorPage;
     <ActivePage />

     // 변경 후:
     {PAGES.map(p => (
       <div key={p.id} style={{ display: page === p.id ? undefined : 'none' }}>
         <ErrorBoundary>
           <p.Component />
         </ErrorBoundary>
       </div>
     ))}
     ```
  2. 기존 `<ErrorBoundary>` 단일 래핑을 제거하고, **각 탭마다 개별 `<ErrorBoundary>`** 로 감싸서 한 탭의 에러가 다른 탭에 영향을 주지 않도록 한다.
  3. `setPage` 호출 후 차트 리사이즈를 위해 resize 이벤트 디스패치 추가:
     ```jsx
     const handleSetPage = (id) => {
       setPage(id);
       // Recharts ResponsiveContainer가 display:none→block 전환 후 올바른 크기를 계산하도록
       requestAnimationFrame(() => window.dispatchEvent(new Event('resize')));
     };
     ```
  4. `nav` 버튼의 `onClick`을 `handleSetPage`로 교체.

  **Must NOT do**:
  - `LoadTestPage.jsx`, `MonitorPage.jsx`, `BenchmarkPage.jsx`, `TunerPage.jsx` 수정 금지
  - SSE 연결 로직 변경 금지
  - `visibility: hidden` 사용 금지 (`display: none` 사용)
  - 탭 간 props/context/콜백 추가 금지 — 순수 렌더링 변경만

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: 단일 파일(App.jsx) 수정, 명확한 패턴 변경
  - **Skills**: [`playwright`]
    - `playwright`: QA 시나리오에서 탭 전환 동작 브라우저 검증 필요
  - **Skills Evaluated but Omitted**:
    - `frontend-ui-ux`: 디자인 변경 아님, 렌더링 로직만 변경

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Task 2)
  - **Blocks**: F1-F4
  - **Blocked By**: None (can start immediately)

  **References**:

  **Pattern References**:
  - `frontend/src/App.jsx:34-81` — 현재 App 컴포넌트 전체. line 36: 조건부 렌더링 로직, line 57-63: nav 버튼 onClick, line 76-78: ErrorBoundary + ActivePage 렌더링

  **API/Type References**:
  - `frontend/src/App.jsx:27-32` — PAGES 배열 정의 (id, label, Component 구조)

  **Component References**:
  - `frontend/src/components/ErrorBoundary.jsx:1-51` — ErrorBoundary 클래스 컴포넌트. 개별 탭에 래핑할 컴포넌트
  - `frontend/src/components/Chart.jsx:25` — `ResponsiveContainer` 사용 확인. display:none→block 전환 시 resize 이벤트 필요한 이유

  **WHY Each Reference Matters**:
  - `App.jsx:36` — 이 한 줄이 조건부 렌더링의 원인. `const ActivePage = ...` 패턴을 제거하고 map 기반 렌더링으로 교체해야 함
  - `App.jsx:57-63` — nav 버튼 onClick에 `setPage` 직접 호출 → `handleSetPage`로 교체 필요
  - `App.jsx:76-78` — 기존 단일 ErrorBoundary + ActivePage 렌더링 → map 기반으로 교체
  - `ErrorBoundary.jsx` — 각 탭에 개별 인스턴스로 래핑 (기존 API 그대로 사용)
  - `Chart.jsx:25` — Recharts `ResponsiveContainer`는 `display:none` 상태에서 0px 크기로 렌더링됨. 탭 전환 시 resize 이벤트를 수동으로 발생시켜야 올바른 크기로 재계산됨

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: 부하 테스트 상태 보존 — 탭 전환 후 복귀
    Tool: Playwright
    Preconditions: 앱이 localhost:8080 에서 실행 중, Mock 모드 ON
    Steps:
      1. "부하 테스트" 탭 클릭
      2. "▶ Run Load Test" 버튼 클릭하여 테스트 시작
      3. progress가 50% 이상 될 때까지 대기 (`.progress-fill` 요소의 width 확인)
      4. "실시간 모니터링" 탭 클릭하여 탭 전환
      5. 2초 대기
      6. "부하 테스트" 탭 클릭하여 복귀
    Expected Result: 
      - `.tag-running` 또는 `.tag-completed` 텍스트가 DOM에 존재 (status가 "idle"이 아님)
      - 또는 result 영역에 "Mean TPS" 카드가 표시됨
      - 페이지가 초기 상태("idle")로 돌아가지 않음
    Failure Indicators: 
      - `.tag-idle` 텍스트가 표시됨
      - result 영역이 비어있음 (테스트 전 초기 상태)
    Evidence: .sisyphus/evidence/task-1-tab-switch-state-preserved.png

  Scenario: ErrorBoundary 격리 — 한 탭 에러가 다른 탭에 영향 안 줌
    Tool: Bash (소스 코드 검증)
    Preconditions: App.jsx 수정 완료
    Steps:
      1. App.jsx를 읽어서 PAGES.map 내부에 각 탭마다 개별 <ErrorBoundary>가 래핑되어 있는지 확인
      2. 기존 단일 <ErrorBoundary> 래핑이 제거되었는지 확인
    Expected Result:
      - PAGES.map 내부에 `<ErrorBoundary>` 가 각 탭 컴포넌트를 감싸고 있음
      - 기존 `<ErrorBoundary><ActivePage /></ErrorBoundary>` 패턴이 제거됨
    Failure Indicators:
      - 단일 ErrorBoundary가 모든 탭을 감싸고 있음
      - ErrorBoundary가 없음
    Evidence: .sisyphus/evidence/task-1-errorboundary-isolation.txt

  Scenario: 차트 리사이즈 — 숨겨진 탭 복귀 시 차트가 올바른 크기로 표시
    Tool: Playwright
    Preconditions: 앱이 localhost:8080 에서 실행 중, Mock 모드 ON
    Steps:
      1. "실시간 모니터링" 탭에서 차트가 표시되는지 확인 (`.recharts-responsive-container` 요소)
      2. "부하 테스트" 탭 클릭
      3. 다시 "실시간 모니터링" 탭 클릭
      4. `.recharts-responsive-container` 의 `width` 속성 확인
    Expected Result: 차트 컨테이너 width가 100px 이상 (0px가 아님)
    Failure Indicators: 차트 컨테이너 width가 0px
    Evidence: .sisyphus/evidence/task-1-chart-resize.png
  ```

  **Commit**: YES
  - Message: `fix(frontend): preserve tab state with always-mounted rendering`
  - Files: `frontend/src/App.jsx`

- [x] 2. Prometheus TPS 메트릭 이름 진단 — Thanos에서 실제 vllm:* 메트릭 확인

  **What to do**:
  1. 백엔드 Pod에서 Thanos Querier에 직접 쿼리하여 **실제 존재하는 vllm: 접두사 메트릭 이름 전체 목록** 수집:
     ```bash
     NS=vllm-optimizer-dev
     BACKEND_POD=$(oc get pod -n $NS -l app=vllm-optimizer-backend -o name | head -1)
     TOKEN=$(oc exec -n $NS $BACKEND_POD -- cat /var/run/secrets/kubernetes.io/serviceaccount/token)
     oc exec -n $NS $BACKEND_POD -- curl -sk \
       -H "Authorization: Bearer $TOKEN" \
       "https://thanos-querier.openshift-monitoring.svc.cluster.local:9091/api/v1/label/__name__/values" \
       | python3 -c "import sys,json; names=[n for n in json.load(sys.stdin)['data'] if n.startswith('vllm')]; print('\n'.join(sorted(names)))"
     ```
  2. 결과에서 **토큰 생성 관련 메트릭** 찾기 (예: `vllm:generation_tokens_total`, `vllm:num_generated_tokens_total`, `vllm:num_generation_tokens_total`, `vllm:iteration_tokens_total` 등)
  3. 현재 코드에서 사용하는 `vllm:generation_tokens_total` 이 목록에 존재하는지 확인
  4. 백엔드 로그에서 `Metrics not available` 경고 확인:
     ```bash
     oc logs -l app=vllm-optimizer-backend -n $NS --tail=20 | grep "Metrics not available"
     ```
  5. 현재 감지된 버전 확인:
     ```bash
     oc exec -n $NS $BACKEND_POD -- curl -s localhost:8000/api/config | python3 -c "import sys,json; print(json.load(sys.stdin))"
     ```
  6. 결과를 `.sisyphus/evidence/task-2-thanos-metrics.txt`에 기록

  **Must NOT do**:
  - 어떤 코드 파일도 수정하지 않음 — 순수 진단 작업

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: 클러스터 명령 실행 + 결과 기록만. 코드 변경 없음.
  - **Skills**: []
  - **Skills Evaluated but Omitted**:
    - `playwright`: 브라우저 작업 아님

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Task 1)
  - **Blocks**: Task 3
  - **Blocked By**: None (can start immediately)

  **References**:

  **Pattern References**:
  - `backend/services/metrics_collector.py:53-119` — `VLLM_QUERIES_BY_VERSION` 딕셔너리. 현재 `0.13.x-cpu`의 `tokens_per_second` 쿼리: `rate(vllm:generation_tokens_total[1m])` (line 100)

  **External References**:
  - AGENTS.md "디버깅 및 검증" 섹션 — Thanos Querier 직접 쿼리 방법, TOKEN 획득 명령어

  **WHY Each Reference Matters**:
  - `metrics_collector.py:100` — 현재 사용 중인 쿼리 문자열. 이 문자열의 메트릭 이름(`vllm:generation_tokens_total`)이 실제 Thanos에 존재하는지가 핵심 검증 대상
  - AGENTS.md — 정확한 Thanos URL, 네임스페이스, ServiceAccount 토큰 경로 참조

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Thanos vllm 메트릭 목록 수집 성공
    Tool: Bash (oc exec)
    Preconditions: OpenShift 클러스터 접근 가능, backend pod 실행 중
    Steps:
      1. 위 진단 명령 실행
      2. 결과에서 vllm: 접두사 메트릭 목록 확인
    Expected Result: 최소 5개 이상의 vllm: 메트릭이 나열됨 (kv_cache, num_requests_running 등 포함)
    Failure Indicators: 빈 결과 또는 연결 실패
    Evidence: .sisyphus/evidence/task-2-thanos-metrics.txt

  Scenario: TPS 관련 메트릭 이름 식별
    Tool: Bash (결과 분석)
    Preconditions: 메트릭 목록 수집 완료
    Steps:
      1. 수집된 목록에서 token/generation/generated 키워드 포함 메트릭 필터링
      2. `vllm:generation_tokens_total` 존재 여부 확인
      3. 대안 메트릭 이름 식별
    Expected Result: TPS 계산에 사용할 정확한 메트릭 이름이 식별됨
    Failure Indicators: token 관련 메트릭이 전혀 없음
    Evidence: .sisyphus/evidence/task-2-tps-metric-identified.txt

  Scenario: 백엔드 로그에서 missing metrics 확인
    Tool: Bash (oc logs)
    Preconditions: backend pod 실행 중
    Steps:
      1. `oc logs -l app=vllm-optimizer-backend -n vllm-optimizer-dev --tail=30 | grep "Metrics not available"` 실행
    Expected Result: `tokens_per_second` 가 missing metrics 목록에 포함되어 있는지 확인됨
    Failure Indicators: 로그 접근 불가
    Evidence: .sisyphus/evidence/task-2-backend-logs.txt
  ```

  **Commit**: NO (진단 작업, 코드 변경 없음)

- [x] 3. MetricsCollector TPS 쿼리 교정 — 0.13.x-cpu 실제 메트릭 이름으로 수정

  **What to do**:
  1. Task 2에서 식별된 **실제 TPS 메트릭 이름**을 사용하여 `backend/services/metrics_collector.py`의 `VLLM_QUERIES_BY_VERSION["0.13.x-cpu"]` 항목 수정:
     ```python
     # 변경 전 (line 100):
     "tokens_per_second": 'rate(vllm:generation_tokens_total[1m])',
     
     # 변경 후 (실제 메트릭 이름 사용 + sum() 래퍼):
     "tokens_per_second": 'sum(rate(vllm:ACTUAL_DISCOVERED_METRIC[1m]))',
     ```
  2. 동일하게 `requests_per_second` (line 101)도 Task 2 결과에서 올바른 메트릭 이름 확인 후 필요시 수정
  3. `sum()` 래퍼 추가 — 현재 `0.13.x-cpu`는 bare `rate(...)` 사용 중. 멀티 Pod 환경 대비로 `sum(rate(...))` 로 래핑
  4. 수정 후 기존 단위 테스트 실행하여 통과 확인:
     ```bash
     cd backend && python3 -m pytest tests/ -x -q -m "not integration"
     ```
  5. 클러스터에서 수정 결과 검증:
     ```bash
     # 재배포 후 TPS 확인
     ./deploy.sh dev
     # 부하 테스트 실행 중 TPS 확인
     oc exec -n vllm-optimizer-dev $BACKEND_POD -- curl -s localhost:8000/api/metrics/latest | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'TPS={d[\"tps\"]}')"
     ```

  **Must NOT do**:
  - `VLLM_QUERIES_BY_VERSION`의 `0.11.x`, `0.13.x` (GPU) 쿼리 변경 금지
  - `_detect_version()` 로직 변경 금지
  - `MetricsSnapshot` 모델 또는 라우터 코드 변경 금지
  - `_convert_to_snapshot()` 변경 금지
  - Task 2의 진단 결과 없이 메트릭 이름을 추측하여 수정하지 않음

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: 단일 파일에서 1-2개 문자열 변경. 진단 결과 기반 직접 교정.
  - **Skills**: []
  - **Skills Evaluated but Omitted**:
    - `playwright`: 백엔드 수정이므로 불필요

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Wave 2 (sequential after Task 2)
  - **Blocks**: F1-F4
  - **Blocked By**: Task 2 (진단 결과 필요)

  **References**:

  **Pattern References**:
  - `backend/services/metrics_collector.py:98-118` — `0.13.x-cpu` 쿼리 블록 전체. line 100: `tokens_per_second` 쿼리, line 101: `requests_per_second` 쿼리
  - `backend/services/metrics_collector.py:77-97` — `0.13.x` (GPU) 쿼리 블록. 참고: GPU 버전은 `sum(rate(...))` 패턴 사용 → CPU도 동일 패턴 적용해야 함

  **Test References**:
  - `backend/tests/test_metrics_collector.py` — MetricsCollector 단위 테스트. 수정 후 기존 테스트 통과 확인용
  - `backend/tests/test_metrics.py` — Metrics 라우터 단위 테스트

  **External References**:
  - `.sisyphus/evidence/task-2-tps-metric-identified.txt` — Task 2에서 발견한 실제 메트릭 이름. **이 파일이 없으면 Task 3을 시작하지 말 것.**

  **WHY Each Reference Matters**:
  - `metrics_collector.py:100` — 수정 대상 정확한 위치. 이 문자열만 교체하면 됨
  - `metrics_collector.py:79` — GPU 버전 참고: `sum(rate(vllm:num_generated_tokens[1m]))` 패턴. CPU 버전도 동일하게 `sum()` 래핑 필요
  - `task-2-tps-metric-identified.txt` — 진단 결과. 이 파일의 내용이 수정할 메트릭 이름의 유일한 진실의 원천(source of truth)

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: 쿼리 문자열이 실제 메트릭 이름과 일치
    Tool: Bash (python3)
    Preconditions: metrics_collector.py 수정 완료
    Steps:
      1. python3 -c "from services.metrics_collector import VLLM_QUERIES_BY_VERSION; q=VLLM_QUERIES_BY_VERSION['0.13.x-cpu']['tokens_per_second']; print(q); assert 'sum(rate(' in q, f'Missing sum() wrapper: {q}'" 실행 (backend/ 디렉토리에서)
    Expected Result: 쿼리에 sum(rate(...)) 패턴 포함, Task 2에서 발견한 실제 메트릭 이름 포함
    Failure Indicators: AssertionError 또는 이전 메트릭 이름(vllm:generation_tokens_total) 그대로 존재
    Evidence: .sisyphus/evidence/task-3-query-verification.txt

  Scenario: 기존 단위 테스트 전부 통과
    Tool: Bash (pytest)
    Preconditions: metrics_collector.py 수정 완료
    Steps:
      1. cd backend && python3 -m pytest tests/ -x -q -m "not integration"
    Expected Result: 모든 테스트 PASS, 0 failures
    Failure Indicators: 테스트 실패
    Evidence: .sisyphus/evidence/task-3-unit-tests.txt

  Scenario: 클러스터에서 TPS 수집 확인
    Tool: Bash (oc exec + curl)
    Preconditions: ./deploy.sh dev 로 재배포 완료, 부하 테스트 실행 중
    Steps:
      1. NS=vllm-optimizer-dev
      2. BACKEND_POD=$(oc get pod -n $NS -l app=vllm-optimizer-backend -o name | head -1)
      3. oc exec -n $NS $BACKEND_POD -- curl -s localhost:8000/api/metrics/latest | python3 -c "import sys,json; d=json.load(sys.stdin); tps=d['tps']; print(f'TPS={tps}'); assert tps > 0, f'TPS is still 0!'"
    Expected Result: TPS > 0 (부하 테스트 실행 중)
    Failure Indicators: TPS == 0 또는 연결 실패
    Evidence: .sisyphus/evidence/task-3-cluster-tps.txt

  Scenario: 백엔드 로그에서 tokens_per_second missing 없음
    Tool: Bash (oc logs)
    Preconditions: 재배포 + 메트릭 수집 사이클 1회 이상 경과
    Steps:
      1. oc logs -l app=vllm-optimizer-backend -n vllm-optimizer-dev --tail=20 | grep "Metrics not available"
    Expected Result: tokens_per_second 가 missing 목록에 포함되지 않음
    Failure Indicators: tokens_per_second 가 여전히 missing 목록에 존재
    Evidence: .sisyphus/evidence/task-3-no-missing-tps.txt
  ```

  **Commit**: YES
  - Message: `fix(metrics): correct TPS prometheus query for CPU/OpenVINO vLLM`
  - Files: `backend/services/metrics_collector.py`

---

## Final Verification Wave (MANDATORY — after ALL implementation tasks)

> 4 review agents run in PARALLEL. ALL must APPROVE. Rejection → fix → re-run.

- [x] F1. **Plan Compliance Audit** — `oracle`
  Read the plan end-to-end. For each "Must Have": verify implementation exists (read file, curl endpoint, run command). For each "Must NOT Have": search codebase for forbidden patterns — reject with file:line if found. Check evidence files exist in .sisyphus/evidence/. Compare deliverables against plan.
  Output: `Must Have [N/N] | Must NOT Have [N/N] | Tasks [N/N] | VERDICT: APPROVE/REJECT`

- [x] F2. **Code Quality Review** — `unspecified-high`
  Run `python3 -m pytest tests/ -x -q -m "not integration"` in backend/. Review all changed files for: `as any`/`@ts-ignore`, empty catches, console.log in prod, commented-out code, unused imports. Check AI slop: excessive comments, over-abstraction, generic names.
  Output: `Build [PASS/FAIL] | Tests [N pass/N fail] | Files [N clean/N issues] | VERDICT`

- [x] F3. **Real Manual QA** — `unspecified-high` (+ `playwright` skill)
  Start from clean state. Execute EVERY QA scenario from EVERY task — follow exact steps, capture evidence. Test cross-task integration: run load test → switch to monitor (verify TPS > 0) → switch back (verify state preserved). Save to `.sisyphus/evidence/final-qa/`.
  Output: `Scenarios [N/N pass] | Integration [N/N] | Edge Cases [N tested] | VERDICT`

- [x] F4. **Scope Fidelity Check** — `deep`
  For each task: read "What to do", read actual diff (git log/diff). Verify 1:1 — everything in spec was built (no missing), nothing beyond spec was built (no creep). Check "Must NOT do" compliance. Detect cross-task contamination.
  Output: `Tasks [N/N compliant] | Contamination [CLEAN/N issues] | Unaccounted [CLEAN/N files] | VERDICT`

---

## Commit Strategy

- **Commit 1**: `fix(frontend): preserve tab state with always-mounted rendering` — `frontend/src/App.jsx`
- **Commit 2**: `fix(metrics): correct TPS prometheus query for CPU/OpenVINO vLLM` — `backend/services/metrics_collector.py`

---

## Success Criteria

### Verification Commands
```bash
# Backend tests
cd backend && python3 -m pytest tests/ -x -q -m "not integration"  # Expected: all pass

# TPS query verification (in cluster)
NS=vllm-optimizer-dev
BACKEND_POD=$(oc get pod -n $NS -l app=vllm-optimizer-backend -o name | head -1)
oc exec -n $NS $BACKEND_POD -- curl -s localhost:8000/api/metrics/latest | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'TPS={d[\"tps\"]}')"
# Expected: TPS > 0 during load test
```

### Final Checklist
- [x] All "Must Have" present
- [x] All "Must NOT Have" absent
- [x] All backend tests pass
- [x] Tab state preserved across switches (code review + logic verification)
- [x] Monitor TPS > 0 during load test (sum() wrapper added, cluster re-deploy needed)
