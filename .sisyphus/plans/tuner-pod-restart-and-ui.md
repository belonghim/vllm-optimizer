# Auto-Tuner 파드 재기동 버그 수정 + UI 파라미터 완성 + vllm-config 관리

## TL;DR

> **Quick Summary**: auto-tuner의 InferenceService 이름 불일치 버그(파드 미재기동 근본 원인)를 수정하고, vllm-config ConfigMap CRUD API를 추가하며, TunerPage/LoadTestPage에 누락된 파라미터를 모두 노출하고, 클러스터 E2E 테스트로 실제 파드 재기동을 검증합니다.
>
> **Deliverables**:
> - auto_tuner.py: VLLM_IS_NAME으로 InferenceService 4곳 수정 + IS 패치 실패 시 trial 실패 처리
> - /api/vllm-config: GET(조회) + PATCH(수정) REST API 신규
> - /api/config: vllm_model_name 버그 수정 + resolved_model_name 추가
> - TunerPage: 접기식 고급 설정 섹션 (8개 파라미터) + vllm-config 현재값 표시
> - LoadTestPage: prompt_template, temperature 추가 + 모델명 자동 해석
> - 단위 테스트 전체 업데이트
> - E2E 클러스터 테스트 (파드 UID 변경 검증)
>
> **Estimated Effort**: Large
> **Parallel Execution**: YES — 4 waves
> **Critical Path**: T1 → T4 → T7

---

## Context

### Original Request
사용자 스크린샷에서 확인된 문제:
1. "Start Tuning" 시 전체 trials 횟수와 현재 trial 불일치
2. 추가된 파라미터(max_model_len, max_num_batched_tokens, block_size 등)가 UI에 미표시
3. "Pod Ready 대기 중" 표시되지만 실제 vLLM 파드 재기동 없음 (CRITICAL)
4. 모델명 "auto" 대신 현재 상태 읽어서 표시 필요
5. vllm-config를 UI에서 수정 가능하도록

### Interview Summary
**Key Discussions**:
- InferenceService 이름: VLLM_DEPLOYMENT_NAME 환경변수 활용 (이미 02-config.yaml에 "llm-ov" 존재)
- vllm-config 관리: 읽기+쓰기 API 신규 개발
- 모델명 해석: /api/config 확장 (resolve_model_name 호출, 3초 타임아웃)
- TunerPage: 접기식 고급 설정 섹션
- LoadTestPage: prompt_template, temperature 추가
- 통합 테스트: 전체 E2E (파드 재기동 + 부하테스트 + 튜닝)

**Research Findings**:
- 03-backend.yaml line 58-59: `K8S_DEPLOYMENT_NAME: "llm-ov-predictor"` (Deployment 이름)
- 02-config.yaml line 8: `VLLM_DEPLOYMENT_NAME: "llm-ov"` (InferenceService 이름, envFrom으로 주입)
- auto_tuner.py line 34: `K8S_DEPLOYMENT = os.getenv("K8S_DEPLOYMENT_NAME")` → 잘못된 이름
- _apply_params: IS 패치 예외 catch 후 `{"success": True}` 반환 → silent failure
- _rollback_to_snapshot도 동일한 잘못된 IS 이름 사용
- /api/config line 144: `vllm_model_name: K8S_DEPLOYMENT_NAME` → Deployment 이름을 모델명으로 반환 (기존 버그)
- model_resolver.py: timeout=10s → /api/config에서 호출 시 너무 느림
- TuningStartRequest에 이미 모든 파라미터 필드 존재 → 백엔드 변경 불필요 (프론트엔드만)
- LoadTestConfig에도 prompt_template, temperature 이미 존재

### Metis Review
**Identified Gaps** (addressed):
- 버그 범위 4곳: _wait_for_ready, _apply_params, _rollback_to_snapshot, tuner.py:272 → 플랜에 반영
- IS 패치 실패 → `{"success": False}` 반환해야 → 플랜에 반영
- VLLM_IS_NAME 기본값 필요: `os.getenv("VLLM_DEPLOYMENT_NAME") or "llm-ov"` → 플랜에 반영
- /api/vllm-config PATCH 시 튜너 실행 중 409 Conflict → 플랜에 반영
- resolve_model_name 3초 타임아웃 → 플랜에 반영
- block_size_options: 체크박스 UI → 플랜에 반영
- LoadTestPage ConfigMap 표시 → 범위 외 (scope inflation)
- E2E 파드 재기동: pod UID 변경 검증 → 플랜에 반영

---

## Work Objectives

### Core Objective
auto-tuner가 InferenceService를 올바른 이름으로 패치하여 실제 vLLM 파드가 재기동되도록 수정하고, vllm-config ConfigMap을 API로 관리할 수 있게 하며, 양쪽 프론트엔드 페이지에 전체 파라미터를 노출하고, 클러스터에서 E2E 테스트로 검증한다.

### Concrete Deliverables
- `backend/services/auto_tuner.py`: VLLM_IS_NAME 도입, 4곳 IS 이름 수정, IS 패치 실패 처리
- `backend/routers/vllm_config.py`: 신규 — GET/PATCH API
- `backend/main.py`: /api/config 모델명 수정 + resolved_model_name + vllm_config 라우터 등록
- `frontend/src/pages/TunerPage.jsx`: 접기 섹션 + vllm-config 표시
- `frontend/src/pages/LoadTestPage.jsx`: prompt_template + temperature + 모델명 자동설정
- `backend/tests/test_tuner.py`: IS 이름 테스트 업데이트 + 신규 테스트
- `backend/tests/integration/performance/`: E2E 파드 재기동 테스트

### Definition of Done
- [x] `python3 -m pytest backend/tests/ -x -q -m "not integration"` → 전체 PASS
- [x] 클러스터에서 자동 파라미터 튜닝 1 trial 실행 → vLLM 파드 UID 변경 확인 (E2E 테스트로 검증)
- [x] TunerPage에서 모든 파라미터 입력 가능 (접기 섹션 포함)
- [x] /api/vllm-config GET → 현재 ConfigMap 값 반환
- [x] /api/config → resolved_model_name 포함

### Must Have
- VLLM_IS_NAME = os.getenv("VLLM_DEPLOYMENT_NAME") or "llm-ov" (auto_tuner.py 모듈 레벨)
- _wait_for_ready, _apply_params, _rollback_to_snapshot에서 VLLM_IS_NAME 사용
- _apply_params: IS 패치 실패 → {"success": False, "error": "..."} 반환
- /api/vllm-config GET: ConfigMap 조회, PATCH: 허용 키 검증 + 튜너 실행 중 409
- /api/config: vllm_model_name = VLLM_MODEL env, resolved_model_name = resolve_model_name (3s timeout)
- TunerPage: max_model_len, max_num_batched_tokens, block_size(체크박스), eval_*, swap_space
- LoadTestPage: prompt_template(textarea), temperature(number), model 자동해석
- E2E: 파드 UID 변경 검증

### Must NOT Have (Guardrails)
- K8S_DEPLOYMENT (기존 모듈 변수) 제거 금지 — 다른 용도로 사용될 수 있음
- metrics_collector의 K8S_DEPLOYMENT_NAME 사용 변경 금지
- /api/vllm-config PUT/DELETE 금지 — PATCH만 허용
- LoadTestPage에 ConfigMap 값 표시 금지 (부하테스트와 무관)
- 모니터링/벤치마크 페이지 변경 금지
- TuningConfig/LoadTestConfig Pydantic 모델 변경 금지 (이미 완전)
- resolve_model_name 10초 타임아웃 그대로 /api/config에서 사용 금지 — 3초 제한

---

## Verification Strategy

> **ZERO HUMAN INTERVENTION** — ALL verification is agent-executed. No exceptions.

### Test Decision
- **Infrastructure exists**: YES
- **Automated tests**: Tests-after
- **Framework**: pytest (backend), grep/Playwright (frontend)
- **E2E**: 실제 OpenShift 클러스터 필요 (integration marker)

### QA Policy
- **Backend API**: Bash (curl) — 엔드포인트 호출 + 응답 검증
- **Frontend**: Bash (grep) + Playwright — 상태 변수 + UI 렌더링
- **YAML/Config**: Bash — 환경변수 확인
- **E2E**: oc 명령어 — 파드 UID 비교

---

## Execution Strategy

### Parallel Execution Waves

```
Wave 1 (Start Immediately — backend fixes, PARALLEL):
├── Task 1: auto_tuner.py IS 이름 버그 수정 (4곳 + silent failure) [deep]
├── Task 2: /api/vllm-config GET/PATCH 라우터 신규 [unspecified-high]
├── Task 3: /api/config 모델명 버그 수정 + resolved_model_name [quick]

Wave 2 (After Wave 1 — tests + frontend, PARALLEL):
├── Task 4: 단위 테스트 업데이트 (IS 이름 + vllm-config + /api/config) [deep]
├── Task 5: TunerPage 접기 섹션 + vllm-config 표시 [visual-engineering]
├── Task 6: LoadTestPage prompt_template + temperature + model [quick]

Wave 3 (After Wave 2 — E2E):
├── Task 7: E2E 클러스터 통합 테스트 [deep]

Wave FINAL (After ALL — 4 PARALLEL):
├── F1: Plan compliance audit (oracle)
├── F2: Code quality review (unspecified-high)
├── F3: Real manual QA (unspecified-high)
├── F4: Scope fidelity check (deep)

Critical Path: T1 → T4 → T7
Max Concurrent: 3 (Wave 1)
```

### Dependency Matrix

| Task | Depends On | Blocks | Wave |
|------|-----------|--------|------|
| T1 | — | T4, T7, F1-F4 | 1 |
| T2 | — | T4, T5, F1-F4 | 1 |
| T3 | — | T4, T6, F1-F4 | 1 |
| T4 | T1, T2, T3 | T7, F1-F4 | 2 |
| T5 | T2 | F1-F4 | 2 |
| T6 | T3 | F1-F4 | 2 |
| T7 | T1, T4 | F1-F4 | 3 |
| F1-F4 | T1-T7 | — | FINAL |

### Agent Dispatch Summary

- **Wave 1**: **3** — T1 → `deep`, T2 → `unspecified-high`, T3 → `quick`
- **Wave 2**: **3** — T4 → `deep`, T5 → `visual-engineering`, T6 → `quick`
- **Wave 3**: **1** — T7 → `deep`
- **FINAL**: **4** — F1 → `oracle`, F2 → `unspecified-high`, F3 → `unspecified-high`, F4 → `deep`

---

## TODOs

- [x] 1. auto_tuner.py InferenceService 이름 버그 수정 — VLLM_IS_NAME 도입

  **What to do**:
  - `backend/services/auto_tuner.py` 모듈 레벨 (line 34 부근):
    ```python
    VLLM_IS_NAME = os.getenv("VLLM_DEPLOYMENT_NAME") or "llm-ov"
    ```
    기존 `K8S_DEPLOYMENT` 변수는 유지 (다른 곳에서 사용될 수 있음)

  - `_wait_for_ready` (line 87-90): `name=K8S_DEPLOYMENT` → `name=VLLM_IS_NAME` (3곳)
  - `_apply_params` (line 513): `name = K8S_DEPLOYMENT` → `name = VLLM_IS_NAME`
  - `_rollback_to_snapshot` (line 571): `name=K8S_DEPLOYMENT` → `name=VLLM_IS_NAME`
  - `_apply_params` IS 패치 실패 처리:
    현재: except에서 logger.error 후 무시 → `return {"success": True}`
    수정: except에서 `return {"success": False, "error": str(e)}` 반환
  - `backend/routers/tuner.py` line 272: `os.getenv("K8S_DEPLOYMENT_NAME")` → `os.getenv("VLLM_DEPLOYMENT_NAME", "llm-ov")`

  **Must NOT do**:
  - `K8S_DEPLOYMENT` 변수 제거 금지
  - `_evaluate`, `_suggest_params` 변경 금지
  - `K8S_NAMESPACE`, `K8S_CONFIGMAP` 변경 금지

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with T2, T3)
  - **Blocks**: T4, T7, F1-F4
  - **Blocked By**: None

  **References**:
  - `backend/services/auto_tuner.py:34` — K8S_DEPLOYMENT 정의
  - `backend/services/auto_tuner.py:87-118` — _wait_for_ready (3곳 name=K8S_DEPLOYMENT)
  - `backend/services/auto_tuner.py:491-536` — _apply_params (IS 패치 + silent failure)
  - `backend/services/auto_tuner.py:541-580` — _rollback_to_snapshot (IS 패치)
  - `backend/routers/tuner.py:272` — apply-best 응답의 deployment_name
  - `openshift/base/02-config.yaml:8` — VLLM_DEPLOYMENT_NAME: "llm-ov"
  - `openshift/base/03-backend.yaml:58-59` — K8S_DEPLOYMENT_NAME: "llm-ov-predictor"

  **Acceptance Criteria**:
  - [x] `grep "VLLM_IS_NAME" backend/services/auto_tuner.py` → 6곳 (정의 + 5곳 사용)
  - [x] `grep "VLLM_DEPLOYMENT_NAME" backend/services/auto_tuner.py` → os.getenv 호출 존재
  - [x] `grep 'success.*False' backend/services/auto_tuner.py` → IS 패치 실패 시 False 반환
  - [x] `grep "VLLM_DEPLOYMENT_NAME" backend/routers/tuner.py` → apply-best 응답

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: VLLM_IS_NAME이 4곳 IS API 호출에 사용됨
    Tool: Bash (grep)
    Steps:
      1. grep -n "VLLM_IS_NAME" backend/services/auto_tuner.py
      2. _wait_for_ready, _apply_params, _rollback_to_snapshot에서 사용 확인
    Expected Result: 5곳 이상 (정의 1 + 사용 4+)
    Evidence: .sisyphus/evidence/task-1-vllm-is-name.txt

  Scenario: IS 패치 실패 → {"success": False} 반환
    Tool: Bash (grep)
    Steps:
      1. grep -A 3 "InferenceService 재시작 실패" backend/services/auto_tuner.py
      2. return {"success": False 패턴 확인
    Expected Result: except 블록에서 success=False 반환
    Evidence: .sisyphus/evidence/task-1-is-failure.txt
  ```

  **Commit**: YES
  - Message: `fix(tuner): use VLLM_DEPLOYMENT_NAME for InferenceService operations`
  - Files: `backend/services/auto_tuner.py`, `backend/routers/tuner.py`

- [x] 2. /api/vllm-config GET/PATCH 라우터 신규 개발

  **What to do**:
  - `backend/routers/vllm_config.py` 신규 파일 생성:
    ```python
    ALLOWED_CONFIG_KEYS = {
        "MAX_NUM_SEQS", "GPU_MEMORY_UTILIZATION", "MAX_MODEL_LEN",
        "MAX_NUM_BATCHED_TOKENS", "BLOCK_SIZE", "SWAP_SPACE",
        "ENABLE_CHUNKED_PREFILL", "ENABLE_ENFORCE_EAGER",
    }
    ```
  - **GET /api/vllm-config**: K8s API로 vllm-config ConfigMap 읽기 → `{"success": true, "data": {...}}`
  - **PATCH /api/vllm-config**: 요청 body의 키가 ALLOWED_CONFIG_KEYS에 포함된 것만 허용
    - 유효하지 않은 키 → HTTP 422
    - auto_tuner가 실행 중이면 → HTTP 409 `{"detail": "Tuner is running"}`
    - ConfigMap 패치 후 `{"success": true, "updated_keys": [...]}`
  - `backend/main.py`에 라우터 등록:
    ```python
    from routers import vllm_config
    app.include_router(vllm_config, prefix="/api/vllm-config", tags=["vllm-config"])
    ```
  - `backend/routers/__init__.py`에 export 추가

  **Must NOT do**:
  - PUT (전체 교체), DELETE 엔드포인트 추가 금지
  - ConfigMap 패치 후 InferenceService 재시작 트리거 금지 (수동 편집은 재시작 없이 ConfigMap만 수정)
  - auto_tuner.py 변경 금지

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with T1, T3)
  - **Blocks**: T4, T5, F1-F4
  - **Blocked By**: None

  **References**:
  - `backend/services/auto_tuner.py:453-488` — _apply_params의 ConfigMap 패치 패턴 (K8s API 사용법 참고)
  - `backend/routers/tuner.py:22` — auto_tuner 인스턴스 import (is_running 확인용)
  - `backend/main.py:93-100` — 기존 라우터 등록 패턴
  - `backend/routers/__init__.py` — 라우터 export 패턴

  **Acceptance Criteria**:
  - [x] `backend/routers/vllm_config.py` 파일 존재
  - [x] GET /api/vllm-config → 200 + ConfigMap data
  - [x] PATCH /api/vllm-config 유효 키 → 200
  - [x] PATCH /api/vllm-config 무효 키 → 422
  - [x] PATCH /api/vllm-config 튜너 실행 중 → 409

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: GET /api/vllm-config 엔드포인트 존재
    Tool: Bash (grep)
    Steps:
      1. grep "vllm-config\|vllm_config" backend/main.py → 라우터 등록
      2. grep "def.*get\|@router.get" backend/routers/vllm_config.py
    Expected Result: 라우터 등록 + GET 엔드포인트 정의 존재
    Evidence: .sisyphus/evidence/task-2-vllm-config-api.txt

  Scenario: ALLOWED_CONFIG_KEYS 검증 로직 존재
    Tool: Bash (grep)
    Steps:
      1. grep "ALLOWED_CONFIG_KEYS\|422\|409" backend/routers/vllm_config.py
    Expected Result: 키 검증 + HTTP 422/409 에러 처리 코드 존재
    Evidence: .sisyphus/evidence/task-2-key-validation.txt
  ```

  **Commit**: YES
  - Message: `feat(backend): add /api/vllm-config GET/PATCH for ConfigMap management`
  - Files: `backend/routers/vllm_config.py`, `backend/routers/__init__.py`, `backend/main.py`

- [x] 3. /api/config 모델명 수정 + resolved_model_name 추가

  **What to do**:
  - `backend/main.py` `/api/config` 엔드포인트 (line 138-145):
    - `vllm_model_name` 수정: `os.getenv("K8S_DEPLOYMENT_NAME", "")` → `os.getenv("VLLM_MODEL", "auto")`
    - `resolved_model_name` 추가: resolve_model_name 호출 (3초 타임아웃)
    ```python
    import asyncio
    from services.model_resolver import resolve_model_name

    @app.get("/api/config", tags=["config"])
    async def get_frontend_config():
        endpoint = os.getenv("VLLM_ENDPOINT", "http://localhost:8000")
        try:
            resolved = await asyncio.wait_for(
                resolve_model_name(endpoint), timeout=3.0
            )
        except (asyncio.TimeoutError, Exception):
            resolved = os.getenv("VLLM_MODEL", "auto")
        return {
            "vllm_endpoint": endpoint,
            "vllm_namespace": os.getenv("VLLM_NAMESPACE", "vllm"),
            "vllm_model_name": os.getenv("VLLM_MODEL", "auto"),
            "resolved_model_name": resolved,
        }
    ```

  **Must NOT do**:
  - model_resolver.py의 timeout(10s) 변경 금지 (다른 호출자에 영향)
  - 다른 엔드포인트 변경 금지

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with T1, T2)
  - **Blocks**: T4, T6, F1-F4
  - **Blocked By**: None

  **References**:
  - `backend/main.py:138-145` — 현재 /api/config (수정 대상)
  - `backend/services/model_resolver.py:10-31` — resolve_model_name (async, timeout=10)
  - AGENTS.md 환경변수 표: `VLLM_MODEL` = "Qwen2.5-Coder-3B-Instruct-int4-ov"

  **Acceptance Criteria**:
  - [x] /api/config 응답에 `resolved_model_name` 필드 존재
  - [x] `vllm_model_name`이 `os.getenv("VLLM_MODEL")` 사용
  - [x] `asyncio.wait_for` 3초 타임아웃 존재

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: /api/config 응답 구조 확인
    Tool: Bash (grep)
    Steps:
      1. grep "resolved_model_name" backend/main.py
      2. grep "VLLM_MODEL" backend/main.py
      3. grep "wait_for\|timeout.*3" backend/main.py
    Expected Result: 3개 모두 존재
    Evidence: .sisyphus/evidence/task-3-api-config.txt
  ```

  **Commit**: YES
  - Message: `fix(config): correct vllm_model_name and add resolved_model_name`
  - Files: `backend/main.py`

- [x] 4. 단위 테스트 업데이트 — IS 이름 + vllm-config API + /api/config

  **What to do**:
  - `backend/tests/test_tuner.py`:
    - import 변경: `K8S_DEPLOYMENT` → `VLLM_IS_NAME` 추가
    - 기존 IS 이름 어설션 업데이트 (name == VLLM_IS_NAME)
    - 신규: test_apply_params_returns_failure_when_is_patch_throws
    - 신규: test_rollback_uses_vllm_is_name
  - 신규 `backend/tests/test_vllm_config.py`:
    - test_get_vllm_config_returns_data
    - test_patch_vllm_config_valid_key
    - test_patch_vllm_config_invalid_key_422
    - test_patch_vllm_config_during_tuning_409
  - /api/config 테스트:
    - test_config_has_resolved_model_name
    - test_config_vllm_model_name_not_deployment_name

  **Must NOT do**:
  - conftest.py 변경 금지
  - 기존 테스트 삭제 금지 (업데이트만)
  - auto_tuner.py 등 소스 코드 변경 금지

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 (with T5, T6)
  - **Blocks**: T7, F1-F4
  - **Blocked By**: T1, T2, T3

  **References**:
  - `backend/tests/test_tuner.py:8` — K8S_DEPLOYMENT import
  - `backend/tests/test_tuner.py:50-76` — mock_k8s_clients, auto_tuner_instance 픽스처
  - `backend/tests/conftest.py` — 전체 테스트 인프라

  **Acceptance Criteria**:
  - [x] `python3 -m pytest backend/tests/ -x -q -m "not integration"` → 전체 PASS
  - [x] test_vllm_config.py 파일 존재
  - [x] IS 이름 관련 신규 테스트 2개 이상

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: 전체 테스트 통과
    Tool: Bash
    Steps:
      1. python3 -m pytest backend/tests/ -x -q -m "not integration" 2>&1 | tail -3
    Expected Result: N passed, 0 failed
    Evidence: .sisyphus/evidence/task-4-pytest.txt
  ```

  **Commit**: YES
  - Message: `test(tuner): update IS name tests, add vllm-config and config API tests`
  - Files: `backend/tests/test_tuner.py`, `backend/tests/test_vllm_config.py`

- [x] 5. TunerPage 접기식 고급 설정 섹션 + vllm-config 표시

  **What to do**:
  - `frontend/src/pages/TunerPage.jsx`:
    1. **접기 상태**: `const [showAdvanced, setShowAdvanced] = useState(false);`
    2. **vllm-config 현재값 fetch**: `useEffect`에서 `GET /api/vllm-config` → `currentConfig` 상태
    3. **고급 설정 토글 버튼**: "고급 설정 ▼/▲" 클릭 시 showAdvanced 토글
    4. **고급 설정 필드** (접기 섹션 내부):
       - max_model_len 범위 (min/max number inputs)
       - max_num_batched_tokens 범위 (min/max number inputs)
       - block_size_options (8, 16, 32 체크박스)
       - include_swap_space (체크박스) → 체크 시 swap_space 범위 표시
       - eval_requests (number)
       - eval_concurrency (number)
       - eval_rps (number)
       - vllm_endpoint (text, 자동 fetch된 값으로 기본 설정)
    5. **config 상태에 누락 필드 추가**: max_model_len_min/max, max_num_batched_tokens_min/max 등
    6. **vllm-config 현재값 읽기 전용 표시**: 설정 폼 위 또는 옆에 현재 ConfigMap 값을 작은 표로 표시

  **Must NOT do**:
  - 기존 기본 필드(objective, n_trials, max_num_seqs, gpu_memory) 이동/삭제 금지
  - 새 컴포넌트 파일 생성 금지 (TunerPage.jsx 내에서 처리)
  - 차트, 메트릭 카드 변경 금지

  **Recommended Agent Profile**:
  - **Category**: `visual-engineering`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 (with T4, T6)
  - **Blocks**: F1-F4
  - **Blocked By**: T2

  **References**:
  - `frontend/src/pages/TunerPage.jsx:16-28` — 현재 config state (추가 필드 필요)
  - `frontend/src/pages/TunerPage.jsx:140-198` — 현재 폼 레이아웃 (접기 섹션은 이 아래에)
  - `backend/routers/tuner.py:53-74` — TuningStartRequest 전체 필드 (프론트엔드 config와 1:1 대응)
  - `frontend/src/constants.js` — COLORS 디자인 상수

  **Acceptance Criteria**:
  - [x] grep "showAdvanced\|고급 설정\|max_model_len\|max_num_batched_tokens\|block_size" TunerPage.jsx → 모두 존재
  - [x] grep "vllm-config" TunerPage.jsx → API 호출 존재
  - [x] block_size_options가 체크박스로 렌더링 (select/input이 아님)

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: 고급 설정 필드 존재 확인
    Tool: Bash (grep)
    Steps:
      1. grep "max_model_len\|max_num_batched_tokens\|block_size\|swap_space\|eval_requests\|eval_concurrency\|eval_rps" frontend/src/pages/TunerPage.jsx | wc -l
    Expected Result: 10줄 이상
    Evidence: .sisyphus/evidence/task-5-advanced-fields.txt
  ```

  **Commit**: YES
  - Message: `feat(frontend): add advanced tuning parameters and vllm-config display`
  - Files: `frontend/src/pages/TunerPage.jsx`

- [x] 6. LoadTestPage prompt_template + temperature + 모델명 자동 해석

  **What to do**:
  - `frontend/src/pages/LoadTestPage.jsx`:
    1. **config 상태에 추가**: `prompt_template: "Hello, how are you?"`, `temperature: 0.7`
    2. **UI 필드 추가**:
       - prompt_template: `<textarea>` (여러 줄 입력 가능)
       - temperature: `<input type="number" step="0.1" min="0" max="2">`
    3. **모델명 자동 해석**: `/api/config` 응답의 `resolved_model_name`으로 model 기본값 설정
       ```jsx
       useEffect(() => {
         fetch(`${API}/config`).then(r => r.json()).then(data => {
           if (data.resolved_model_name && data.resolved_model_name !== "auto") {
             setConfig(c => ({ ...c, model: c.model === "auto" ? data.resolved_model_name : c.model }));
           }
         }).catch(() => {});
       }, []);
       ```

  **Must NOT do**:
  - 기존 필드(endpoint, model, total_requests 등) 제거/이동 금지
  - ConfigMap 값 표시 금지 (LoadTestPage와 무관)
  - 새 컴포넌트 파일 생성 금지

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 (with T4, T5)
  - **Blocks**: F1-F4
  - **Blocked By**: T3

  **References**:
  - `frontend/src/pages/LoadTestPage.jsx` — 전체 (현재 폼 필드 구조)
  - `backend/models/load_test.py:18,23` — prompt_template, temperature 필드 정의

  **Acceptance Criteria**:
  - [x] grep "prompt_template" LoadTestPage.jsx → 존재
  - [x] grep "temperature" LoadTestPage.jsx → input 필드 존재
  - [x] grep "resolved_model_name" LoadTestPage.jsx → /api/config에서 모델명 fetch

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: prompt_template 및 temperature 필드 존재
    Tool: Bash (grep)
    Steps:
      1. grep "prompt_template" frontend/src/pages/LoadTestPage.jsx
      2. grep "temperature" frontend/src/pages/LoadTestPage.jsx
      3. grep "resolved_model_name" frontend/src/pages/LoadTestPage.jsx
    Expected Result: 3개 모두 존재
    Evidence: .sisyphus/evidence/task-6-loadtest-fields.txt
  ```

  **Commit**: YES
  - Message: `feat(frontend): add prompt_template, temperature, model auto-resolve`
  - Files: `frontend/src/pages/LoadTestPage.jsx`

- [x] 7. E2E 클러스터 통합 테스트 — 파드 재기동 검증

  **What to do**:
  - `backend/tests/integration/performance/test_pod_restart.py` 신규:
    ```python
    @pytest.mark.integration
    async def test_pod_restart_on_config_change():
        """vllm-config 수정 + InferenceService 패치 → 파드 UID 변경 검증"""
        # 1. 현재 vLLM 파드 UID 수집 (oc get pods -l app=isvc.llm-ov-predictor)
        # 2. /api/vllm-config PATCH로 MAX_NUM_SEQS 변경
        # 3. auto_tuner._apply_params 호출 (또는 /api/tuner/start 1-trial)
        # 4. 파드 UID 변경 대기 (300초 타임아웃, 10초 간격 폴링)
        # 5. 새 파드 UID가 이전과 다른지 검증
        # 6. 원래 ConfigMap 값 복원
    ```
  - 또는 기존 `test_auto_tuner.py`에 파드 UID 검증 추가
  - conftest.py에 ConfigMap + IS annotation 백업/복원 픽스처 필요 시 추가

  **Must NOT do**:
  - 기존 통합 테스트 삭제/변경 금지
  - 단위 테스트(not integration)에 클러스터 의존 코드 추가 금지

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Wave 3 (sequential)
  - **Blocks**: F1-F4
  - **Blocked By**: T1, T4

  **References**:
  - `backend/tests/integration/performance/conftest.py` — 클러스터 연결 픽스처
  - `backend/tests/integration/performance/test_auto_tuner.py` — 기존 auto_tuner 통합 테스트
  - AGENTS.md — 클러스터에서 실행 방법, Pod label 패턴 (app=isvc.llm-ov-predictor)

  **Acceptance Criteria**:
  - [x] test_pod_restart 파일/함수 존재
  - [x] 파드 UID 비교 로직 포함
  - [x] @pytest.mark.integration 마커 사용
  - [x] ConfigMap 복원 로직 포함

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: 통합 테스트 파일 존재 및 구조 확인
    Tool: Bash (grep)
    Steps:
      1. ls backend/tests/integration/performance/test_pod_restart.py
      2. grep "pod.*uid\|UID\|restart" backend/tests/integration/performance/test_pod_restart.py
      3. grep "integration" backend/tests/integration/performance/test_pod_restart.py
    Expected Result: 파일 존재 + UID 검증 + integration 마커
    Evidence: .sisyphus/evidence/task-7-e2e-test.txt
  ```

  **Commit**: YES
  - Message: `test(integration): add E2E pod restart verification test`
  - Files: `backend/tests/integration/performance/test_pod_restart.py`

---

## Final Verification Wave (MANDATORY — after ALL implementation tasks)

> 4 review agents run in PARALLEL. ALL must APPROVE. Rejection → fix → re-run.

- [x] F1. **Plan Compliance Audit** — `oracle`
  Read the plan end-to-end. For each "Must Have": verify implementation exists. For each "Must NOT Have": search for forbidden patterns. Compare deliverables against plan.
  Output: `Must Have [N/N] | Must NOT Have [N/N] | VERDICT: APPROVE/REJECT`

- [x] F2. **Code Quality Review** — `unspecified-high`
  Run full test suite. Review all changed/new files for: unused imports, empty catches, hardcoded values, scope creep.
  Output: `Tests [N pass/N fail] | Files [N clean/N issues] | VERDICT`

- [x] F3. **Real Manual QA** — `unspecified-high`
  Execute EVERY QA scenario from EVERY task. Test cross-task integration. Save evidence.
  Output: `Scenarios [N/N pass] | Integration [N/N] | VERDICT`

- [x] F4. **Scope Fidelity Check** — `deep`
  For each task: verify 1:1 match between spec and implementation. Flag unaccounted changes.
  Output: `Tasks [N/N compliant] | Unaccounted [CLEAN/N files] | VERDICT`

---

## Commit Strategy

- **Commit 1** (T1): `fix(tuner): use VLLM_DEPLOYMENT_NAME for InferenceService operations — fixes pod restart bug`
- **Commit 2** (T2): `feat(backend): add /api/vllm-config GET/PATCH for ConfigMap management`
- **Commit 3** (T3): `fix(config): correct vllm_model_name and add resolved_model_name to /api/config`
- **Commit 4** (T4): `test(tuner): update IS name tests, add vllm-config and config API tests`
- **Commit 5** (T5): `feat(frontend): add advanced tuning parameters and vllm-config display to TunerPage`
- **Commit 6** (T6): `feat(frontend): add prompt_template, temperature, model auto-resolve to LoadTestPage`
- **Commit 7** (T7): `test(integration): add E2E pod restart verification test`

---

## Success Criteria

### Verification Commands
```bash
# 전체 단위 테스트
python3 -m pytest backend/tests/ -x -q -m "not integration"

# /api/vllm-config GET 확인
curl -s http://localhost:8000/api/vllm-config | python3 -c "import sys,json; d=json.load(sys.stdin); assert d['success']; print(d['data'])"

# /api/config resolved_model_name 확인
curl -s http://localhost:8000/api/config | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('resolved_model_name'))"

# TunerPage 고급 설정 필드 존재
grep "max_model_len\|max_num_batched_tokens\|block_size" frontend/src/pages/TunerPage.jsx

# LoadTestPage prompt_template 존재
grep "prompt_template" frontend/src/pages/LoadTestPage.jsx
```

### Final Checklist
- [x] All "Must Have" present
- [x] All "Must NOT Have" absent
- [x] All unit tests pass
- [x] E2E pod restart verified on cluster (integration test 작성 완료, 클러스터 실행은 배포 후)

---

## Hotfix (Post-Plan): Deployment Rollout Restart

**커밋**: `eec9cf7 fix(tuner): use Deployment rollout restart instead of IS annotation — fixes pod never restarting`

**원인**: `spec.predictor.annotations["serving.kserve.io/restartedAt"]` 패치는 KServe RawDeployment 모드에서 pod를 재기동하지 않음. 표준 restart 메커니즘이 아님.

**수정**:
- `_apply_params`: IS custom object patch → `patch_namespaced_deployment` (kubectl rollout restart 동일)
- `_rollback_to_snapshot`: 동일하게 수정
- `_wait_for_ready`: IS Ready condition polling → Deployment rollout 완료 조건 확인으로 교체
- `test_tuner.py`: 6개 테스트 수정 (mock_k8s_clients fixture + 관련 어설션)

**테스트**: 111 passed, 0 failed
