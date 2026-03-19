# MonitorPage P99/TTFT 그래프 끊김 및 MetricCard "—" 수정

## TL;DR

> **Quick Summary**: Latency 차트가 활성 데이터(P99≈5ms, TTFT≈2.5ms) 존재에도 짧고 규칙적인 gap을 보이고, MetricCard가 간헐적 "—" 표시. 3중 수정: (1) Chart 애니메이션 비활성화 + linear 보간으로 connectNulls 안정화, (2) gap-fill 유틸리티로 null 구간을 점선 채움, (3) MetricCard에 lastGoodMetrics 캐시 추가.
> 
> **Deliverables**:
> - `buildGapFill` 유틸리티 함수 + 단위 테스트
> - Chart.jsx 이중 시리즈 렌더링 (실선 + 점선) + 커스텀 Tooltip
> - MonitorPage 데이터 후처리 + MetricCard 복원력 개선
> 
> **Estimated Effort**: Short
> **Parallel Execution**: YES — 2 waves
> **Critical Path**: Task 1 → Task 3 → Task 4

---

## Context

### Original Request
대시보드 실시간 모니터링 탭에서 P99/TTFT 값이 "—"로 나오고 그래프 라인이 끊기는 문제. 이전 fix-latency-graph-gaps (커밋 c243609) 적용 후에도 지속됨.

### Interview Summary
**Key Discussions**:
- fix-latency-graph-gaps는 올바르게 적용되어 있음 (백엔드: 0→null 변환, Chart: connectNulls=true)
- **스크린샷 분석** (2026-03-08 221240.png): P99≈5ms, TTFT≈2.5ms 유효 데이터가 있는데도 짧고 규칙적인 gap 반복
- 이는 "긴 idle 기간" 문제가 아닌 **"활성 중 간헐적 null + connectNulls 미작동"** 이중 문제
- MetricCard "—": 유저 보고 — API 실패 또는 탭 전환 시 재마운트로 추정
- 유저 선호: 유효 데이터는 실선, idle 구간은 점선/회색으로 구분

**Research Findings**:
- Recharts 실제 설치 버전 **2.15.4** (package.json ^2.10.3 → lock file 2.15.4)
- `isAnimationActive` 미설정 (기본 `true`) → 2초 polling re-render마다 애니메이션 트리거 → gap 원인 가능
- `type="monotone"` (cubic spline) + null 데이터 → interpolation 계산 시 gap 발생 가능
- Recharts Tooltip은 모든 Line 시리즈를 기본 표시 → 커스텀 Tooltip 필요 (fill 시리즈 숨기기)
- `legendType="none"`은 Legend에서만 숨김, Tooltip에서는 안 숨김
- Chart.jsx는 MonitorPage + LoadTestPage 양쪽에서 사용 → 후방호환 필수
- `mockHistory()`는 mock 모드 앱에서 사용 → 수정 금지, 새 테스트 픽스처만 추가

### Metis Review
**Identified Gaps** (addressed):
- MetricCard "—" vs "0" 혼동: `/latest`가 0.0 반환하므로 "—"는 fetch 실패 또는 재마운트 시에만 발생 → MetricCard에 lastKnownMetrics 캐시 추가
- Tooltip 이중 표시 위험: fill 시리즈가 Tooltip에 노출됨 → 커스텀 Tooltip으로 `_fill` 키 필터링
- Mock 모드 오버랩: null 없을 때 fill 라인이 실선과 동일 위치 → null 없으면 fill 시리즈 생략
- Chart.jsx 후방호환: LoadTestPage도 Chart 사용 → optional props with defaults

---

## Work Objectives

### Core Objective
MonitorPage의 Latency 차트에서 idle 구간을 점선으로 채우고, MetricCard가 fetch 실패 시에도 마지막 유효값을 표시하도록 개선.

### Concrete Deliverables
- `frontend/src/utils/gapFill.js` — buildGapFill 유틸리티 함수
- `frontend/src/utils/gapFill.test.js` — 단위 테스트 (5+ 케이스)
- `frontend/src/components/Chart.jsx` — dash prop + 커스텀 Tooltip 지원
- `frontend/src/pages/MonitorPage.jsx` — gap-fill 적용 + MetricCard 복원력
- `frontend/src/mockData.js` — mockHistoryWithGaps() 테스트 픽스처 추가

### Definition of Done
- [x] `npm test` — 모든 테스트 통과 (기존 + 신규)
- [x] `npm run build` — 빌드 성공 (exit 0)
- [x] buildGapFill 유틸리티가 all-null, leading-null, trailing-null, mixed, no-null 케이스 처리
- [x] Chart에 dash prop 없이 호출 시 기존 동작과 100% 동일

### Must Have
- Latency 차트: idle 구간에 점선 표시 (마지막 유효값 캐리포워드)
- Chart.jsx 후방호환: LoadTestPage 동작 무변경
- Tooltip에서 fill 시리즈 숨김
- Legend에서 fill 시리즈 숨김
- MetricCard fetch 실패 시 마지막 유효값 유지 (null 방지)

### Must NOT Have (Guardrails)
- ❌ 백엔드 코드 변경 (`backend/` 디렉토리 일체 수정 금지)
- ❌ `mockHistory()` 기존 함수 수정 (mock 모드 앱에서 사용 중)
- ❌ 비-latency 차트에 gap-fill 적용 (TPS, KV Cache, Request Queue는 null 없음)
- ❌ Chart.jsx의 `lines` prop 구조 변경 (optional 필드만 추가)
- ❌ MetricCard 컴포넌트 자체 수정 (MonitorPage에서 전달 값만 변경)
- ❌ `COLORS.amber` 불일치 수정 (별도 작업)
- ❌ App.jsx의 dead Chart import 제거 (별도 클린업)
- ❌ Loading skeleton / spinner 추가 (scope creep)

---

## Verification Strategy (MANDATORY)

> **ZERO HUMAN INTERVENTION** — ALL verification is agent-executed. No exceptions.

### Test Decision
- **Infrastructure exists**: YES (Vitest + @testing-library/react)
- **Automated tests**: YES (Tests-after) — buildGapFill 유틸리티에 대한 단위 테스트
- **Framework**: Vitest

### QA Policy
Every task MUST include agent-executed QA scenarios.
Evidence saved to `.sisyphus/evidence/task-{N}-{scenario-slug}.{ext}`.

- **Library/Module**: Use Bash (node/vitest) — Import, call functions, compare output
- **Frontend build**: Use Bash (npm run build) — Assert exit code 0

---

## Execution Strategy

### Parallel Execution Waves

```
Wave 1 (Start Immediately — independent foundation):
├── Task 1: buildGapFill 유틸리티 + 테스트 [quick]
├── Task 2: Chart.jsx dual-series 지원 + 커스텀 Tooltip [quick]
└── Task 3: mockHistoryWithGaps 테스트 픽스처 [quick]

Wave 2 (After Wave 1 — integration):
└── Task 4: MonitorPage 통합 (gap-fill + MetricCard 복원력) [unspecified-high]

Wave 3 (After Wave 2 — verification):
└── Task 5: 최종 빌드 + 테스트 검증 [quick]

Wave FINAL (After ALL tasks):
├── Task F1: Plan compliance audit (oracle)
├── Task F2: Code quality review (unspecified-high)
└── Task F3: Scope fidelity check (deep)

Critical Path: Task 1 → Task 4 → Task 5 → F1-F3
Parallel Speedup: Wave 1에서 3개 태스크 병렬 실행
Max Concurrent: 3 (Wave 1)
```

### Dependency Matrix

| Task | Depends On | Blocks |
|------|-----------|--------|
| 1 | — | 4 |
| 2 | — | 4 |
| 3 | — | 4 |
| 4 | 1, 2, 3 | 5 |
| 5 | 4 | F1-F3 |
| F1-F3 | 5 | — |

### Agent Dispatch Summary

- **Wave 1**: 3 — T1 → `quick`, T2 → `quick`, T3 → `quick`
- **Wave 2**: 1 — T4 → `unspecified-high`
- **Wave 3**: 1 — T5 → `quick`
- **FINAL**: 3 — F1 → `oracle`, F2 → `unspecified-high`, F3 → `deep`

---

## TODOs

- [x] 1. buildGapFill 유틸리티 함수 + 단위 테스트

  **What to do**:
  - `frontend/src/utils/gapFill.js` 생성 — `buildGapFill(history, keys)` 함수 구현
  - 입력: history 배열 (각 요소는 `{ t, ttft, lat_p99, ... }` 형태), keys 배열 (gap-fill 적용할 키 목록)
  - 동작: 각 key에 대해 `{key}_fill` 필드를 추가. null인 포인트는 마지막 유효값으로 채움
  - 첫 유효값 이전의 null은 null 유지 (carry-forward할 이전 값 없음)
  - 입력 배열에 null이 하나도 없으면 `_fill` 필드 추가하지 않음 (불필요한 점선 방지)
  - 순수 함수, 사이드이펙트 없음, 입력 배열 mutation 없음 (새 배열 반환)
  - `frontend/src/utils/gapFill.test.js` 생성 — 최소 5개 테스트 케이스:
    1. all-null 입력: `[{ttft:null}, {ttft:null}]` → fill 필드도 전부 null (이전 값 없음)
    2. leading-null: `[{ttft:null}, {ttft:80}, {ttft:null}]` → fill: `[null, 80, 80]`
    3. trailing-null: `[{ttft:80}, {ttft:null}]` → fill: `[80, 80]`
    4. mixed: `[{ttft:80}, {ttft:null}, {ttft:null}, {ttft:95}]` → fill: `[80, 80, 80, 95]`
    5. no-null: `[{ttft:80}, {ttft:90}]` → `_fill` 필드 미추가 (null 없으므로)

  **Must NOT do**:
  - 비-latency 키에 gap-fill 적용 금지 (함수 자체는 범용이지만, 호출 시 ttft/lat_p99만 전달)
  - 입력 배열 직접 수정 금지 (immutable)

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: 단일 유틸리티 함수 + 테스트 파일 생성. 로직이 명확하고 의존성 없음
  - **Skills**: []
    - 프론트엔드 프레임워크 지식 불필요. 순수 JS 유틸리티

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Tasks 2, 3)
  - **Blocks**: Task 4
  - **Blocked By**: None (can start immediately)

  **References**:

  **Pattern References**:
  - `frontend/src/pages/MonitorPage.jsx:42-46` — 현재 history 데이터 매핑 로직. `ttft: m.ttft_mean, lat_p99: m.latency_p99` 형태로 null 값이 들어옴
  - `frontend/src/mockData.js:12-17` — mockHistory 데이터 구조. gap-fill의 입력 형태 참고

  **API/Type References**:
  - `backend/services/metrics_collector.py:354-357` — `get_history_dict`에서 `or None` 변환. 이게 null의 원천

  **Test References**:
  - `frontend/src/mockData.test.js` — 기존 테스트 패턴. `describe`/`it`/`expect` 구조 확인

  **WHY Each Reference Matters**:
  - MonitorPage 데이터 매핑: buildGapFill의 입력 형태를 정확히 맞추기 위해 참고
  - mockHistory: 테스트 픽스처 작성 시 데이터 구조 일관성 확보
  - 기존 테스트: 이 프로젝트의 Vitest 테스트 컨벤션 따르기

  **Acceptance Criteria**:

  - [x] `frontend/src/utils/gapFill.js` 파일 존재
  - [x] `frontend/src/utils/gapFill.test.js` 파일 존재
  - [x] `cd frontend && npx vitest run src/utils/gapFill.test.js` → PASS (5+ tests, 0 failures)

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: buildGapFill이 mixed null 패턴을 올바르게 처리
    Tool: Bash
    Preconditions: frontend/src/utils/gapFill.js 존재
    Steps:
      1. `cd frontend && npx vitest run src/utils/gapFill.test.js --reporter=verbose`
      2. 출력에 5개 이상 test case가 PASS인지 확인
      3. "Tests  5 passed" (또는 그 이상) 메시지 확인
    Expected Result: 모든 테스트 PASS, exit code 0
    Failure Indicators: 하나라도 FAIL이거나 import 에러 발생
    Evidence: .sisyphus/evidence/task-1-gapfill-tests.txt

  Scenario: buildGapFill이 입력 배열을 mutate하지 않음
    Tool: Bash
    Preconditions: 테스트에 mutation 체크 케이스 포함
    Steps:
      1. 테스트 코드에서 원본 배열 참조를 유지하고, buildGapFill 호출 후 원본이 변경되지 않았음을 assert
    Expected Result: 원본 배열 unchanged 확인 테스트 PASS
    Failure Indicators: 원본 배열이 변경됨
    Evidence: .sisyphus/evidence/task-1-gapfill-immutable.txt
  ```

  **Commit**: YES
  - Message: `feat(frontend): add buildGapFill utility for latency chart gap interpolation`
  - Files: `frontend/src/utils/gapFill.js`, `frontend/src/utils/gapFill.test.js`
  - Pre-commit: `cd frontend && npx vitest run src/utils/gapFill.test.js`

- [x] 2. Chart.jsx dual-series 렌더링 + 커스텀 Tooltip + 애니메이션/보간 수정

  **What to do**:
  - `frontend/src/components/Chart.jsx` 수정

  **A. 기본 렌더링 안정화 (connectNulls 미작동 원인 대응)**:
  - 모든 Line에 `isAnimationActive={false}` 추가 — 2초 polling re-render 시 애니메이션이 시각적 gap을 유발하는 것 방지
  - `type="monotone"` → `type="linear"` 변경 — cubic spline 보간이 null 근처에서 불안정할 수 있음. linear는 connectNulls와 더 안정적

  **B. Dual-series 지원 (점선 스타일)**:
  - `lines` prop의 각 아이템에 optional `dash` 필드 추가: `{ key, color, label, dash?: boolean }`
  - `dash: true`인 Line에 `strokeDasharray="5 3"`, `opacity={0.35}`, `strokeWidth={1}` 적용
  - `dash: true`인 Line에 `legendType="none"` 적용 (Legend에서 숨김)
  
  **C. 커스텀 Tooltip**:
  - 커스텀 Tooltip 컴포넌트 구현: payload에서 `dash: true`인 시리즈 필터링하여 표시 제외
  - Tooltip formatter에서 dash line의 dataKey를 인식하여 제외해야 함 (dataKey가 `_fill`로 끝나는 항목 필터)
  - `dash` prop이 없는 기존 호출은 현재와 100% 동일하게 동작해야 함 (backward compat)

  **Must NOT do**:
  - `lines` prop의 기존 필드(`key`, `color`, `label`) 수정 금지
  - Chart 컴포넌트의 기존 외부 API 변경 금지 (새 optional 필드만 추가)
  - LoadTestPage의 Chart 사용에 영향을 주는 변경 금지

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: 단일 컴포넌트 수정, 명확한 prop 추가
  - **Skills**: []
    - Recharts API는 코드에서 이미 사용 중이므로 별도 스킬 불필요

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Tasks 1, 3)
  - **Blocks**: Task 4
  - **Blocked By**: None (can start immediately)

  **References**:

  **Pattern References**:
  - `frontend/src/components/Chart.jsx:1-31` — 현재 Chart 컴포넌트 전체 코드. Line props 패턴, Tooltip 구성 확인
  - `frontend/src/pages/LoadTestPage.jsx:234-237` — LoadTestPage에서 Chart 사용. `lines=[{key, color, label}]` 형태 → backward compat 확인용

  **API/Type References**:
  - `frontend/src/constants.js:4-15` — COLORS 객체. 차트 스타일링에 사용되는 색상값

  **External References**:
  - Recharts `<Line>` 컴포넌트: `strokeDasharray`, `legendType`, `dot`, `connectNulls` props
  - Recharts `<Tooltip>` 컴포넌트: `content` prop으로 커스텀 렌더러 지정 가능

  **WHY Each Reference Matters**:
  - Chart.jsx 전체 코드: 현재 구조를 정확히 이해하고 최소 변경으로 기능 추가
  - LoadTestPage: 변경 후에도 이 페이지의 Chart가 동일하게 동작하는지 확인하기 위한 reference
  - COLORS: Tooltip 커스텀 렌더러의 스타일링에 필요

  **Acceptance Criteria**:

  - [x] Chart.jsx에 `dash` prop 지원 추가됨
  - [x] `dash: true` Line에 `strokeDasharray`, 낮은 `opacity`, `legendType="none"` 적용
  - [x] 커스텀 Tooltip이 `dash: true` 시리즈를 필터링하여 표시 제외
  - [x] `lines` prop에 `dash` 없이 호출 시 기존과 동일하게 렌더링 (regression 없음)

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: dash prop 없이 호출 시 backward compatibility 확인
    Tool: Bash
    Preconditions: Chart.jsx 수정 완료
    Steps:
      1. `cd frontend && npx vitest run` — 모든 기존 테스트 통과 확인
      2. Chart.jsx에서 `lines.map` 내부 분기 확인:
         - `l.dash` undefined일 때 → strokeDasharray 미적용, opacity 1.0, legendType 기본값
    Expected Result: 기존 테스트 모두 PASS
    Failure Indicators: 기존 테스트 FAIL 또는 import 에러
    Evidence: .sisyphus/evidence/task-2-backward-compat.txt

  Scenario: 렌더링 안정화 변경 확인
    Tool: Bash
    Preconditions: Chart.jsx 수정 완료
    Steps:
      1. Chart.jsx 코드 읽기
      2. 모든 Line에 `isAnimationActive={false}` 존재 확인
      3. `type="linear"` 존재 확인 (type="monotone" 제거됨)
      4. `connectNulls={true}` 여전히 존재 확인 (제거하면 안 됨)
    Expected Result: 세 가지 설정 모두 확인됨
    Failure Indicators: isAnimationActive 누락, type="monotone" 잔존
    Evidence: .sisyphus/evidence/task-2-render-stability.txt

  Scenario: dash: true Line에 점선 스타일 적용 확인
    Tool: Bash
    Preconditions: Chart.jsx 수정 완료
    Steps:
      1. Chart.jsx 코드 읽기 — `l.dash === true` 분기에서:
         - `strokeDasharray="5 3"` 존재
         - `opacity={0.35}` (또는 유사한 낮은 값)
         - `legendType="none"` 존재
      2. 커스텀 Tooltip 컴포넌트에서 `dash` 시리즈 필터링 로직 존재 확인
    Expected Result: 조건부 스타일링 코드가 올바르게 구현됨
    Failure Indicators: strokeDasharray나 legendType 미적용, Tooltip 필터 누락
    Evidence: .sisyphus/evidence/task-2-dash-styling.txt
  ```

  **Commit**: YES
  - Message: `feat(frontend): support dual-series rendering in Chart with dash and custom tooltip`
  - Files: `frontend/src/components/Chart.jsx`
  - Pre-commit: `cd frontend && npx vitest run`

- [x] 3. mockHistoryWithGaps 테스트 픽스처 추가

  **What to do**:
  - `frontend/src/mockData.js`에 `mockHistoryWithGaps()` 함수 export 추가
  - 60개 데이터 포인트 중 일부(약 15-20개)에 `ttft: null`, `lat_p99: null` 설정
  - 패턴: 처음 10개 유효 → 15개 null → 10개 유효 → 10개 null → 15개 유효
  - 이렇게 하면 leading valid, gap, valid, gap, trailing valid 패턴 모두 포함
  - 기존 `mockHistory()` 함수는 **절대 수정하지 않음**

  **Must NOT do**:
  - `mockHistory()` 함수 수정 금지 (mock 모드에서 앱이 사용 중)
  - `mockMetrics()` 함수 수정 금지
  - `simulateLoadTest()` 함수 수정 금지

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: 단일 함수 추가, 기존 코드 수정 없음
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Tasks 1, 2)
  - **Blocks**: Task 4
  - **Blocked By**: None (can start immediately)

  **References**:

  **Pattern References**:
  - `frontend/src/mockData.js:12-17` — 기존 `mockHistory()` 함수. 동일한 데이터 구조를 따라야 함. 필드: `t`, `tps`, `ttft`, `lat_p99`, `kv`, `running`, `waiting`

  **WHY Each Reference Matters**:
  - mockHistory: 동일한 필드 구조를 유지하면서 null 갭을 포함한 변형 생성

  **Acceptance Criteria**:

  - [x] `mockData.js`에 `mockHistoryWithGaps` export 존재
  - [x] 기존 `mockHistory` 함수 코드 변경 없음
  - [x] `cd frontend && npx vitest run src/mockData.test.js` → PASS

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: mockHistoryWithGaps가 올바른 구조 반환
    Tool: Bash
    Preconditions: mockData.js 수정 완료
    Steps:
      1. `cd frontend && npx vitest run src/mockData.test.js --reporter=verbose`
      2. mockHistoryWithGaps 관련 테스트가 PASS인지 확인
    Expected Result: 60개 포인트 반환, null gap 포함, 기존 테스트도 PASS
    Failure Indicators: 배열 길이 불일치, null 위치 잘못됨, 기존 테스트 FAIL
    Evidence: .sisyphus/evidence/task-3-mock-gaps.txt
  ```

  **Commit**: YES
  - Message: `test(frontend): add mockHistoryWithGaps test fixture`
  - Files: `frontend/src/mockData.js`
  - Pre-commit: `cd frontend && npx vitest run src/mockData.test.js`

- [x] 4. MonitorPage 통합: gap-fill 적용 + MetricCard 복원력

  **What to do**:
  - `frontend/src/pages/MonitorPage.jsx` 수정

  **A. History 데이터 후처리 (gap-fill)**:
  - `import { buildGapFill } from '../utils/gapFill'` 추가
  - `fetchHistory` 내에서 history 데이터 매핑 후 `buildGapFill(mapped, ['ttft', 'lat_p99'])` 호출
  - gap-fill된 데이터를 `setHistory`에 저장
  - Latency 차트에 fill 시리즈 전달:
    ```jsx
    <Chart data={history} title="Latency (ms)" lines={[
      { key: "ttft_fill", color: COLORS.cyan, label: "TTFT (idle)", dash: true },
      { key: "lat_p99_fill", color: COLORS.red, label: "P99 (idle)", dash: true },
      { key: "ttft", color: COLORS.cyan, label: "TTFT" },
      { key: "lat_p99", color: COLORS.red, label: "P99" },
    ]} />
    ```
  - **중요**: fill 시리즈를 실선 시리즈보다 먼저 나열 (z-order: 먼저 선언된 Line이 아래에 렌더링)
  - fill 키가 데이터에 없으면 (null 없는 경우) 해당 Line은 자연스럽게 렌더링되지 않음

  **B. MetricCard 복원력**:
  - `useRef`로 `lastGoodMetrics` 추적
  - `fetchLatest` 성공 시 `lastGoodMetrics.current = d` 업데이트
  - `fetchLatest` 실패 시 `setMetrics(lastGoodMetrics.current)` 로 마지막 유효 메트릭 복원 (null 방지)
  - 초기 상태(`metrics === null`)에서는 "—" 표시 유지 (첫 성공 fetch까지)

  **C. 비-latency 차트는 변경 없음**:
  - TPS, KV Cache, Request Queue 차트는 현재와 동일하게 유지

  **Must NOT do**:
  - 비-latency 차트에 gap-fill 적용 금지
  - `fetchLatest`의 정상 동작 변경 금지
  - MetricCard 컴포넌트 자체(`MetricCard.jsx`) 수정 금지
  - `fmt` 함수 동작 변경 금지

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
    - Reason: 여러 관심사 통합 (데이터 처리 + 차트 + 상태 관리), 정확한 z-order와 데이터 흐름 이해 필요
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Wave 2 (sequential)
  - **Blocks**: Task 5
  - **Blocked By**: Tasks 1, 2, 3

  **References**:

  **Pattern References**:
  - `frontend/src/pages/MonitorPage.jsx:37-50` — 현재 fetchHistory + 데이터 매핑. 이 로직 뒤에 buildGapFill 호출 추가
  - `frontend/src/pages/MonitorPage.jsx:26-36` — fetchLatest 로직. catch 블록에 lastGoodMetrics 복원 추가
  - `frontend/src/pages/MonitorPage.jsx:89-94` — Latency 차트 렌더링. lines prop에 fill 시리즈 추가

  **API/Type References**:
  - `frontend/src/utils/gapFill.js` (Task 1에서 생성) — buildGapFill 함수 시그니처
  - `frontend/src/components/Chart.jsx` (Task 2에서 수정) — dash prop 사용법

  **Test References**:
  - `frontend/src/utils/gapFill.test.js` (Task 1에서 생성) — buildGapFill 동작 확인

  **WHY Each Reference Matters**:
  - fetchHistory: buildGapFill 호출 위치 결정. 매핑 후, setHistory 전
  - fetchLatest: lastGoodMetrics 캐시 로직 삽입 위치
  - Latency 차트: lines prop 수정 위치. fill 시리즈의 z-order 결정

  **Acceptance Criteria**:

  - [x] MonitorPage에서 buildGapFill import 및 호출
  - [x] Latency 차트에 4개 Line 전달 (ttft_fill, lat_p99_fill, ttft, lat_p99)
  - [x] fill 시리즈가 실선 시리즈보다 먼저 선언 (z-order)
  - [x] lastGoodMetrics ref로 fetch 실패 시 이전 값 유지
  - [x] `cd frontend && npm run build` → exit 0
  - [x] `cd frontend && npx vitest run` → 모든 테스트 PASS

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: MonitorPage 빌드 성공 확인
    Tool: Bash
    Preconditions: Task 1, 2, 3 완료
    Steps:
      1. `cd frontend && npm run build`
      2. exit code 0 확인
      3. 빌드 경고 중 import 관련 에러 없음 확인
    Expected Result: 빌드 성공, exit 0
    Failure Indicators: JSX 구문 에러, import 경로 오류, 타입 불일치
    Evidence: .sisyphus/evidence/task-4-build.txt

  Scenario: 전체 테스트 suite 통과 확인
    Tool: Bash
    Preconditions: MonitorPage.jsx 수정 완료
    Steps:
      1. `cd frontend && npx vitest run --reporter=verbose`
      2. 모든 테스트 PASS 확인
      3. 기존 테스트 (MetricCard, mockData, ErrorBoundary) 포함
    Expected Result: 전체 PASS, 0 failures
    Failure Indicators: regression 발생 (기존 테스트 FAIL)
    Evidence: .sisyphus/evidence/task-4-tests.txt

  Scenario: gap-fill 데이터 흐름 코드 검증
    Tool: Bash (grep)
    Preconditions: MonitorPage.jsx 수정 완료
    Steps:
      1. MonitorPage.jsx 읽기
      2. `buildGapFill` import 존재 확인
      3. `buildGapFill(` 호출 존재 확인 (인자: mapped history, ['ttft', 'lat_p99'])
      4. Latency Chart의 lines prop에 `dash: true` 포함 확인
      5. `lastGoodMetrics` ref 존재 확인
    Expected Result: 모든 코드 패턴 존재
    Failure Indicators: import 누락, 호출 누락, dash prop 누락
    Evidence: .sisyphus/evidence/task-4-code-review.txt
  ```

  **Commit**: YES
  - Message: `fix(dashboard): fill latency graph gaps with dashed idle line and preserve MetricCard on fetch failure`
  - Files: `frontend/src/pages/MonitorPage.jsx`
  - Pre-commit: `cd frontend && npx vitest run`

- [x] 5. 최종 빌드 + 테스트 검증

  **What to do**:
  - 전체 프론트엔드 빌드 실행: `cd frontend && npm run build`
  - 전체 테스트 실행: `cd frontend && npx vitest run`
  - 백엔드 코드 변경 없음 확인: `git diff --name-only` 에서 `backend/` 파일 없음
  - mockHistory() 함수 변경 없음 확인: `git diff frontend/src/mockData.js` 에서 기존 함수 body 미변경
  - Chart.jsx backward compat 확인: LoadTestPage.jsx에서 Chart 호출 코드 읽고, `dash` prop 없이 호출되는지 확인

  **Must NOT do**:
  - 코드 수정 (검증만 수행)

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: 빌드/테스트 실행 + 결과 확인만
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Wave 3 (sequential)
  - **Blocks**: F1, F2, F3
  - **Blocked By**: Task 4

  **References**:

  **Pattern References**:
  - `frontend/src/pages/LoadTestPage.jsx:234-237` — LoadTestPage의 Chart 호출. `dash` prop 없이 호출되는지 확인
  - `frontend/src/mockData.js:12-17` — mockHistory 원본. 변경되지 않았는지 diff로 확인

  **WHY Each Reference Matters**:
  - LoadTestPage: Chart.jsx 후방호환 검증 — `dash` 없는 호출이 정상 동작하는지
  - mockHistory: 기존 mock 함수 보호 검증

  **Acceptance Criteria**:

  - [x] `cd frontend && npm run build` → exit 0
  - [x] `cd frontend && npx vitest run` → all PASS
  - [x] `git diff --name-only` 에서 `backend/` 파일 없음
  - [x] LoadTestPage.jsx의 Chart 호출에 `dash` prop 없음 (기존 방식 유지)

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: 전체 빌드 + 테스트 최종 검증
    Tool: Bash
    Preconditions: Task 1-4 모두 완료
    Steps:
      1. `cd frontend && npm run build` — exit 0 확인
      2. `cd frontend && npx vitest run --reporter=verbose` — 전체 PASS 확인
      3. `git diff --name-only` — backend/ 경로 파일 없음 확인
      4. `grep -c "dash" frontend/src/pages/LoadTestPage.jsx` — 0 (dash prop 미사용)
    Expected Result: 빌드 성공, 전체 테스트 PASS, 백엔드 미변경, 후방호환 유지
    Failure Indicators: 빌드 실패, 테스트 FAIL, 백엔드 파일 변경됨
    Evidence: .sisyphus/evidence/task-5-final-verification.txt
  ```

  **Commit**: NO (verification only)

---

## Final Verification Wave (MANDATORY — after ALL implementation tasks)

> 3 review agents run in PARALLEL. ALL must APPROVE. Rejection → fix → re-run.

- [x] F1. **Plan Compliance Audit** — `oracle`
  Read the plan end-to-end. For each "Must Have": verify implementation exists (read file, run command). For each "Must NOT Have": search codebase for forbidden patterns — reject with file:line if found. Check evidence files exist in .sisyphus/evidence/. Compare deliverables against plan.
  Output: `Must Have [N/N] | Must NOT Have [N/N] | Tasks [N/N] | VERDICT: APPROVE/REJECT`

- [x] F2. **Code Quality Review** — `unspecified-high`
  Run `npm run build` + `npm test` in frontend/. Review all changed files for: console.log in prod, commented-out code, unused imports. Check AI slop: excessive comments, over-abstraction. Verify Chart.jsx backward compatibility by reading LoadTestPage.jsx usage.
  Output: `Build [PASS/FAIL] | Tests [N pass/N fail] | Files [N clean/N issues] | VERDICT`

- [x] F3. **Scope Fidelity Check** — `deep`
  For each task: read "What to do", read actual diff (git log/diff). Verify 1:1 — everything in spec was built (no missing), nothing beyond spec was built (no creep). Check "Must NOT do" compliance (no backend changes, no mockHistory() modification). Flag unaccounted changes.
  Output: `Tasks [N/N compliant] | Unaccounted [CLEAN/N files] | VERDICT`

---

## Commit Strategy

- **1**: `feat(frontend): add buildGapFill utility for latency chart gap interpolation` — frontend/src/utils/gapFill.js, frontend/src/utils/gapFill.test.js
- **2**: `feat(frontend): support dual-series rendering in Chart with dash and custom tooltip` — frontend/src/components/Chart.jsx
- **3**: `test(frontend): add mockHistoryWithGaps test fixture` — frontend/src/mockData.js
- **4**: `fix(dashboard): fill latency graph gaps with dashed idle line and preserve MetricCard on fetch failure` — frontend/src/pages/MonitorPage.jsx
- **5**: No commit (verification only)

---

## Success Criteria

### Verification Commands
```bash
cd frontend && npm test          # Expected: all tests pass, exit 0
cd frontend && npm run build     # Expected: build succeeds, exit 0
```

### Final Checklist
- [x] buildGapFill handles all edge cases (all-null, leading-null, trailing-null, mixed, no-null)
- [x] Chart.jsx renders identically when no dash prop provided (backward compat)
- [x] Tooltip does NOT show fill series entries
- [x] Legend does NOT show fill series entries
- [x] MonitorPage latency chart has solid + dashed dual rendering
- [x] MetricCard preserves last value on fetch failure
- [x] No backend files modified
- [x] mockHistory() function unchanged
- [x] All existing tests pass
- [x] Build succeeds
