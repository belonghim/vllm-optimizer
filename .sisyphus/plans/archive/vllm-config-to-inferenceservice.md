# vLLM ConfigMap to InferenceService 연결 작업 계획

## TL;DR

> ConfigMap의 값을 ServingRuntime에 연결하여 Auto-tuner가 최적化した 파라미터를 실제로 vLLM에 적용할 수 있게 한다.

**작업內容**:
1. ServingRuntime에 ConfigMap envFrom 추가 + shell parameter substitution
2. Auto-tuner에 InferenceService 재시작 로직 추가

**예상 노력**: Short
**병렬 실행**: 가능 (서로 독립적인 변경)

---

## Context

### 현재 문제
- Auto-tuner가 ConfigMap (vllm-config)을 수정하면 값이 변경되지만, vLLM Pod에는 적용되지 않음
- ServingRuntime의 args가 하드코딩되어 있어서 ConfigMap을 참조하지 않음

### 해결 방식 (사용자提案)
```yaml
envFrom:
  - configMapRef:
      name: vllm-config
args:
  - |
    exec python -m vllm.entrypoints.openai.api_server \
      --max-num-seqs=${MAX_NUM_SEQS:-256} \
      ...
```

### Metis Review
- Gap: InferenceService 재시작 로직 부재 → Auto-tuner에 추가 필요

---

## Work Objectives

### Core Objective
ConfigMap 수정 시 vLLM InferenceService에 실제 적용

### Concrete Deliverables
1. `openshift/dev-only/vllm-runtime.yaml` - envFrom + parameter substitution 적용
2. `backend/services/auto_tuner.py` - ConfigMap 패치 후 InferenceService 재시작 로직 추가

### Must Have
- ConfigMap envFrom으로 주입
- Shell parameter substitution으로 CLI 인자 전달
- InferenceService 재시작 트리거

### Must NOT Have
- InferenceService 직접 수정 (ServingRuntime만 변경)
- 불필요한 환경 변수 추가

---

## Verification Strategy

### Test Decision
- **Infrastructure exists**: YES (pytest in backend/tests/)
- **Automated tests**: Tests-after
- **Framework**: pytest

### QA Policy
Backend 변경 후:
```bash
# 로컬 테스트
cd backend && python -m pytest tests/test_tuner.py -v

# 빌드 및 배포
podman build -t vllm-optimizer-backend:dev ./backend
# ... OpenShift 배포 ...
```

OpenShift 검증:
```bash
# ServingRuntime 적용 확인
oc get servingruntime vllm-openvino-runtime -n vllm -o yaml | grep -A5 envFrom

# InferenceService 재시작 후 ConfigMap 값 확인
oc rollout restart inferenceervice/llm-ov -n vllm
oc get pod -l serving.kserve.io/inferenceservice=llm-ov -n vllm
```

---

## Execution Strategy

### 병렬 가능 여부
**NO** - Task 2는 Task 1의 변경을 가정하므로 순차 실행

### Dependency
- Task 1 → Task 2

---

## TODOs

- [x] 1. ServingRuntime (vllm-runtime.yaml) 수정 - ConfigMap envFrom + shell parameter substitution

  **What to do**:
  - `openshift/dev-only/vllm-runtime.yaml` 파일 수정
  - 기존 args를 shell parameter substitution 형태로 변경
  - **command: ["/bin/sh", "-c"]** 추가 (핵심!)
  - envFrom으로 vllm-config ConfigMap 참조 추가
  - vLLM 인자: --max-num-seqs, --max-model-len, --gpu-memory-utilization, --enforce-eager

  **Must NOT do**:
  - InferenceService YAML 직접 수정
  - 기존 하드코딩된 env 유지 (불필요한 것만)

  **References**:
  - `openshift/dev-only/vllm-runtime.yaml` - 현재 하드코딩된 args (수정 대상)
  - `openshift/dev-only/vllm-config.yaml` - ConfigMap 키 목록

  **QA Scenarios**:

  ```
  Scenario: ServingRuntime YAML 검증
    Tool: Bash (oc)
    Preconditions: OpenShift 클러스터 접근 가능
    Steps:
      1. oc apply -f openshift/dev-only/vllm-runtime.yaml -n vllm
      2. oc get servingruntime vllm-openvino-runtime -n vllm -o yaml
    Expected Result: envFrom에 configMapRef 포함, args에 ${VAR:-default} 형태 포함
    Evidence: .sisyphus/evidence/task-1-servingruntime-applied.yaml

  Scenario: Pod 환경 변수 확인
    Tool: Bash (oc)
    Preconditions: InferenceService 재시작 후
    Steps:
      1. oc exec -it <vllm-pod> -n vllm -- env | grep MAX_NUM_SEQS
    Expected Result: ConfigMap의 값이 환경 변수로 설정됨
    Evidence: .sisyphus/evidence/task-1-env-vars.txt
  ```

  **Commit**: YES
  - Message: `feat(serve): connect ConfigMap to ServingRuntime via envFrom`
  - Files: `openshift/dev-only/vllm-runtime.yaml`

- [x] 2. Auto-tuner에 InferenceService 재시작 로직 추가

  **What to do**:
  - `backend/services/auto_tuner.py` 수정
  - ConfigMap 패치 후 `oc rollout restart inferenceervice/<name>` 또는 K8s API로 InferenceService 재시작 트리거
  - K8s client에 AppsV1Api 사용하여 patch 또는 restart 호출

  **Must NOT do**:
  - ServingRuntime 재시작 (InferenceService로 충분)

  **References**:
  - `backend/services/auto_tuner.py` - 현재 ConfigMap 패치만 수행 (재시작 로직 없음)
  - Kubernetes Python client: `kubernetes.client.AppsV1Api().patch_namespaced_deployment` 또는 Similar

  **QA Scenarios**:

  ```
  Scenario: Auto-tuner가 ConfigMap 패치 후 InferenceService 재시작
    Tool: Bash (curl + oc)
    Preconditions: Backend 배포 완료, InferenceService 실행 중
    Steps:
      1. curl -X POST http://localhost:8000/api/tuner/start -H "Content-Type: application/json" -d '{"config": {"n_trials": 1, "objective": "tps", "max_num_seqs_range": [64, 128]}}'
      2. oc get inferenceervice llm-ov -n vllm -o jsonpath='{.metadata.annotations.kserve\.io/restartedAt}'
    Expected Result: restartedAt annotation이 ConfigMap 패치 후 업데이트됨
    Evidence: .sisyphus/evidence/task-2-inference-restart.json

  Scenario: 튜닝 완료 후 ConfigMap 값이 InferenceService에 적용됨
    Tool: Bash (oc)
    Preconditions: 튜닝 완료
    Steps:
      1. oc get cm vllm-config -n vllm -o jsonpath='{.data.MAX_NUM_SEQS}'
      2. oc exec -it <vllm-pod> -n vllm -- cat /proc/1/cmdline | tr '\0' ' '
    Expected Result: ConfigMap의 MAX_NUM_SEQS 값이 vLLM 시작 인자로 사용됨
    Evidence: .sisyphus/evidence/task-2-final-config.txt
  ```

  **Commit**: YES
  - Message: `feat(tuner): restart InferenceService after ConfigMap patch`
  - Files: `backend/services/auto_tuner.py`

---

## Final Verification Wave

- [x] F1. **Plan Compliance Audit** — `oracle`
  - ConfigMap → ServingRuntime 연결 확인
  - InferenceService 재시작 로직 존재 확인
  - VERDICT: APPROVE/REJECT

- [x] F2. **Code Quality Review** — `unspecified-high`
  - `cd backend && python -m pytest tests/test_tuner.py -v`
  - Syntax/lint 확인
  - VERDICT: APPROVE/REJECT

- [x] F3. **Manual QA** — `unspecified-high` (+ `oc-openshift-cli` skill)
  - OpenShift에서 실제 튜닝 워크플로우 실행
  - ConfigMap 변경 → InferenceService 재시작 → vLLM 적용 확인
  - VERDICT: APPROVE/REJECT

---

## Commit Strategy

- **1**: `feat(serve): connect ConfigMap to ServingRuntime via envFrom` — vllm-runtime.yaml
- **2**: `feat(tuner): restart InferenceService after ConfigMap patch` — auto_tuner.py

---

## Success Criteria

- [x] ServingRuntime에 envFrom으로 vllm-config 연결
- [x] Shell parameter substitution으로 CLI 인자 전달
- [x] Auto-tuner ConfigMap 패치 후 InferenceService 재시작
- [x] 테스트 통과

