# Fix: enable_chunked_prefill → ENABLE_ENFORCE_EAGER 매핑 버그 수정

## TL;DR

> **Quick Summary**: Auto Tuner가 `enable_chunked_prefill` 파라미터를 `ENABLE_ENFORCE_EAGER` ConfigMap 키에 잘못 매핑하고 있음. 두 파라미터를 분리하여 각각 독립적으로 동작하도록 수정.
>
> **Deliverables**:
> - `auto_tuner.py`: ConfigMap 패치에서 `ENABLE_CHUNKED_PREFILL` 키 사용
> - `vllm-runtime.yaml`: `--enable-chunked-prefill` CLI 인자 추가
> - `vllm-config.yaml`: `ENABLE_CHUNKED_PREFILL` 키 추가
> - `test_tuner.py`: ConfigMap 매핑 검증 테스트 추가
>
> **Estimated Effort**: Quick
> **Parallel Execution**: NO — 단일 태스크 (4개 파일 동시 수정)
> **Critical Path**: Task 1 → F1

---

## Context

### Original Request
Auto Tuner의 `_suggest_params()`가 `enable_chunked_prefill` 파라미터를 제안하지만, `_apply_params()`에서 이 값을 `ENABLE_ENFORCE_EAGER` ConfigMap 키에 기록하고 있음.
`enforce_eager`와 `enable_chunked_prefill`은 완전히 다른 vLLM 파라미터이므로, 이 매핑은 버그.

### 현재 상태 (버그)

**auto_tuner.py:233-234**
```python
"ENABLE_ENFORCE_EAGER": str(params["enable_chunked_prefill"]).lower(),
```

**vllm-runtime.yaml:24**
```yaml
${ENABLE_ENFORCE_EAGER:+"--enforce-eager"}
```

→ `enable_chunked_prefill=True`로 튜닝하면 `--enforce-eager`가 켜지는 엉뚱한 동작.

### 수정 후 목표 상태

| 파라미터 | ConfigMap 키 | vLLM CLI 인자 | 제어 주체 |
|---|---|---|---|
| `enforce_eager` | `ENABLE_ENFORCE_EAGER` | `--enforce-eager` | 고정 설정 (ConfigMap 직접 편집) |
| `enable_chunked_prefill` | `ENABLE_CHUNKED_PREFILL` | `--enable-chunked-prefill` | Auto Tuner 튜닝 대상 |

---

## Work Objectives

### Core Objective
`enable_chunked_prefill` 파라미터를 독립된 ConfigMap 키(`ENABLE_CHUNKED_PREFILL`)와 ServingRuntime CLI 인자(`--enable-chunked-prefill`)로 올바르게 매핑.

### Concrete Deliverables
- `backend/services/auto_tuner.py` — ConfigMap 패치 키 수정
- `openshift/dev-only/vllm-runtime.yaml` — CLI 인자 추가
- `openshift/dev-only/vllm-config.yaml` — 새 키 추가
- `backend/tests/test_tuner.py` — ConfigMap 키 매핑 검증 테스트 추가

### Definition of Done
- [x] `python3 -m pytest tests/test_tuner.py -x -q` PASS
- [x] `ENABLE_CHUNKED_PREFILL`이 ConfigMap에 독립 키로 존재
- [x] `ENABLE_ENFORCE_EAGER`는 auto_tuner가 건드리지 않음

### Must Have
- `enable_chunked_prefill` → `ENABLE_CHUNKED_PREFILL` 매핑
- ServingRuntime에 `--enable-chunked-prefill` 인자 지원
- 기존 `ENABLE_ENFORCE_EAGER` 동작 변경 없음 (고정 설정 유지)

### Must NOT Have (Guardrails)
- `ENABLE_ENFORCE_EAGER` 키를 삭제하거나 동작을 변경하지 않을 것
- ConfigMap 마운트 방식 변경 (envFrom 유지 — 이번 스코프 아님)
- `enforce_eager`를 Auto Tuner 튜닝 대상에 추가하지 않을 것
- vLLM 엔드포인트나 모델 설정 변경 없음

---

## Verification Strategy

> **ZERO HUMAN INTERVENTION** — ALL verification is agent-executed.

### Test Decision
- **Infrastructure exists**: YES
- **Automated tests**: YES (Tests-after — 매핑 검증 테스트 추가)
- **Framework**: pytest

### QA Policy
Every task includes agent-executed QA scenarios.
Evidence saved to `.sisyphus/evidence/task-{N}-{scenario-slug}.{ext}`.

---

## Execution Strategy

### Parallel Execution Waves

```
Wave 1 (단일 태스크 — 4개 파일 동시 수정):
└── Task 1: 매핑 버그 수정 + 테스트 [quick]

Wave FINAL (After Task 1):
└── Task F1: 테스트 실행 + 매핑 검증 [quick]

Critical Path: Task 1 → F1
```

### Dependency Matrix
| Task | Depends On | Blocks |
|------|-----------|--------|
| 1 | — | F1 |
| F1 | 1 | — |

### Agent Dispatch Summary
- **Wave 1**: 1 task — T1 → `quick`
- **FINAL**: 1 task — F1 → `quick`

---

## TODOs

- [x] 1. enable_chunked_prefill 매핑 수정 + 테스트

  **What to do**:

  **(A) `backend/services/auto_tuner.py` — `_apply_params()` 메서드 (228-235행)**

  현재 `patch_body`에서 `ENABLE_ENFORCE_EAGER` 키를 `enable_chunked_prefill` 값으로 쓰는 부분을 수정:

  ```python
  # 변경 전 (line 233)
  "ENABLE_ENFORCE_EAGER": str(params["enable_chunked_prefill"]).lower(),

  # 변경 후
  "ENABLE_CHUNKED_PREFILL": str(params["enable_chunked_prefill"]).lower(),
  ```

  `ENABLE_ENFORCE_EAGER`는 `patch_body`에서 **제거** — Auto Tuner가 enforce_eager를 건드리지 않도록.

  **(B) `openshift/dev-only/vllm-runtime.yaml` — args 블록 (16-24행)**

  기존 `ENABLE_ENFORCE_EAGER` 라인 다음에 `ENABLE_CHUNKED_PREFILL` 라인 추가:

  ```yaml
  ${ENABLE_ENFORCE_EAGER:+"--enforce-eager"} \
  ${ENABLE_CHUNKED_PREFILL:+"--enable-chunked-prefill"}
  ```

  주의: 기존 24행의 `ENABLE_ENFORCE_EAGER` 라인 끝에 `\` (line continuation) 추가 필요.

  **(C) `openshift/dev-only/vllm-config.yaml` — data 섹션**

  새 키 추가:
  ```yaml
  ENABLE_CHUNKED_PREFILL: ""
  ```
  기본값은 빈 문자열 (비활성). Auto Tuner가 `"true"`로 설정하면 활성화됨.
  `ENABLE_ENFORCE_EAGER: "true"`는 그대로 유지.

  **(D) `backend/tests/test_tuner.py` — 새 테스트 추가**

  `test_apply_params_patches_correct_annotation_location` (92행) 아래에 ConfigMap 매핑 검증 테스트 추가:
  - `_apply_params()` 호출 시 `patch_namespaced_config_map`의 `body.data`에 `ENABLE_CHUNKED_PREFILL` 키가 존재하는지 확인
  - `ENABLE_ENFORCE_EAGER` 키가 `body.data`에 존재하지 **않는지** 확인
  - `ENABLE_CHUNKED_PREFILL` 값이 `str(params["enable_chunked_prefill"]).lower()`와 일치하는지 확인

  **Must NOT do**:
  - `ENABLE_ENFORCE_EAGER` 키를 ConfigMap이나 ServingRuntime에서 삭제하지 않을 것
  - `enforce_eager`를 `_suggest_params()`에 추가하지 않을 것

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: 4개 파일의 명확한 수정. 로직 변경 최소.
  - **Skills**: []
    - 스킬 불필요 — 순수 코드 편집 + 테스트 작업

  **Parallelization**:
  - **Can Run In Parallel**: NO (단일 태스크)
  - **Parallel Group**: Wave 1
  - **Blocks**: F1
  - **Blocked By**: None

  **References**:

  **Pattern References** (수정 대상 코드):
  - `backend/services/auto_tuner.py:228-240` — `_apply_params()` 메서드의 `patch_body` 딕셔너리. 233행이 버그 위치.
  - `backend/services/auto_tuner.py:208-211` — `_suggest_params()`의 `enable_chunked_prefill` 파라미터 정의. 이 부분은 수정하지 않음.

  **API/Type References** (구조 확인):
  - `openshift/dev-only/vllm-runtime.yaml:14-24` — ServingRuntime args 블록. shell 변수 치환 패턴 (`${VAR:+"--flag"}`) 확인.
  - `openshift/dev-only/vllm-config.yaml:6-10` — ConfigMap data 섹션. 기존 키 이름 패턴 확인.

  **Test References** (테스트 패턴):
  - `backend/tests/test_tuner.py:92-118` — `test_apply_params_patches_correct_annotation_location`. 이 테스트와 동일한 mock 구조(`mock_k8s_clients`)를 사용하여 ConfigMap 패치를 검증하는 새 테스트 작성.
  - `backend/tests/test_tuner.py:96-101` — 테스트용 params 딕셔너리 구조. 동일한 형태 사용.

  **Acceptance Criteria**:

  - [x] `python3 -m pytest tests/test_tuner.py -x -q -m "not integration"` → ALL PASS
  - [x] `auto_tuner.py`의 `patch_body`에 `ENABLE_ENFORCE_EAGER` 키가 없음
  - [x] `auto_tuner.py`의 `patch_body`에 `ENABLE_CHUNKED_PREFILL` 키가 있음
  - [x] `vllm-runtime.yaml` args에 `${ENABLE_CHUNKED_PREFILL:+"--enable-chunked-prefill"}` 라인 존재
  - [x] `vllm-config.yaml`에 `ENABLE_CHUNKED_PREFILL` 키 존재
  - [x] `vllm-config.yaml`에 `ENABLE_ENFORCE_EAGER` 키 여전히 존재 (삭제되지 않음)

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: ConfigMap 패치에 올바른 키가 사용됨
    Tool: Bash (grep)
    Preconditions: auto_tuner.py 수정 완료
    Steps:
      1. grep -n "ENABLE_CHUNKED_PREFILL" backend/services/auto_tuner.py
      2. grep -n "ENABLE_ENFORCE_EAGER" backend/services/auto_tuner.py (patch_body 내에 없어야 함)
    Expected Result:
      - ENABLE_CHUNKED_PREFILL이 patch_body 딕셔너리 내에 존재
      - ENABLE_ENFORCE_EAGER가 patch_body 딕셔너리 내에 존재하지 않음 (ConfigMap 읽기용 외)
    Failure Indicators: ENABLE_ENFORCE_EAGER가 patch_body 내에 여전히 있음
    Evidence: .sisyphus/evidence/task-1-configmap-key-check.txt

  Scenario: ServingRuntime에 chunked-prefill CLI 인자 존재
    Tool: Bash (grep)
    Preconditions: vllm-runtime.yaml 수정 완료
    Steps:
      1. grep -n "enable-chunked-prefill" openshift/dev-only/vllm-runtime.yaml
      2. grep -n "enforce-eager" openshift/dev-only/vllm-runtime.yaml
    Expected Result:
      - --enable-chunked-prefill 라인이 args 블록에 존재
      - --enforce-eager 라인도 여전히 존재
    Failure Indicators: enable-chunked-prefill 라인이 없거나, enforce-eager 라인이 사라짐
    Evidence: .sisyphus/evidence/task-1-runtime-args-check.txt

  Scenario: 단위 테스트 전체 통과
    Tool: Bash (pytest)
    Preconditions: 모든 파일 수정 완료
    Steps:
      1. cd backend && python3 -m pytest tests/test_tuner.py -x -v -m "not integration"
    Expected Result: ALL PASSED, 0 failures
    Failure Indicators: FAILED 또는 ERROR 출력
    Evidence: .sisyphus/evidence/task-1-pytest-result.txt
  ```

  **Commit**: YES
  - Message: `fix(tuner): map enable_chunked_prefill to correct ConfigMap key`
  - Files: `backend/services/auto_tuner.py`, `openshift/dev-only/vllm-runtime.yaml`, `openshift/dev-only/vllm-config.yaml`, `backend/tests/test_tuner.py`
  - Pre-commit: `cd backend && python3 -m pytest tests/test_tuner.py -x -q -m "not integration"`

---

## Final Verification Wave

- [x] F1. **테스트 실행 + 매핑 일관성 검증** — `quick`
  `cd backend && python3 -m pytest tests/test_tuner.py -x -v -m "not integration"` 실행.
  `grep -rn "ENABLE_CHUNKED_PREFILL" backend/services/ openshift/dev-only/` 로 모든 파일에서 일관된 키 이름 사용 확인.
  `grep -rn "ENABLE_ENFORCE_EAGER" backend/services/auto_tuner.py` 로 auto_tuner에서 해당 키가 patch_body에 없음을 확인.
  Output: `Tests [PASS/FAIL] | Key Consistency [PASS/FAIL] | VERDICT`

---

## Commit Strategy

| Task | Commit Message | Files |
|------|---------------|-------|
| 1 | `fix(tuner): map enable_chunked_prefill to correct ConfigMap key` | `auto_tuner.py`, `vllm-runtime.yaml`, `vllm-config.yaml`, `test_tuner.py` |

---

## Success Criteria

### Verification Commands
```bash
cd backend && python3 -m pytest tests/test_tuner.py -x -q -m "not integration"
# Expected: all tests passed

grep "ENABLE_CHUNKED_PREFILL" backend/services/auto_tuner.py
# Expected: patch_body에서 ENABLE_CHUNKED_PREFILL 키 사용

grep "enable-chunked-prefill" openshift/dev-only/vllm-runtime.yaml
# Expected: --enable-chunked-prefill CLI 인자 존재
```

### Final Checklist
- [x] `enable_chunked_prefill` → `ENABLE_CHUNKED_PREFILL`로 올바르게 매핑
- [x] `ENABLE_ENFORCE_EAGER`는 고정 설정으로 유지 (auto_tuner가 건드리지 않음)
- [x] ServingRuntime에 두 CLI 인자 모두 존재
- [x] 전체 단위 테스트 통과
