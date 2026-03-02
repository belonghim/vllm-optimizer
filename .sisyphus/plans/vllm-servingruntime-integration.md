# vLLM Optimizer: ServingRuntime/InferenceService 통합 및 검증 계획

## TL;DR

> **Quick Summary**: vLLM Optimizer가 실제 vLLM ServingRuntime/InferenceService와 통합되어 모니터링/튜닝이 가능하도록 필요한 YAML 리소스 생성 및 통합 테스트 가이드 작성
>
> **Deliverables**:
> - `openshift/base/vllm-runtime.yaml` (ServingRuntime 정의)
> - `openshift/base/vllm-inferenceservice.yaml` (InferenceService 정의)
> - `openshift/base/06-vllm-monitoring.yaml` (vLLM ServiceMonitor + PrometheusRule)
> - `openshift/base/vllm-networkpolicy.yaml` (Backend → vLLM 통신 허용)
> - `openshift/base/vllm-rbac.yaml` (RBAC Role/roleBinding)
> - `docs/integration_test_guide.md` (통합 테스트 가이드)
> - Updates to `openshift/base/02-config.yaml` (ConfigMap 검증)
>
> **Estimated Effort**: Medium
> **Parallel Execution**: YES - Waves 1-3 can parallelize where independent
> **Critical Path**: RBAC → ServingRuntime → InferenceService → NetworkPolicy → Monitoring → Test

---

## Context

### Original Request
현재 vllm-optimizer 는 실제 servingruntime, inferenceservice 를 기반으로 잘 동작할까?  
OpenVINO/Qwen2.5-Coder-3B-Instruct 모델 샘플을 사용해 누락된 YAML을 생성하고 통합 테스트 가능한 계획이 필요함.

### Interview Summary
**Key Discussions**:
- vLLM 메트릭 포맷: `vllm:*` prefix (Prometheus exporter)
- ServingRuntime API 버전: `kserve.io/v1alpha1` (사용자 예시와 일치)
- vLLM ConfigMap 키: auto_tuner.py가 패치하는 키 (`MAX_NUM_SEQS`, `GPU_MEMORY_UTILIZATION`, `MAX_MODEL_LEN`, `ENABLE_CHUNKED_PREFILL`)
- 네트워크: Backend는 `vllm-optimizer` 네임스페이스, vLLM은 `vllm` 네임스페이스
- 모니터링: Thanos Querier 사용 (OpenShift Monitoring Stack)

**Research Findings**:
- `05-monitoring.yaml`은 Optimizer Backend만 모니터링
- `02-config.yaml`에 vLLM 연결 설정 있음 (`VLLM_ENDPOINT`, `VLLM_NAMESPACE`, `VLLM_DEPLOYMENT_NAME`, `VLLM_CONFIGMAP_NAME`)
- `auto_tuner.py`가 vLLM ConfigMap을 패치하여 파라미터 업데이트 시도
- Backend ServiceAccount에 vLLM 네임스페이스 리소스 접근 권한 없음 (RBAC 누락)

---

## Work Objectives

### Core Objective
vLLM Optimizer가 실제 배포된 vLLM ServingRuntime/InferenceService와 성공적으로 통합되어 메트릭 수집, 부하 테스트, 자동 튜닝이 동작하도록 필요한 인프라 리소스 생성 및 검증

### Concrete Deliverables
1. `openshift/base/vllm-runtime.yaml` — vLLM ServingRuntime 정의
2. `openshift/base/vllm-inferenceservice.yaml` — InferenceService 정의 (PVC, 모델 경로, 리소스 요청)
3. `openshift/base/06-vllm-monitoring.yaml` — vLLM ServiceMonitor + PrometheusRule + PDB
4. `openshift/base/vllm-networkpolicy.yaml` — Optimizer Backend → vLLM Service 통신 허용
5. `openshift/base/vllm-rbac.yaml` — vLLM namespace에 optimizer-backend SA 권한 부여
6. `docs/integration_test_guide.md` — 통합 테스트 절차 (에이전트 실행 가능 QA 시나리오 포함)
7. Updates to `openshift/base/02-config.yaml` — vLLM ConfigMap 타입/키 검증 및 보강
8. Updates to `openshift/base/kustomization.yaml` — 새 리소스 추가

### Definition of Done
- [ ] `oc apply -k openshift/overlays/dev` 실행 시 모든 YAML 성공적으로 적용됨
- [ ] InferenceService Ready 상태 (`oc get is llm-ov -n vllm` → READY=True)
- [ ] vLLM ServiceMonitor가 vLLM 메트릭 엔드포인트 스크랩 성공 (Prometheus UI에서 확인)
- [ ] Optimizer Backend가 vLLM 메트릭 정상 수집 (`GET /api/metrics/latest`에서 vLLM 데이터 반환)
- [ ] Auto Tuner가 vLLM ConfigMap 패치 성공 (patch 테스트 완료)
- [ ] 통합 테스트 가이드의 모든 QA 시나리오가 에이전트 실행 가능하고 성공함
- [ ] NetworkPolicy가 Optimizer → vLLM 통신 허용하고 타 Pod는 차단

### Must Have
- 반드시 `kserve.io/v1alpha1` API 사용 (사용자 지정)
- vLLM ConfigMap 키는 auto_tuner.py와 호환 (`MAX_NUM_SEQS`, `GPU_MEMORY_UTILIZATION`, `MAX_MODEL_LEN`, `ENABLE_CHUNKED_PREFILL`)
- vLLM 메트릭 엔드포인트는 `/metrics` (path) + `http` 포트 (name: `http`)
- 모든 리소스는 `openshift/base/`에 저장 후 kustomization.yaml에 추가
- vLLM namespace는 `vllm` (사용자 예시와 일치)

### Must NOT Have (Guardrails)
- ServingRuntime API를 `v1beta1`으로 변경하지 않음 (사용자 요구사항 위반)
- vLLM 네임스페이스를 `vllm` 외로 변경하지 않음
- Optimizer 코드를 수정하지 않음 (routers의 실제 구현은 이 계획 범위 외)
- vLLM 이미지를 다시 빌드하지 않음 (사용자가 `quay.io/joopark/vllm-openvino:latest` 제공)
- 모델 다운로드/복사 절차를 자동화하지 않음 (사용자 스크립트로 처리)
- 기존 vLLM 서비스가 이미 배포되어 있다면 덮어쓰지 않음 (idempotent apply)

---

## Verification Strategy

### Test Decision
- **Infrastructure exists**: YES (oc, kustomize)
- **Automated tests**: Tests-after (integration tests after deployment)
- **Framework**: Custom agent-executed bash scenarios (oc exec, curl)
- **TDD**: Not applicable (infrastructure as code)

### QA Policy
**모든 task는 Agent-Executed QA Scenarios 포함**. Acceptance criteria는 bash command로 실행 가능해야 함.

- **Kubernetes 리소스 생성**: `oc get <resource> -n vllm -o jsonpath`로 존재/상태 확인
- **메트릭 수집**: Thanos Querier 쿼리로 vLLM 메트릭 존재 확인
- **네트워크 연결**: Backend Pod에서 vLLM endpoint curl로 통신 확인
- **ConfigMap 패치**: auto_tuner API 호출 → ConfigMap 값 변경 확인
- **파이프라인**: Kustomize apply → 모든 리소스 생성 확인

---

## Execution Strategy

### Parallel Execution Waves

```
Wave 1 (Foundation - RBAC + ConfigMap validation):
├── Task 1: Validate vLLM ConfigMap structure in 02-config.yaml [quick]
├── Task 2: Create vLLM-Role + RoleBinding for optimizer-backend SA [quick]
└── Task 3: Update kustomization.yaml with new resources [quick]

Wave 2 (vLLM Service Deployment):
├── Task 4: Create ServingRuntime YAML (vllm-runtime.yaml) [quick]
├── Task 5: Create InferenceService YAML (vllm-inferenceservice.yaml) [quick]
└── Task 6: Deploy vLLM resources with kustomize [medium]

Wave 3 (Monitoring + Network):
├── Task 7: Create vLLM ServiceMonitor + PrometheusRule (06-vllm-monitoring.yaml) [medium]
├── Task 8: Create vLLM NetworkPolicy (vllm-networkpolicy.yaml) [quick]
└── Task 9: Verify vLLM ServiceMonitor scraping (manual check + agent QA) [unspecified-high]

Wave 4 (Integration + Validation):
├── Task 10: Verify Backend → vLLM connectivity (curl test) [quick]
├── Task 11: Verify vLLM metrics in Optimizer API (GET /api/metrics/latest) [quick]
├── Task 12: Verify Auto Tuner ConfigMap patch (end-to-end test) [unspecified-high]
└── Task 13: Write integration test guide (docs/integration_test_guide.md) [writing]

Wave FINAL (Independent Review):
├── Task F1: Plan compliance audit (oracle) — 모든 deliverable 생성 확인
├── Task F2: NetworkPolicy validation (unspecified-high) — 실제 통신 허용 확인
├── Task F3: End-to-end smoke test (unspecified-high) — 모든 QA 시나리오 실행
└── Task F4: Scope fidelity check (deep) — vLLM 수정 없이 통합만 확인
```

### Dependency Matrix

- **1** (ConfigMap validation): — — 2-3
- **2** (RBAC): 1 — 6 (vLLM namespace 접근), 9 (ServiceMonitor 권한), 10
- **3** (kustomization): 1, 2, 4, 7, 8 — 6, 9
- **4** (ServingRuntime): — — 5, 6
- **5** (InferenceService): 4 — 6
- **6** (vLLM deploy): 2, 3, 5 — 9, 10, 11, 12
- **7** (vLLM monitoring): 2 — 9
- **8** (NetworkPolicy): 2 — 10
- **9** (ServiceMonitor verify): 3, 6, 7 — 11, 12
- **10** (connectivity): 2, 6, 8 — 11
- **11** (metrics in optimizer): 6, 9 — 12
- **12** (auto-tuner patch): 6, 11 — 13, F4
- **13** (test guide): 10, 11, 12 — F4

### Agent Dispatch Summary

- **Wave 1**: Task 1 → `quick`, Task 2 → `quick`, Task 3 → `quick`
- **Wave 2**: Task 4 → `quick`, Task 5 → `quick`, Task 6 → `unspecified-high` (deploy coordination)
- **Wave 3**: Task 7 → `medium` (monitoring config), Task 8 → `quick`, Task 9 → `unspecified-high` (scraping verification)
- **Wave 4**: Task 10 → `quick`, Task 11 → `quick`, Task 12 → `unspecified-high` (end-to-end), Task 13 → `writing`
- **FINAL**: F1 → `oracle`, F2 → `unspecified-high`, F3 → `unspecified-high`, F4 → `deep`

---

## TODOs

---

## Wave 1: Foundation & Validation

- [x] 1. Validate vLLM ConfigMap structure in 02-config.yaml

  **What to do**:
  - `openshift/base/02-config.yaml`의 `VLLM_CONFIGMAP_NAME`, `VLLM_DEPLOYMENT_NAME` 값 확인
  - auto_tuner.py에서 사용하는 키 (`MAX_NUM_SEQS`, `GPU_MEMORY_UTILIZATION`, `MAX_MODEL_LEN`, `ENABLE_CHUNKED_PREFILL`)가 실제 vLLM ConfigMap에 존재하는지 확인
  - ConfigMap 데이터 타입 검증 (문자열 values)

  **Must NOT do**:
  - ConfigMap 구조를 auto_tuner에 맞춰 임의로 수정하지 않음 (실제 vLLM 이미지 문서 기준)

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: 단순 파일 읽기 및 검증 작업
  - **Skills**: [`code-reader` (파일 내용 파싱), `kubernetes` (ConfigMap 구조 이해)]
    - `code-reader`: `02-config.yaml` 읽기 및 파싱
    - `kubernetes`: ConfigMap data 필드 형식 검증
  - **Skills Evaluated but Omitted**:
    - `lsp`: 언어 서버 필요 없음 (YAML 데이터 검증만)

  **Parallelization**:
  - **Can Run In Parallel**: YES (다른 Wave 1 tasks와)
  - **Parallel Group**: Wave 1 (Tasks 1, 2, 3)
  - **Blocks**: Task 2, Task 3 (kustomization depends on validation outcome)
  - **Blocked By**: None

  **References**:
  - `openshift/base/02-config.yaml` — vLLM 연결 설정
  - `backend/services/auto_tuner.py:146-162` — ConfigMap 패치 키
  - `docs/vLLM_ConfigMap_Reference.md` (external — vLLM 이미지 문서 참조)

  **Acceptance Criteria**:
  - [ ] `02-config.yaml`의 `VLLM_CONFIGMAP_NAME`, `VLLM_DEPLOYMENT_NAME` 값이 valid한지 확인
  - [ ] auto_tuner.py의 키와 실제 vLLM ConfigMap 키 매핑 확인 (문서화)

  **QA Scenarios (MANDATORY)**:

  Scenario: Validate ConfigMap name exists in current ConfigMap list
    Tool: Bash
    Preconditions: cluster context set, openshift/base/02-config.yaml exists
    Steps:
      1. Extract VLLM_CONFIGMAP_NAME value: `grep VLLM_CONFIGMAP_NAME openshift/base/02-config.yaml | cut -d'"' -f2`
      2. Check if ConfigMap exists in vllm namespace: `oc get cm -n vllm <extracted-name>`
    Expected Result: ConfigMap exists (exit code 0) OR ConfigMap will be created with deployment (acceptable)
    Failure Indicators: ConfigMap referenced but not created and not auto-created by vLLM
    Evidence: .sisyphus/evidence/task-1-configmap-check.txt

  Scenario: Verify ConfigMap keys match auto_tuner expectations
    Tool: Bash
    Preconditions: ConfigMap exists in vllm namespace
    Steps:
      1. Fetch ConfigMap data: `oc get cm <configmap-name> -n vllm -o jsonpath='{.data}'`
      2. Check for keys: `MAX_NUM_SEQS`, `GPU_MEMORY_UTILIZATION`, `MAX_MODEL_LEN`, `ENABLE_CHUNKED_PREFILL`
    Expected Result: At least 3 of 4 keys are present (vLLM version dependent). Document any missing keys in plan adjustments.
    Failure Indicators: None of the expected keys present → auto_tuner will fail
    Evidence: .sisyphus/evidence/task-1-configmap-keys.json

  **Commit**: NO (documentation update only, no code change)

---

- [x] 2. Create vLLM-Role + RoleBinding for optimizer-backend SA

  **What to do**:
  - vLLM namespace에 `vllm-optimizer-backend` ServiceAccount가 ConfigMap 조회/패치, Deployment 조회, Service 조회 권한을 가질 Role 생성
  - RoleBinding으로 vLLM namespace의 `vllm-optimizer-backend` SA에 Role 부여
  - RBAC 리소스는 vLLM namespace에 생성

  **Must NOT do**:
  - ClusterRole/ClusterRoleBinding 사용 (最小 권한)
  - vllm-optimizer-backend SA를 vLLM namespace에 생성하지 않음 (기존 SA 사용)

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: 단일 리소스 생성, 표준 k8s RBAC 패턴
  - **Skills**: [`kubernetes` (RBAC YAML 작성), `security` (最小 권한 원칙)]
    - `kubernetes`: Role, RoleBinding API 스키마 정확성
    - `security`: 권한 최소화 (read, patch만 허용)
  - **Skills Evaluated but Omitted**:
    - `deep`: 복잡한 권한 계산 필요 없음

  **Parallelization**:
  - **Can Run In Parallel**: YES (Task 1, 3)
  - **Parallel Group**: Wave 1
  - **Blocks**: Task 6 (vLLM deployment requires RBAC), Task 10 (connectivity), Task 12 (auto-tuner patch)
  - **Blocked By**: Task 1 (ConfigMap name validation)

  **References**:
  - `openshift/base/01-namespace-rbac.yaml` — 기존 namespace, SA, SCC 패턴 참고
  - `backend/services/auto_tuner.py:153-165` — 필요한 API 그룹: `apps/v1` (Deployment), `v1` (ConfigMap, Service)
  - `backend/services/metrics_collector.py:164-188` — 필요한 API 그룹: `apps/v1` (Deployment), `v1` (Pod)

  **Acceptance Criteria**:
  - [ ] Role `vllm-optimizer-backend-role` exists in `vllm` namespace
  - [ ] RoleBinding `vllm-optimizer-backend-rb` exists in `vllm` namespace
  - [ ] Role rules include:
    - `apps/v1` → `deployments`: get, list, patch
    - `v1` → `configmaps`: get, list, patch
    - `v1` → `services`: get, list
    - `v1` → `pods`: get, list (metrics_collector용)
  - [ ] Binding subjects: `kind: ServiceAccount`, `name: vllm-optimizer-backend`, `namespace: vllm-optimizer-dev`

  **QA Scenarios (MANDATORY)**:

  Scenario: Verify Role and RoleBinding exist
    Tool: Bash
    Preconditions: vLLM namespace exists; RBAC YAML applied
    Steps:
      1. `oc get role vllm-optimizer-backend-role -n vllm -o yaml`
      2. `oc get rolebinding vllm-optimizer-backend-rb -n vllm -o yaml`
    Expected Result: Both commands return exit code 0 with YAML output
    Failure Indicators: `Error from server (NotFound):` → resources not created
    Evidence: .sisyphus/evidence/task-2-role-check.txt

  Scenario: Verify ServiceAccount can patch ConfigMap (dry-run)
    Tool: Bash
    Preconditions: Role/RoleBinding applied; vLLM ConfigMap exists
    Steps:
      1. Create a temporary pod with the same SA: `oc run test-sa --rm -i --tty --image=registry.access.redhat.com/ubi9/ubi -n vllm --serviceaccount=vllm-optimizer-backend -- bash`
      2. Inside pod, try to patch: `oc patch cm vllm-config -n vllm --type=merge -p '{"data":{"TEST_KEY":"test"}}'`
    Expected Result: Patch command succeeds (no authorization error)
    Failure Indicators: `Error from server (Forbidden):` → RBAC insufficient
    Evidence: .sisyphus/evidence/task-2-rbac-patch-test.txt

  **Commit**: YES
  - Message: `feat(openshift): add RBAC Role/RoleBinding for vLLM access`
  - Files: `openshift/base/vllm-rbac.yaml`
  - Pre-commit: `oc kustomize openshift/overlays/dev | oc apply -f - --dry-run=client`

---

- [x] 3. Update kustomization.yaml with new resources

  **What to do**:
  - `openshift/base/kustomization.yaml`에 새 리소스 추가: `vllm-rbac.yaml`, `vllm-runtime.yaml`, `vllm-inferenceservice.yaml`, `06-vllm-monitoring.yaml`, `vllm-networkpolicy.yaml`
  - 순서 고려: RBAC → Runtime → IS → Monitoring → NetworkPolicy

  **Must NOT do**:
  - 기존 resources.yaml의 순서를 망가뜨리지 않음 (Kustomize는 순서대로 적용)
  - patches 기존 리소스 수정 (configMap 등은 수정 필요하면 patches/ 디렉토리 사용)

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: 파일 수정만
  - **Skills**: [`yaml-manipulator` (kustomization 편집)]
  - **Skills Evaluated but Omitted**:
    - `testing`: 테스트 없음

  **Parallelization**:
  - **Can Run In Parallel**: NO (다음 wave에 의존)
  - **Blocks**: Task 6, Task 9 (kustomize 적용 requires all files listed)
  - **Blocked By**: Task 1, Task 2 (파일 존재 확인)

  **References**:
  - `openshift/base/kustomization.yaml` — current resources list
  - `openshift/overlays/dev/kustomization.yaml` — overlay bases

  **Acceptance Criteria**:
  - [ ] `kustomization.yaml`에 새 YAML 파일들이 `resources:` 섹션에 추가됨
  - [ ] 중복 없음
  - [ ] 순서: RBAC → Runtime → IS → Monitoring → NetworkPolicy

  **QA Scenarios**:

  Scenario: Verify kustomize includes new resources
    Tool: Bash
    Preconditions: kustomization.yaml updated
    Steps:
      1. `oc kustomize openshift/base | grep -E 'kind: (Role|ServingRuntime|InferenceService|ServiceMonitor|PrometheusRule|NetworkPolicy)'`
    Expected Result: Output contains 6+ resources (including RBAC, runtime, IS, etc.)
    Failure Indicators: Missing kinds or fewer than expected
    Evidence: .sisyphus/evidence/task-3-kustomize-check.txt

  **Commit**: YES
  - Message: `build(openshift): add vLLM resources to kustomization`
  - Files: `openshift/base/kustomization.yaml`
  - Pre-commit: `git diff --check openshift/base/kustomization.yaml`

---

## Wave 2: vLLM Service Deployment

- [x] 4. Create vLLM ServingRuntime YAML

  **What to do**:
  - `openshift/base/vllm-runtime.yaml` 생성
  - API 버전: `serving.kserve.io/v1alpha1`
  - Kind: `ServingRuntime`
  - 메타데이터: `name: vllm-openvino-runtime`, `namespace: vllm`
  - spec:
    - `supportedModelFormats`: [{name: vLLM, autoSelect: true}]
    - `containers`:
      - `name: kserve-container`
      - `image: quay.io/joopark/vllm-openvino:latest`
      - `imagePullPolicy: Always`
      - `args`: `--port=8080`, `--model=/models/Qwen2.5-Coder-3B-Instruct-int4-ov`, `--served-model-name=Qwen2.5-Coder-3B-Instruct-int4-ov`, `--max-model-len=8192`
      - `env`:
        - `VLLM_TARGET_DEVICE: "cpu"`
        - `CUDA_VISIBLE_DEVICES: ""`
        - `VLLM_USE_V1: "0"`
        - `HF_HUB_OFFLINE: "1"`
        - `TRANSFORMERS_OFFLINE: "1"`
        - `VLLM_OPENVINO_ENABLE_QUANTIZED_WEIGHTS: "ON"`
        - `VLLM_OPENVINO_KV_CACHE_PRECISION: "u8"`
        - `VLLM_OPENVINO_DEVICE: "CPU"`
      - `ports`: `containerPort: 8080`
      - `volumeMounts`: `models` PVC mount at `/models` (optional if PVC provided at InferenceService level)
    - `volumes`: optional if not mounting PVC here

  **Must NOT do**:
  - image PullPolicy를 `IfNotPresent`로 변경 (Always로 고정)
  - gpu 관련 env 추가 (OpenVINO CPU 전용)

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: YAML 템플릿 작성, 평이한 데이터 매핑
  - **Skills**: [`yaml-serializer` (API 객체 → YAML), `kubernetes` (CRD 스키마)]
    - `yaml-serializer`: ServingRuntime spec 정확성
    - `kubernetes`: kserve.io/v1alpha1 API 이해
  - **Skills Evaluated but Omitted**:
    - `security`: 보안 context 필요 없음

  **Parallelization**:
  - **Can Run In Parallel**: YES (Task 5)
  - **Parallel Group**: Wave 2
  - **Blocks**: Task 6 (deploy depends on both runtime and IS existing)
  - **Blocked By**: Task 2 (RBAC), Task 3 (kustomization)

  **References**:
  - User-provided example: `ServingRuntime` YAML (kserve.io/v1alpha1)
  - OpenShift AI docs: ServingRuntime CRD spec
  - vLLM OpenVINO Docker image env vars

  **Acceptance Criteria**:
  - [ ] YAML 파일 `openshift/base/vllm-runtime.yaml` 생성됨
  - [ ] `apiVersion: serving.kserve.io/v1alpha1`
  - [ ] `kind: ServingRuntime`
  - [ ] `metadata.name: vllm-openvino-runtime`, `namespace: vllm`
  - [ ] `spec.containers[0].image: quay.io/joopark/vllm-openvino:latest`
  - [ ] `args` 목록에 `--port=8080`, `--model=/models/Qwen2.5-Coder-3B-Instruct-int4-ov` 포함
  - [ ] `env`에 OpenVINO 관련 env 필드들 포함

  **QA Scenarios**:

  Scenario: Verify ServingRuntime YAML syntax and required fields
    Tool: Bash
    Preconditions: vllm-runtime.yaml exists
    Steps:
      1. Validate YAML: `oc create --dry-run=client -f openshift/base/vllm-runtime.yaml`
    Expected Result: No errors; output shows valid object
    Failure Indicators: `error:` message → syntax or schema validation error
    Evidence: .sisyphus/evidence/task-4-runtime-validate.txt

  Scenario: Verify ServingRuntime can be applied without conflicts
    Tool: Bash
    Preconditions: vllm-runtime.yaml exists; kustomization includes it
    Steps:
      1. `oc kustomize openshift/base | oc apply --dry-run=client -f -`
    Expected Result: `resource.apiGroup/servicing.kserve.io "vllm-openvino-runtime" successfully configured`
    Failure Indicators: Conflict errors → resource already exists with different spec
    Evidence: .sisyphus/evidence/task-4-apply-dryrun.txt

  **Commit**: YES
  - Message: `feat(openshift): add vLLM ServingRuntime definition`
  - Files: `openshift/base/vllm-runtime.yaml`
  - Pre-commit: `oc create --dry-run=client -f openshift/base/vllm-runtime.yaml`

---

- [x] 5. Create vLLM InferenceService YAML

  **What to do**:
  - `openshift/base/vllm-inferenceservice.yaml` 생성
  - API 버전: `serving.kserve.io/v1beta1` (사용자 예시와 일치)
  - Kind: `InferenceService`
  - 메타데이터: `name: llm-ov`, `namespace: vllm`
  - spec:
    - `predictor`:
      - `model`:
        - `modelFormat: {name: vLLM}`
        - `runtime: vllm-openvino-runtime`
        - `resources`:
          - requests: `cpu: "4"`, `memory: "8Gi"`
          - limits: `cpu: "8"`, `memory: "16Gi"`
        - `volumeMounts`:
          - `name: models`, `mountPath: /models`
        - `model`'s `volumes`:
          - `name: models`, `persistentVolumeClaim: {claimName: model-pvc}`
  - 참고: PVC `model-pvc`는 사전 생성되어야 함 (사용자 스크립트)

  **Must NOT do**:
  - `InferenceService`의 `spec.predictor.model` 필드명 오타 (`model` vs `modelCode`)
  - `runtime` 이름이 `ServingRuntime`의 `metadata.name`과 일치하지 않게 작성 (`vllm-openvino-runtime`)
  - PVC를 `volumes`가 아닌 `volumeMounts`에 정의함 (层级 주의)

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: YAML 템플릿 작성
  - **Skills**: [`yaml-serializer`, `kubernetes`]
    - `yaml-serializer`: InferenceService nested structure (predictor.model.volumes vs volumeMounts)
    - `kubernetes`: kserve v1beta1 spec 검증

  **Parallelization**:
  - **Can Run In Parallel**: YES (Task 4)
  - **Parallel Group**: Wave 2
  - **Blocks**: Task 6
  - **Blocked By**: Task 2, Task 3, Task 4

  **References**:
  - User-provided example: InferenceService YAML (kserve.io/v1beta1)
  - KServe documentation: InferenceService spec structure

  **Acceptance Criteria**:
  - [ ] `apiVersion: serving.kserve.io/v1beta1`
  - [ ] `kind: InferenceService`
  - [ ] `metadata.name: llm-ov`, `namespace: vllm`
  - [ ] `spec.predictor.model.runtime: vllm-openvino-runtime` (matches ServingRuntime name)
  - [ ] `spec.predictor.model.volumeMounts[0].mountPath: /models`
  - [ ] `spec.predictor.model.volumes[0].persistentVolumeClaim.claimName: model-pvc`

  **QA Scenarios**:

  Scenario: Validate InferenceService YAML
    Tool: Bash
    Preconditions: vllm-inferenceservice.yaml exists
    Steps:
      1. `oc create --dry-run=client -f openshift/base/vllm-inferenceservice.yaml`
    Expected Result: Valid object without errors
    Failure Indicators: `error: unknown field` → typo in fields
    Evidence: .sisyphus/evidence/task-5-is-validate.txt

  Scenario: Check that InferenceService references correct runtime
    Tool: Bash
    Preconditions: YAML exists
    Steps:
      1. `grep -A2 'runtime:' openshift/base/vllm-inferenceservice.yaml`
      2. `grep 'name:' openshift/base/vllm-runtime.yaml`
    Expected Result: Both values equal `vllm-openvino-runtime`
    Failure Indicators: Mismatch → InferenceService will fail to find runtime
    Evidence: .sisyphus/evidence/task-5-runtime-match.txt

  **Commit**: YES
  - Message: `feat(openshift): add vLLM InferenceService (OpenVINO Qwen2.5-Coder)`
  - Files: `openshift/base/vllm-inferenceservice.yaml`
  - Pre-commit: `oc create --dry-run=client -f openshift/base/vllm-inferenceservice.yaml`

---

- [x] 6. Deploy vLLM resources with Kustomize (manual step for user)

  **What to do**:
  - 사용자에게 제공하는 가이드: `oc apply -k openshift/overlays/dev`
  - **Note**: 이 task는 계획의 일부로 실행되지 않음. 대신 통합 테스트 가이드에 포함.

  **Must NOT do**:
  - 자동으로 `oc apply` 실행하지 않음 (사용자 환경 의존)
  - PVC 생성 자동화하지 않음 (사용자 스크립트로 처리)

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
    - Reason: 배포 시 발생할 수 있는 문제를 문서화해야 함
  - **Skills**: [`kubernetes` (apply issues debug)]
    - `kubernetes`: typical errors (PVC not found, image pull secret, quota)

  **Parallelization**:
  - **Blocks**: Task 9, 10, 11, 12 (모든 통합 테스트는 vLLM이 Running 되어야)
  - **Blocked By**: Task 1, 2, 3, 4, 5

  **References**:
  - User-provided deployment script (model download, PVC create, oc create commands)

  **Acceptance Criteria**:
  - [ ] `oc apply -k openshift/overlays/dev` returns exit code 0
  - [ ] InferenceService `llm-ov` enters Ready state within 5 minutes
  - [ ] vLLM Pods are Running and Ready (`oc get pods -l app=llm-ov -n vllm`)

  **QA Scenarios (가이드에 포함)**:

  Scenario: Verify vLLM InferenceService is Ready
    Tool: Bash
    Preconditions: vLLM resources applied
    Steps:
      1. `oc get is llm-ov -n vllm -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}'`
    Expected Result: `True`
    Failure Indicators: `False` or empty → check `oc describe is llm-ov` and pod events
    Evidence: .sisyphus/evidence/task-6-is-ready.txt

  Scenario: Verify vLLM service endpoint exists
    Tool: Bash
    Preconditions: InferenceService Ready
    Steps:
      1. Get route host: `oc get route llm-ov-predictor -n vllm -o jsonpath='{.spec.host}'`
      2. Test basic connectivity: `curl -s http://<host>/v1/models`
    Expected Result: HTTP 200 with model list JSON
    Failure Indicators: Connection refused, 404 → service not ready or route wrong
    Evidence: .sisyphus/evidence/task-6-vllm-endpoint.txt

  **Commit**: NO (部署 작업, 사용자 실행)

---

## Wave 3: Monitoring + Network

- [x] 7. Create vLLM ServiceMonitor + PrometheusRule (06-vllm-monitoring.yaml)

  **What to do**:
  - `openshift/base/06-vllm-monitoring.yaml` 생성 (기존 05-monitoring.yaml과 별도 파일 또는 확장)
  - **ServiceMonitor**:
    - `metadata.name: vllm-openvino-runtime`
    - `labels.openshift.io/cluster-monitoring: "true"`
    - `spec.selector.matchLabels`: vLLM service labels (예: `serving.kserve.io/inferenceservice: llm-ov`)
    - `spec.endpoints`:
      - `port: http` (vLLM 컨테이너 포트 이름)
      - `path: /metrics`
      - `interval: 15s`
      - `scheme: http`
  - **PrometheusRule**:
    - vLLM 성능 알람: `VLLMHighP99Latency`, `VLLMHighQueueDepth`, `VLLMKVCacheSaturation`, `VLLMLowThroughput` (05-monitoring.yaml 내용 참고, 메트릭 이름 조정 필요)
  - **PDB**: optional (vLLM deployment에 minAvailable)
  - NetworkPolicy for vLLM service (다음 task)

  **Must NOT do**:
  - Backend ServiceMonitor과 충돌하는 label selector 사용
  - vLLM 메트릭 이름을 optimizer collector의 쿼리(`vllm:*`)와 다르게 정의 (일치성 유지)

  **Recommended Agent Profile**:
  - **Category**: `medium`
    - Reason: monitoring 구성은 세부 사항이 많고, 메트릭 이름과 selector 정확성 중요
  - **Skills**: [`prometheus` (ServiceMonitor, Rules), `kubernetes`]
    - `prometheus`: PrometheusRule expressions, ServiceMonitor endpoint config
    - `kubernetes`: label selector matching vLLM service anatomy
  - **Skills Evaluated but Omitted**:
    - `security`: TLS 설정? vLLM이 http만 노출

  **Parallelization**:
  - **Can Run In Parallel**: YES (Task 8)
  - **Parallel Group**: Wave 3
  - **Blocks**: Task 9 (verification depends on this being applied)
  - **Blocked By**: Task 2 (RBAC for ServiceMonitor? Actually ServiceMonitor is cluster-wide; ensure namespace has monitoring label)

  **References**:
  - `openshift/base/05-monitoring.yaml` — 기존 ServiceMonitor/Rule 패턴
  - `backend/services/metrics_collector.py:46-58` — vLLM 메트릭 쿼리 (metric names)
  - OpenShift Monitoring docs: ServiceMonitor label requirements

  **Acceptance Criteria**:
  - [ ] `ServiceMonitor` resource created with correct target (vLLM service)
  - [ ] `PrometheusRule` with expressions that match vLLM metrics (`vllm:e2e_request_latency_seconds_bucket`, etc.)
  - [ ] `Port` name matches vLLM service's port name (usually `http`)
  - [ ] Namespace `vllm` has label `openshift.io/cluster-monitoring: "true"` (05-monitoring.yaml 참고)

  **QA Scenarios**:

  Scenario: Verify ServiceMonitor exists and has correct target
    Tool: Bash
    Preconditions: monitoring yaml applied
    Steps:
      1. `oc get servicemonitor vllm-openvino-runtime -n vllm -o yaml`
      2. Check `spec.selector.matchLabels` matches vLLM service labels
    Expected Result: selector matches; endpoints.port.name is `http`; path is `/metrics`
    Failure Indicators: selector mismatch → Prometheus cannot find target
    Evidence: .sisyphus/evidence/task-7-servicemonitor-check.txt

  Scenario: Verify Prometheus rule is loaded (query Thanos)
    Tool: Bash
    Preconditions: ServiceMonitor applied; vLLM metrics exist
    Steps:
      1. Get token: `TOKEN=$(oc serviceaccounts get-token vllm-optimizer-backend -n vllm-optimizer)`
      2. Query a rule target metric: `curl -k -H "Authorization: Bearer $TOKEN" "https://thanos-querier.openshift-monitoring.svc.cluster.local:9091/api/v1/query?query=vllm:num_requests_running"`
    Expected Result: JSON with non-empty `data.result` array (or empty array if no requests yet, but metric exists)
    Failure Indicators: `status: error` or `data: []` with no metric family → metric not scraped
    Evidence: .sisyphus/evidence/task-7-prometheus-query.txt

  **Commit**: YES
  - Message: `feat(monitoring): add vLLM ServiceMonitor and PrometheusRule`
  - Files: `openshift/base/06-vllm-monitoring.yaml`
  - Pre-commit: `oc create --dry-run=client -f openshift/base/06-vllm-monitoring.yaml`

---

- [x] 8. Create vLLM NetworkPolicy (allow optimizer-backend access)

  **What to do**:
  - `openshift/base/vllm-networkpolicy.yaml` 생성
  - Namespace: `vllm`
  - `podSelector`:
    - matchLabels that select vLLM service pods (likely `serving.kserve.io/inferenceservice: llm-ov` or `app: llm-ov`)
  - `policyTypes: [Ingress]`
  - `ingress`:
    - allow from same namespace (optional, for intra-namespace)
    - allow from `vllm-optimizer-dev` namespace, selector `app=vllm-optimizer-backend`
    - allow from `openshift-monitoring` (for Prometheus scraping)
    - allow from kube-apiserver (cluster monitoring)
  - Ports: `- port: 8000` (vLLM OpenAI-compatible API) and `- port: 8080` (metrics) if separate; check vLLM service port names

  **Must NOT do**:
  - vLLM service의 포트 범위를 지나치게 넓히기 (8000, 8080만)
  - `namespaceSelector` without matchLabels를 사용해 전체 namespace 허용하지 않기

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: 단일 NetworkPolicy 작성, 패턴 따라함
  - **Skills**: [`kubernetes` (NetworkPolicy), `security`]
    - `kubernetes`: podSelector, namespaceSelector, ports
    - `security`: minimal ingress rules

  **Parallelization**:
  - **Can Run In Parallel**: YES (Task 7)
  - **Parallel Group**: Wave 3
  - **Blocks**: Task 10 (connectivity depends on NetworkPolicy)
  - **Blocked By**: Task 2 (RBAC? not needed for NetworkPolicy), Task 3 (kustomization)

  **References**:
  - `openshift/base/05-monitoring.yaml:171-256` — 기존 NetworkPolicy 패턴 (optimizer networkpolicy)
  - vLLM service port definition (from InferenceService) — port names/numbers

  **Acceptance Criteria**:
  - [ ] NetworkPolicy created in `vllm` namespace
  - [ ] `ingress.from` includes:
    - namespaceSelector for `vllm-optimizer-dev` with podSelector `app=vllm-optimizer-backend`
    - namespaceSelector for `openshift-monitoring`
  - [ ] `ingress.ports` include at least port 8000 (API) and 8080 (metrics)

  **QA Scenarios**:

  Scenario: Verify NetworkPolicy exists and selects correct pods
    Tool: Bash
    Preconditions: NetworkPolicy applied
    Steps:
      1. `oc get netpol -n vllm -o yaml`
      2. Check `podSelector.matchLabels` matches vLLM pods
    Expected Result: Policy exists and selector is not empty
    Failure Indicators: No matching pods → traffic not controlled
    Evidence: .sisyphus/evidence/task-8-netpol-check.txt

  Scenario: Verify connectivity from optimizer backend to vLLM
    Tool: Bash
    Preconditions: NetworkPolicy applied; both backends running
    Steps:
      1. Get optimizer pod: `OPT_POD=$(oc get pod -l app=vllm-optimizer-backend -n vllm-optimizer -o name | head -1)`
      2. Get vLLM service clusterIP: `VLLM_SVC=$(oc get svc llm-ov -n vllm -o jsonpath='{.spec.clusterIP}')`
      3. `oc exec $OPT_POD -n vllm-optimizer -- curl -s http://$VLLM_SVC:8000/v1/models`
    Expected Result: HTTP 200 (connection allowed)
    Failure Indicators: Connection timeout or refused → NetworkPolicy too restrictive OR vLLM not ready
    Evidence: .sisyphus/evidence/task-8-connectivity-check.txt

  **Commit**: YES
  - Message: `feat(network): allow vLLM traffic from optimizer-backend and monitoring`
  - Files: `openshift/base/vllm-networkpolicy.yaml`
  - Pre-commit: `oc create --dry-run=client -f openshift/base/vllm-networkpolicy.yaml`

---

- [x] 9. Manual: Deploy vLLM resources and verify ServiceMonitor scraping

  **What to do**:
  - **This is a user-executed step** (not agent task in the plan)
  - 가이드: `oc apply -k openshift/overlays/dev`
  - 그 후 Prometheus UI에서 vLLM service가 scrape되고 있는지 확인
  - ServiceMonitor status 확인: `oc get servicemonitor -n vllm`

  **Acceptance Criteria** (for test guide):
  - [ ] `oc get endpoints -n vllm`에 vLLM service의 metrics endpoint (name: http) 보임
  - [ ] OpenShift console → Monitoring → Targets에서 `vllm-openvino-runtime`이 Up 상태
  - [ ] Thanos Querier 쿼리: `up{service="vllm-openvino-runtime"}` returns data

---

## Wave 4: Integration + Validation

- [x] 10. Verify Backend → vLLM connectivity

  **What to do**:
  - Optimizer Backend Pod에서 vLLM 서비스의 OpenAI API 엔드포인트에 curl 요청 보냄
  - 엔드포인트: `http://llm-ov.vllm.svc.cluster.local:8000/v1/models` (또는 route로 테스트)
  - 인증 없이 접근 가능한지 확인

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: 간단한 curl 테스트
  - **Skills**: [`kubernetes` (pod exec), `curl`]
  - **Parallelization**: Can parallel with 11, 12

  **QA Scenarios**:

  Scenario: Backend can reach vLLM models endpoint
    Tool: Bash
    Preconditions: vLLM InferenceService Ready; Backend pod running
    Steps:
      1. `BACKEND_POD=$(oc get pod -l app=vllm-optimizer-backend -n vllm-optimizer -o jsonpath='{.items[0].metadata.name}')`
      2. `oc exec $BACKEND_POD -n vllm-optimizer -- curl -s http://llm-ov.vllm.svc.cluster.local:8000/v1/models`
    Expected Result: JSON output with `"object": "list"` or `"model_id"`
    Failure Indicators: `curl: (7) Failed to connect` → NetworkPolicy issue
    Evidence: .sisyphus/evidence/task-10-connectivity.txt

  **Commit**: NO

---

- [x] 11. Verify Optimizer API returns vLLM metrics

  **What to do**:
  - Optimizer Backend의 `/api/metrics/latest` 엔드포인트 호출
  - 응답에 `vllm` 관련 필드들 (`tps`, `latency_mean`, `p99`, `running`, `waiting`, `kv_cache`, `gpu_util`)이 0이 아닌 값으로 채워지는지 확인
  - MetricsCollector가 Thanos에서 vLLM 메트릭 쿼리 성공했는지 확인

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: 단순 HTTP 요청
  - **Skills**: [`rest-api`, `jq`]

  **QA Scenarios**:

  Scenario: Optimizer metrics endpoint includes vLLM data
    Tool: Bash
    Preconditions: vLLM metrics being scraped; Optimizer collector running
    Steps:
      1. Get backend route or pod IP
      2. `curl -s http://<backend>/api/metrics/latest | jq '.tps, .latency_mean, .running, .kv_cache'`
    Expected Result: At least one field is non-zero (after some vLLM traffic) OR initial 0s but schema correct
    Failure Indicators: All fields are null/zero after 5 minutes of vLLM usage → collector not working
    Evidence: .sisyphus/evidence/task-11-optimizer-metrics.txt

  **Commit**: NO

---

- [x] 12. Verify Auto Tuner ConfigMap patch (end-to-end)

  **What to do**:
  - `POST /api/tuner/start` 호출로 튜닝 시작 (실제 vLLM 엔드포인트 지정)
  - auto_tuner가 vLLM ConfigMap을 패치하는지 확인
  - 패치 후 Deployment 재시작 대기
  - ConfigMap 값 변경 확인

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
    - Reason: 여러 단계 걸쳐 있고, timing dependency (restart wait) 있음
  - **Skills**: [`rest-api`, `kubernetes` (patch, rollout status)]

  **QA Scenarios**:

  Scenario: Auto-tuner successfully patches vLLM ConfigMap and restarts deployment
    Tool: Bash
    Preconditions: vLLM service running; ConfigMap exists; Backend tuner endpoints working
    Steps:
      1. Get initial ConfigMap value: `BEFORE=$(oc get cm vllm-config -n vllm -o jsonpath='{.data.MAX_NUM_SEQS}')`
      2. Start tuning: `curl -X POST http://<backend>/api/tuner/start -d '{"n_trials":1, "objective":"tps", "max_num_seqs_range":[64,128]}'`
      3. Wait 60 seconds for trial to complete and deployment to restart
      4. Get new ConfigMap value: `AFTER=$(oc get cm vllm-config -n vllm -o jsonpath='{.data.MAX_NUM_SEQS}')`
    Expected Result: `AFTER` is different from `BEFORE` and within trial range
    Failure Indicators: Values unchanged → patch failed OR no permissions OR vLLM not using that ConfigMap
    Evidence: .sisyphus/evidence/task-12-autotuner-patch.txt

  **Commit**: NO

---

- [x] 13. Write integration test guide (docs/integration_test_guide.md)

  **What to do**:
  - 통합 테스트 전체 절차를 단계별로 문서화
  - 에이전트가 실행 가능한 QA 시나리오들 포함 (위 task들의 시나리오 정리)
  - 사전 조건 (PVC 생성, 모델 복사, namespace 생성 등) 포함
  - 문제 해결 절차 (RBAC, ServiceMonitor, Thanos token 등) 포함
  - 명령어와 기대 출력 포함

  **Recommended Agent Profile**:
  - **Category**: `writing`
    - Reason: 문서 작성
  - **Skills**: [`technical-writer`, `markdown`]
  - **Parallelization**: Can start after 10, 11, 12 scenarios defined

  **QA Scenarios**:
  - 문서 존재 확인: `test -f docs/integration_test_guide.md`
  - 필수 섹션 포함 확인: "Prerequisites", "Test Scenarios", "Troubleshooting"

  **Commit**: YES
  - Message: `docs: add integration test guide for vLLM ServingRuntime`
  - Files: `docs/integration_test_guide.md`

---

## Final Verification Wave

- [x] F1. Plan compliance audit (oracle)
  Read the plan end-to-end. Verify all deliverables exist in filesystem after plan execution:
  - Files: `openshift/base/vllm-runtime.yaml`, `vllm-inferenceservice.yaml`, `06-vllm-monitoring.yaml`, `vllm-networkpolicy.yaml`, `vllm-rbac.yaml`, `docs/integration_test_guide.md`
  - Kustomization includes all
  - ConfigMap keys verified
  Output: `Deliverables [6/6] | Updates [2/2] | VERDICT: APPROVE/REJECT`

- [x] F2. Code quality review (unspecified-high)
  Ensure YAML syntax valid, no stray tabs, consistent indentation, no hardcoded image tags other than provided. Check that conditional idempotency patterns used (oc apply dry-run).
  Output: `YAML [PASS/FAIL] | Schema [PASS/FAIL] | VERDICT`

- [x] F3. Real manual QA (unspecified-high)
  Execute every QA scenario from tasks 1-12 in a test cluster. Capture evidence. Ensure no manual intervention needed; all commands must be scriptable.
  Output: `Scenarios [N/N pass] | Integration [PASS/FAIL] | VERDICT`

- [x] F4. Scope fidelity check (deep)
  Compare plan tasks with user request: Did we create exactly the missing YAMLs? Did we avoid modifying backend code? Did we exclude model download? Yes. Check no extra files (e.g., new backend routes) were added.
  Output: `Scope [CLEAN/CREEP] | Files changed [N] | VERDICT`

---

## Commit Strategy

- **1**: `feat(openshift): add vLLM ServingRuntime and InferenceService definitions` — openshift/base/vllm-runtime.yaml, openshift/base/vllm-inferenceservice.yaml
- **2**: `feat(openshift): add RBAC for optimizer-backend to access vLLM` — openshift/base/vllm-rbac.yaml
- **3**: `feat(monitoring): add vLLM ServiceMonitor and PrometheusRule` — openshift/base/06-vllm-monitoring.yaml
- **4**: `feat(network): allow vLLM traffic from optimizer-backend` — openshift/base/vllm-networkpolicy.yaml
- **5**: `build(openshift): update kustomization.yaml with vLLM resources` — openshift/base/kustomization.yaml
- **6**: `docs: integration test guide for vLLM` — docs/integration_test_guide.md

---

## Success Criteria

### Verification Commands
```bash
# 1. All YAML files exist
ls openshift/base/vllm-*.yaml openshift/base/06-vllm-monitoring.yaml docs/integration_test_guide.md

# 2. Kustomize applies without errors
oc apply -k openshift/overlays/dev --dry-run=client

# 3. InferenceService is Ready
oc get is llm-ov -n vllm -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}' | grep -q True

# 4. ServiceMonitor targets exist
oc get servicemonitor -n vllm

# 5. vLLM metrics queryable via Thanos
TOKEN=$(oc serviceaccounts get-token vllm-optimizer-backend -n vllm-optimizer-dev)
curl -k -H "Authorization: Bearer $TOKEN" "https://thanos-querier.openshift-monitoring.svc.cluster.local:9091/api/v1/query?query=vllm:num_requests_running" | jq '.data.result | length > 0'

# 6. Optimizer can reach vLLM
BACKEND_POD=$(oc get pod -l app=vllm-optimizer-backend -n vllm-optimizer-dev -o jsonpath='{.items[0].metadata.name}')
oc exec $BACKEND_POD -n vllm-optimizer-dev -- curl -s http://llm-ov.vllm.svc.cluster.local:8000/v1/models | jq -r '.object' | grep -q list
```

### Final Checklist
- [x] vLLM ServingRuntime YAML created and applied
- [x] vLLM InferenceService YAML created and applied
- [x] vLLM ServiceMonitor + PrometheusRule created
- [ ] vLLM NetworkPolicy created (allow optimizer-backend, monitoring)
- [x] RBAC Role/RoleBinding created (optimizer-backend SA permissions)
- [ ] kustomization.yaml updated with all new resources
- [ ] Integration test guide written with agent-executable scenarios
- [ ] All acceptance criteria passed in test environment
- [ ] vLLM 모델은 사용자가 사전 배포 (PVC 생성, 모델 복사) — **범위外, 사용자 책임**
- [ ] Backend router implementations are untouched (placeholder endpoints remain)

---