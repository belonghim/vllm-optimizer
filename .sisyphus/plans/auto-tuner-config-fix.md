# Auto-Tuner 설정 불일치 수정 및 진행 상태 개선

## TL;DR

> **Quick Summary**: vLLM auto-tuner가 ConfigMap에 기록하지만 vLLM 프로세스에 전달되지 않는 3개 파라미터(헛튜닝), ENABLE_CHUNKED_PREFILL 셸 확장 버그, ENABLE_ENFORCE_EAGER 미연동 문제를 수정하고, 튜닝 trial 내부 단계별 SSE 진행 상태를 프론트엔드에 추가합니다.
>
> **Deliverables**:
> - vllm-runtime.yaml에 누락된 4개 파라미터 args 추가
> - vllm-config.yaml 템플릿에 신규 키 기본값 추가
> - CHUNKED_PREFILL False 시 빈 문자열("") 기록 버그 수정
> - ENFORCE_EAGER 튜닝 대상 추가 (suggest + apply)
> - Trial 내부 5단계 SSE phase 이벤트 브로드캐스트
> - 프론트엔드 TunerPage 단계별 상태 표시
> - 기존 단위 테스트 업데이트 + 신규 테스트 케이스
>
> **Estimated Effort**: Medium
> **Parallel Execution**: YES — 4 waves
> **Critical Path**: T2 → T3 → T5

---

## Context

### Original Request
사용자가 지적한 3가지 문제:
1. vllm-config ConfigMap에 수정하는 항목에 비해 openshift/dev-only에 설정 가능한 항목이 없음
2. 자동 파라미터 튜닝 진행 상태를 알 수 없음
3. vllm-config ConfigMap만 수정하고 파드 재기동/테스트 연동이 의심됨

### Interview Summary
**Key Discussions**:
- 헛튜닝 해결: 양쪽 모두 정비 (Runtime args 추가 + 튜너 유지)
- GPU 파라미터(gpu_memory_utilization, swap_space): 향후 GPU 환경 대비 유지
- CHUNKED_PREFILL 버그: 튜너에서 False 시 빈 문자열("") 사용, Runtime 셸 구문 유지
- ENFORCE_EAGER: Runtime args 추가 + 튜닝 대상 포함
- 진행 상태: SSE 세분화(5단계) + 프론트엔드 UI 개선
- 테스트: 기존 test_tuner.py 업데이트

**Research Findings**:
- vllm-runtime.yaml은 `envFrom: configMapRef`로 ConfigMap을 환경변수로 주입하고, 셸 변수 확장으로 vLLM args에 전달
- 파드 재기동 메커니즘은 정상 동작 확인: KServe `restartedAt` 어노테이션 패치 → InferenceService Ready 폴링
- `_evaluate`는 인스턴스 메서드이므로 `self._broadcast()` 직접 호출 가능
- test_tuner.py 428-429행에 `assert "ENABLE_ENFORCE_EAGER" not in patch_data` — ENFORCE_EAGER 추가 시 반드시 수정 필요

### Metis Review
**Identified Gaps** (addressed):
- 셸 확장 패턴: `max_num_batched_tokens`는 항상 제안되므로 `${VAR:-default}`, `block_size`/`swap_space`는 조건부이므로 `${VAR:+"--arg=${VAR}"}` → 플랜에 반영
- `ENABLE_ENFORCE_EAGER: "true"` → runtime args 추가 시 즉시 동작 변경 — `""` 로 변경하여 안전 배포
- `max_num_batched_tokens > max_model_len` 기존 제약 버그 — 별도 이슈, 범위 외
- SSE keepalive 600초 제한 — 프론트엔드 polling fallback 존재, 범위 외
- 기존 테스트 어설션 반전 필수 (line 429)

---

## Work Objectives

### Core Objective
auto-tuner가 조정하는 모든 파라미터가 실제 vLLM 프로세스에 전달되도록 Runtime YAML과 ConfigMap을 정비하고, CHUNKED_PREFILL 셸 확장 버그를 수정하며, 튜닝 진행 상태를 실시간으로 확인 가능하게 만든다.

### Concrete Deliverables
- `openshift/dev-only/vllm-runtime.yaml`: 4개 args 추가 (`--max-num-batched-tokens`, `--block-size`, `--swap-space`, `--enforce-eager`)
- `openshift/dev-only/vllm-config.yaml`: 3개 키 추가 (`MAX_NUM_BATCHED_TOKENS`, `BLOCK_SIZE`, `SWAP_SPACE`), `ENABLE_ENFORCE_EAGER` 기본값 `""` 변경
- `backend/services/auto_tuner.py`: CHUNKED_PREFILL `""` 수정 + ENFORCE_EAGER suggest/apply + 5단계 SSE phase 이벤트
- `frontend/src/pages/TunerPage.jsx`: currentPhase 상태 표시
- `backend/tests/test_tuner.py`: 기존 테스트 업데이트 + 신규 테스트 케이스

### Definition of Done
- [x] `python3 -m pytest backend/tests/ -x -q -m "not integration"` → 전체 PASS
- [x] `./kustomize build openshift/dev-only/` → exit code 0 (YAML valid 검증 완료, kustomize 바이너리 미설치)
- [x] `grep "block-size" openshift/dev-only/vllm-runtime.yaml` → 조건부 확장 패턴 확인
- [x] `grep "currentPhase" frontend/src/pages/TunerPage.jsx` → 상태 변수 존재

### Must Have
- MAX_NUM_BATCHED_TOKENS, BLOCK_SIZE, SWAP_SPACE가 vLLM 프로세스에 전달되는 Runtime args
- ENABLE_CHUNKED_PREFILL: False 시 빈 문자열("") 기록
- ENABLE_ENFORCE_EAGER: 튜닝 대상 (suggest + apply + ConfigMap 기록)
- Trial 내부 5단계 SSE phase 이벤트 (applying_config, restarting, waiting_ready, warmup, evaluating)
- 프론트엔드에서 현재 trial의 단계(phase) 표시
- 기존 test_tuner.py의 ENFORCE_EAGER 어설션 반전

### Must NOT Have (Guardrails)
- K8S_DEPLOYMENT_NAME / InferenceService 이름 불일치 수정 (범위 외). **주의**: KServe에서 InferenceService 이름(`llm-ov`)과 생성되는 Deployment/Service 이름(`llm-ov-predictor`)은 다름. `auto_tuner.py`의 `K8S_DEPLOYMENT`는 InferenceService API 호출에 사용되므로, 이 값이 InferenceService 이름과 일치해야 함 (Deployment 이름 아님). 이 이름 체계를 변경하거나 "수정"하려 하지 말 것.
- block_size, max_num_batched_tokens 범위, enforce_eager 토글 UI 폼 컨트롤 추가
- Prometheus 메트릭 신규 추가
- SSE event ID / 재연결 복구 / keepalive 확장
- `max_num_batched_tokens <= max_model_len` 제약 추가 (기존 이슈, 별도 처리)
- 수정 대상 외 파일 변경 (auto_tuner.py, tuner.py(?), vllm-runtime.yaml, vllm-config.yaml, TunerPage.jsx, test_tuner.py만 허용)
- 프론트엔드 progress bar, timeline 컴포넌트 — 단순 텍스트 상태 표시만

---

## Verification Strategy

> **ZERO HUMAN INTERVENTION** — ALL verification is agent-executed. No exceptions.

### Test Decision
- **Infrastructure exists**: YES
- **Automated tests**: Tests-after (기존 테스트 업데이트)
- **Framework**: pytest (backend), 프론트엔드는 grep 검증

### QA Policy
Every task MUST include agent-executed QA scenarios.
Evidence saved to `.sisyphus/evidence/task-{N}-{scenario-slug}.{ext}`.

- **YAML**: Use Bash (kustomize build) — 파싱 검증
- **Backend**: Use Bash (pytest) — 단위 테스트 실행
- **Frontend**: Use Bash (grep) + Playwright — 상태 변수 확인 및 UI 렌더링

---

## Execution Strategy

### Parallel Execution Waves

```
Wave 1 (Start Immediately — foundation, PARALLEL):
├── Task 1: OpenShift YAML 정비 (vllm-config.yaml + vllm-runtime.yaml) [quick]
├── Task 2: auto_tuner.py 파라미터 수정 (CHUNKED_PREFILL 빈 문자열 + ENFORCE_EAGER) [deep]

Wave 2 (After Task 2 — SSE phase 이벤트):
├── Task 3: auto_tuner.py SSE phase 이벤트 추가 (depends: T2) [unspecified-high]

Wave 3 (After Task 3 — frontend + tests, PARALLEL):
├── Task 4: TunerPage.jsx 단계별 상태 UI (depends: T3) [visual-engineering]
├── Task 5: test_tuner.py 테스트 업데이트 (depends: T2, T3) [deep]

Wave FINAL (After ALL tasks — verification, 4 PARALLEL):
├── Task F1: Plan compliance audit (oracle)
├── Task F2: Code quality review (unspecified-high)
├── Task F3: Real manual QA (unspecified-high)
├── Task F4: Scope fidelity check (deep)

Critical Path: T2 → T3 → T5
Parallel Speedup: ~40% faster than sequential
Max Concurrent: 2 (Waves 1 & 3)
```

### Dependency Matrix

| Task | Depends On | Blocks | Wave |
|------|-----------|--------|------|
| T1 | — | F1-F4 | 1 |
| T2 | — | T3, T5, F1-F4 | 1 |
| T3 | T2 | T4, T5, F1-F4 | 2 |
| T4 | T3 | F1-F4 | 3 |
| T5 | T2, T3 | F1-F4 | 3 |
| F1-F4 | T1-T5 | — | FINAL |

### Agent Dispatch Summary

- **Wave 1**: **2** — T1 → `quick`, T2 → `deep`
- **Wave 2**: **1** — T3 → `unspecified-high`
- **Wave 3**: **2** — T4 → `visual-engineering`, T5 → `deep`
- **FINAL**: **4** — F1 → `oracle`, F2 → `unspecified-high`, F3 → `unspecified-high`, F4 → `deep`

---

## TODOs

- [x] 1. OpenShift YAML 정비 — vllm-runtime.yaml + vllm-config.yaml

  **What to do**:
  - `openshift/dev-only/vllm-runtime.yaml`의 vLLM 기동 명령(args)에 누락된 4개 파라미터 추가:
    ```bash
    # 항상 존재 (기본값 포함) — max_num_batched_tokens는 튜너가 항상 제안
    --max-num-batched-tokens=${MAX_NUM_BATCHED_TOKENS:-2048} \
    # 조건부 (빈 문자열이면 생략) — block_size, swap_space는 튜너가 조건부 제안
    ${BLOCK_SIZE:+"--block-size=${BLOCK_SIZE}"} \
    ${SWAP_SPACE:+"--swap-space=${SWAP_SPACE}"} \
    # Boolean 플래그 (CHUNKED_PREFILL과 동일 패턴)
    ${ENABLE_ENFORCE_EAGER:+"--enforce-eager"}
    ```
  - `openshift/dev-only/vllm-config.yaml`에 신규 키 추가 및 기존 키 수정:
    ```yaml
    data:
      MAX_NUM_SEQS: "256"
      GPU_MEMORY_UTILIZATION: "0.90"
      MAX_MODEL_LEN: "8192"
      MAX_NUM_BATCHED_TOKENS: "2048"     # 신규 — 튜너 기본 탐색 범위 하한
      BLOCK_SIZE: ""                     # 신규 — 비어있으면 vLLM 기본값 사용
      SWAP_SPACE: ""                     # 신규 — 비어있으면 전달 안 함 (CPU 환경)
      ENABLE_ENFORCE_EAGER: ""           # 변경 — "true" → "" (안전 기본값, 즉시 동작변경 방지)
      ENABLE_CHUNKED_PREFILL: ""         # 유지 — 비어있으면 chunked prefill 비활성
    ```
  - **주의**: `ENABLE_ENFORCE_EAGER`를 `"true"` → `""`로 변경. 기존에 Runtime args에 `--enforce-eager`가 없었으므로 실제 vLLM 동작에는 변화 없음. 새로 args에 추가하면서 기본값을 `""`로 설정하여 배포 시 동작 변경을 방지.

  **Must NOT do**:
  - 기존 args(max-num-seqs, max-model-len, gpu-memory-utilization, enable-chunked-prefill)의 셸 확장 패턴 변경 금지
  - containers, envFrom, env, volumeMounts 등 기존 구조 변경 금지
  - `ENABLE_CHUNKED_PREFILL`의 셸 확장 패턴(`${VAR:+"--flag"}`) 변경 금지 — 튜너 측에서 수정

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: YAML 파일 2개 수정, 명확한 패턴 추가 작업
  - **Skills**: []
  - **Skills Evaluated but Omitted**:
    - `playwright`: YAML 수정에 브라우저 불필요

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Task 2)
  - **Blocks**: F1, F2, F3, F4
  - **Blocked By**: None (can start immediately)

  **References**:

  **Pattern References**:
  - `openshift/dev-only/vllm-runtime.yaml:17-24` — 현재 vLLM 기동 명령. args 블록에 새 라인 추가. 기존 `${ENABLE_CHUNKED_PREFILL:+"--enable-chunked-prefill"}` 패턴을 ENFORCE_EAGER에도 적용.
  - `openshift/dev-only/vllm-runtime.yaml:25-27` — `envFrom: configMapRef: name: vllm-config` — ConfigMap 값이 환경변수로 주입되는 구조 확인
  - `openshift/dev-only/vllm-config.yaml:1-11` — 현재 ConfigMap 전체 내용. data 섹션에 새 키 추가

  **External References**:
  - vLLM CLI 매뉴얼: `--max-num-batched-tokens`, `--block-size`, `--swap-space`, `--enforce-eager` 각각의 의미와 기본값
  - Bash 매뉴얼: `${VAR:-default}` (기본값 치환), `${VAR:+"value"}` (비어있지 않으면 치환) 패턴

  **WHY Each Reference Matters**:
  - vllm-runtime.yaml 17-24행: 새 args를 기존 셸 멀티라인(`\` 이스케이프) 구조에 맞춰 추가해야 함
  - vllm-config.yaml: 새 키의 기본값이 Runtime의 `${VAR:-default}` fallback과 일치해야 함 (MAX_NUM_BATCHED_TOKENS: "2048" ↔ `${MAX_NUM_BATCHED_TOKENS:-2048}`)

  **Acceptance Criteria**:
  - [x] `./kustomize build openshift/dev-only/` → exit code 0 (YAML valid 검증)
  - [x] vllm-runtime.yaml에 `--max-num-batched-tokens`, `--block-size`, `--swap-space`, `--enforce-eager` 4개 args 존재
  - [x] vllm-config.yaml에 `MAX_NUM_BATCHED_TOKENS`, `BLOCK_SIZE`, `SWAP_SPACE` 3개 신규 키 존재
  - [x] vllm-config.yaml의 `ENABLE_ENFORCE_EAGER` 값이 `""` (빈 문자열)

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Kustomize 빌드 성공 확인
    Tool: Bash
    Preconditions: kustomize 바이너리 존재 (./kustomize)
    Steps:
      1. ./kustomize build openshift/dev-only/ > /tmp/kustomize-output.yaml
      2. exit code 확인 (0이어야 함)
      3. grep "max-num-batched-tokens" /tmp/kustomize-output.yaml
      4. grep "block-size" /tmp/kustomize-output.yaml
      5. grep "swap-space" /tmp/kustomize-output.yaml
      6. grep "enforce-eager" /tmp/kustomize-output.yaml
    Expected Result: exit code 0, 4개 모두 grep 매칭
    Failure Indicators: exit code != 0, 또는 grep 매칭 실패
    Evidence: .sisyphus/evidence/task-1-kustomize-build.txt

  Scenario: ConfigMap 신규 키 기본값 확인
    Tool: Bash (grep)
    Preconditions: vllm-config.yaml 수정 완료
    Steps:
      1. grep 'MAX_NUM_BATCHED_TOKENS' openshift/dev-only/vllm-config.yaml → "2048" 포함
      2. grep 'BLOCK_SIZE' openshift/dev-only/vllm-config.yaml → '""' (빈 문자열)
      3. grep 'SWAP_SPACE' openshift/dev-only/vllm-config.yaml → '""' (빈 문자열)
      4. grep 'ENABLE_ENFORCE_EAGER' openshift/dev-only/vllm-config.yaml → '""' (빈 문자열)
    Expected Result: 4개 키 모두 존재하고 기본값 일치
    Failure Indicators: 키 누락 또는 기본값 불일치
    Evidence: .sisyphus/evidence/task-1-configmap-keys.txt

  Scenario: 조건부 셸 확장 패턴 검증 — BLOCK_SIZE, SWAP_SPACE
    Tool: Bash (grep)
    Preconditions: vllm-runtime.yaml 수정 완료
    Steps:
      1. grep 'BLOCK_SIZE:+' openshift/dev-only/vllm-runtime.yaml → 조건부 확장 패턴 존재
      2. grep 'SWAP_SPACE:+' openshift/dev-only/vllm-runtime.yaml → 조건부 확장 패턴 존재
      3. BLOCK_SIZE가 `--block-size=${BLOCK_SIZE}` 형태인지 확인 (key=value 패턴)
    Expected Result: 두 파라미터 모두 ${VAR:+"--arg=${VAR}"} 패턴 사용
    Failure Indicators: `${VAR:-default}` 패턴이나 bare 플래그 패턴 사용 시 실패
    Evidence: .sisyphus/evidence/task-1-shell-expansion.txt
  ```

  **Commit**: YES
  - Message: `fix(openshift): add missing vLLM args to runtime and update config defaults`
  - Files: `openshift/dev-only/vllm-runtime.yaml`, `openshift/dev-only/vllm-config.yaml`
  - Pre-commit: `./kustomize build openshift/dev-only/ > /dev/null`

- [x] 2. auto_tuner.py 파라미터 수정 — CHUNKED_PREFILL 버그 + ENFORCE_EAGER 추가

  **What to do**:
  - `backend/services/auto_tuner.py` `_apply_params` 메서드 (line 463-481):
    - `ENABLE_CHUNKED_PREFILL` 값 기록 방식 변경:
      - 현재: `str(params["enable_chunked_prefill"]).lower()` → `"true"` 또는 `"false"`
      - 수정: `"true" if params["enable_chunked_prefill"] else ""`
      - 이유: Runtime의 `${VAR:+"--flag"}` 구문에서 빈 문자열만 False로 인식
    - `ENABLE_ENFORCE_EAGER` ConfigMap 기록 추가:
      - `config_data["ENABLE_ENFORCE_EAGER"] = "true" if params.get("enable_enforce_eager") else ""`
      - `enable_chunked_prefill`과 동일한 패턴 사용

  - `backend/services/auto_tuner.py` `_suggest_params` 메서드 (line 380-445):
    - `enable_enforce_eager` 카테고리컬 파라미터 추가:
      ```python
      params["enable_enforce_eager"] = trial.suggest_categorical(
          "enable_enforce_eager", [True, False]
      )
      ```
    - `enable_chunked_prefill` 바로 뒤에 추가 (line 412 이후)

  **Must NOT do**:
  - SSE phase 이벤트 추가 (Task 3에서 처리)
  - `_evaluate` 메서드 변경 금지
  - `_wait_for_ready`, `_rollback_to_snapshot` 변경 금지
  - `TuningConfig` Pydantic 모델 변경 금지 (enforce_eager는 항상 제안, config 옵션 불필요)

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: 파라미터 적용 로직의 정확성이 중요. 셸 확장 동작과 매칭되는 값 기록 필요.
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Task 1)
  - **Blocks**: T3, T5, F1-F4
  - **Blocked By**: None (can start immediately)

  **References**:

  **Pattern References**:
  - `backend/services/auto_tuner.py:463-481` — `_apply_params`의 `config_data` 딕셔너리 구성. CHUNKED_PREFILL 값 변환 로직이 여기 있음. line 469-471에서 `str(params["enable_chunked_prefill"]).lower()` → `"true" if ... else ""` 로 수정
  - `backend/services/auto_tuner.py:380-445` — `_suggest_params`의 Optuna trial 파라미터 제안. line 411-413의 `enable_chunked_prefill` 카테고리컬과 동일한 패턴으로 `enable_enforce_eager` 추가
  - `backend/services/auto_tuner.py:474-481` — 조건부 파라미터 기록 패턴 (block_size, swap_space). ENFORCE_EAGER도 항상 기록하므로 line 472 부근에 추가 (조건부가 아닌 필수 기록)

  **Test References**:
  - `backend/tests/test_tuner.py:428-429` — `assert "ENABLE_ENFORCE_EAGER" not in patch_data` — **이 어설션은 Task 5에서 반전해야 함**. Task 2에서는 auto_tuner.py만 수정.

  **WHY Each Reference Matters**:
  - line 469-471: CHUNKED_PREFILL 버그의 정확한 위치. `str(False).lower()` = `"false"` → 비어있지 않음 → Runtime에서 항상 플래그 추가
  - line 411-413: `enable_chunked_prefill` 카테고리컬 제안 패턴 — `enable_enforce_eager`도 동일 구조
  - line 474-481: 조건부 vs 필수 기록 패턴 차이 이해 필요

  **Acceptance Criteria**:
  - [x] `_apply_params`에서 `ENABLE_CHUNKED_PREFILL` 값: True→`"true"`, False→`""`
  - [x] `_apply_params`에서 `ENABLE_ENFORCE_EAGER` 키가 `config_data`에 포함
  - [x] `_suggest_params`에서 `enable_enforce_eager` 카테고리컬 [True, False] 제안
  - [x] 기존 파라미터(max_num_seqs, gpu_memory_utilization 등) 동작 변경 없음

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: CHUNKED_PREFILL False 시 빈 문자열 기록 확인
    Tool: Bash (python3)
    Preconditions: auto_tuner.py 수정 완료
    Steps:
      1. python3 -c "
         # _apply_params의 CHUNKED_PREFILL 값 변환 로직 단독 테스트
         params = {'enable_chunked_prefill': False, 'max_num_seqs': 64, 'gpu_memory_utilization': 0.9, 'max_model_len': 2048, 'max_num_batched_tokens': 512}
         val = 'true' if params['enable_chunked_prefill'] else ''
         assert val == '', f'Expected empty string, got: {val}'
         params2 = {'enable_chunked_prefill': True, 'max_num_seqs': 64, 'gpu_memory_utilization': 0.9, 'max_model_len': 2048, 'max_num_batched_tokens': 512}
         val2 = 'true' if params2['enable_chunked_prefill'] else ''
         assert val2 == 'true', f'Expected true, got: {val2}'
         print('PASS: CHUNKED_PREFILL values correct')
         "
    Expected Result: "PASS: CHUNKED_PREFILL values correct" 출력
    Failure Indicators: AssertionError 발생
    Evidence: .sisyphus/evidence/task-2-chunked-prefill.txt

  Scenario: ENFORCE_EAGER가 _suggest_params에 포함 확인
    Tool: Bash (grep)
    Preconditions: auto_tuner.py 수정 완료
    Steps:
      1. grep "enable_enforce_eager" backend/services/auto_tuner.py
      2. 결과에 suggest_categorical 호출 포함 확인
      3. 결과에 config_data 기록 포함 확인
    Expected Result: suggest_categorical과 config_data 두 곳 모두에서 enable_enforce_eager 발견
    Failure Indicators: grep 매칭 실패 또는 한쪽만 존재
    Evidence: .sisyphus/evidence/task-2-enforce-eager.txt
  ```

  **Commit**: YES (groups with T3)
  - Message: `fix(tuner): fix chunked_prefill shell bug, add enforce_eager, add SSE phase events`
  - Files: `backend/services/auto_tuner.py`
  - Pre-commit: N/A (테스트는 T5에서 업데이트 후 실행)

- [x] 3. auto_tuner.py SSE phase 이벤트 추가

  **What to do**:
  - `backend/services/auto_tuner.py` `start()` 메서드에 trial 내부 단계별 SSE 이벤트 브로드캐스트 추가:

    1. **applying_config** — `_apply_params` 호출 직전 (line 243 부근):
       ```python
       await self._broadcast({
           "type": "phase",
           "data": {"trial_id": trial_num, "phase": "applying_config"},
       })
       ```

    2. **restarting** — `_apply_params` 호출 성공 후, `_wait_for_ready` 호출 직전 (line 250 부근):
       ```python
       await self._broadcast({
           "type": "phase",
           "data": {"trial_id": trial_num, "phase": "restarting"},
       })
       ```

    3. **waiting_ready** — `_wait_for_ready` 호출 직전 (line 250 부근, restarting 직후):
       ```python
       await self._broadcast({
           "type": "phase",
           "data": {"trial_id": trial_num, "phase": "waiting_ready"},
       })
       ```
       Note: restarting과 waiting_ready를 분리하는 대신, 단순히 `_wait_for_ready` 호출 직전에 하나의 이벤트로 합칠 수도 있음. 구현 시 `restarting` 이벤트는 `_apply_params` 성공 직후, `waiting_ready`는 바로 다음에 발행.

  - `backend/services/auto_tuner.py` `_evaluate()` 메서드에 phase 이벤트 추가:

    4. **warmup** — warmup 실행 직전 (line 574 `if config.warmup_requests > 0:` 블록 내부):
       ```python
       await self._broadcast({
           "type": "phase",
           "data": {"trial_id": trial_num, "phase": "warmup", "requests": config.warmup_requests},
       })
       ```
       **주의**: `_evaluate`는 현재 `trial_num` 인자를 받지 않음. `_evaluate` 시그니처에 `trial_num: int` 추가 필요. 호출부(line 259)도 수정.

    5. **evaluating** — fast probe 실행 직전 (line 599 `fast_config` 생성 후):
       ```python
       await self._broadcast({
           "type": "phase",
           "data": {"trial_id": trial_num, "phase": "evaluating"},
       })
       ```

  - `_evaluate` 시그니처 변경:
    - 현재: `async def _evaluate(self, endpoint, config, trial=None)`
    - 수정: `async def _evaluate(self, endpoint, config, trial=None, trial_num: int = 0)`
    - 호출부 수정: `await self._evaluate(vllm_endpoint, config, trial=trial, trial_num=trial_num)`

  **Must NOT do**:
  - SSE 이벤트 타입을 "phase" 외 다른 이름 사용 금지 (프론트엔드와 일관성)
  - `_apply_params`, `_suggest_params`, `_rollback_to_snapshot` 로직 변경 금지
  - 기존 `trial_start`, `trial_complete`, `tuning_complete` 이벤트 구조 변경 금지
  - `warmup_requests=0`일 때 warmup phase 이벤트 발행 금지 (if 블록 내부에만 추가)

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
    - Reason: 여러 메서드에 걸친 이벤트 삽입 위치 정확성이 중요. 기존 이벤트 순서를 깨뜨리면 안 됨.
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Wave 2 (sequential after T2)
  - **Blocks**: T4, T5, F1-F4
  - **Blocked By**: T2

  **References**:

  **Pattern References**:
  - `backend/services/auto_tuner.py:237-240` — 기존 `trial_start` 브로드캐스트 패턴. 동일한 `await self._broadcast({...})` 구조 사용
  - `backend/services/auto_tuner.py:341-351` — 기존 `trial_complete` 브로드캐스트. phase 이벤트는 이 사이에 위치
  - `backend/services/auto_tuner.py:242-250` — `_apply_params` → `_wait_for_ready` 호출 순서. 이 사이에 applying_config, restarting, waiting_ready 삽입
  - `backend/services/auto_tuner.py:565-636` — `_evaluate` 메서드 전체. warmup 블록(574-587)과 fast_config(598-607) 위치에 phase 이벤트 삽입

  **WHY Each Reference Matters**:
  - line 237-240: phase 이벤트의 JSON 구조와 `_broadcast` 호출 패턴 참고
  - line 242-250: applying_config/restarting/waiting_ready 삽입 정확 위치
  - line 565-636: _evaluate 내부 warmup/evaluating 삽입 위치. 시그니처에 trial_num 추가 필요

  **Acceptance Criteria**:
  - [x] `start()` 메서드에서 trial_start → applying_config → restarting → waiting_ready → (warmup →) evaluating → trial_complete 순서로 이벤트 발행
  - [x] `_evaluate` 시그니처에 `trial_num` 파라미터 추가
  - [x] `warmup_requests=0`이면 warmup phase 이벤트 미발행
  - [x] 기존 trial_start, trial_complete, tuning_complete 이벤트 구조 변경 없음

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: phase 이벤트 삽입 위치 및 순서 확인
    Tool: Bash (grep)
    Preconditions: auto_tuner.py 수정 완료
    Steps:
      1. grep -n '"phase"' backend/services/auto_tuner.py
      2. 결과에서 applying_config, restarting, waiting_ready, warmup, evaluating 5개 phase 확인
      3. 행 번호 순서가 올바른지 확인 (applying_config < restarting < waiting_ready < warmup < evaluating)
    Expected Result: 5개 phase 이벤트 존재, 행 번호 기준 올바른 순서
    Failure Indicators: phase 누락 또는 순서 역전
    Evidence: .sisyphus/evidence/task-3-phase-events.txt

  Scenario: _evaluate 시그니처에 trial_num 포함 확인
    Tool: Bash (grep)
    Preconditions: auto_tuner.py 수정 완료
    Steps:
      1. grep "async def _evaluate" backend/services/auto_tuner.py
      2. 결과에 trial_num 파라미터 포함 확인
    Expected Result: `async def _evaluate(self, endpoint, config, trial=None, trial_num` 패턴 매칭
    Failure Indicators: trial_num 파라미터 누락
    Evidence: .sisyphus/evidence/task-3-evaluate-signature.txt

  Scenario: warmup_requests=0일 때 warmup 이벤트 미발행 구조 확인
    Tool: Bash (grep)
    Preconditions: auto_tuner.py 수정 완료
    Steps:
      1. grep -A 5 "warmup_requests > 0" backend/services/auto_tuner.py
      2. warmup broadcast가 if 블록 내부에 있는지 확인
    Expected Result: warmup broadcast 호출이 `if config.warmup_requests > 0:` 블록 내에 위치
    Failure Indicators: warmup broadcast가 if 외부에 있음
    Evidence: .sisyphus/evidence/task-3-warmup-conditional.txt
  ```

  **Commit**: YES (groups with T2)
  - Message: `fix(tuner): fix chunked_prefill shell bug, add enforce_eager, add SSE phase events`
  - Files: `backend/services/auto_tuner.py`
  - Pre-commit: N/A (T5 이후 테스트)

- [x] 4. TunerPage.jsx 단계별 상태 UI

  **What to do**:
  - `frontend/src/pages/TunerPage.jsx`에 현재 trial의 phase 상태를 표시하는 기능 추가:

  1. **State 추가** (line 13 부근):
     ```jsx
     const [currentPhase, setCurrentPhase] = useState(null);
     ```

  2. **SSE 핸들러 확장** (line 58-67 useEffect 내부):
     - 기존 `trial_complete`, `tuning_complete` 외에 `phase` 이벤트 타입 처리 추가:
     ```jsx
     if (data.type === "phase") {
       setCurrentPhase(data.data);  // { trial_id, phase, requests? }
     }
     if (data.type === "trial_complete" || data.type === "tuning_complete") {
       setCurrentPhase(null);  // trial 완료 시 phase 초기화
       fetchStatus();
     }
     ```

  3. **Phase 한글 매핑 함수** 추가:
     ```jsx
     const PHASE_LABELS = {
       applying_config: "⚙ ConfigMap 업데이트 중...",
       restarting: "🔄 InferenceService 재시작 중...",
       waiting_ready: "⏳ Pod Ready 대기 중...",
       warmup: "🔥 Warmup 요청 전송 중...",
       evaluating: "📊 성능 평가 중...",
     };
     ```

  4. **Phase 표시 영역** — Start/Stop 버튼 아래 (line 196 부근):
     ```jsx
     {currentPhase && status.running && (
       <div style={{
         marginTop: 12, padding: "10px 16px",
         background: "rgba(0,163,255,0.08)",
         border: `1px solid ${COLORS.accent}`,
         fontSize: 12, fontFamily: "'JetBrains Mono', monospace",
         color: COLORS.accent,
       }}>
         Trial {currentPhase.trial_id + 1}: {PHASE_LABELS[currentPhase.phase] || currentPhase.phase}
       </div>
     )}
     ```

  5. **tuning 완료/중단 시 phase 초기화** — stop() 함수 내에서도:
     ```jsx
     const stop = async () => {
       await fetch(`${API}/tuner/stop`, { method: "POST" });
       setCurrentPhase(null);
       fetchStatus();
     };
     ```

  **Must NOT do**:
  - Progress bar, timeline, 다단계 UI 컴포넌트 추가 금지 — 단순 텍스트 상태 표시만
  - 기존 차트(ScatterChart, LineChart), 메트릭 카드, 설정 폼 구조 변경 금지
  - 새로운 컴포넌트 파일 생성 금지 (TunerPage.jsx 내에서만 처리)
  - 이모지 사용하지 말 것 — 순수 텍스트 또는 CSS 기반 인디케이터 사용

  **Recommended Agent Profile**:
  - **Category**: `visual-engineering`
    - Reason: 프론트엔드 UI 상태 표시 추가. 기존 디자인 시스템(COLORS, font) 활용.
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 3 (with Task 5)
  - **Blocks**: F1-F4
  - **Blocked By**: T3

  **References**:

  **Pattern References**:
  - `frontend/src/pages/TunerPage.jsx:55-68` — 기존 SSE EventSource 핸들러. `es.onmessage` 내부에 `data.type` 분기 추가
  - `frontend/src/pages/TunerPage.jsx:178-196` — Start/Stop 버튼 영역. 이 아래에 phase 표시 영역 추가
  - `frontend/src/pages/TunerPage.jsx:190-191` — 기존 상태 태그(`TUNING.../IDLE`)와 trial 카운터. phase 표시는 이 아래에 위치
  - `frontend/src/pages/TunerPage.jsx:127-136` — 에러 메시지 표시 패턴. phase 표시도 유사한 스타일링 패턴 사용
  - `frontend/src/constants.js` — COLORS, font 등 디자인 상수

  **WHY Each Reference Matters**:
  - line 55-68: SSE 이벤트 핸들러 확장 위치. 기존 trial_complete/tuning_complete 분기에 phase 분기 추가
  - line 178-196: phase 표시 DOM 삽입 위치. 버튼 그룹과 차트 사이에 위치
  - line 127-136: 에러 박스와 유사한 스타일링 패턴 (border, padding, fontFamily)

  **Acceptance Criteria**:
  - [x] `currentPhase` useState 변수 존재
  - [x] SSE 핸들러에서 `phase` 타입 이벤트 처리
  - [x] trial_complete/tuning_complete 시 currentPhase null 초기화
  - [x] stop() 호출 시 currentPhase null 초기화
  - [x] phase 표시 영역이 status.running && currentPhase 조건부 렌더링

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: currentPhase 상태 변수 및 SSE 핸들러 존재 확인
    Tool: Bash (grep)
    Preconditions: TunerPage.jsx 수정 완료
    Steps:
      1. grep "currentPhase" frontend/src/pages/TunerPage.jsx | wc -l → 5개 이상
      2. grep "setCurrentPhase" frontend/src/pages/TunerPage.jsx | wc -l → 3개 이상 (setState, trial_complete 초기화, stop 초기화)
      3. grep '"phase"' frontend/src/pages/TunerPage.jsx → SSE 타입 분기 존재
    Expected Result: currentPhase 관련 코드 5곳 이상, setCurrentPhase 3곳 이상, "phase" 분기 존재
    Failure Indicators: grep 매칭 부족
    Evidence: .sisyphus/evidence/task-4-phase-state.txt

  Scenario: phase 표시 영역 조건부 렌더링 확인
    Tool: Bash (grep)
    Preconditions: TunerPage.jsx 수정 완료
    Steps:
      1. grep -A 2 "currentPhase &&" frontend/src/pages/TunerPage.jsx
      2. status.running과 AND 조건 확인
    Expected Result: `currentPhase && status.running` 조건부 렌더링 패턴 존재
    Failure Indicators: 조건부 렌더링 없이 항상 표시
    Evidence: .sisyphus/evidence/task-4-conditional-render.txt
  ```

  **Commit**: YES
  - Message: `feat(frontend): show tuning trial phase status in TunerPage`
  - Files: `frontend/src/pages/TunerPage.jsx`

- [x] 5. test_tuner.py 테스트 업데이트

  **What to do**:
  - `backend/tests/test_tuner.py` 기존 테스트 업데이트 및 신규 테스트 케이스 추가:

  1. **기존 테스트 수정 — ENFORCE_EAGER 어설션 반전** (line 428-429):
     - 변경 전: `assert "ENABLE_ENFORCE_EAGER" not in patch_data`
     - 변경 후: `assert "ENABLE_ENFORCE_EAGER" in patch_data`
     - 추가: `assert patch_data["ENABLE_ENFORCE_EAGER"] == ""` (enable_enforce_eager=False인 경우)

  2. **신규 테스트 — CHUNKED_PREFILL False 시 빈 문자열**:
     ```python
     async def test_chunked_prefill_false_writes_empty_string(auto_tuner):
         """enable_chunked_prefill=False → ENABLE_CHUNKED_PREFILL="" (빈 문자열, NOT "false")"""
         # _apply_params mock에서 patch_data 캡처
         # params = {"enable_chunked_prefill": False, ...}
         # assert patch_data["ENABLE_CHUNKED_PREFILL"] == ""
     ```

  3. **신규 테스트 — ENFORCE_EAGER True/False 값**:
     ```python
     async def test_enforce_eager_writes_correct_values(auto_tuner):
         """enable_enforce_eager=True → "true", False → "" """
         # True 케이스: assert patch_data["ENABLE_ENFORCE_EAGER"] == "true"
         # False 케이스: assert patch_data["ENABLE_ENFORCE_EAGER"] == ""
     ```

  4. **신규 테스트 — suggest_params에 enforce_eager 포함**:
     ```python
     async def test_suggest_params_includes_enforce_eager(auto_tuner):
         """_suggest_params 결과에 enable_enforce_eager 키 포함"""
         # Optuna Trial mock 사용
         # params = auto_tuner._suggest_params(trial, config)
         # assert "enable_enforce_eager" in params
     ```

  5. **신규 테스트 — SSE phase 이벤트 브로드캐스트 순서**:
     ```python
     async def test_phase_events_broadcast_order(auto_tuner):
         """trial 실행 시 phase 이벤트가 올바른 순서로 발행"""
         # auto_tuner.subscribe() → q
         # trial 1회 실행
         # q에서 이벤트 수집
         # 순서 검증: trial_start → phase(applying_config) → phase(restarting) → phase(waiting_ready) → phase(warmup)? → phase(evaluating) → trial_complete
     ```

  6. **기존 테스트 호환성 확인**:
     - `_evaluate`를 AsyncMock으로 대체하는 기존 테스트들은 변경 불필요 (mock은 phase 이벤트를 발행하지 않으므로 phase 관련 어설션 없음)
     - `_evaluate` 시그니처에 `trial_num` 추가되었으므로, 기존 mock 호출부에서 새 인자 전달 여부 확인. `trial_num` 기본값이 0이므로 기존 mock 호출은 호환됨.

  **Must NOT do**:
  - 기존 `_evaluate` mock 패턴 변경 금지 (새 phase 테스트는 별도 테스트 함수로)
  - 통합 테스트 (integration marker) 추가 금지
  - conftest.py 변경 금지 (기존 픽스처 사용)
  - auto_tuner.py, tuner.py 등 테스트 대상 소스 변경 금지

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: 기존 테스트 패턴 이해 후 일관된 스타일로 신규 테스트 작성. mock 패턴과 async 테스트 구조 정확성 필요.
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 3 (with Task 4)
  - **Blocks**: F1-F4
  - **Blocked By**: T2, T3

  **References**:

  **Pattern References**:
  - `backend/tests/test_tuner.py:428-429` — 반전 대상 어설션. `"ENABLE_ENFORCE_EAGER" not in patch_data` → `in`
  - `backend/tests/test_tuner.py` 전체 — 기존 테스트 패턴: `@pytest.mark.asyncio`, `auto_tuner` 픽스처, `AsyncMock`, `patch` 사용법
  - `backend/tests/conftest.py` — 테스트 픽스처 정의. `auto_tuner` 픽스처 구조 확인

  **API/Type References**:
  - `backend/services/auto_tuner.py:_apply_params` — 테스트할 메서드의 실제 동작
  - `backend/services/auto_tuner.py:_suggest_params` — 테스트할 메서드. Optuna Trial mock 필요
  - `backend/services/auto_tuner.py:_broadcast` — phase 이벤트 발행 메서드. subscribe/unsubscribe 테스트 패턴

  **WHY Each Reference Matters**:
  - line 428-429: 정확한 반전 위치. 이 어설션만 변경하고 주변 로직은 유지
  - conftest.py: auto_tuner 픽스처가 어떤 mock을 주입하는지 이해 필요 (K8s client mock, load_engine mock 등)
  - _broadcast: phase 이벤트 순서 테스트 시 subscribe → 이벤트 수집 → 순서 검증 패턴

  **Acceptance Criteria**:
  - [x] `python3 -m pytest backend/tests/ -x -q -m "not integration"` → 전체 PASS (0 failures)
  - [x] `ENABLE_ENFORCE_EAGER in patch_data` 어설션 존재 (반전 완료)
  - [x] CHUNKED_PREFILL `""` 빈 문자열 테스트 존재 및 PASS
  - [x] enforce_eager suggest 테스트 존재 및 PASS
  - [x] phase 이벤트 순서 테스트 존재

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: 전체 단위 테스트 통과
    Tool: Bash
    Preconditions: auto_tuner.py 수정 (T2+T3) + test_tuner.py 수정 (T5) 완료
    Steps:
      1. cd /home/user/project/vllm-optimizer
      2. python3 -m pytest backend/tests/ -x -q -m "not integration" 2>&1
      3. 출력에서 "passed" 확인, "failed" 없음 확인
    Expected Result: "N passed, 0 failed" 또는 "N passed" (failure 없음)
    Failure Indicators: "FAILED" 또는 "ERROR" 출력
    Evidence: .sisyphus/evidence/task-5-pytest-results.txt

  Scenario: ENFORCE_EAGER 어설션 반전 확인
    Tool: Bash (grep)
    Preconditions: test_tuner.py 수정 완료
    Steps:
      1. grep "ENABLE_ENFORCE_EAGER" backend/tests/test_tuner.py
      2. "not in patch_data" 패턴이 없어야 함
      3. "in patch_data" 패턴이 있어야 함
    Expected Result: "not in" 없음, "in" 있음
    Failure Indicators: "not in patch_data" 패턴 여전히 존재
    Evidence: .sisyphus/evidence/task-5-enforce-eager-assertion.txt

  Scenario: 신규 테스트 함수 존재 확인
    Tool: Bash (grep)
    Preconditions: test_tuner.py 수정 완료
    Steps:
      1. grep "def test_chunked_prefill" backend/tests/test_tuner.py → 존재
      2. grep "def test_enforce_eager" backend/tests/test_tuner.py → 존재
      3. grep "def test_.*phase" backend/tests/test_tuner.py → 존재
    Expected Result: 3개 이상의 신규 테스트 함수 발견
    Failure Indicators: 신규 테스트 함수 누락
    Evidence: .sisyphus/evidence/task-5-new-tests.txt
  ```

  **Commit**: YES
  - Message: `test(tuner): update tests for enforce_eager, chunked_prefill fix, and phase events`
  - Files: `backend/tests/test_tuner.py`
  - Pre-commit: `python3 -m pytest backend/tests/ -x -q -m "not integration"`

---

## Final Verification Wave (MANDATORY — after ALL implementation tasks)

> 4 review agents run in PARALLEL. ALL must APPROVE. Rejection → fix → re-run.

- [x] F1. **Plan Compliance Audit** — `oracle`
  Read the plan end-to-end. For each "Must Have": verify implementation exists (read file, run command). For each "Must NOT Have": search codebase for forbidden patterns — reject with file:line if found. Check evidence files exist in .sisyphus/evidence/. Compare deliverables against plan.
  Output: `Must Have [N/N] | Must NOT Have [N/N] | Tasks [N/N] | VERDICT: APPROVE/REJECT`

- [x] F2. **Code Quality Review** — `unspecified-high`
  Run `python3 -m pytest backend/tests/ -x -q -m "not integration"`. Review all changed files (auto_tuner.py, vllm-runtime.yaml, vllm-config.yaml, TunerPage.jsx, test_tuner.py) for: unused imports, empty catches, commented-out code, `as any` equivalents. Check AI slop: excessive comments, over-abstraction.
  Output: `Tests [N pass/N fail] | Files [N clean/N issues] | VERDICT`

- [x] F3. **Real Manual QA** — `unspecified-high`
  Start from clean state. Execute EVERY QA scenario from EVERY task — follow exact steps, capture evidence. Test cross-task integration. Save to `.sisyphus/evidence/final-qa/`.
  Output: `Scenarios [N/N pass] | Integration [N/N] | VERDICT`

- [x] F4. **Scope Fidelity Check** — `deep`
  For each task: read "What to do", read actual diff (git log/diff). Verify 1:1. Check "Must NOT do" compliance. Flag unaccounted changes.
  Output: `Tasks [N/N compliant] | Unaccounted [CLEAN/N files] | VERDICT`

---

## Commit Strategy

- **Commit 1** (T1): `fix(openshift): add missing vLLM args to runtime and config defaults` — `openshift/dev-only/vllm-runtime.yaml`, `openshift/dev-only/vllm-config.yaml`
  Pre-commit: `./kustomize build openshift/dev-only/ > /dev/null`
- **Commit 2** (T2+T3): `fix(tuner): fix chunked_prefill shell bug, add enforce_eager, add SSE phase events` — `backend/services/auto_tuner.py`
  Pre-commit: `python3 -m pytest backend/tests/ -x -q -m "not integration"`
- **Commit 3** (T4): `feat(frontend): show tuning trial phase status in TunerPage` — `frontend/src/pages/TunerPage.jsx`
- **Commit 4** (T5): `test(tuner): update tests for enforce_eager, chunked_prefill fix, and phase events` — `backend/tests/test_tuner.py`
  Pre-commit: `python3 -m pytest backend/tests/ -x -q -m "not integration"`

---

## Success Criteria

### Verification Commands
```bash
# 전체 단위 테스트
python3 -m pytest backend/tests/ -x -q -m "not integration"
# Expected: all tests PASSED

# Kustomize 빌드 검증
./kustomize build openshift/dev-only/ > /dev/null
# Expected: exit code 0

# Runtime YAML에 새 args 존재 확인
grep "max-num-batched-tokens" openshift/dev-only/vllm-runtime.yaml
grep "block-size" openshift/dev-only/vllm-runtime.yaml
grep "swap-space" openshift/dev-only/vllm-runtime.yaml
grep "enforce-eager" openshift/dev-only/vllm-runtime.yaml
# Expected: all 4 patterns found with correct shell expansion

# ConfigMap에 새 키 존재 확인
grep "MAX_NUM_BATCHED_TOKENS" openshift/dev-only/vllm-config.yaml
grep "BLOCK_SIZE" openshift/dev-only/vllm-config.yaml
grep "SWAP_SPACE" openshift/dev-only/vllm-config.yaml
# Expected: all 3 keys present

# 프론트엔드 phase 상태 확인
grep "currentPhase" frontend/src/pages/TunerPage.jsx
# Expected: useState and render usage found
```

### Final Checklist
- [x] All "Must Have" present
- [x] All "Must NOT Have" absent
- [x] All tests pass
- [x] Kustomize build succeeds (YAML valid 검증, kustomize 바이너리 미설치 환경)
