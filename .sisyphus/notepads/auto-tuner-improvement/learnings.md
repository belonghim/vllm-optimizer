# Learnings — auto-tuner-improvement

## [2026-03-14] Session Init

### Key Architecture Facts
- `auto_tuner.py`: get_importance() **이미 구현됨** (303-309행), 라우터가 무시 중
- `auto_tuner.py`: _apply_params() **완전 작동 중**, 라우터가 미연결
- `test_tuner_apply_best_response`: success:False를 assert → stub 수정 전 **테스트 먼저 업데이트**
- `_suggest_params`: max_model_len categorical 필터링 시 빈 리스트 → ValueError 잠재 버그
- MedianPruner + multi-objective → Optuna에서 상호 배타적 (RuntimeError)
- WarmStartSampler: Optuna 3.5.x 미지원 → `study.enqueue_trial()` 사용
- max_num_batched_tokens >= max_num_seqs 강제 필요

### File Ownership (Wave별)
- T1: backend/models/load_test.py, backend/routers/tuner.py (모델 필드만)
- T2: backend/routers/tuner.py (stub 로직), backend/tests/test_tuner.py, frontend/src/pages/TunerPage.jsx (applyBest 버그)
- T3: backend/metrics/prometheus_metrics.py
- T4: frontend/src/pages/TunerPage.jsx (config form)
- T5~T15: backend/services/auto_tuner.py (핵심)

### Naming Conventions
- ConfigMap 키: 대문자 + 밑줄 (MAX_NUM_SEQS, GPU_MEMORY_UTILIZATION)
- Prometheus 메트릭: vllm_optimizer_ prefix
- K8s API: asyncio.to_thread() 필수

### Must NOT
- load_engine.py 수정 금지
- metrics_collector.py 수정 금지  
- LoadTestPage.jsx 수정 금지
- OpenShift YAML 수정 금지
- swap_space 기본 활성화 금지
 
- Implemented: backend/metrics/prometheus_metrics.py 3 new tuner metrics:
-   - vllm_optimizer_tuner_trials_total (Counter) with label 'status'
-   - vllm_optimizer_tuner_best_score (Gauge) with label 'objective'
-   - vllm_optimizer_tuner_trial_duration_seconds (Histogram)
- Verified: Python import check prints 'OK', tests ran (non-integration) and passed (68+ passing in prior run).
- No emission in auto_tuner.py yet (per plan: T14 will handle emission when wired).

## F3 Manual QA Results (2026-03-14)

### Prometheus metrics endpoint
- Prometheus metrics are at `/api/metrics` (NOT `/metrics` — that returns 404)
- Scenario 6 used `/metrics` which 404s; correct endpoint is `/api/metrics`
- All 3 tuner metrics exist: `vllm_optimizer_tuner_trials_total`, `vllm_optimizer_tuner_best_score`, `vllm_optimizer_tuner_trial_duration_seconds`
- Implementation is correct; QA scenario used wrong path
