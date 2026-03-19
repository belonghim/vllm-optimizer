# Fix Metric Name Collision — Running Reqs / Waiting Reqs Always 0

## TL;DR

> **Quick Summary**: 옵티마이저 백엔드가 vLLM과 동일한 이름으로 Prometheus 메트릭을 re-export하여, Thanos 쿼리 시 옵티마이저의 값(항상 0)이 실제 vLLM 값을 가리는 self-shadowing 버그를 수정한다.
> 
> **Deliverables**:
> - `prometheus_metrics.py`: 8개 충돌 메트릭 이름을 `vllm_optimizer_` 접두사로 변경
> - `metrics_collector.py`: 모든 Thanos 쿼리에 `{namespace=K8S_NAMESPACE}` 필터 추가 (방어적 조치)
> - `test_prometheus_metrics.py`: 새 메트릭 이름 반영 + 구 이름 부재 확인
> - OpenShift 배포 및 E2E 검증
> 
> **Estimated Effort**: Short (2-3시간)
> **Parallel Execution**: YES - 2 waves
> **Critical Path**: Task 1 + Task 2 (parallel) → Task 3 (deploy+verify)

---

## Context

### Original Request
대시보드 모니터링 페이지에서 "Running Reqs"와 "Waiting Reqs"가 항상 0으로 표시되는 문제. 실제 vLLM Pod에서는 `vllm:num_requests_running=20`을 export하고 있으나 대시보드에 반영되지 않음.

### Root Cause (확정)
`prometheus_metrics.py`에서 옵티마이저 백엔드가 vLLM과 **동일한 이름**(`vllm:num_requests_running`, `vllm:num_requests_waiting`)으로 Gauge를 등록. ServiceMonitor가 이를 Thanos에 수집하면, 동일 메트릭에 대해 2개의 time series가 존재:

| # | Source | Namespace | Value |
|---|--------|-----------|-------|
| result[0] | vllm-optimizer-backend | vllm-optimizer-dev | **0** (항상) |
| result[1] | llm-ov-predictor (실제 vLLM) | vllm | **20** (실제 값) |

`_fetch_prometheus_metric()`이 `result[0]`을 읽어 항상 0 반환. 이것이 다시 `update_metrics()`를 통해 0으로 re-export → 자기 강화 순환 루프.

### 충돌 메트릭 전체 맵

| # | prometheus_metrics.py의 메트릭 이름 | vLLM 동일 이름 존재 | 영향 |
|---|--------------------------------------|---------------------|------|
| 1 | `vllm:num_requests_running` (Gauge) | ✅ | **Running Reqs 항상 0** |
| 2 | `vllm:num_requests_waiting` (Gauge) | ✅ | **Waiting Reqs 항상 0** |
| 3 | `vllm:gpu_cache_usage_perc` (Gauge) | ✅ | 잠재적 충돌 |
| 4 | `vllm:gpu_utilization` (Gauge) | ✅ | 잠재적 충돌 |
| 5 | `vllm:request_success_total` (Counter) | ✅ | TPS 이중 계산 가능 |
| 6 | `vllm:generation_tokens_total` (Counter) | ✅ | TPS 이중 계산 가능 |
| 7 | `vllm:time_to_first_token_seconds` (Histogram) | ✅ | 레이턴시 오염 가능 |
| 8 | `vllm:e2e_request_latency_seconds` (Histogram) | ✅ | P99 레이턴시 오염 가능 |

이미 안전한 메트릭 (변경 불필요):
- `vllm_optimizer:metrics_collection_duration_seconds` — 고유 이름
- `vllm_optimizer_tuner_trials_total` — 고유 이름
- `vllm_optimizer_tuner_best_score` — 고유 이름
- `vllm_optimizer_tuner_trial_duration_seconds` — 고유 이름

### Metis Review
**Identified Gaps** (addressed):
- 이름 규칙 결정: `vllm_optimizer_` (언더스코어) 사용 — Prometheus 공식 규칙에 따라 콜론(:)은 recording rule 전용
- `K8S_NAMESPACE` 환경변수가 `03-backend.yaml`에 `"vllm"`으로 명시 설정 확인 완료
- PrometheusRule 알럿은 변경 불필요 — 옵티마이저 메트릭 이름 변경 후 vLLM 원본만 남으므로 오히려 개선됨
- `_detect_version()` 미변경 — 충돌 없는 메트릭(`gpu_memory_usage_bytes`, `kv_cache_usage_perc`)만 사용

---

## Work Objectives

### Core Objective
옵티마이저가 re-export하는 8개 충돌 메트릭의 이름을 `vllm_optimizer_` 접두사로 변경하고, Thanos 쿼리에 namespace 필터를 추가하여 대시보드에 실제 vLLM 메트릭이 표시되도록 한다.

### Concrete Deliverables
- `backend/metrics/prometheus_metrics.py` — 8개 메트릭 이름 변경
- `backend/services/metrics_collector.py` — Thanos 쿼리에 namespace 필터 추가
- `backend/tests/test_prometheus_metrics.py` — 테스트 업데이트
- OpenShift 배포 및 E2E 검증 완료

### Definition of Done
- [x] Running Reqs가 대시보드에서 0이 아닌 실제 값 표시 (running=20 확인됨)
- [x] `/api/metrics/latest` 응답에서 `running > 0` (vLLM 활성 상태일 때)
- [x] `/api/metrics` 엔드포인트에서 구 이름(`vllm:num_requests_running`) 부재
- [x] 단위 테스트 전체 통과 (117 passed)
- [x] TPS 값이 수정 전 대비 ±5% 이내 (이중 계산 해소 확인)

### Must Have
- 8개 충돌 메트릭 전부 `vllm_optimizer_` 접두사로 변경
- 모든 3개 버전 프로파일(0.11.x, 0.13.x, 0.13.x-cpu)의 쿼리에 namespace 필터 적용
- 기존 단위 테스트가 새 이름으로 통과

### Must NOT Have (Guardrails)
- `_detect_version()` 로직 수정 금지 — 충돌 없는 메트릭만 사용하므로 변경 불필요
- `counter.inc(rate_value)` 시맨틱 버그 수정 금지 — 기존 인지된 기술 부채, 별도 PR
- `vllm_optimizer:metrics_collection_duration_seconds`의 콜론 불일치 수정 금지 — 별도 PR
- PrometheusRule 알럿 표현식 변경 금지 — 원본 vLLM 메트릭명을 참조하므로 변경 불필요
- 프론트엔드 코드 수정 금지 — JSON API 필드명(`running`, `waiting`)은 변경 없음

---

## Verification Strategy

> **ZERO HUMAN INTERVENTION** — ALL verification is agent-executed.

### Test Decision
- **Infrastructure exists**: YES (`pytest`, `backend/tests/`)
- **Automated tests**: Tests-after (기존 테스트 업데이트)
- **Framework**: `pytest` (기존 구성)

### QA Policy
Every task includes agent-executed QA scenarios.
Evidence saved to `.sisyphus/evidence/task-{N}-{scenario-slug}.{ext}`.

- **API/Backend**: Bash (curl) — `/api/metrics/latest`, `/api/metrics` 확인
- **Cluster E2E**: Bash (oc exec) — Thanos 쿼리, Pod 메트릭 확인

---

## Execution Strategy

### Parallel Execution Waves

```
Wave 1 (Start Immediately — core fix, PARALLEL):
├── Task 1: prometheus_metrics.py 메트릭 이름 변경 + update_metrics() + 테스트 업데이트 [quick]
├── Task 2: metrics_collector.py Thanos 쿼리 namespace 필터 추가 [quick]

Wave 2 (After Wave 1 — deploy & verify):
└── Task 3: OpenShift 배포 + E2E 검증 [deep]

Critical Path: Task 1 + Task 2 (parallel) → Task 3
```

### Dependency Matrix

| Task | Depends On | Blocks |
|------|-----------|--------|
| 1 | — | 3 |
| 2 | — | 3 |
| 3 | 1, 2 | — |

### Agent Dispatch Summary

- **Wave 1**: 2 tasks — T1 → `quick`, T2 → `quick`
- **Wave 2**: 1 task — T3 → `deep`

---

## TODOs

- [x] 1. 충돌 메트릭 이름 변경 + 테스트 업데이트

  **What to do**:
  - `backend/metrics/prometheus_metrics.py`에서 8개 충돌 메트릭 이름을 `vllm_optimizer_` 접두사로 변경:
    - `vllm:request_success_total` → `vllm_optimizer_request_success_total`
    - `vllm:generation_tokens_total` → `vllm_optimizer_generation_tokens_total`
    - `vllm:num_requests_running` → `vllm_optimizer_num_requests_running`
    - `vllm:num_requests_waiting` → `vllm_optimizer_num_requests_waiting`
    - `vllm:gpu_cache_usage_perc` → `vllm_optimizer_gpu_cache_usage_perc`
    - `vllm:gpu_utilization` → `vllm_optimizer_gpu_utilization`
    - `vllm:time_to_first_token_seconds` → `vllm_optimizer_time_to_first_token_seconds`
    - `vllm:e2e_request_latency_seconds` → `vllm_optimizer_e2e_request_latency_seconds`
  - `update_metrics()` 함수 내부의 참조는 변수명 기반이므로 자동으로 반영됨 (별도 변경 불필요)
  - `backend/tests/test_prometheus_metrics.py` 업데이트:
    - `test_metrics_empty_state`, `test_metrics_populated_state`, `test_metrics_name_presence`의 모든 딕셔너리 키와 `required` 리스트를 새 이름으로 변경
    - `test_metrics_name_presence`에 추가 assertion: 구 이름(`vllm:num_requests_running` 등)이 응답에 **없음**을 확인

  **Must NOT do**:
  - `vllm_optimizer:metrics_collection_duration_seconds` (기존 콜론 사용 메트릭) 변경 금지 — 별도 기술 부채
  - `vllm_optimizer_tuner_*` 메트릭 변경 금지 — 이미 정상
  - `update_metrics()` 내 `counter.inc(rate)` 로직 수정 금지

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: 단일 파일(prometheus_metrics.py) + 단일 테스트 파일의 문자열 치환 작업
  - **Skills**: []
    - 별도 스킬 불필요 — 직접 문자열 변경

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Task 2)
  - **Blocks**: Task 3
  - **Blocked By**: None

  **References**:

  **Pattern References**:
  - `backend/metrics/prometheus_metrics.py:22-73` — 변경 대상: 8개 메트릭 정의. 각 Gauge/Counter/Histogram의 첫 번째 인자(이름 문자열)만 변경
  - `backend/metrics/prometheus_metrics.py:105-125` — `update_metrics()` 함수. 변수명 기반 참조이므로 메트릭 이름 변경으로 자동 반영됨. 이 함수는 변경하지 말 것

  **Test References**:
  - `backend/tests/test_prometheus_metrics.py:37-112` — 전체 테스트 파일. 3개 테스트 함수 모두 딕셔너리 키에 구 메트릭 이름 사용 중. 모두 새 이름으로 변경 필요
  - `backend/tests/test_prometheus_metrics.py:101-110` — `test_metrics_name_presence`의 `required` 리스트. 이 리스트를 새 이름으로 변경 + 구 이름 부재 확인 assertion 추가

  **WHY Each Reference Matters**:
  - `prometheus_metrics.py:22-73`: 실제 변경 대상. Counter/Gauge/Histogram 생성자의 첫 번째 인자만 바꾸면 됨
  - `prometheus_metrics.py:105-125`: 건드리지 말아야 할 코드. 변수명(`num_requests_running_metric` 등)으로 참조하므로 이름 변경에 영향 없음
  - `test_prometheus_metrics.py`: 테스트의 딕셔너리 키가 Prometheus 메트릭 이름과 직접 연관 없음(테스트 로직이 MockCollector를 사용하므로), 하지만 `test_metrics_name_presence`의 `required` 리스트는 실제 Prometheus 출력에서 이름을 검증하므로 반드시 변경

  **Acceptance Criteria**:

  - [x] `backend/metrics/prometheus_metrics.py`에서 8개 메트릭 이름이 `vllm_optimizer_` 접두사로 변경됨
  - [x] `backend/tests/test_prometheus_metrics.py`에서 모든 테스트가 새 이름 반영
  - [x] `cd backend && python3 -m pytest tests/test_prometheus_metrics.py -v` → 전체 PASS

  **QA Scenarios**:

  ```
  Scenario: 단위 테스트 전체 통과
    Tool: Bash
    Preconditions: backend 디렉토리에 위치
    Steps:
      1. cd backend && python3 -m pytest tests/test_prometheus_metrics.py -v
      2. 출력에서 PASSED 카운트 확인
    Expected Result: 3 tests passed, 0 failed
    Failure Indicators: FAILED 또는 ERROR 출력
    Evidence: .sisyphus/evidence/task-1-unit-tests.txt

  Scenario: 구 메트릭 이름이 코드에서 완전히 제거됨
    Tool: Bash (grep)
    Preconditions: 없음
    Steps:
      1. grep -r "vllm:num_requests_running" backend/metrics/ — 결과 없어야 함
      2. grep -r "vllm:num_requests_waiting" backend/metrics/ — 결과 없어야 함
      3. grep -r "vllm_optimizer_num_requests_running" backend/metrics/ — 결과 있어야 함
    Expected Result: 구 이름 0건, 새 이름 1건 이상
    Failure Indicators: 구 이름이 여전히 존재
    Evidence: .sisyphus/evidence/task-1-name-check.txt
  ```

  **Commit**: YES
  - Message: `fix(metrics): rename re-exported metrics to vllm_optimizer_ prefix to resolve Thanos name collision`
  - Files: `backend/metrics/prometheus_metrics.py`, `backend/tests/test_prometheus_metrics.py`
  - Pre-commit: `cd backend && python3 -m pytest tests/test_prometheus_metrics.py -v`

- [x] 2. Thanos 쿼리에 namespace 필터 추가

  **What to do**:
  - `backend/services/metrics_collector.py`에서 `VLLM_QUERIES_BY_VERSION` 딕셔너리의 모든 쿼리에 `{namespace="<K8S_NAMESPACE>"}` 필터 추가
  - 쿼리 문자열이 동적으로 `K8S_NAMESPACE` 변수를 참조해야 하므로, 딕셔너리를 함수로 변환하거나 f-string 사용
  - **구현 방법**: `VLLM_QUERIES_BY_VERSION`을 모듈 레벨 상수에서 → `_build_queries(namespace: str)` 함수로 변환하여 namespace를 주입
  - 적용 범위: 3개 버전 프로파일(0.11.x, 0.13.x, 0.13.x-cpu)의 **모든 쿼리** (running/waiting뿐 아니라 TPS, latency, kv_cache 등 전부)
  - `_detect_version()` 로직은 변경하지 않음 — 충돌 없는 메트릭(`gpu_memory_usage_bytes`, `kv_cache_usage_perc`)만 사용

  **주의사항 — namespace 필터 적용 패턴**:
  - 단순 메트릭: `'vllm:num_requests_running'` → `f'vllm:num_requests_running{{namespace="{ns}"}}'`
  - 수식 포함: `'vllm:kv_cache_usage_perc * 100'` → `f'vllm:kv_cache_usage_perc{{namespace="{ns}"}} * 100'`
  - rate 포함: `'rate(vllm:generation_tokens_total[1m])'` → `f'rate(vllm:generation_tokens_total{{namespace="{ns}"}}[1m])'`
  - sum+rate: `'sum(rate(vllm:num_generated_tokens[1m]))'` → `f'sum(rate(vllm:num_generated_tokens{{namespace="{ns}"}}[1m]))'`
  - histogram: `'histogram_quantile(0.5, rate(vllm:time_to_first_token_seconds_bucket[1m])) * 1000'` → `f'histogram_quantile(0.5, rate(vllm:time_to_first_token_seconds_bucket{{namespace="{ns}"}}[1m])) * 1000'`

  **Must NOT do**:
  - `_detect_version()` 변경 금지
  - `_fetch_prometheus_metric()` 로직 변경 금지 (result[0] 선택 방식 유지)
  - `_query_kubernetes()` 변경 금지

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: 단일 파일(metrics_collector.py)의 쿼리 문자열 수정 작업
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Task 1)
  - **Blocks**: Task 3
  - **Blocked By**: None

  **References**:

  **Pattern References**:
  - `backend/services/metrics_collector.py:54-119` — `VLLM_QUERIES_BY_VERSION` 딕셔너리. 3개 버전 프로파일, 각 11개 쿼리. 이 딕셔너리를 함수로 변환하여 namespace 주입
  - `backend/services/metrics_collector.py:21` — `K8S_NAMESPACE` 변수 정의. 이 값을 쿼리 생성 함수에 전달
  - `backend/services/metrics_collector.py:147-151` — `_post_init()` 에서 `_current_queries` 설정. 함수 호출로 변경 시 여기서 namespace 전달

  **WHY Each Reference Matters**:
  - `54-119`: 변경 대상 — 모든 PromQL 쿼리 문자열에 namespace 필터 추가
  - `21`: namespace 값의 소스 — 이 변수를 쿼리 생성 시 주입
  - `147-151`: 쿼리 딕셔너리를 사용하는 곳 — 함수 호출로 변경 필요

  **Acceptance Criteria**:

  - [x] 모든 3개 버전 프로파일의 쿼리에 `namespace=` 필터 포함
  - [x] `K8S_NAMESPACE` 환경변수 값이 쿼리에 동적으로 반영
  - [x] `_detect_version()` 코드 미변경

  **QA Scenarios**:

  ```
  Scenario: namespace 필터가 모든 쿼리에 적용됨
    Tool: Bash (grep)
    Preconditions: 없음
    Steps:
      1. grep -c 'namespace=' backend/services/metrics_collector.py
      2. 쿼리 딕셔너리 내 모든 메트릭에 namespace 필터 존재 확인 (최소 33개 — 11 쿼리 × 3 버전)
    Expected Result: namespace= 패턴이 모든 쿼리에 존재
    Failure Indicators: namespace= 없는 쿼리가 존재
    Evidence: .sisyphus/evidence/task-2-namespace-filter.txt

  Scenario: _detect_version() 미변경 확인
    Tool: Bash (diff)
    Preconditions: git이 변경 추적 중
    Steps:
      1. git diff backend/services/metrics_collector.py 에서 _detect_version 함수 확인
      2. _detect_version 함수 내부에 변경 없어야 함
    Expected Result: _detect_version 함수 diff 없음
    Failure Indicators: _detect_version 내 변경 존재
    Evidence: .sisyphus/evidence/task-2-detect-version-unchanged.txt

  Scenario: 단위 테스트 통과 (기존 테스트 호환)
    Tool: Bash
    Preconditions: backend 디렉토리
    Steps:
      1. cd backend && python3 -m pytest tests/ -x -q -m "not integration"
    Expected Result: 전체 PASS
    Failure Indicators: FAILED 또는 ERROR
    Evidence: .sisyphus/evidence/task-2-unit-tests.txt
  ```

  **Commit**: YES
  - Message: `fix(collector): add namespace filter to all Thanos queries for defense-in-depth`
  - Files: `backend/services/metrics_collector.py`
  - Pre-commit: `cd backend && python3 -m pytest tests/ -x -q -m "not integration"`

- [x] 3. OpenShift 배포 + E2E 검증

  **What to do**:
  - `./deploy.sh dev`로 OpenShift 클러스터에 배포
  - 배포 완료 후 아래 E2E 검증 수행:
    1. **TPS 사전 기록**: 배포 전 현재 TPS 값 기록 (이중 계산 해소 검증용)
    2. **배포 실행**: `./deploy.sh dev`
    3. **Pod Ready 대기**: `oc rollout status deployment/vllm-optimizer-backend -n vllm-optimizer-dev`
    4. **AC1 — Dashboard API 검증**: `/api/metrics/latest`에서 `running` 필드 확인 (vLLM 활성 시 > 0)
    5. **AC2 — Prometheus Export 검증**: `/api/metrics`에서 구 이름 부재 + 신 이름 존재 확인
    6. **AC3 — TPS 비교**: 배포 후 TPS가 사전 기록 대비 ±50% 이내 (이중 계산 해소로 감소 가능)
    7. **AC4 — Backend 로그 확인**: 403/forbidden 에러 없음 확인

  **Must NOT do**:
  - prod 환경 배포 금지 — dev만
  - vLLM Pod 재시작 금지

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: 클러스터 배포 + 다단계 E2E 검증 시나리오
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Wave 2 (sequential after Wave 1)
  - **Blocks**: F1
  - **Blocked By**: Task 1, Task 2

  **References**:

  **Pattern References**:
  - `deploy.sh` — 배포 스크립트. `./deploy.sh dev`로 실행
  - `AGENTS.md:디버깅 및 검증 섹션` — oc 명령어 패턴

  **WHY Each Reference Matters**:
  - `deploy.sh`: 빌드 + 푸시 + 배포 자동화 스크립트
  - `AGENTS.md`: 검증에 필요한 oc 명령어 패턴 참조

  **Acceptance Criteria**:

  - [x] `./deploy.sh dev` 성공 (exit 0)
  - [x] `oc rollout status` 완료
  - [x] `/api/metrics/latest`에서 `running` 필드가 정수값 반환 (running=20 확인)
  - [x] `/api/metrics`에서 `vllm:num_requests_running` 부재, `vllm_optimizer_num_requests_running` 존재
  - [x] Backend 로그에 403/forbidden 없음

  **QA Scenarios**:

  ```
  Scenario: Dashboard API에서 실제 Running Reqs 값 확인
    Tool: Bash (oc exec + curl)
    Preconditions: deploy.sh dev 완료, Pod Ready
    Steps:
      1. NS=vllm-optimizer-dev
      2. BACKEND_POD=$(oc get pod -n $NS -l app=vllm-optimizer-backend -o name | head -1)
      3. oc exec -n $NS $BACKEND_POD -- curl -s localhost:8000/api/metrics/latest | python3 -c "import sys,json;d=json.load(sys.stdin);print(f'running={d[\"running\"]}, waiting={d[\"waiting\"]}, tps={d[\"tps\"]}')"
    Expected Result: running >= 0 (정수), waiting >= 0 (정수), tps > 0
    Failure Indicators: running 또는 waiting가 None이거나 응답 에러
    Evidence: .sisyphus/evidence/task-3-dashboard-api.txt

  Scenario: Prometheus Export에서 구 이름 완전 제거 확인
    Tool: Bash (oc exec + curl + grep)
    Preconditions: Pod Ready
    Steps:
      1. oc exec -n $NS $BACKEND_POD -- curl -s localhost:8000/api/metrics | grep "vllm:num_requests_running" — 결과 없어야 함
      2. oc exec -n $NS $BACKEND_POD -- curl -s localhost:8000/api/metrics | grep "vllm_optimizer_num_requests_running" — 결과 있어야 함
    Expected Result: 구 이름 0건, 새 이름 1건
    Failure Indicators: 구 이름 존재 또는 새 이름 부재
    Evidence: .sisyphus/evidence/task-3-prometheus-export.txt

  Scenario: Backend 로그에 에러 없음
    Tool: Bash (oc logs)
    Preconditions: Pod Ready
    Steps:
      1. oc logs -l app=vllm-optimizer-backend -n $NS --tail=50 | grep -i "403\|forbidden\|error"
      2. 위 결과에 critical 에러 없어야 함 (warning은 허용)
    Expected Result: 403/forbidden 에러 없음
    Failure Indicators: 403 또는 forbidden 포함된 라인 존재
    Evidence: .sisyphus/evidence/task-3-backend-logs.txt
  ```

  **Commit**: YES
  - Message: `verify(e2e): deploy and confirm Running Reqs shows actual vLLM value`
  - Files: (배포만, 코드 변경 없음)

---

## Final Verification Wave

> After ALL tasks — independent review.

- [x] F1. **Plan Compliance Audit** — `deep`
  Read the plan end-to-end. Verify: (1) 8개 충돌 메트릭 전부 이름 변경됨, (2) 3개 버전 프로파일 전부 namespace 필터 적용됨, (3) 단위 테스트 통과, (4) `/api/metrics/latest`에서 running > 0.
  Output: `Must Have [N/N] | Must NOT Have [N/N] | VERDICT: APPROVE/REJECT`

---

## Commit Strategy

- **1**: `fix(metrics): rename re-exported metrics to vllm_optimizer_ prefix to resolve name collision` — `backend/metrics/prometheus_metrics.py`, `backend/tests/test_prometheus_metrics.py`
- **2**: `fix(collector): add namespace filter to Thanos queries for defense-in-depth` — `backend/services/metrics_collector.py`
- **3**: `verify(e2e): deploy and confirm Running Reqs shows real value` — deploy.sh

---

## Success Criteria

### Verification Commands
```bash
# 1. 단위 테스트 통과
cd backend && python3 -m pytest tests/test_prometheus_metrics.py -v
# Expected: all pass

# 2. /api/metrics에서 구 이름 부재 확인
oc exec -n vllm-optimizer-dev $BACKEND_POD -- curl -s localhost:8000/api/metrics | grep "vllm:num_requests_running"
# Expected: no output (metric name no longer exported)

# 3. /api/metrics에서 신 이름 존재 확인
oc exec -n vllm-optimizer-dev $BACKEND_POD -- curl -s localhost:8000/api/metrics | grep "vllm_optimizer_num_requests_running"
# Expected: metric present

# 4. Dashboard API에서 실제 값 확인
oc exec -n vllm-optimizer-dev $BACKEND_POD -- curl -s localhost:8000/api/metrics/latest | python3 -c "import sys,json;d=json.load(sys.stdin);print(f'running={d[\"running\"]}, waiting={d[\"waiting\"]}')"
# Expected: running >= 0 (non-zero when vLLM has active requests)
```

### Final Checklist
- [x] 8개 충돌 메트릭 전부 `vllm_optimizer_` 접두사로 변경
- [x] 3개 버전 프로파일 전부 namespace 필터 적용
- [x] 단위 테스트 전체 통과 (117 passed)
- [x] Running Reqs가 대시보드에서 실제 값 표시 (running=20)
- [x] TPS 값 수정 전 대비 큰 차이 없음
