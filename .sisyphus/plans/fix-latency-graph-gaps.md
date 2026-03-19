# Fix Latency Graph Gaps on Dashboard

## TL;DR

> **Quick Summary**: vLLM이 idle 상태일 때 `histogram_quantile()` PromQL이 NaN을 반환하여 `/api/metrics/history` 전체가 HTTP 500으로 실패하고, 대시보드 Latency 차트가 끊어져 보이는 문제를 수정한다.
>
> **Deliverables**:
> - Backend: NaN/Infinity 필터링 추가 (`_fetch_prometheus_metric`)
> - Backend: idle 시 latency 필드를 `null`로 직렬화 (0 대신)
> - Frontend: Recharts `connectNulls` 적용으로 null 구간 선 연결
> - 각 수정에 대한 회귀 테스트
>
> **Estimated Effort**: Short (3 tasks, 4-5 files)
> **Parallel Execution**: YES — 2 waves
> **Critical Path**: Task 1 → Task 2 (Task 3은 독립)

---

## Context

### Original Request
대시보드에서 Latency 2개 그래프(TTFT, P99)가 중간 중간 끊어져서 보이는 현상 수정 요청.

### Root Cause Analysis
코드 전체 데이터 흐름을 추적하여 근본 원인을 확인함:

**원인 1 — NaN이 JSON 직렬화를 깨뜨림 (Critical)**:
1. vLLM idle 시 `histogram_quantile(0.5, rate(...bucket[1m]))` → Prometheus가 `"NaN"` 반환
2. `_fetch_prometheus_metric`에서 `float("NaN")` → Python nan으로 변환 (필터링 없음)
3. `_query_prometheus`에서 `nan is not None → True` → result dict에 포함
4. VLLMMetrics에 nan 저장 → history deque에 누적
5. `/api/metrics/history` 응답 시 `json.dumps(allow_nan=False)` → `ValueError` → HTTP 500
6. Frontend fetch 실패 → history 상태 미갱신 → 차트 정지/끊김

**원인 2 — Empty result가 0으로 기본값 설정됨 (Medium)**:
- Prometheus가 빈 결과 반환 시 → latency가 0.0으로 기본값
- 0ms latency는 물리적으로 불가능한 값 (측정 없음을 의미)
- 차트가 수백ms ↔ 0ms 사이를 급격히 오가며 시각적으로 끊어져 보임

**원인 3 — Recharts `connectNulls` 미설정 (Low)**:
- `Chart.jsx`의 `<Line>` 컴포넌트에 `connectNulls` prop 없음
- null/undefined 데이터 포인트에서 선이 끊어짐

**왜 Latency만 끊어지나?**:
- TTFT/P99만 `histogram_quantile()` 사용 → idle 시 NaN 발생
- TPS(`rate()`), KV Cache(gauge), Queue(gauge)는 idle 시 유효한 0 반환

### Metis Review
**확인된 사항**:
- NaN 흐름 경로를 Starlette 소스코드까지 검증 (`allow_nan=False` 확인됨)
- Pydantic v2가 float 필드에 NaN을 조용히 수용하는 것 확인됨
- `MetricsSnapshot(ttft_mean=None)` → `float` 타입이면 `ValidationError` 발생 확인

**반영된 갭**:
- Task 2 내부 순서 의존성: MetricsSnapshot 모델 변경이 `get_history_dict` 변경보다 먼저 되어야 함
- `/latest` 엔드포인트 불일치: scope 외로 명시하고 코멘트로 기록
- 회귀 테스트 필수: NaN → 500 경로와 0 → null 변환 모두 테스트

---

## Work Objectives

### Core Objective
idle 기간의 NaN/Infinity 값이 API 응답을 깨뜨리지 않도록 필터링하고, 측정 없음(idle)을 `null`로 표현하여 차트가 끊어지지 않게 한다.

### Concrete Deliverables
- `backend/services/metrics_collector.py` — NaN/Inf 필터링 로직
- `backend/models/load_test.py` — latency 필드 `Optional[float]` 변경
- `backend/services/metrics_collector.py` — `get_history_dict`에서 0 → None 변환
- `frontend/src/components/Chart.jsx` — `connectNulls={true}` 추가
- `backend/tests/test_metrics_collector.py` — NaN 필터링 회귀 테스트
- `backend/tests/test_metrics.py` — history 엔드포인트 null 직렬화 테스트

### Definition of Done
- [x] `cd backend && python3 -m pytest tests/ -x -q -m "not integration"` → 0 failures
- [x] `/api/metrics/history` 응답에 `NaN` 문자열이 없음 (NaN 주입 시에도 200 반환)
- [x] idle latency 필드가 `null`로 직렬화됨 (`0.0`이 아닌)
- [x] `grep 'connectNulls' frontend/src/components/Chart.jsx` → 결과 있음

### Must Have
- NaN과 Infinity 모두 필터링 (`math.isnan` + `math.isinf`)
- NaN 필터링은 `float()` 호출 후, `round()` 호출 전에 위치
- latency 전용 4개 필드만 Optional: `ttft_mean`, `ttft_p99`, `latency_mean`, `latency_p99`
- MetricsSnapshot 모델 변경 → `get_history_dict` 변경 순서 엄수
- 각 태스크별 회귀 테스트

### Must NOT Have (Guardrails)
- `VLLMMetrics` dataclass 필드를 `Optional[float]`로 변경하지 않음 (영향 범위 과대)
- `tps`, `rps`, `kv_cache`, `kv_hit_rate`, `gpu_mem_used`, `gpu_util` 필드를 Optional로 변경하지 않음 (이들은 0이 유효한 값)
- `_convert_to_snapshot`(`routers/metrics.py`)을 수정하지 않음 (`/latest` 엔드포인트는 현행 유지, 불일치는 코멘트로 기록)
- `Chart.jsx`에서 `<Area>`, `<Bar>`, `<AreaChart>` 등 다른 컴포넌트 수정하지 않음
- TPS/RPS의 idle 시 0 표시를 바꾸지 않음 (scope 외)

---

## Verification Strategy

> **ZERO HUMAN INTERVENTION** — ALL verification is agent-executed. No exceptions.

### Test Decision
- **Infrastructure exists**: YES
- **Automated tests**: YES (Tests-after — 각 수정에 맞는 테스트 추가)
- **Framework**: pytest (backend), grep 검증 (frontend)

### QA Policy
Every task MUST include agent-executed QA scenarios.
Evidence saved to `.sisyphus/evidence/task-{N}-{scenario-slug}.{ext}`.

- **Backend API**: Use Bash (pytest, python3 -c) — 테스트 실행, 직렬화 검증
- **Frontend**: Use Bash (grep) — prop 존재 확인

---

## Execution Strategy

### Parallel Execution Waves

```
Wave 1 (Start Immediately — independent tasks):
├── Task 1: Backend NaN/Inf 필터링 + 회귀 테스트 [quick]
└── Task 3: Frontend connectNulls 추가 [quick]

Wave 2 (After Task 1 — depends on NaN filter):
└── Task 2: MetricsSnapshot Optional + 0→null 변환 + 테스트 [quick]

Wave FINAL (After ALL tasks):
├── Task F1: Plan compliance audit [oracle]
├── Task F2: Code quality review [unspecified-high]
├── Task F3: Real QA [unspecified-high]
└── Task F4: Scope fidelity check [deep]

Critical Path: Task 1 → Task 2 → Final
Parallel Speedup: Task 1 + Task 3 동시 실행
Max Concurrent: 2 (Wave 1)
```

### Dependency Matrix

| Task | Depends On | Blocks |
|------|-----------|--------|
| 1 | — | 2 |
| 2 | 1 | Final |
| 3 | — | Final |
| F1-F4 | 1, 2, 3 | — |

### Agent Dispatch Summary

- **Wave 1**: 2 tasks — T1 → `quick`, T3 → `quick`
- **Wave 2**: 1 task — T2 → `quick`
- **FINAL**: 4 tasks — F1 → `oracle`, F2 → `unspecified-high`, F3 → `unspecified-high`, F4 → `deep`

---

## TODOs

- [x] 1. [Backend] NaN/Infinity 필터링 + 회귀 테스트

  **What to do**:
  1. `backend/services/metrics_collector.py` 상단에 `import math` 추가
  2. `_fetch_prometheus_metric` 메서드에서 `value = float(...)` 호출 후, `round()` 호출 전에 NaN/Inf 체크 추가:
     ```python
     value = float(data["data"]["result"][0]["value"][1])
     if math.isnan(value) or math.isinf(value):
         return metric_name, None
     return metric_name, round(value, 3)
     ```
  3. `backend/tests/test_metrics_collector.py`에 회귀 테스트 추가:
     - Prometheus가 `"NaN"` 문자열을 반환할 때 `_fetch_prometheus_metric`이 `(name, None)`을 반환하는지 검증
     - Prometheus가 `"+Inf"` 문자열을 반환할 때도 동일하게 `(name, None)` 반환 검증
     - Prometheus가 `"-Inf"` 문자열을 반환할 때도 동일하게 검증
  4. `backend/tests/test_metrics.py`에 통합 회귀 테스트 추가:
     - history deque에 NaN이 포함된 VLLMMetrics를 주입한 후 `/api/metrics/history` 호출 시 HTTP 200 반환 확인
     - 응답 body에 `"NaN"` 문자열이 없는지 확인
  5. 기존 테스트 전부 통과 확인: `cd backend && python3 -m pytest tests/ -x -q -m "not integration"`

  **Must NOT do**:
  - `_query_prometheus`나 `_collect` 등 다른 메서드에서 NaN 처리하지 않음 (단일 지점에서 필터링)
  - VLLMMetrics dataclass의 필드 타입을 변경하지 않음
  - NaN 체크를 `round()` 호출 이후에 배치하지 않음

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: 단일 파일 수정 + 테스트 추가. 로직이 명확하고 변경 범위가 작음
  - **Skills**: []
    - 추가 스킬 불필요 (Python 기본 작업)
  - **Skills Evaluated but Omitted**:
    - `playwright`: 브라우저 작업 없음

  **Parallelization**:
  - **Can Run In Parallel**: YES (Task 3과 동시 실행 가능)
  - **Parallel Group**: Wave 1 (with Task 3)
  - **Blocks**: Task 2 (NaN 필터 완료 후 null 직렬화 작업 가능)
  - **Blocked By**: None (즉시 시작 가능)

  **References**:

  **Pattern References** (existing code to follow):
  - `backend/services/metrics_collector.py:234-246` — `_fetch_prometheus_metric` 메서드 전체. NaN 체크를 line 242의 `float()` 호출과 line 243의 `round()` 호출 사이에 삽입해야 함
  - `backend/services/metrics_collector.py:261-273` — `_query_prometheus`의 None 체크 로직. NaN→None 변환 후 이 로직이 자연스럽게 None을 제외함

  **Test References** (testing patterns to follow):
  - `backend/tests/test_metrics_collector.py` — MetricsCollector 관련 기존 테스트 패턴. mock 구성 방식과 fixture 사용법 참고
  - `backend/tests/test_metrics.py` — metrics 라우터 엔드포인트 테스트 패턴. FastAPI TestClient 사용법 참고
  - `backend/tests/conftest.py` — 테스트 fixture 정의. `metrics_collector` mock과 `client` fixture 확인

  **API/Type References**:
  - `backend/services/metrics_collector.py:27-49` — `VLLMMetrics` dataclass 정의. `mean_ttft_ms`, `p99_e2e_latency_ms` 등 latency 필드가 float 기본값 0 사용
  - `backend/services/metrics_collector.py:52-118` — `VLLM_QUERIES_BY_VERSION`. histogram_quantile 쿼리가 NaN을 반환하는 원인

  **WHY Each Reference Matters**:
  - `_fetch_prometheus_metric`은 수정 대상의 정확한 위치. `float()` → NaN 체크 → `round()` 순서가 핵심
  - `_query_prometheus`는 None 처리 로직이 이미 있으므로 NaN→None 변환만으로 기존 흐름에 자연스럽게 통합됨
  - 테스트 파일은 mock 패턴과 fixture를 따라야 기존 테스트와 일관성 유지

  **Acceptance Criteria**:

  - [x] `import math`가 `metrics_collector.py` 상단에 추가됨
  - [x] `_fetch_prometheus_metric`에 `math.isnan(value) or math.isinf(value)` 체크가 `float()` 후 `round()` 전에 위치
  - [x] NaN 필터링 테스트 추가됨 (`test_metrics_collector.py`)
  - [x] History 엔드포인트 500 방지 테스트 추가됨 (`test_metrics.py`)
  - [x] `cd backend && python3 -m pytest tests/ -x -q -m "not integration"` → 0 failures

  **QA Scenarios (MANDATORY)**:

  ```
  Scenario: NaN 값이 None으로 필터링됨
    Tool: Bash (pytest)
    Preconditions: backend/tests/ 디렉토리에 새 테스트가 추가된 상태
    Steps:
      1. `cd /home/user/project/vllm-optimizer/backend && python3 -m pytest tests/test_metrics_collector.py -k "nan" -v`
      2. 테스트가 PASSED로 표시되는지 확인
    Expected Result: 1+ tests PASSED, 0 failures
    Failure Indicators: FAILED 또는 ERROR 메시지
    Evidence: .sisyphus/evidence/task-1-nan-filter-test.txt

  Scenario: NaN 주입 시에도 /history가 200 반환
    Tool: Bash (pytest)
    Preconditions: test_metrics.py에 NaN 주입 통합 테스트가 추가된 상태
    Steps:
      1. `cd /home/user/project/vllm-optimizer/backend && python3 -m pytest tests/test_metrics.py -k "nan" -v`
      2. HTTP 200 반환 및 응답에 "NaN" 문자열 없음 확인
    Expected Result: 1+ tests PASSED, 0 failures
    Failure Indicators: FAILED, status_code != 200, "NaN" in response
    Evidence: .sisyphus/evidence/task-1-history-nan-test.txt

  Scenario: 기존 테스트 전부 통과 (회귀 없음)
    Tool: Bash (pytest)
    Preconditions: Task 1 수정 완료
    Steps:
      1. `cd /home/user/project/vllm-optimizer/backend && python3 -m pytest tests/ -x -q -m "not integration"`
    Expected Result: all passed, 0 failures
    Failure Indicators: 하나라도 FAILED
    Evidence: .sisyphus/evidence/task-1-regression.txt
  ```

  **Commit**: YES (단독 커밋)
  - Message: `fix(metrics): filter NaN/Infinity from Prometheus responses to prevent HTTP 500`
  - Files: `backend/services/metrics_collector.py`, `backend/tests/test_metrics_collector.py`, `backend/tests/test_metrics.py`
  - Pre-commit: `cd backend && python3 -m pytest tests/ -x -q -m "not integration"`

- [x] 2. [Backend] Latency 필드 Optional 변경 + idle 시 0→null 직렬화

  **What to do**:

  > ⚠️ **순서 엄수**: Step A → Step B → Step C. 순서 위반 시 ValidationError 발생!

  **Step A (모델 변경 먼저)**:
  1. `backend/models/load_test.py`에서 `MetricsSnapshot` 클래스의 latency 필드 4개를 Optional로 변경:
     ```python
     from typing import Any, Optional
     # ...
     ttft_mean: Optional[float] = Field(default=None, description="Time to first token (mean) in ms")
     ttft_p99: Optional[float] = Field(default=None, description="Time to first token (P99) in ms")
     latency_mean: Optional[float] = Field(default=None, description="End-to-end latency (mean) in ms")
     latency_p99: Optional[float] = Field(default=None, description="End-to-end latency (P99) in ms")
     ```
  2. 변경 후 바로 검증: `python3 -c "from models.load_test import MetricsSnapshot; s = MetricsSnapshot(timestamp=1.0, ttft_mean=None); print(s.model_dump_json())"`

  **Step B (직렬화 변경)**:
  3. `backend/services/metrics_collector.py`의 `get_history_dict` 메서드에서 latency 4개 필드에 0→None 변환 적용:
     ```python
     "ttft_mean": m.mean_ttft_ms or None,
     "ttft_p99": m.p99_ttft_ms or None,
     "latency_mean": m.mean_e2e_latency_ms or None,
     "latency_p99": m.p99_e2e_latency_ms or None,
     ```
     (Python에서 `0.0 or None` → `None`, `500.0 or None` → `500.0`)

  **Step C (불일치 문서화)**:
  4. `backend/routers/metrics.py`의 `_convert_to_snapshot` 함수 위에 코멘트 추가:
     ```python
     # Known limitation: /latest returns 0.0 for idle latency fields;
     # /history returns null. This is intentional — /latest shows "last known"
     # while /history provides chart-friendly nullable time series.
     ```
  5. 테스트 추가:
     - `MetricsSnapshot(timestamp=1.0, ttft_mean=None)` 생성 시 정상 직렬화 확인
     - `/api/metrics/history`에서 idle VLLMMetrics(latency=0.0)일 때 응답의 latency 필드가 `null`인지 확인

  **Must NOT do**:
  - `_convert_to_snapshot` 함수의 로직을 변경하지 않음 (코멘트만 추가)
  - `VLLMMetrics` dataclass의 필드를 Optional로 변경하지 않음
  - `tps`, `rps`, `kv_cache`, `kv_hit_rate`, `gpu_mem_used`, `gpu_util`, `pods`, `pods_ready` 등 비-latency 필드를 Optional로 변경하지 않음
  - `get_history_dict`에서 비-latency 필드에 `or None` 적용하지 않음

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: 모델 타입 변경 + 직렬화 로직 수정. 패턴이 반복적이고 변경 범위가 제한적
  - **Skills**: []
  - **Skills Evaluated but Omitted**:
    - `playwright`: 브라우저 작업 없음

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Wave 2 (단독)
  - **Blocks**: Final Verification
  - **Blocked By**: Task 1 (NaN 필터가 먼저 적용되어야 테스트 시 NaN 오염 방지)

  **References**:

  **Pattern References**:
  - `backend/models/load_test.py:103-120` — `MetricsSnapshot` 모델 전체. 변경 대상 4개 필드: `ttft_mean`(line 108), `ttft_p99`(line 109), `latency_mean`(line 110), `latency_p99`(line 111)
  - `backend/services/metrics_collector.py:344-370` — `get_history_dict` 메서드. latency 필드 출력 위치: `ttft_mean`(line 349), `ttft_p99`(line 350), `latency_mean`(line 351), `latency_p99`(line 352)

  **API/Type References**:
  - `backend/routers/metrics.py:16-55` — `_convert_to_snapshot` 함수. 코멘트만 추가, 로직 변경 금지. `/latest`와 `/history`의 불일치를 문서화할 위치
  - `backend/routers/metrics.py:75-110` — `/history` 엔드포인트. `MetricsSnapshot` 인스턴스를 생성하는 위치. Optional 필드가 None일 때 `null`로 직렬화됨

  **Test References**:
  - `backend/tests/test_metrics.py` — 기존 metrics 엔드포인트 테스트. 동일한 패턴으로 null 직렬화 테스트 추가

  **WHY Each Reference Matters**:
  - `MetricsSnapshot` 모델이 가장 먼저 변경되어야 함. Pydantic v2에서 `float` 필드에 `None`을 넘기면 `ValidationError` 발생하므로 `Optional[float]`로 변경 필수
  - `get_history_dict`는 `or None` 패턴으로 0→None 변환. Python truthy 특성 활용 (`0.0 or None` → `None`)
  - `_convert_to_snapshot`은 변경하지 않지만 불일치를 문서화해야 향후 혼란 방지

  **Acceptance Criteria**:

  - [x] `MetricsSnapshot`의 `ttft_mean`, `ttft_p99`, `latency_mean`, `latency_p99`가 `Optional[float]` 타입
  - [x] `python3 -c "from models.load_test import MetricsSnapshot; s = MetricsSnapshot(timestamp=1.0, ttft_mean=None); print(s.model_dump_json())"` → `"ttft_mean":null` 포함
  - [x] `get_history_dict`에서 latency 0.0 → None 변환 적용됨
  - [x] `_convert_to_snapshot` 위에 Known limitation 코멘트 있음
  - [x] `cd backend && python3 -m pytest tests/ -x -q -m "not integration"` → 0 failures

  **QA Scenarios (MANDATORY)**:

  ```
  Scenario: MetricsSnapshot이 None latency를 null로 직렬화
    Tool: Bash (python3 -c)
    Preconditions: Step A (모델 변경) 완료
    Steps:
      1. `cd /home/user/project/vllm-optimizer/backend && python3 -c "from models.load_test import MetricsSnapshot; s = MetricsSnapshot(timestamp=1.0, ttft_mean=None, ttft_p99=None, latency_mean=None, latency_p99=None); print(s.model_dump_json())"`
      2. 출력에 `"ttft_mean":null`, `"ttft_p99":null`, `"latency_mean":null`, `"latency_p99":null` 포함 확인
    Expected Result: 4개 latency 필드 모두 `null`로 직렬화, ValidationError 없음
    Failure Indicators: `ValidationError`, `"ttft_mean":0.0`, traceback
    Evidence: .sisyphus/evidence/task-2-optional-serialize.txt

  Scenario: /history에서 idle latency가 null로 반환됨
    Tool: Bash (pytest)
    Preconditions: Step A + Step B 완료, 테스트 추가됨
    Steps:
      1. `cd /home/user/project/vllm-optimizer/backend && python3 -m pytest tests/test_metrics.py -k "null" -v`
      2. idle 상태의 history 응답에서 latency 필드가 null인지 확인
    Expected Result: 1+ tests PASSED
    Failure Indicators: FAILED, latency 값이 0.0
    Evidence: .sisyphus/evidence/task-2-history-null-test.txt

  Scenario: 기존 테스트 전부 통과 (회귀 없음)
    Tool: Bash (pytest)
    Preconditions: Task 2 전체 완료
    Steps:
      1. `cd /home/user/project/vllm-optimizer/backend && python3 -m pytest tests/ -x -q -m "not integration"`
    Expected Result: all passed, 0 failures
    Failure Indicators: 하나라도 FAILED
    Evidence: .sisyphus/evidence/task-2-regression.txt
  ```

  **Commit**: YES (Task 3과 합산)
  - Message: `fix(dashboard): represent idle latency as null and bridge chart gaps with connectNulls`
  - Files: `backend/models/load_test.py`, `backend/services/metrics_collector.py`, `backend/routers/metrics.py`, `backend/tests/test_metrics.py`, `frontend/src/components/Chart.jsx`
  - Pre-commit: `cd backend && python3 -m pytest tests/ -x -q -m "not integration"`

- [x] 3. [Frontend] Chart.jsx에 `connectNulls={true}` 추가

  **What to do**:
  1. `frontend/src/components/Chart.jsx`의 `<Line>` 컴포넌트(line 22)에 `connectNulls={true}` prop 추가:
     ```jsx
     <Line key={l.key} type="monotone" dataKey={l.key} stroke={l.color}
       dot={false} strokeWidth={1.5} name={l.label} connectNulls={true} />
     ```
  2. `frontend/package.json`에서 Recharts 버전 확인 (2.x 이상이면 connectNulls 지원 확인됨)

  **Must NOT do**:
  - `<Line>` 외의 다른 Recharts 컴포넌트(`<Area>`, `<Bar>`, `<Scatter>`)에 prop 추가하지 않음
  - Chart.jsx의 다른 구조(layout, tooltip, axis 등)를 변경하지 않음
  - MonitorPage.jsx의 데이터 매핑 로직을 변경하지 않음

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: 단일 prop 추가. 한 줄 변경
  - **Skills**: []
  - **Skills Evaluated but Omitted**:
    - `playwright`: 실제 브라우저 렌더링 테스트는 Final QA에서 수행
    - `frontend-ui-ux`: UI 디자인 변경이 아닌 기능 prop 추가

  **Parallelization**:
  - **Can Run In Parallel**: YES (Task 1과 동시 실행 가능)
  - **Parallel Group**: Wave 1 (with Task 1)
  - **Blocks**: Final Verification
  - **Blocked By**: None (즉시 시작 가능)

  **References**:

  **Pattern References**:
  - `frontend/src/components/Chart.jsx:21-24` — `<Line>` 컴포넌트 렌더링 위치. `connectNulls={true}`를 기존 props와 같은 줄에 추가

  **API/Type References**:
  - `frontend/package.json` — Recharts 버전 확인. `connectNulls`는 Recharts 2.x에서 안정적 지원

  **External References**:
  - Recharts Line API: `connectNulls` prop은 null/undefined 데이터 포인트 사이를 선으로 연결

  **WHY Each Reference Matters**:
  - Chart.jsx의 `<Line>`이 유일한 수정 지점. `lines.map()` 안에 있으므로 모든 차트의 모든 라인에 자동 적용됨
  - 비-latency 메트릭은 null이 아닌 0을 반환하므로 `connectNulls`가 동작에 영향 없음 (안전)

  **Acceptance Criteria**:

  - [x] `grep -n "connectNulls" frontend/src/components/Chart.jsx` → `connectNulls={true}` 포함
  - [x] Recharts 버전이 2.x 이상

  **QA Scenarios (MANDATORY)**:

  ```
  Scenario: connectNulls prop이 Line 컴포넌트에 존재
    Tool: Bash (grep)
    Preconditions: Chart.jsx 수정 완료
    Steps:
      1. `grep -n "connectNulls" /home/user/project/vllm-optimizer/frontend/src/components/Chart.jsx`
      2. 출력에 `connectNulls={true}` 포함 확인
    Expected Result: 1줄 이상 매칭, `connectNulls={true}` 포함
    Failure Indicators: grep 결과 없음, `connectNulls` 미포함
    Evidence: .sisyphus/evidence/task-3-connect-nulls-grep.txt

  Scenario: Recharts 버전이 connectNulls 지원
    Tool: Bash (grep)
    Preconditions: None
    Steps:
      1. `grep "recharts" /home/user/project/vllm-optimizer/frontend/package.json`
      2. 버전이 "2." 이상인지 확인
    Expected Result: recharts 버전 2.x 이상
    Failure Indicators: 버전 1.x 이하
    Evidence: .sisyphus/evidence/task-3-recharts-version.txt
  ```

  **Commit**: YES (Task 2와 합산)
  - Message: (Task 2 커밋에 포함)
  - Files: `frontend/src/components/Chart.jsx`

---

## Final Verification Wave

> 4 review agents run in PARALLEL. ALL must APPROVE. Rejection → fix → re-run.

- [x] F1. **Plan Compliance Audit** — `oracle`
  Read the plan end-to-end. For each "Must Have": verify implementation exists (read file, run command). For each "Must NOT Have": search codebase for forbidden patterns — reject with file:line if found. Check evidence files exist in .sisyphus/evidence/. Compare deliverables against plan.
  Output: `Must Have [N/N] | Must NOT Have [N/N] | Tasks [N/N] | VERDICT: APPROVE/REJECT`

- [x] F2. **Code Quality Review** — `unspecified-high`
  Run `python3 -m pytest tests/ -x -q -m "not integration"` in backend. Review all changed files for: unused imports, bare except, missing type hints, commented-out code. Check for AI slop: excessive comments, over-abstraction, generic variable names.
  Output: `Tests [N pass/N fail] | Files [N clean/N issues] | VERDICT`

- [x] F3. **Real QA** — `unspecified-high`
  Execute EVERY QA scenario from EVERY task — follow exact steps, capture evidence. Test cross-task integration (NaN filtering + null serialization + connectNulls working together). Save to `.sisyphus/evidence/final-qa/`.
  Output: `Scenarios [N/N pass] | Integration [N/N] | VERDICT`

- [x] F4. **Scope Fidelity Check** — `deep`
  For each task: read "What to do", read actual diff. Verify 1:1 — everything in spec was built, nothing beyond spec was built. Check "Must NOT do" compliance. Flag unaccounted changes.
  Output: `Tasks [N/N compliant] | VERDICT`

---

## Commit Strategy

- **Commit 1** (after Task 1): `fix(metrics): filter NaN/Infinity from Prometheus responses to prevent HTTP 500`
  - Files: `backend/services/metrics_collector.py`, `backend/tests/test_metrics_collector.py`, `backend/tests/test_metrics.py`
  - Pre-commit: `cd backend && python3 -m pytest tests/ -x -q -m "not integration"`

- **Commit 2** (after Task 2 + Task 3): `fix(dashboard): represent idle latency as null and bridge chart gaps with connectNulls`
  - Files: `backend/models/load_test.py`, `backend/services/metrics_collector.py`, `backend/routers/metrics.py`, `backend/tests/test_metrics.py`, `frontend/src/components/Chart.jsx`
  - Pre-commit: `cd backend && python3 -m pytest tests/ -x -q -m "not integration"`

---

## Success Criteria

### Verification Commands
```bash
# 전체 단위 테스트 통과
cd backend && python3 -m pytest tests/ -x -q -m "not integration"
# Expected: all tests passed, 0 failures

# NaN 주입 시 API 500이 아닌 200 반환 (테스트로 검증)
cd backend && python3 -m pytest tests/test_metrics.py -k "nan" -v
# Expected: PASSED

# null 직렬화 검증
cd backend && python3 -c "from models.load_test import MetricsSnapshot; s = MetricsSnapshot(timestamp=1.0, ttft_mean=None); print(s.model_dump_json())"
# Expected: {"timestamp":1.0,...,"ttft_mean":null,...}

# connectNulls 존재 확인
grep -n "connectNulls" frontend/src/components/Chart.jsx
# Expected: connectNulls={true}
```

### Final Checklist
- [x] All "Must Have" present
- [x] All "Must NOT Have" absent
- [x] All tests pass
- [x] NaN → 500 경로가 완전히 차단됨
- [x] idle latency가 null로 표시됨
- [x] 차트 선이 null 구간을 가로질러 연결됨
