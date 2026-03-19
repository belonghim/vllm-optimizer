# Auto Tuner 포괄적 개선

## TL;DR

> **Quick Summary**: vLLM Auto Parameter Tuner의 미완성 stub 수정, Bayesian 최적화 알고리즘 고도화(Multi-objective Pareto, MedianPruner, SQLite 영속성, Warm-start), 검색 공간 확장(3개 신규 파라미터), 안전성 강화(ConfigMap 롤백), 실시간 UX(SSE 스트리밍 + 수렴/Pareto 차트), 운영성(Prometheus 메트릭) 전면 개선
>
> **Deliverables**:
> - 2개 stub 엔드포인트 실제 구현 (/importance, /apply-best)
> - Pareto 모드 + 기존 단일목적 모드 동시 지원
> - MedianPruner 2-phase 평가 기반 조기 중단
> - SQLite 기반 Study 영속성 + Warm-start (enqueue_trial)
> - max_num_batched_tokens, block_size, swap_space(옵션) 검색 공간 확장
> - ConfigMap 메모리 스냅샷 + 자동 롤백
> - SSE 스트리밍 Trial 실시간 전달 + 프론트엔드 EventSource
> - 수렴 그래프 + Pareto front 시각화
> - 3개 Prometheus 튜너 메트릭
>
> **Estimated Effort**: Large
> **Parallel Execution**: YES - 5 waves + final verification
> **Critical Path**: T1 → T5 → T8 → T11 → T12 → T14/T15

---

## Context

### Original Request
"자동 파라미터 튜닝 기능을 개선하고 싶어. 추천해줘."

### Interview Summary
**Key Discussions**:
- 6개 카테고리 전체 개선 선택 (Stub 완성, 알고리즘, 검색 공간, 안전성, UX, 운영성)
- Multi-objective: 기존 단일목적(tps/latency/balanced) + "pareto" 모드 추가
- Study 영속성: SQLite (가볍게, 초기화 가능하도록)
- 추가 파라미터: max_num_batched_tokens, swap_space(플래그), block_size
- Rollback: 메모리 스냅샷 (ConfigMap 원본 저장 → 실패 시 자동 복원)
- 테스트: Tests-after (기존 test_tuner.py 확장)
- SSE: Trial 진행 실시간 스트리밍 도입

**Research Findings**:
- auto_tuner.py: get_importance() 이미 구현됨(303-309행), 라우터가 무시 중
- auto_tuner.py: _apply_params() 완전 작동 중, 라우터가 미연결
- TunerPage.jsx: eval_requests 미노출, applyBest() 무조건 성공 알림 버그
- MedianPruner와 multi-objective는 Optuna에서 상호 배타적
- WarmStartSampler는 Optuna 3.6.0+ 필요 → study.enqueue_trial() 사용
- max_num_batched_tokens >= max_num_seqs 제약조건 필수
- swap_space는 CPU/OpenVINO 환경에서 무의미

### Metis Review
**Identified Gaps** (addressed):
- test_tuner_apply_best_response 테스트가 success:False 검증 → stub 수정 전 테스트 업데이트 포함
- _suggest_params 빈 리스트 크래시 잠재 버그 → T5에서 수정
- MedianPruner black-box _evaluate() 비호환 → 2-phase 평가 방식으로 해결
- get_param_importances() multi-obj RuntimeError → single-obj guard 추가
- SQLite check_same_thread=False 필요 → T9에서 적용
- tuning_id 미사용 → 단일 세션 SSE로 단순화
- 프론트엔드 max_model_len 범위 설정 미노출 → T4에서 추가

---

## Work Objectives

### Core Objective
vLLM Auto Tuner를 미완성 프로토타입에서 프로덕션 품질의 자동 최적화 시스템으로 고도화한다.

### Concrete Deliverables
- `backend/services/auto_tuner.py` — 핵심 로직 전면 개선
- `backend/routers/tuner.py` — stub 제거, SSE 엔드포인트 추가
- `backend/models/load_test.py` — 확장된 모델 필드
- `backend/metrics/prometheus_metrics.py` — 튜너 메트릭 추가
- `backend/tests/test_tuner.py` — 새 기능 테스트 추가
- `frontend/src/pages/TunerPage.jsx` — SSE + 차트 + 설정 확장

### Definition of Done
- [x] `pytest backend/tests/test_tuner.py -v` 전체 PASS (48/48)
- [x] `/api/tuner/importance` 실제 FAnova 값 반환 (5+ trials 후)
- [x] `/api/tuner/apply-best` ConfigMap 패치 성공
- [x] `/api/tuner/start` with `objective="pareto"` 성공
- [x] `/api/tuner/stream` SSE 이벤트 수신 확인
- [x] `curl localhost:8000/metrics | grep tuner` 3개 이상 메트릭

### Must Have
- 기존 단일목적 모드 (tps/latency/balanced) 하위 호환성 유지
- 기존 API 응답 스키마 유지 (신규 필드만 추가, 기존 필드 삭제/변경 금지)
- 모든 K8s API 호출 asyncio.to_thread() 래핑
- ConfigMap 롤백 자동 실행 (_wait_for_ready 타임아웃 시)

### Must NOT Have (Guardrails)
- load_engine.py 수정 금지 — 범위 외
- metrics_collector.py 수정 금지 — 범위 외
- LoadTestPage.jsx 수정 금지 — 범위 외
- PVC 추가 금지 — SQLite는 ephemeral, 환경변수로 설정
- OpenShift YAML 수정 금지 (PrometheusRule 등) — prometheus_metrics.py만 수정
- 신규 차트 컴포넌트 생성 금지 — 기존 ScatterChart/Recharts 활용
- WarmStartSampler 사용 금지 — study.enqueue_trial() 사용
- swap_space 기본 활성화 금지 — include_swap_space: bool = False 플래그 필수

---

## Verification Strategy (MANDATORY)

> **ZERO HUMAN INTERVENTION** — ALL verification is agent-executed. No exceptions.

### Test Decision
- **Infrastructure exists**: YES (pytest, conftest.py, 292줄 test_tuner.py)
- **Automated tests**: Tests-after
- **Framework**: pytest + pytest-asyncio
- **Pattern**: 기존 test_tuner.py 패턴 따라 확장

### QA Policy
Every task MUST include agent-executed QA scenarios.
Evidence saved to `.sisyphus/evidence/task-{N}-{scenario-slug}.{ext}`.

- **Backend API**: Use Bash (curl) — Send requests, assert status + response fields
- **Backend Logic**: Use Bash (pytest) — Run specific test cases
- **Frontend**: Use Playwright (playwright skill) — Navigate, interact, assert DOM, screenshot

---

## Execution Strategy

### Parallel Execution Waves

```
Wave 1 (Start Immediately — foundation, zero file overlap):
├── Task 1: Expand Pydantic models [quick]
├── Task 2: Fix stubs: /importance + /apply-best [quick]
├── Task 3: Prometheus tuner metric definitions [quick]
└── Task 4: Frontend bug fixes + config form expansion [visual-engineering]

Wave 2 (After Wave 1 — auto_tuner.py core, non-overlapping sections):
├── Task 5: Search space expansion + constraints (depends: 1) [deep]
├── Task 6: Eval configuration + warmup (depends: 1) [unspecified-high]
└── Task 7: SSE broadcast infrastructure (depends: none) [quick]

Wave 3 (After Wave 2 — safety + persistence + SSE endpoint):
├── Task 8: ConfigMap snapshot + rollback (depends: 5) [deep]
├── Task 9: SQLite persistence + warm-start (depends: 6) [unspecified-high]
└── Task 10: /api/tuner/stream SSE endpoint (depends: 7) [quick]

Wave 4 (After Wave 3 — algorithm enhancement):
├── Task 11: MedianPruner + two-phase eval (depends: 6, 8) [deep]
└── Task 12: Pareto mode + NSGAIISampler (depends: 9) [deep]

Wave 5 (After Wave 4 — frontend + metrics + tests):
├── Task 13: Frontend: SSE + convergence chart + Pareto highlight (depends: 10, 11, 12) [visual-engineering]
├── Task 14: Prometheus metric emission (depends: 3, 12) [quick]
└── Task 15: Comprehensive test additions (depends: 11, 12) [unspecified-high]

Wave FINAL (After ALL tasks — independent review, 4 parallel):
├── Task F1: Plan compliance audit (oracle)
├── Task F2: Code quality review (unspecified-high)
├── Task F3: Real manual QA (unspecified-high)
└── Task F4: Scope fidelity check (deep)

Critical Path: T1 → T5 → T8 → T11 → T12 → T13/T14/T15 → F1-F4
Parallel Speedup: ~60% faster than sequential
Max Concurrent: 4 (Wave 1)
```

### Dependency Matrix

| Task | Blocked By | Blocks | Wave |
|------|-----------|--------|------|
| 1 | — | 5, 6 | 1 |
| 2 | — | — | 1 |
| 3 | — | 14 | 1 |
| 4 | — | 13 | 1 |
| 5 | 1 | 8 | 2 |
| 6 | 1 | 9, 11 | 2 |
| 7 | — | 10 | 2 |
| 8 | 5 | 11 | 3 |
| 9 | 6 | 12 | 3 |
| 10 | 7 | 13 | 3 |
| 11 | 6, 8 | 13, 15 | 4 |
| 12 | 9 | 13, 14, 15 | 4 |
| 13 | 10, 11, 12 | — | 5 |
| 14 | 3, 12 | — | 5 |
| 15 | 11, 12 | — | 5 |

### Agent Dispatch Summary

- **Wave 1**: **4** — T1 → `quick`, T2 → `quick`, T3 → `quick`, T4 → `visual-engineering`
- **Wave 2**: **3** — T5 → `deep`, T6 → `unspecified-high`, T7 → `quick`
- **Wave 3**: **3** — T8 → `deep`, T9 → `unspecified-high`, T10 → `quick`
- **Wave 4**: **2** — T11 → `deep`, T12 → `deep`
- **Wave 5**: **3** — T13 → `visual-engineering`, T14 → `quick`, T15 → `unspecified-high`
- **FINAL**: **4** — F1 → `oracle`, F2 → `unspecified-high`, F3 → `unspecified-high`, F4 → `deep`

---

## TODOs

- [x] 1. Pydantic 모델 확장 — 새 필드 일괄 추가

  **What to do**:
  - `backend/models/load_test.py`의 `TuningConfig` 모델에 다음 필드 추가:
    - `max_num_batched_tokens_range: tuple[int, int] = Field(default=(256, 2048))` — 배치 토큰 수 범위
    - `block_size_options: list[int] = Field(default=[8, 16, 32])` — KV cache 블록 크기 옵션
    - `include_swap_space: bool = Field(default=False)` — swap_space 검색 활성화 플래그 (CPU 환경 기본 비활성)
    - `swap_space_range: tuple[float, float] = Field(default=(1.0, 8.0))` — swap_space 범위 (GB)
    - `eval_concurrency: int = Field(default=32, ge=1)` — 평가 부하 테스트 동시 요청 수
    - `eval_rps: int = Field(default=20, ge=0)` — 평가 부하 테스트 RPS
    - `eval_fast_fraction: float = Field(default=0.5, ge=0.1, le=1.0)` — MedianPruner용 빠른 평가 비율
  - `TuningTrial` 모델에 다음 필드 추가:
    - `is_pareto_optimal: bool = Field(default=False)` — Pareto 최적 여부
    - `pruned: bool = Field(default=False)` — MedianPruner에 의해 pruning 되었는지
  - `backend/routers/tuner.py`의 `TuningStartRequest` 모델에 다음 필드 추가:
    - `max_num_batched_tokens_min: int = 256`
    - `max_num_batched_tokens_max: int = 2048`
    - `block_size_options: list[int] = [8, 16, 32]`
    - `include_swap_space: bool = False`
    - `swap_space_min: float = 1.0`
    - `swap_space_max: float = 8.0`
    - `eval_requests: int = 200`
    - `eval_concurrency: int = 32`
    - `eval_rps: int = 20`
  - `TuningStartRequest` → `TuningConfig` 변환 로직(tuner.py:104-111)에 새 필드 매핑 추가
  - `TrialFrontendInfo` 모델에 `is_pareto_optimal: bool = False`, `pruned: bool = False` 추가
  - `TunerStatusFrontendResponse`에 `best_score_history: list[float] = []` 추가 (수렴 그래프용)

  **Must NOT do**:
  - auto_tuner.py 수정 금지 (T5에서 처리)
  - 기존 필드 삭제/이름 변경 금지
  - 기본값 변경 금지

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Pydantic 모델 필드 추가는 단순 반복 작업
  - **Skills**: []
  - **Skills Evaluated but Omitted**:
    - `playwright`: 프론트엔드 작업 아님

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Tasks 2, 3, 4)
  - **Blocks**: Tasks 5, 6
  - **Blocked By**: None

  **References**:

  **Pattern References**:
  - `backend/models/load_test.py:80-91` — 현재 TuningConfig 구조. 여기에 새 필드를 같은 패턴으로 추가
  - `backend/models/load_test.py:94-101` — 현재 TuningTrial 구조. is_pareto_optimal, pruned 추가
  - `backend/routers/tuner.py:48-60` — TuningStartRequest flat 스키마. 새 필드를 같은 flat 패턴으로 추가
  - `backend/routers/tuner.py:84-91` — TrialFrontendInfo. 새 필드 추가 위치
  - `backend/routers/tuner.py:76-81` — TunerStatusFrontendResponse. best_score_history 추가 위치

  **API/Type References**:
  - `backend/routers/tuner.py:104-111` — TuningStartRequest → TuningConfig 변환. 새 필드 매핑 추가 필요

  **WHY Each Reference Matters**:
  - models/load_test.py:80-91 — 기존 필드 패턴(Field + default + description)을 정확히 따라야 함
  - tuner.py:48-60 — 프론트엔드는 flat JSON을 보내므로 nested가 아닌 flat 필드로 추가해야 함
  - tuner.py:104-111 — 여기서 flat request를 nested TuningConfig로 변환하므로 새 필드도 매핑 필수

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: TuningConfig 새 필드 기본값 검증
    Tool: Bash (python)
    Preconditions: Backend 서버 실행 불필요 (단위 검증)
    Steps:
      1. python -c "from backend.models.load_test import TuningConfig; c = TuningConfig(); print(c.max_num_batched_tokens_range, c.block_size_options, c.include_swap_space, c.eval_concurrency, c.eval_rps, c.eval_fast_fraction)"
      2. 출력 확인: (256, 2048) [8, 16, 32] False 32 20 0.5
    Expected Result: 모든 기본값이 명세와 일치
    Failure Indicators: ImportError 또는 기본값 불일치
    Evidence: .sisyphus/evidence/task-1-model-defaults.txt

  Scenario: TuningStartRequest → TuningConfig 변환 검증
    Tool: Bash (pytest)
    Preconditions: 테스트 환경 준비
    Steps:
      1. python -m pytest backend/tests/test_tuner.py -v -k "start" --tb=short
    Expected Result: 기존 start 테스트 PASS + 새 필드 매핑 정상
    Failure Indicators: AssertionError 또는 KeyError
    Evidence: .sisyphus/evidence/task-1-conversion.txt
  ```

  **Commit**: YES
  - Message: `feat(models): expand TuningConfig and TuningTrial for tuner improvements`
  - Files: `backend/models/load_test.py`, `backend/routers/tuner.py`
  - Pre-commit: `python -m pytest backend/tests/test_tuner.py -x -q -m "not integration"`

- [x] 2. Stub 엔드포인트 수정 — /importance + /apply-best 실제 구현

  **What to do**:
  - **`/importance` 수정** (`tuner.py:170-179`):
    - 하드코딩된 dict 제거
    - `auto_tuner.get_importance()` 호출로 교체
    - 이미 `auto_tuner.py:303-309`에 구현되어 있으므로 라우터만 수정
  - **`/apply-best` 수정** (`tuner.py:182-190`):
    - `auto_tuner.best`가 None이면 `{"success": False, "message": "No best trial available"}` 반환
    - `auto_tuner.is_running`이면 `{"success": False, "message": "Tuning in progress"}` 반환
    - 그 외: `auto_tuner._apply_params(auto_tuner.best.params)` 호출 후 결과 반환
    - `applied_parameters: auto_tuner.best.params`, `deployment_name: K8S_DEPLOYMENT` 포함
  - **테스트 업데이트** (`test_tuner.py`):
    - `test_tuner_apply_best_response` (line 64-68): `success: False` 검증을 유지하되 메시지를 "No best trial available"로 변경 (idle 상태에서 best가 없으므로 여전히 False)
    - 새 테스트 추가: `test_apply_best_with_existing_trial` — mock best trial 주입 후 success: True 검증
    - 새 테스트 추가: `test_importance_returns_real_values` — 5+ trials mock 후 실제 FAnova 값 반환 검증
    - 새 테스트 추가: `test_importance_returns_empty_when_no_trials` — trials 없을 때 {} 반환
  - **프론트엔드 버그 수정** (`TunerPage.jsx:84-87`):
    - `applyBest()` 함수: API 응답의 `data.success`를 확인 후 성공/실패 메시지 분기

  **Must NOT do**:
  - auto_tuner.py 수정 금지 (get_importance() 이미 구현됨)
  - 기존 응답 스키마 변경 금지

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: 이미 구현된 메서드를 라우터에 연결하는 단순 작업
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Tasks 1, 3, 4)
  - **Blocks**: None
  - **Blocked By**: None

  **References**:

  **Pattern References**:
  - `backend/services/auto_tuner.py:303-309` — get_importance() 이미 구현됨. Optuna FAnova 사용, 5 trials 미만 시 {} 반환
  - `backend/services/auto_tuner.py:213-275` — _apply_params() 이미 구현됨. K8s ConfigMap 패치 + InferenceService 재시작
  - `backend/routers/tuner.py:124-141` — /status 엔드포인트 패턴. auto_tuner 속성 접근 방식 참고
  - `backend/tests/test_tuner.py:64-68` — test_tuner_apply_best_response. success: False 검증 → 메시지 변경 필요
  - `backend/tests/test_tuner.py:224-267` — test_tuner_trials_item_shape_with_data. mock 패턴 참고 (handler_globals patch)

  **API/Type References**:
  - `backend/routers/tuner.py:40-45` — ApplyBestResponse 모델. 이 스키마에 맞게 응답 반환
  - `backend/services/auto_tuner.py:100-106` — best property, trials property

  **WHY Each Reference Matters**:
  - auto_tuner.py:303-309 — 핵심: 이 메서드를 호출만 하면 됨. 새 로직 작성 불필요
  - test_tuner.py:64-68 — 이 테스트가 기존 stub 동작을 검증하므로 반드시 먼저 업데이트해야 함
  - test_tuner.py:224-267 — mock_tuner + handler_globals 패턴을 그대로 사용하여 best trial 주입 테스트 작성

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: /importance returns empty dict when no trials
    Tool: Bash (curl)
    Preconditions: Backend 서버 실행, 튜닝 미실행 상태
    Steps:
      1. curl -s http://localhost:8000/api/tuner/importance
      2. 응답 확인: {} (빈 dict)
    Expected Result: {} — 하드코딩된 {max_num_seqs: 0.4, ...} 아님
    Failure Indicators: 하드코딩된 값 반환 또는 500 에러
    Evidence: .sisyphus/evidence/task-2-importance-empty.txt

  Scenario: /apply-best returns failure message when no best trial
    Tool: Bash (curl)
    Preconditions: Backend 서버 실행, 튜닝 미실행
    Steps:
      1. curl -s -X POST http://localhost:8000/api/tuner/apply-best | jq '.'
      2. 확인: {"success": false, "message": "No best trial available", ...}
    Expected Result: success=false, message 포함
    Failure Indicators: success=true 또는 500 에러
    Evidence: .sisyphus/evidence/task-2-apply-best-no-trial.txt

  Scenario: 기존 테스트 전체 통과
    Tool: Bash (pytest)
    Preconditions: 테스트 환경
    Steps:
      1. cd backend && python -m pytest tests/test_tuner.py -v --tb=short -m "not integration"
    Expected Result: ALL PASS (기존 + 신규 테스트)
    Failure Indicators: ANY FAIL
    Evidence: .sisyphus/evidence/task-2-tests.txt
  ```

  **Commit**: YES
  - Message: `fix(tuner): implement /importance and /apply-best stub endpoints`
  - Files: `backend/routers/tuner.py`, `backend/tests/test_tuner.py`, `frontend/src/pages/TunerPage.jsx`
  - Pre-commit: `python -m pytest backend/tests/test_tuner.py -x -q -m "not integration"`

- [x] 3. Prometheus 튜너 메트릭 정의

  **What to do**:
  - `backend/metrics/prometheus_metrics.py`에 3개 튜너 메트릭 추가:
    - `vllm_optimizer_tuner_trials_total` — Counter, label: `status` (completed/pruned/failed)
    - `vllm_optimizer_tuner_best_score` — Gauge, label: `objective` (tps/latency/balanced/pareto)
    - `vllm_optimizer_tuner_trial_duration_seconds` — Histogram, buckets: [10, 30, 60, 120, 300, 600]
  - 메트릭 정의만 추가 (emit은 T14에서 처리)
  - 기존 메트릭 네이밍 컨벤션 따르기

  **Must NOT do**:
  - 기존 메트릭 수정 금지
  - auto_tuner.py에서 메트릭 emit 하지 말 것 (T14 범위)

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: 3줄 메트릭 정의 추가
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Tasks 1, 2, 4)
  - **Blocks**: Task 14
  - **Blocked By**: None

  **References**:

  **Pattern References**:
  - `backend/metrics/prometheus_metrics.py` — 기존 메트릭 정의 패턴. Counter/Gauge/Histogram 사용법 참고

  **WHY Each Reference Matters**:
  - prometheus_metrics.py — 기존 네이밍 컨벤션(vllm_optimizer_ prefix)과 import 패턴을 따라야 /metrics 엔드포인트에서 자동 노출됨

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: 메트릭 정의 import 성공
    Tool: Bash (python)
    Preconditions: 없음
    Steps:
      1. python -c "from backend.metrics.prometheus_metrics import tuner_trials_total, tuner_best_score, tuner_trial_duration; print('OK')"
    Expected Result: OK 출력, ImportError 없음
    Failure Indicators: ImportError 또는 NameError
    Evidence: .sisyphus/evidence/task-3-import.txt

  Scenario: /metrics 엔드포인트에 튜너 메트릭 노출
    Tool: Bash (curl)
    Preconditions: Backend 서버 실행
    Steps:
      1. curl -s http://localhost:8000/metrics | grep "vllm_optimizer_tuner"
    Expected Result: 3개 메트릭 이름 포함
    Failure Indicators: grep 결과 없음
    Evidence: .sisyphus/evidence/task-3-metrics-endpoint.txt
  ```

  **Commit**: YES
  - Message: `feat(metrics): add Prometheus tuner metric definitions`
  - Files: `backend/metrics/prometheus_metrics.py`
  - Pre-commit: `python -m pytest backend/tests/ -x -q -m "not integration"`

- [x] 4. 프론트엔드 버그 수정 + 설정 폼 확장

  **What to do**:
  - **config state 확장** (`TunerPage.jsx:16-22`):
    - `eval_requests: 200` 추가 (현재 프론트엔드에서 누락, 백엔드 기본값 10으로 전송 중)
    - `eval_concurrency: 32` 추가
    - `eval_rps: 20` 추가
    - `max_model_len_min: 2048`, `max_model_len_max: 8192` 추가 (백엔드에 존재하나 프론트 미노출)
    - `max_num_batched_tokens_min: 256`, `max_num_batched_tokens_max: 2048` 추가
    - `block_size_options: [8, 16, 32]` 추가
  - **설정 폼 UI 추가** (기존 grid-form 섹션에):
    - eval_requests 입력 필드
    - eval_concurrency, eval_rps 입력 필드
    - max_model_len 범위 (min/max) 입력 필드
    - max_num_batched_tokens 범위 (min/max) 입력 필드
    - block_size 체크박스 또는 multi-select (8/16/32)
  - 기존 디자인 패턴 (className="input", className="label") 따르기
  - `applyBest()` 함수의 무조건 성공 알림 버그는 T2에서 처리하므로 여기서는 config form만

  **Must NOT do**:
  - 새 React 컴포넌트 파일 생성 금지 — TunerPage.jsx 내에서 처리
  - Recharts 외 차트 라이브러리 추가 금지
  - 기존 ScatterChart 수정 금지 (T13에서 처리)

  **Recommended Agent Profile**:
  - **Category**: `visual-engineering`
    - Reason: UI 폼 레이아웃과 반응형 디자인이 필요
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Tasks 1, 2, 3)
  - **Blocks**: Task 13
  - **Blocked By**: None

  **References**:

  **Pattern References**:
  - `frontend/src/pages/TunerPage.jsx:16-22` — 현재 config state. 새 필드 추가 위치
  - `frontend/src/pages/TunerPage.jsx:111-144` — 기존 설정 폼 UI. grid-form 레이아웃, input/label className 패턴
  - `frontend/src/pages/TunerPage.jsx:60-77` — start() 함수. config를 JSON.stringify 하여 전송. 새 필드도 자동 포함됨

  **External References**:
  - `frontend/src/constants.js` — COLORS, API 등 상수 정의

  **WHY Each Reference Matters**:
  - TunerPage.jsx:111-144 — 기존 grid-form의 스타일 패턴(label + input + 범위 입력)을 정확히 따라야 일관된 UI
  - TunerPage.jsx:16-22 — state 초기값이 API 전송 시 기본값 역할

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: 새 config 필드가 UI에 렌더링됨
    Tool: Playwright (playwright skill)
    Preconditions: Frontend 서버 실행 (npm run dev)
    Steps:
      1. Navigate to http://localhost:5173 (또는 빌드된 URL)
      2. Click on "Auto Tuner" 탭
      3. 확인: "eval_requests" 또는 "평가 요청 수" 레이블이 있는 input 필드 존재
      4. 확인: "max_num_batched_tokens" 범위 입력 필드 존재
      5. 확인: "block_size" 선택 옵션 존재
      6. Screenshot 캡처
    Expected Result: 모든 새 필드가 기존 설정 섹션에 표시됨
    Failure Indicators: 필드 누락 또는 레이아웃 깨짐
    Evidence: .sisyphus/evidence/task-4-config-form.png

  Scenario: 새 필드가 API 요청에 포함됨
    Tool: Playwright (playwright skill)
    Preconditions: Frontend + Backend 실행
    Steps:
      1. DevTools Network 탭 열기
      2. Start Tuning 버튼 클릭
      3. /api/tuner/start POST 요청 payload 확인
      4. eval_requests, eval_concurrency, max_num_batched_tokens_min 등 포함 여부 확인
    Expected Result: 모든 새 필드가 request body에 포함
    Failure Indicators: 필드 누락
    Evidence: .sisyphus/evidence/task-4-api-request.png
  ```

  **Commit**: YES
  - Message: `fix(frontend): expand tuner config form with new fields`
  - Files: `frontend/src/pages/TunerPage.jsx`
  - Pre-commit: `cd frontend && npm run build`

- [x] 5. 검색 공간 확장 — 새 파라미터 + 제약조건 + 빈 리스트 버그 수정

  **What to do**:
  - **빈 리스트 크래시 수정** (`auto_tuner.py:203-207`):
    - `max_model_len` categorical 리스트 필터링 결과가 빈 리스트일 때 `ValueError` 방지
    - 빈 리스트면 범위 내 가장 가까운 2의 거듭제곱 값을 동적 생성하거나 에러 반환
  - **`_suggest_params` 확장** (`auto_tuner.py:190-211`):
    - `max_num_batched_tokens`: `trial.suggest_int()` — **floor 제약: max(low, max_num_seqs)** 적용하여 vLLM 크래시 방지
    - `block_size`: `trial.suggest_categorical(config.block_size_options)` — [8, 16, 32] 중 선택
    - `swap_space`: `config.include_swap_space`가 True일 때만 `trial.suggest_float()` — CPU/OpenVINO 환경 기본 비활성
  - **`_apply_params` ConfigMap 키 추가** (`auto_tuner.py:228-234`):
    - `"MAX_NUM_BATCHED_TOKENS": str(params.get("max_num_batched_tokens", ""))` — 값이 있을 때만
    - `"BLOCK_SIZE": str(params.get("block_size", ""))` — 값이 있을 때만
    - `"SWAP_SPACE": str(params.get("swap_space", ""))` — 값이 있을 때만
    - 빈 문자열인 키는 ConfigMap에 포함하지 않도록 필터링

  **Must NOT do**:
  - _evaluate() 수정 금지 (T6 범위)
  - start() 루프 로직 수정 금지 (T8, T11 범위)
  - swap_space를 기본 활성화하지 말 것

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: 파라미터 제약조건과 엣지케이스 처리가 복잡
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 (with Tasks 6, 7)
  - **Blocks**: Task 8
  - **Blocked By**: Task 1 (모델 필드 필요)

  **References**:

  **Pattern References**:
  - `backend/services/auto_tuner.py:190-211` — 현재 _suggest_params. 기존 4개 파라미터 suggest 패턴
  - `backend/services/auto_tuner.py:228-234` — 현재 _apply_params ConfigMap patch_body. 새 키 추가 위치
  - `backend/tests/test_tuner.py:270-292` — test_apply_params_uses_correct_configmap_keys 패턴. 새 키 테스트도 이 패턴 따르기

  **API/Type References**:
  - `backend/models/load_test.py` — TuningConfig (T1에서 확장됨). max_num_batched_tokens_range, block_size_options, include_swap_space

  **WHY Each Reference Matters**:
  - auto_tuner.py:190-211 — suggest 순서가 중요: max_num_seqs를 먼저 suggest한 후 max_num_batched_tokens의 floor로 사용
  - auto_tuner.py:228-234 — ConfigMap 키는 대문자 + 밑줄 패턴. vLLM InferenceService가 이 환경변수를 읽음
  - test_tuner.py:270-292 — 새 ConfigMap 키 테스트도 동일한 mock 패턴 사용

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: max_num_batched_tokens >= max_num_seqs 제약 검증
    Tool: Bash (python)
    Preconditions: 없음
    Steps:
      1. python -c "
         import optuna
         from backend.services.auto_tuner import AutoTuner
         from backend.models.load_test import TuningConfig
         study = optuna.create_study(sampler=optuna.samplers.TPESampler(seed=42))
         config = TuningConfig()
         tuner = AutoTuner.__new__(AutoTuner)
         for _ in range(20):
             trial = study.ask()
             params = tuner._suggest_params(trial, config)
             assert params['max_num_batched_tokens'] >= params['max_num_seqs'], f'Constraint violated: {params}'
             study.tell(trial, 0)
         print('All 20 trials passed constraint check')
         "
    Expected Result: "All 20 trials passed constraint check"
    Failure Indicators: AssertionError
    Evidence: .sisyphus/evidence/task-5-constraint.txt

  Scenario: 빈 리스트 크래시 방지 검증
    Tool: Bash (python)
    Preconditions: 없음
    Steps:
      1. python -c "
         import optuna
         from backend.services.auto_tuner import AutoTuner
         from backend.models.load_test import TuningConfig
         config = TuningConfig(max_model_len_range=(10000, 16384))
         study = optuna.create_study()
         tuner = AutoTuner.__new__(AutoTuner)
         trial = study.ask()
         try:
             params = tuner._suggest_params(trial, config)
             print(f'OK: {params[\"max_model_len\"]}')
         except ValueError as e:
             print(f'CRASH: {e}')
         "
    Expected Result: OK 또는 적절한 fallback 값, CRASH 아님
    Failure Indicators: CRASH 또는 ValueError
    Evidence: .sisyphus/evidence/task-5-empty-list.txt

  Scenario: swap_space는 기본 비활성
    Tool: Bash (python)
    Preconditions: 없음
    Steps:
      1. python -c "
         import optuna
         from backend.services.auto_tuner import AutoTuner
         from backend.models.load_test import TuningConfig
         config = TuningConfig()  # include_swap_space=False (default)
         study = optuna.create_study()
         tuner = AutoTuner.__new__(AutoTuner)
         trial = study.ask()
         params = tuner._suggest_params(trial, config)
         assert 'swap_space' not in params, f'swap_space should not be in params: {params}'
         print('OK: swap_space excluded')
         "
    Expected Result: "OK: swap_space excluded"
    Failure Indicators: AssertionError
    Evidence: .sisyphus/evidence/task-5-swap-space.txt
  ```

  **Commit**: YES
  - Message: `feat(tuner): expand search space with parameter constraints`
  - Files: `backend/services/auto_tuner.py`
  - Pre-commit: `python -m pytest backend/tests/test_tuner.py -x -q -m "not integration"`

- [x] 6. 평가 설정 가변화 + Warmup 구현

  **What to do**:
  - **`_evaluate` 하드코딩 제거** (`auto_tuner.py:277-301`):
    - `concurrency=32` → `config.eval_concurrency` 사용
    - `rps=20` → `config.eval_rps` 사용
    - config를 인스턴스 변수 `self._config`에 저장하여 _evaluate에서 접근
  - **Warmup 구현**:
    - `TuningConfig.warmup_requests` (이미 존재, 기본값 50) 활용
    - `_evaluate()` 호출 전 warmup 부하 실행: `warmup_requests > 0`이면 짧은 부하 테스트 실행 후 결과 무시
    - Warmup은 `load_engine.run()` 동일 패턴 사용하되 결과를 점수에 반영하지 않음
  - **`_evaluate` 리팩토링** — 추후 T11 (MedianPruner 2-phase)에서 분할할 수 있도록 config 접근 경로 정리

  **Must NOT do**:
  - load_engine.py 수정 금지
  - _suggest_params 수정 금지 (T5 범위)
  - start() 루프 수정 금지 (T8/T11 범위)

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
    - Reason: 비동기 부하 테스트 호출 패턴과 config 플로우 이해 필요
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 (with Tasks 5, 7)
  - **Blocks**: Tasks 9, 11
  - **Blocked By**: Task 1 (eval_concurrency, eval_rps 필드)

  **References**:

  **Pattern References**:
  - `backend/services/auto_tuner.py:277-301` — 현재 _evaluate(). concurrency=32, rps=20 하드코딩 위치
  - `backend/services/auto_tuner.py:120-184` — start() 메서드. config를 self._config로 저장하는 위치
  - `backend/services/load_engine.py:90-240` — LoadTestEngine.run(). LoadTestConfig 인터페이스 확인
  - `backend/models/load_test.py:14-24` — LoadTestConfig. concurrency, rps 필드 타입

  **WHY Each Reference Matters**:
  - auto_tuner.py:277-301 — LoadTestConfig 생성 시 hardcoded 값을 config 참조로 교체
  - load_engine.py:90-240 — load_engine.run()이 LoadTestConfig를 받으므로 warmup도 동일 인터페이스 사용
  - auto_tuner.py:120-184 — start()에서 config를 받으므로 self._config = config 저장 필요

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: eval_concurrency/eval_rps 설정이 부하 테스트에 반영됨
    Tool: Bash (pytest)
    Preconditions: 테스트 환경
    Steps:
      1. 테스트 작성: _evaluate() 호출 시 load_engine.run()에 전달되는 LoadTestConfig의 concurrency와 rps 값이 config에서 온 값인지 검증
      2. python -m pytest backend/tests/test_tuner.py -v -k "eval_config" --tb=short
    Expected Result: PASS — LoadTestConfig.concurrency == config.eval_concurrency
    Failure Indicators: 여전히 32/20 하드코딩
    Evidence: .sisyphus/evidence/task-6-eval-config.txt

  Scenario: warmup 실행 후 본 평가 진행
    Tool: Bash (pytest)
    Preconditions: 테스트 환경
    Steps:
      1. 테스트 작성: warmup_requests=10 설정 시 load_engine.run()이 2번 호출되는지 검증 (warmup 1번 + 본 평가 1번)
      2. python -m pytest backend/tests/test_tuner.py -v -k "warmup" --tb=short
    Expected Result: load_engine.run.call_count == 2
    Failure Indicators: call_count != 2 또는 warmup 미실행
    Evidence: .sisyphus/evidence/task-6-warmup.txt
  ```

  **Commit**: YES
  - Message: `feat(tuner): configurable eval params and warmup implementation`
  - Files: `backend/services/auto_tuner.py`
  - Pre-commit: `python -m pytest backend/tests/test_tuner.py -x -q -m "not integration"`

- [x] 7. SSE 브로드캐스트 인프라 추가

  **What to do**:
  - `AutoTuner` 클래스에 SSE 이벤트 브로드캐스트 패턴 추가 (LoadTestEngine 패턴 복제):
    - `self._subscribers: list[asyncio.Queue] = []` 필드 추가
    - `self._subscribers_lock: asyncio.Lock = asyncio.Lock()` 필드 추가
    - `async def subscribe(self) -> asyncio.Queue` 메서드 추가
    - `async def unsubscribe(self, q: asyncio.Queue)` 메서드 추가
    - `async def _broadcast(self, data: dict)` 메서드 추가
  - `start()` 메서드의 trial 루프에서 이벤트 브로드캐스트:
    - Trial 시작: `{"type": "trial_start", "data": {"trial_id": trial_num, "params": params}}`
    - Trial 완료: `{"type": "trial_complete", "data": {"trial_id": trial_num, "score": score, "tps": tps, "p99_latency": p99_lat}}`
    - 튜닝 완료: `{"type": "tuning_complete", "data": {"best_params": ..., "total_trials": ...}}`
  - 클라이언트 연결/해제가 튜닝 프로세스에 영향 없도록 설계

  **Must NOT do**:
  - load_engine.py 수정 금지 (패턴만 복사)
  - _evaluate() 수정 금지 (T6 범위)
  - /api/tuner/stream 엔드포인트 추가 금지 (T10 범위)

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: LoadTestEngine의 동일 패턴을 복사하는 단순 작업
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 (with Tasks 5, 6)
  - **Blocks**: Task 10
  - **Blocked By**: None

  **References**:

  **Pattern References**:
  - `backend/services/load_engine.py:54-68` — LoadTestEngine subscribe/unsubscribe/_broadcast 패턴. **이 패턴을 정확히 복제**
  - `backend/services/load_engine.py:36-41` — _subscribers, _subscribers_lock 필드 선언 패턴
  - `backend/services/auto_tuner.py:135-170` — start() trial 루프. broadcast 호출 삽입 위치

  **WHY Each Reference Matters**:
  - load_engine.py:54-68 — 검증된 SSE pub/sub 패턴. 새 시스템을 발명하지 말고 이 패턴을 그대로 사용
  - auto_tuner.py:135-170 — trial 루프의 각 단계에서 적절한 이벤트를 broadcast

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: subscribe/broadcast 기능 동작 검증
    Tool: Bash (pytest)
    Preconditions: 테스트 환경
    Steps:
      1. 테스트 작성: auto_tuner.subscribe() 후 _broadcast() 호출 시 Queue에 이벤트 도착 검증
      2. python -m pytest backend/tests/test_tuner.py -v -k "broadcast" --tb=short
    Expected Result: Queue.get_nowait()로 이벤트 수신 성공
    Failure Indicators: Queue.Empty 또는 구독 실패
    Evidence: .sisyphus/evidence/task-7-broadcast.txt

  Scenario: 구독 해제 후 이벤트 미수신
    Tool: Bash (pytest)
    Preconditions: 테스트 환경
    Steps:
      1. subscribe → unsubscribe → broadcast → Queue 비어있는지 확인
    Expected Result: Queue가 비어있음
    Failure Indicators: Queue에 이벤트 남아있음
    Evidence: .sisyphus/evidence/task-7-unsubscribe.txt
  ```

  **Commit**: YES
  - Message: `feat(tuner): add SSE broadcast infrastructure`
  - Files: `backend/services/auto_tuner.py`
  - Pre-commit: `python -m pytest backend/tests/test_tuner.py -x -q -m "not integration"`

- [x] 8. ConfigMap 스냅샷 + 자동 롤백 메커니즘

  **What to do**:
  - **스냅샷 저장** — `_apply_params()` 호출 전 현재 ConfigMap을 메모리에 저장:
    - `self._cm_snapshot: dict | None = None` 필드 추가 (init에서)
    - `_apply_params()` 시작 시 (restart_only가 아닌 경우): `read_namespaced_config_map`으로 현재 ConfigMap.data를 `self._cm_snapshot`에 저장
  - **롤백 메서드** 추가:
    - `async def _rollback_to_snapshot(self) -> bool` — self._cm_snapshot이 있으면 ConfigMap을 원래 값으로 패치 + InferenceService 재시작
    - 롤백 성공 시 True, 실패/스냅샷 없음 시 False 반환
  - **자동 롤백 트리거** — `start()` trial 루프에서:
    - `_wait_for_ready()` 반환값이 False (타임아웃)면 즉시 `_rollback_to_snapshot()` 호출
    - `_evaluate()` 예외 발생 시에도 `_rollback_to_snapshot()` 호출
    - 롤백 실행 시 `self._last_rollback_trial: int | None = None` 기록
  - **상태 노출** — `tuner.py`의 `/status` 응답에 `last_rollback_trial: int | None` 필드 추가

  **Must NOT do**:
  - K8s ConfigMap 백업 (별도 ConfigMap 생성) 금지 — 메모리 스냅샷만
  - 정상 trial에서 롤백 트리거 금지 — 타임아웃/예외 시에만

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: K8s API 호출 + 비동기 에러 핸들링 + 트랜잭션 패턴
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 3 (with Tasks 9, 10)
  - **Blocks**: Task 11
  - **Blocked By**: Task 5 (_apply_params 수정 완료 필요)

  **References**:

  **Pattern References**:
  - `backend/services/auto_tuner.py:213-275` — 현재 _apply_params(). ConfigMap read + patch 패턴. 스냅샷 저장 위치
  - `backend/services/auto_tuner.py:135-170` — start() trial 루프. _wait_for_ready() 반환값 체크 후 롤백 삽입 위치
  - `backend/services/auto_tuner.py:57-98` — _wait_for_ready(). False 반환 조건 이해
  - `backend/routers/tuner.py:124-141` — /status 응답. last_rollback_trial 필드 추가 위치

  **WHY Each Reference Matters**:
  - auto_tuner.py:213-275 — `read_namespaced_config_map`이 이미 호출되므로(224행) 반환값을 저장하면 됨
  - auto_tuner.py:135-170 — 152행에서 _wait_for_ready() 호출 후 롤백 조건 삽입
  - tuner.py:124-141 — TunerStatusFrontendResponse에 필드 추가 + 응답 매핑 추가

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: _wait_for_ready 타임아웃 시 자동 롤백
    Tool: Bash (pytest)
    Preconditions: 테스트 환경
    Steps:
      1. auto_tuner._wait_for_ready = AsyncMock(return_value=False) 설정
      2. _apply_params 호출 후 _wait_for_ready 타임아웃 시뮬레이션
      3. ConfigMap이 스냅샷 값으로 복원되었는지 mock 검증
    Expected Result: patch_namespaced_config_map이 스냅샷 데이터로 호출됨
    Failure Indicators: 롤백 미실행 또는 스냅샷 데이터 불일치
    Evidence: .sisyphus/evidence/task-8-rollback.txt

  Scenario: /status 응답에 last_rollback_trial 포함
    Tool: Bash (curl)
    Preconditions: Backend 실행
    Steps:
      1. curl -s http://localhost:8000/api/tuner/status | jq '.last_rollback_trial'
    Expected Result: null (롤백 미발생 시)
    Failure Indicators: 필드 없음 또는 500 에러
    Evidence: .sisyphus/evidence/task-8-status-field.txt
  ```

  **Commit**: YES
  - Message: `feat(tuner): ConfigMap snapshot and rollback mechanism`
  - Files: `backend/services/auto_tuner.py`, `backend/routers/tuner.py`
  - Pre-commit: `python -m pytest backend/tests/test_tuner.py -x -q -m "not integration"`

- [x] 9. SQLite Study 영속성 + Warm-start

  **What to do**:
  - **환경변수 기반 스토리지 설정**:
    - `OPTUNA_STORAGE_URL` 환경변수 읽기 (기본값: None = 인메모리)
    - None이면 기존 인메모리 방식 유지
    - `sqlite:///path/to/db` 형식이면 Optuna RDBStorage 사용
  - **`start()` 메서드 수정** — create_study 분기:
    - 인메모리: `optuna.create_study(direction=..., sampler=...)` (현재 방식)
    - SQLite: `optuna.create_study(storage=storage_url, study_name="vllm-tuner-{objective}", load_if_exists=True, direction=..., sampler=...)`
    - **주의**: SQLite 사용 시 `engine_kwargs={"connect_args": {"check_same_thread": False}}` 필요
    - **주의**: create_study/load_study는 `asyncio.to_thread()`로 래핑 (SQLite 블로킹 I/O)
  - **Warm-start 구현** — `study.enqueue_trial()` 사용 (WarmStartSampler 아님):
    - `load_if_exists=True`로 기존 study 로드 시, `study.best_trial` 존재하면
    - `study.enqueue_trial(params=study.best_trial.params)` 호출하여 이전 최적 파라미터를 첫 trial로 재평가
    - Single-objective에서만 적용 (multi-obj는 best_trial 대신 best_trials 사용 → T12에서 처리)

  **Must NOT do**:
  - PVC 추가 금지 — SQLite는 ephemeral 경로 사용
  - WarmStartSampler import 금지 — Optuna 3.5.x 호환성 위험
  - _evaluate() 수정 금지 (T6에서 완료)
  - Pareto 모드 warm-start 금지 (T12 범위)

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
    - Reason: Optuna storage API + SQLite threading + asyncio 통합
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 3 (with Tasks 8, 10)
  - **Blocks**: Task 12
  - **Blocked By**: Task 6 (config 접근 패턴)

  **References**:

  **Pattern References**:
  - `backend/services/auto_tuner.py:129-133` — 현재 create_study. 여기를 분기 로직으로 교체
  - `backend/services/auto_tuner.py:67-68` — asyncio.to_thread() 패턴. SQLite 호출도 동일하게 래핑
  - `backend/services/auto_tuner.py:22-24` — 환경변수 읽기 패턴. OPTUNA_STORAGE_URL 추가

  **External References**:
  - Optuna RDBStorage docs: `optuna.storages.RDBStorage(url, engine_kwargs={"connect_args": {"check_same_thread": False}})`
  - Optuna study.enqueue_trial: `study.enqueue_trial(params={"max_num_seqs": 128, ...})`

  **WHY Each Reference Matters**:
  - auto_tuner.py:129-133 — create_study를 storage 유무에 따라 분기. load_if_exists=True 핵심
  - auto_tuner.py:67-68 — asyncio.to_thread() 패턴을 따라야 이벤트 루프 블로킹 방지

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: OPTUNA_STORAGE_URL 미설정 시 인메모리 동작
    Tool: Bash (pytest)
    Preconditions: OPTUNA_STORAGE_URL 환경변수 미설정
    Steps:
      1. 테스트 작성: OPTUNA_STORAGE_URL 없이 start() 호출 → 정상 완료 검증
      2. /tmp/optuna.db 파일 미생성 확인
    Expected Result: 튜닝 정상 실행, 파일 미생성
    Failure Indicators: FileNotFoundError 또는 DB 파일 생성
    Evidence: .sisyphus/evidence/task-9-inmemory.txt

  Scenario: SQLite 설정 시 DB 파일 생성 + warm-start
    Tool: Bash (pytest)
    Preconditions: 테스트 환경
    Steps:
      1. OPTUNA_STORAGE_URL=sqlite:////tmp/test_optuna.db 설정
      2. start() 호출 (2 trials) → 완료
      3. /tmp/test_optuna.db 파일 존재 확인
      4. start() 재호출 → study.enqueue_trial 호출 확인 (mock)
    Expected Result: DB 파일 존재 + enqueue_trial 호출됨
    Failure Indicators: 파일 미생성 또는 enqueue_trial 미호출
    Evidence: .sisyphus/evidence/task-9-sqlite.txt
  ```

  **Commit**: YES
  - Message: `feat(tuner): SQLite study persistence and warm-start`
  - Files: `backend/services/auto_tuner.py`
  - Pre-commit: `python -m pytest backend/tests/test_tuner.py -x -q -m "not integration"`

- [x] 10. /api/tuner/stream SSE 엔드포인트

  **What to do**:
  - `backend/routers/tuner.py`에 `GET /stream` 엔드포인트 추가:
    - `StreamingResponse(media_type="text/event-stream")` 사용
    - `auto_tuner.subscribe()`로 Queue 구독
    - Queue에서 이벤트를 pop하여 `data: {json}\n\n` 형식으로 SSE 전송
    - 클라이언트 연결 해제 시 `auto_tuner.unsubscribe(q)` 호출
    - 튜닝 미실행 시 `{"type": "idle"}` 이벤트 하나 전송 후 유지 (keepalive)
  - 30초마다 keepalive 코멘트 전송 (`: keepalive\n\n`) — 프록시 타임아웃 방지
  - nginx.conf에 /api/tuner/stream SSE 관련 설정 필요 여부 확인 (기존 SSE가 있으므로 대부분 불필요)

  **Must NOT do**:
  - WebSocket 사용 금지 — SSE만
  - auto_tuner.py 수정 금지 (T7에서 인프라 추가 완료)
  - 기존 load_test SSE 엔드포인트 수정 금지

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: 기존 load_test SSE 패턴을 복제하는 작업
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 3 (with Tasks 8, 9)
  - **Blocks**: Task 13
  - **Blocked By**: Task 7 (SSE 인프라)

  **References**:

  **Pattern References**:
  - `backend/routers/load_test.py` — 기존 SSE 엔드포인트 패턴. StreamingResponse + asyncio.Queue 사용법
  - `backend/services/auto_tuner.py` — subscribe()/unsubscribe() 메서드 (T7에서 추가됨)
  - `frontend/nginx.conf` — SSE 관련 프록시 설정 확인

  **WHY Each Reference Matters**:
  - load_test.py — 검증된 SSE 패턴을 따라야 nginx 프록시 호환 보장
  - auto_tuner.py subscribe — Queue 기반 구독 API 사용

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: SSE 스트림 연결 성공
    Tool: Bash (curl)
    Preconditions: Backend 실행
    Steps:
      1. curl -N -H "Accept: text/event-stream" http://localhost:8000/api/tuner/stream &
      2. 3초 후 출력 확인
      3. 최소 1개 이벤트 (idle 또는 keepalive) 수신 확인
    Expected Result: text/event-stream 형식 데이터 수신
    Failure Indicators: 404 또는 연결 실패
    Evidence: .sisyphus/evidence/task-10-sse-connect.txt

  Scenario: SSE 연결 해제 시 튜닝 계속
    Tool: Bash (pytest)
    Preconditions: 테스트 환경
    Steps:
      1. subscribe → 즉시 unsubscribe → tuner.is_running 확인
      2. 튜닝이 계속 실행 중인지 검증
    Expected Result: is_running == True (연결 해제와 무관)
    Failure Indicators: 튜닝 중단
    Evidence: .sisyphus/evidence/task-10-disconnect.txt
  ```

  **Commit**: YES
  - Message: `feat(tuner): add /stream SSE endpoint`
  - Files: `backend/routers/tuner.py`
  - Pre-commit: `python -m pytest backend/tests/test_tuner.py -x -q -m "not integration"`

- [x] 11. MedianPruner + 2-Phase 평가

  **What to do**:
  - **MedianPruner 추가** — `start()`에서 create_study 시:
    - Single-objective 모드(tps/latency/balanced)에만 적용
    - `optuna.pruners.MedianPruner(n_startup_trials=3, n_warmup_steps=0)` 사용
    - Multi-objective(pareto)에서는 MedianPruner 비활성화 (Optuna 제약)
  - **2-Phase 평가 구현** — `_evaluate()` 리팩토링:
    - Phase 1 (Fast Probe): `eval_requests * eval_fast_fraction` 만큼 부하 테스트 실행
    - Phase 1 점수를 `trial.report(score, step=0)` + `trial.should_prune()` 체크
    - Pruned면 trial을 `PRUNED` 상태로 표시, Phase 2 건너뜀
    - Phase 2 (Full Eval): 나머지 `eval_requests * (1 - eval_fast_fraction)` 실행
    - 최종 점수는 Phase 1 + Phase 2 합산 결과 기반
  - **Trial 상태 기록**:
    - Pruned trial: `TuningTrial(status="pruned", pruned=True, score=phase1_score)`
    - SSE 브로드캐스트에 `"pruned": True` 포함
  - **`_best_score_history` 추가** — 수렴 그래프 데이터:
    - `self._best_score_history: list[float] = []` 필드 추가
    - 매 trial 완료 후 현재 best_score를 append
    - `/status` 응답에 포함 (T1의 TunerStatusFrontendResponse.best_score_history)

  **Must NOT do**:
  - Multi-objective에 MedianPruner 적용 금지 (Optuna RuntimeError)
  - _suggest_params 수정 금지 (T5에서 완료)
  - load_engine.py 수정 금지

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: Optuna pruning API + 2-phase 평가 분할 + 비동기 부하 테스트 통합
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 4 (with Task 12)
  - **Blocks**: Tasks 13, 15
  - **Blocked By**: Tasks 6, 8

  **References**:

  **Pattern References**:
  - `backend/services/auto_tuner.py:277-301` — 현재 _evaluate(). Phase 1/2로 분할할 코드
  - `backend/services/auto_tuner.py:129-133` — create_study. pruner 파라미터 추가 위치
  - `backend/services/auto_tuner.py:135-170` — start() trial 루프. pruning 체크 + 상태 기록 위치
  - `backend/services/auto_tuner.py:159-170` — TuningTrial 생성. status="pruned" 처리

  **External References**:
  - Optuna MedianPruner: `optuna.pruners.MedianPruner(n_startup_trials=3)` — 첫 3 trials는 pruning 안 함
  - Optuna trial.report/should_prune: `trial.report(value, step=0); if trial.should_prune(): raise optuna.TrialPruned()`

  **WHY Each Reference Matters**:
  - auto_tuner.py:277-301 — LoadTestConfig의 total_requests를 phase별로 분할하여 2번 호출
  - auto_tuner.py:129-133 — pruner는 create_study의 kwarg으로 전달

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: MedianPruner로 나쁜 trial 조기 중단
    Tool: Bash (pytest)
    Preconditions: 테스트 환경
    Steps:
      1. 테스트 작성: _evaluate mock으로 처음 3 trials 높은 점수, 4번째 trial 매우 낮은 점수 반환
      2. 4번째 trial의 status가 "pruned"인지 검증
      3. python -m pytest backend/tests/test_tuner.py -v -k "pruner" --tb=short
    Expected Result: trial.status == "pruned", trial.pruned == True
    Failure Indicators: 모든 trial이 "completed"
    Evidence: .sisyphus/evidence/task-11-pruner.txt

  Scenario: best_score_history 기록 검증
    Tool: Bash (pytest)
    Preconditions: 테스트 환경
    Steps:
      1. 5 trials mock 실행
      2. auto_tuner._best_score_history 길이 == 5 확인
      3. 리스트가 단조 증가(maximize) 또는 단조 감소(minimize)인지 확인
    Expected Result: len(history) == 5, 단조성 만족
    Failure Indicators: 빈 리스트 또는 길이 불일치
    Evidence: .sisyphus/evidence/task-11-convergence.txt
  ```

  **Commit**: YES
  - Message: `feat(tuner): MedianPruner with two-phase evaluation`
  - Files: `backend/services/auto_tuner.py`
  - Pre-commit: `python -m pytest backend/tests/test_tuner.py -x -q -m "not integration"`

- [x] 12. Multi-objective Pareto 모드 + NSGAIISampler

  **What to do**:
  - **Pareto 모드 추가** — `objective="pareto"` 지원:
    - `start()`에서 `config.objective == "pareto"`이면:
      - `directions=["maximize", "minimize"]` (TPS 최대화, P99 Latency 최소화)
      - `sampler=optuna.samplers.NSGAIISampler(seed=42)` 사용
      - MedianPruner 비활성화 (None)
    - `_evaluate()`에서 pareto 모드: `return (tps, p99_lat), tps, p99_lat` — 2개 값 반환
    - `study.tell(trial, [tps, -p99_lat])` — 두 값을 리스트로 전달
  - **best_trial → best_trials 처리**:
    - Pareto 모드: `study.best_trials` (Pareto front 전체) 사용
    - `self._best_trial`은 Pareto front 중 balanced score 최고점으로 설정
    - 모든 Pareto-optimal trials에 `is_pareto_optimal=True` 마킹
  - **get_importance() guard**:
    - `study.directions`가 2개 이상이면 `{}` 반환 (multi-obj에서 FAnova 미지원)
  - **SQLite DB 이름 분리**:
    - Pareto 모드: study_name="vllm-tuner-pareto"
    - Single-obj: study_name="vllm-tuner-{objective}"
  - **Warm-start for Pareto**:
    - 기존 pareto study 로드 시: best_trials 중 가장 balanced한 trial의 params를 enqueue_trial
  - **API 응답 확장**:
    - `tuner.py`의 `/trials` 응답에 `is_pareto_optimal` 필드 포함 (T1에서 모델 추가됨)
    - `/status` 응답에 Pareto front 크기 표시: `pareto_front_size: int | None`

  **Must NOT do**:
  - 기존 단일목적 모드 동작 변경 금지
  - MedianPruner를 multi-obj에 적용 금지
  - get_param_importances()를 multi-obj에서 호출 금지

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: Optuna multi-objective API + Pareto front 계산 + 기존 코드 분기 복잡
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 4 (with Task 11)
  - **Blocks**: Tasks 13, 14, 15
  - **Blocked By**: Task 9 (SQLite + warm-start 기반)

  **References**:

  **Pattern References**:
  - `backend/services/auto_tuner.py:120-184` — start(). create_study + trial 루프. Pareto 분기 추가 위치
  - `backend/services/auto_tuner.py:129-133` — create_study. directions + sampler 파라미터 변경
  - `backend/services/auto_tuner.py:155-157` — study.tell(). Pareto 모드에서 리스트로 전달
  - `backend/services/auto_tuner.py:303-309` — get_importance(). multi-obj guard 추가 위치
  - `backend/routers/tuner.py:144-158` — /trials 응답. is_pareto_optimal 매핑 추가

  **External References**:
  - Optuna multi-objective: `optuna.create_study(directions=["maximize", "minimize"], sampler=NSGAIISampler())`
  - Optuna Pareto front: `study.best_trials` — 리스트 반환

  **WHY Each Reference Matters**:
  - auto_tuner.py:129-133 — direction(단수) vs directions(복수) 분기가 핵심
  - auto_tuner.py:303-309 — get_param_importances()는 multi-obj에서 RuntimeError 발생하므로 반드시 guard

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Pareto 모드 시작 성공
    Tool: Bash (curl)
    Preconditions: Backend 실행
    Steps:
      1. curl -s -X POST http://localhost:8000/api/tuner/start -H 'Content-Type: application/json' -d '{"objective":"pareto","n_trials":2,"eval_requests":5,"vllm_endpoint":"http://mock:8080"}'
      2. 응답 확인: {"success": true, ...}
    Expected Result: success=true
    Failure Indicators: 500 에러 또는 success=false
    Evidence: .sisyphus/evidence/task-12-pareto-start.txt

  Scenario: /importance가 Pareto 모드에서 {} 반환
    Tool: Bash (pytest)
    Preconditions: Pareto 모드 튜닝 완료 상태
    Steps:
      1. Pareto study mock 설정 후 get_importance() 호출
      2. 반환값 == {} 검증
    Expected Result: 빈 dict
    Failure Indicators: RuntimeError 또는 하드코딩된 값
    Evidence: .sisyphus/evidence/task-12-importance-pareto.txt

  Scenario: is_pareto_optimal 마킹 검증
    Tool: Bash (pytest)
    Preconditions: 테스트 환경
    Steps:
      1. 5 trials mock Pareto 튜닝 후 trials 목록 확인
      2. is_pareto_optimal=True인 trial이 1개 이상 존재
    Expected Result: Pareto front에 해당하는 trial들이 마킹됨
    Failure Indicators: 모든 trial이 False
    Evidence: .sisyphus/evidence/task-12-pareto-optimal.txt
  ```

  **Commit**: YES
  - Message: `feat(tuner): multi-objective Pareto mode with NSGAIISampler`
  - Files: `backend/services/auto_tuner.py`, `backend/routers/tuner.py`
  - Pre-commit: `python -m pytest backend/tests/test_tuner.py -x -q -m "not integration"`

- [x] 13. 프론트엔드: SSE 통합 + 수렴 그래프 + Pareto 하이라이트

  **What to do**:
  - **SSE 통합** — 폴링을 SSE로 교체 (튜닝 실행 중에만):
    - `status.running === true`이면 `EventSource("/api/tuner/stream")` 연결
    - `trial_complete` 이벤트 수신 시 trials 상태 업데이트
    - `tuning_complete` 이벤트 수신 시 EventSource 종료 + 최종 폴링 전환
    - `status.running === false`이면 기존 3초 폴링 유지
  - **수렴 그래프 추가** — 기존 ScatterChart 아래에:
    - Recharts `LineChart` 사용 (이미 import 가능)
    - X축: Trial 번호, Y축: Best Score (누적 최고)
    - 데이터 소스: `/status` 응답의 `best_score_history`
  - **Pareto front 하이라이트** — 기존 ScatterChart 수정:
    - `is_pareto_optimal === true`인 점은 다른 색상 (예: `COLORS.green`) + 크기 확대
    - `is_pareto_optimal === false`인 점은 기존 `COLORS.cyan` 유지
    - 두 Scatter 레이어 사용: 일반 + Pareto
  - **Pruned trial 표시** — trials 테이블에:
    - `status === "pruned"` trial은 배경색 변경 또는 "(pruned)" 표시

  **Must NOT do**:
  - 새 React 컴포넌트 파일 생성 금지
  - Recharts 외 차트 라이브러리 추가 금지
  - 기존 ScatterChart 삭제 금지 — 수정만

  **Recommended Agent Profile**:
  - **Category**: `visual-engineering`
    - Reason: 차트 시각화 + EventSource 통합 + 조건부 스타일링
  - **Skills**: [`playwright`]
    - `playwright`: QA 스크린샷 캡처

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 5 (with Tasks 14, 15)
  - **Blocks**: None
  - **Blocked By**: Tasks 10 (SSE endpoint), 11 (convergence data), 12 (Pareto data)

  **References**:

  **Pattern References**:
  - `frontend/src/pages/TunerPage.jsx:24-47` — 현재 폴링 로직. SSE 전환 시 교체 위치
  - `frontend/src/pages/TunerPage.jsx:89-206` — ScatterChart. Pareto 하이라이트 추가 위치
  - `frontend/src/pages/TunerPage.jsx:192-206` — ScatterChart 설정. 두 번째 Scatter 레이어 추가
  - `frontend/src/pages/LoadTestPage.jsx` — EventSource 사용 패턴 참고 (SSE 수신)
  - `frontend/src/constants.js` — COLORS 상수 (green, cyan 등)

  **External References**:
  - Recharts LineChart: `<LineChart data={bestScoreHistory}><Line dataKey="score" /><XAxis dataKey="trial" /></LineChart>`

  **WHY Each Reference Matters**:
  - TunerPage.jsx:24-47 — useEffect + setInterval 패턴을 EventSource 조건부 전환으로 교체
  - LoadTestPage.jsx — 검증된 EventSource 사용 패턴 (onmessage, onerror, close)
  - TunerPage.jsx:192-206 — 기존 Scatter에 두 번째 데이터셋 추가로 Pareto 하이라이트

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: 수렴 그래프 렌더링
    Tool: Playwright (playwright skill)
    Preconditions: Frontend 빌드 완료 + mock 데이터 모드
    Steps:
      1. Navigate to TunerPage
      2. Mock 데이터로 best_score_history가 있는 상태 시뮬레이션
      3. LineChart 존재 확인 (SVG path element)
      4. Screenshot 캡처
    Expected Result: 수렴 그래프 표시됨
    Failure Indicators: 차트 미표시 또는 렌더링 에러
    Evidence: .sisyphus/evidence/task-13-convergence-chart.png

  Scenario: Pareto 점 하이라이트
    Tool: Playwright (playwright skill)
    Preconditions: Frontend + mock Pareto 데이터
    Steps:
      1. Navigate to TunerPage
      2. ScatterChart에서 Pareto-optimal 점이 다른 색상으로 표시되는지 확인
      3. Screenshot 캡처
    Expected Result: 2가지 색상의 scatter points 존재
    Failure Indicators: 모든 점이 같은 색상
    Evidence: .sisyphus/evidence/task-13-pareto-highlight.png
  ```

  **Commit**: YES
  - Message: `feat(frontend): SSE integration, convergence chart, Pareto highlight`
  - Files: `frontend/src/pages/TunerPage.jsx`
  - Pre-commit: `cd frontend && npm run build`

- [x] 14. Prometheus 메트릭 실제 emit

  **What to do**:
  - `auto_tuner.py`의 `start()` trial 루프에서 T3에서 정의한 메트릭을 emit:
    - Trial 완료 시: `tuner_trials_total.labels(status="completed").inc()`
    - Trial pruned 시: `tuner_trials_total.labels(status="pruned").inc()`
    - Trial 실패 시: `tuner_trials_total.labels(status="failed").inc()`
    - Best score 갱신 시: `tuner_best_score.labels(objective=config.objective).set(score)`
    - Trial 소요 시간: `tuner_trial_duration.observe(duration)` — trial 시작/종료 시간 측정
  - `backend/metrics/prometheus_metrics.py`에서 import 후 사용
  - 메트릭 emit은 try-except로 감싸서 메트릭 실패가 튜닝을 중단시키지 않도록

  **Must NOT do**:
  - prometheus_metrics.py에 새 메트릭 정의 추가 금지 (T3에서 완료)
  - OpenShift YAML (PrometheusRule 등) 수정 금지

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: import + 5-6줄 emit 코드 삽입
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 5 (with Tasks 13, 15)
  - **Blocks**: None
  - **Blocked By**: Tasks 3 (메트릭 정의), 12 (Pareto 모드 objective 분기)

  **References**:

  **Pattern References**:
  - `backend/metrics/prometheus_metrics.py` — T3에서 추가된 메트릭 정의. import 경로 확인
  - `backend/services/metrics_collector.py:218-219` — update_metrics() 호출 패턴. 메트릭 emit 방식 참고
  - `backend/services/auto_tuner.py:135-170` — start() trial 루프. emit 삽입 위치

  **WHY Each Reference Matters**:
  - prometheus_metrics.py — 정확한 변수명과 label 이름 확인
  - auto_tuner.py:135-170 — trial 완료/pruned/실패 각 분기점에서 적절한 메트릭 emit

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: 튜닝 후 Prometheus 메트릭 증가 확인
    Tool: Bash (curl)
    Preconditions: Backend 실행 + 최소 2 trials 완료 상태
    Steps:
      1. curl -s http://localhost:8000/metrics | grep "vllm_optimizer_tuner_trials_total"
      2. completed 카운터 > 0 확인
    Expected Result: vllm_optimizer_tuner_trials_total{status="completed"} >= 2
    Failure Indicators: 메트릭 0 또는 미존재
    Evidence: .sisyphus/evidence/task-14-metrics-emit.txt

  Scenario: 메트릭 emit 실패가 튜닝을 중단시키지 않음
    Tool: Bash (pytest)
    Preconditions: 테스트 환경
    Steps:
      1. prometheus 메트릭 모듈 import를 mock으로 실패시킨 후 start() 실행
      2. 튜닝 정상 완료 확인
    Expected Result: 튜닝 완료, 예외 없음
    Failure Indicators: 예외 발생 또는 튜닝 중단
    Evidence: .sisyphus/evidence/task-14-resilience.txt
  ```

  **Commit**: YES
  - Message: `feat(tuner): emit Prometheus metrics during tuning`
  - Files: `backend/services/auto_tuner.py`
  - Pre-commit: `python -m pytest backend/tests/test_tuner.py -x -q -m "not integration"`

- [x] 15. 새 기능 통합 테스트 추가

  **What to do**:
  - `backend/tests/test_tuner.py`에 다음 테스트 추가:
    - **Pareto 모드 테스트**:
      - `test_pareto_mode_creates_multi_objective_study` — directions == ["maximize", "minimize"] 검증
      - `test_pareto_mode_marks_pareto_optimal_trials` — is_pareto_optimal 마킹 검증
      - `test_importance_returns_empty_for_pareto` — multi-obj에서 {} 반환
    - **MedianPruner 테스트**:
      - `test_pruner_marks_trial_as_pruned` — 나쁜 trial이 pruned로 마킹
      - `test_pruner_disabled_in_pareto_mode` — Pareto에서 pruner 없음 검증
    - **Rollback 테스트**:
      - `test_rollback_restores_configmap_on_timeout` — _wait_for_ready False 시 롤백
      - `test_rollback_records_last_rollback_trial` — last_rollback_trial 기록 검증
    - **SSE 브로드캐스트 테스트**:
      - `test_broadcast_trial_events` — trial_start/trial_complete 이벤트 수신
    - **SQLite 영속성 테스트**:
      - `test_sqlite_persistence_creates_db` — OPTUNA_STORAGE_URL 설정 시 DB 생성
      - `test_warmstart_enqueues_best_trial` — enqueue_trial 호출 검증
    - **검색 공간 제약 테스트**:
      - `test_suggest_params_constraint_batched_tokens` — max_num_batched_tokens >= max_num_seqs
      - `test_suggest_params_empty_categorical_fallback` — 빈 categorical 리스트 처리
      - `test_swap_space_excluded_by_default` — include_swap_space=False 기본값
  - 모든 테스트는 기존 fixture 패턴(`auto_tuner_instance`, `mock_k8s_clients`) 사용
  - 모든 async 테스트는 `@pytest.mark.asyncio` 데코레이터 사용

  **Must NOT do**:
  - 실제 K8s API 호출 금지 — mock만
  - 실제 vLLM 엔드포인트 호출 금지 — mock만
  - 기존 테스트 삭제 금지

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
    - Reason: 다양한 기능의 mock 설정 + asyncio 테스트 패턴
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 5 (with Tasks 13, 14)
  - **Blocks**: None
  - **Blocked By**: Tasks 11, 12 (테스트 대상 기능 구현 완료)

  **References**:

  **Pattern References**:
  - `backend/tests/test_tuner.py:12-42` — 기존 fixture. auto_tuner_instance, mock_k8s_clients 패턴
  - `backend/tests/test_tuner.py:91-118` — async 테스트 패턴. @pytest.mark.asyncio + AsyncMock
  - `backend/tests/test_tuner.py:121-154` — _wait_for_ready 테스트 패턴. side_effect로 상태 시뮬레이션
  - `backend/tests/test_tuner.py:157-195` — start() 통합 테스트 패턴. _evaluate mock + 결과 검증
  - `backend/tests/test_tuner.py:224-267` — handler_globals patch 패턴. 라우터 테스트에 사용

  **WHY Each Reference Matters**:
  - test_tuner.py:12-42 — 모든 새 테스트는 이 fixture를 재사용해야 일관성 유지
  - test_tuner.py:91-118 — asyncio.to_thread mock 패턴을 Pareto/SQLite 테스트에도 적용
  - test_tuner.py:157-195 — start() 통합 테스트에서 _evaluate side_effect로 다양한 시나리오 시뮬레이션

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: 전체 테스트 스위트 통과
    Tool: Bash (pytest)
    Preconditions: 모든 구현 완료
    Steps:
      1. cd backend && python -m pytest tests/test_tuner.py -v --tb=short -m "not integration"
    Expected Result: ALL PASS, 0 failures
    Failure Indicators: ANY failure
    Evidence: .sisyphus/evidence/task-15-all-tests.txt

  Scenario: 새 테스트 커버리지 확인
    Tool: Bash (pytest)
    Preconditions: 테스트 환경
    Steps:
      1. python -m pytest tests/test_tuner.py -v -k "pareto or pruner or rollback or broadcast or sqlite or warmstart or constraint or swap" --tb=short
      2. 최소 12개 테스트 PASS 확인
    Expected Result: 12+ tests passed
    Failure Indicators: 12 미만
    Evidence: .sisyphus/evidence/task-15-new-tests.txt
  ```

  **Commit**: YES
  - Message: `test(tuner): comprehensive test additions for new features`
  - Files: `backend/tests/test_tuner.py`
  - Pre-commit: `python -m pytest backend/tests/test_tuner.py -x -q -m "not integration"`

---

## Final Verification Wave

- [x] F1. **Plan Compliance Audit** — `oracle`
  Read the plan end-to-end. For each "Must Have": verify implementation exists (read file, curl endpoint, run command). For each "Must NOT Have": search codebase for forbidden patterns — reject with file:line if found. Check evidence files exist in .sisyphus/evidence/. Compare deliverables against plan.
  Output: `Must Have [N/N] | Must NOT Have [N/N] | Tasks [N/N] | VERDICT: APPROVE/REJECT`

- [x] F2. **Code Quality Review** — `unspecified-high`
  Run `python -m pytest backend/tests/ -x -q -m "not integration"` + linter. Review all changed files for: `as any`/type ignoring, empty catches, console.log/print in prod, commented-out code, unused imports. Check AI slop: excessive comments, over-abstraction, generic names. Verify all async K8s calls use asyncio.to_thread().
  Output: `Tests [N pass/N fail] | Files [N clean/N issues] | VERDICT`

- [x] F3. **Real Manual QA** — `unspecified-high` (+ `playwright` skill)
  Start backend server. Execute EVERY QA scenario from EVERY task — follow exact steps, capture evidence. Test cross-task integration (Pareto mode + SSE + importance). Test edge cases: empty trials, stop during tuning, apply-best when idle.
  Output: `Scenarios [N/N pass] | Integration [N/N] | Edge Cases [N tested] | VERDICT`

- [x] F4. **Scope Fidelity Check** — `deep`
  For each task: read "What to do", read actual diff (git log/diff). Verify 1:1 — everything in spec was built, nothing beyond spec was built. Check "Must NOT do" compliance: no load_engine.py changes, no metrics_collector.py changes, no OpenShift YAML changes, no PVC additions.
  Output: `Tasks [N/N compliant] | Contamination [CLEAN/N issues] | VERDICT`

---

## Commit Strategy

- **T1**: `feat(models): expand TuningConfig and TuningTrial for tuner improvements` — models/load_test.py
- **T2**: `fix(tuner): implement /importance and /apply-best stub endpoints` — tuner.py, test_tuner.py
- **T3**: `feat(metrics): add Prometheus tuner metric definitions` — prometheus_metrics.py
- **T4**: `fix(frontend): fix tuner alert bug and expand config form` — TunerPage.jsx
- **T5**: `feat(tuner): expand search space with constraints` — auto_tuner.py
- **T6**: `feat(tuner): configurable eval params and warmup` — auto_tuner.py
- **T7**: `feat(tuner): add SSE broadcast infrastructure` — auto_tuner.py
- **T8**: `feat(tuner): ConfigMap snapshot and rollback mechanism` — auto_tuner.py
- **T9**: `feat(tuner): SQLite study persistence and warm-start` — auto_tuner.py
- **T10**: `feat(tuner): add /stream SSE endpoint` — tuner.py
- **T11**: `feat(tuner): MedianPruner with two-phase evaluation` — auto_tuner.py
- **T12**: `feat(tuner): multi-objective Pareto mode with NSGAIISampler` — auto_tuner.py, tuner.py
- **T13**: `feat(frontend): SSE integration, convergence chart, Pareto highlight` — TunerPage.jsx
- **T14**: `feat(tuner): emit Prometheus metrics during tuning` — auto_tuner.py
- **T15**: `test(tuner): comprehensive test additions for new features` — test_tuner.py

---

## Success Criteria

### Verification Commands
```bash
# Tests
python -m pytest backend/tests/test_tuner.py -v  # Expected: ALL PASS

# Stub fixes
curl -s http://localhost:8000/api/tuner/apply-best | jq '.success'  # Expected: false (no trials yet) with proper message
curl -s http://localhost:8000/api/tuner/importance  # Expected: {} (no trials yet, not hardcoded)

# Pareto mode
curl -s -X POST http://localhost:8000/api/tuner/start -H 'Content-Type: application/json' -d '{"objective":"pareto","n_trials":2}' | jq '.success'  # Expected: true

# SSE stream
curl -N http://localhost:8000/api/tuner/stream  # Expected: SSE events during tuning

# Prometheus
curl -s http://localhost:8000/metrics | grep "vllm_optimizer_tuner"  # Expected: 3+ metrics
```

### Final Checklist
- [x] 기존 단일목적 모드 (tps/latency/balanced) 정상 작동
- [x] Pareto 모드 Pareto front 반환
- [x] MedianPruner pruned trial 표시
- [x] SQLite 영속성 (환경변수 설정 시)
- [x] ConfigMap 롤백 (타임아웃 시)
- [x] SSE 실시간 trial 이벤트
- [x] 수렴 그래프 + Pareto 하이라이트
- [x] Prometheus 메트릭 3개
- [x] load_engine.py, metrics_collector.py, OpenShift YAML 미변경
