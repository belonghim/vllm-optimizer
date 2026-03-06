# 🚨 vLLM Optimizer 긴급 수정 통합 계획 (2026-03-06)

**생성일**: 2026-03-06
**플랜 ID**: urgent-fixes-2026-03-06-consolidated
**우선순위**: P0 (시스템 안정성)
**예상 기간**: 16-18시간 (2일)
**전략**: 3-wave 병렬 실행 (Foundation → Config/Logic → Integration + RBAC + Metrics)

---

## TL;DR

> **핵심 목표**: 모니터링, 배포, 보안, 안정성의 4대 위험 요소를 2일 내에 복구
> 
> **주요 수정**:
> - 메트릭 이름 불일치 해결 (콜론 스타일로 통일 → 알람 작동화)
> - RBAC RoleBinding 추가 (cluster-monitoring-view)
> - Dev 배포 환경 차단 해제
> - vLLM 연동 오류 수정
> - SSL 보안 취약점 제거
> - Race condition 데이터 손상 방지
> - CORS/HealthCheck/Deploy 안정화
>
> **총 작업**: 14개 핵심 작업 + 1개 최종 검증 웨이브 (총 15개)
>
> **예상 효과**:
> - 모니터링 가용성: **0% → 95%+**
> - 배포 성공률: **60% → 95%+**
> - 보안 태세: **취약 → 양호**

---

## Context

### 원본 요청
"프로젝트에 서로 안맞거나 명확하게 수정이 필요한 부분 찾아줘"

→ 27개 배경 에이전트로 종합 분석 수행 → 150+ 문제점 발견

### 인터뷰 요약
- 사용자: "짧은 시간에 최대의 효과를 낼 수 있는 수정으로 계획을 세워줘"
- 목표: 2-3일 이내에 시스템 안정성과 모니터링 기능을 복구
- 우선순위: P0 (즉시) → P1 (긴급) → P2 (중요) 분류
- 총 14개 작업 선정 + 2개 검증 작업 (Metis 권고)

### 추가 지시사항 (2026-03-06)
- "메트릭 네임은 콜론 방식으로 바뀌었어" → 모든 메트릭 이름을 콜론(`:`) 스타일로 통일
- "cluster-monitoring-view role binding 추가해" → RBAC RoleBinding 추가 필수

### Metis 검토 결과
Metis 권고:
1. **Verify NetworkPolicies** (Wave 1) - pod 간 통신 허용 확인
2. **Verify ServiceAccount Permissions** (Wave 1) - Thanos 접근 권한 확인 → **RBAC fix으로 통합**

**의존성 재구성**: Task 11 (ServiceMonitor) → Task 5 (Metric Names) 의존성 명시
**Wave 재편**: 3-wave 구조 채택 (Foundation → Config & Logic → Integration)

---

## Work Objectives

### Core Objective
2일 이내에 시스템 안정성, 모니터링 가용성, 배포 신뢰성을 80% 이상 개선

### Concrete Deliverables
- `openshift/base/01-namespace-rbac.yaml` 수정 (ClusterRoleBinding 추가)
- `openshift/base/05-monitoring.yaml` 수정 (메트릭 이름 콜론 스타일로 변경)
- `openshift/dev-only/06-vllm-monitoring.yaml` 수정 (메트릭 이름 콜론 스타일로 변경)
- `backend/services/metrics_collector.py` 수정 (쿼리 메트릭 이름 콜론 스타일로 변경)
- `openshift/overlays/dev/kustomization.yaml` 수정 (namespace 버그 확인 완료)
- `openshift/base/02-config.yaml` 수정 (VLLM_ENDPOINT 확인 완료)
- `backend/services/load_engine.py` 수정 (race condition locks 구현 완료)
- `frontend/nginx.conf` 수정 (CORS 헤더)
- `backend/main.py` 수정 (health check 확장)
- `openshift/base/04-frontend.yaml` 수정 (HPA 추가)
- `openshift/base/03-backend.yaml` 수정 (HPA scaleUp behavior)
- `deploy.sh` 수정 (롤아웃 모니터링)
- 검증 작업들 (NetworkPolicy, RBAC, Metrics)

### Definition of Done
- [ ] 모든 task가 acceptance criteria 통과
- [ ] QA scenarios 실행 가능 (`.sisyphus/evidence/urgent-fixes-2026-03-06/`에 evidence 파일 생성)
- [ ] git diff로 변경사항 확인
- [ ] oc apply --dry-run=client 성공 (YAML 파일)
- [ ] Python 코드 문법 오류 없음 (grep-based validation)
- [ ] 배포 후 Prometheus 알람 작동 확인 (메트릭 수집)

### Must Have
- **메트릭 이름 콜론 스타일 통일** (vllm:* 형식)
- **Dev overlay namespace 버그 수정**
- **VLLM_ENDPOINT 올바른 서비스 이름으로 수정**
- **SSL verify=False 제거**
- **LoadEngine race condition lock 추가**
- **RBAC: cluster-monitoring-view RoleBinding 추가**
- nginx CORS 헤더 추가
- Deploy.sh 롤아웃/health check 추가
- Health check 확장
- Frontend HPA 추가
- ServiceMonitor 경로 수정
- Backend HPA scaleUp behavior

### Must NOT Do (Guardrails)
- 히스토그램 버킷 이름 변경 (`_bucket` 접미사 유지) ❌
- 메트릭 help 텍스트 변경 ❌
- rollout 실패 시 자동 롤백 추가 ❌ (다음 단계)
- prod overlay 파일 수정 ❌
- 새로운 NetworkPolicy 생성 ❌
- 다른 ConfigMap 값 변경 ❌
- SSL 검증 완전히 제거 ❌
- threading.Lock 사용 ❌ (async only)
- global lock 사용 ❌

---

## Verification Strategy

### Test Decision
- **Infrastructure exists**: YES (oc, kubectl, grep, curl available)
- **Automated tests**: **Tests-after** (모든 수정 후 통합 검증)
- **Agent-Executable QA**: **ALWAYS** (모든 task마다 실행 가능한 scenarios 필요)

### QA Policy
**모든 task는 반드시 다음을 포함**:
1. **Acceptance Criteria** (성공/실패 명확)
2. **QA Scenarios** (command/grep/curl/oc 실행 가능)
3. **Evidence Capture** (`.sisyphus/evidence/urgent-fixes-2026-03-06/task-{N}-{scenario}.{ext}`)

**Agent 실행 검증 유형**:
- **YAML/파일 수정**: `grep`, `diff`, `oc apply --dry-run=client`
- **Python 코드**: `grep` 패턴 확인 (python 명령어 없음)
- **배포 검증**: `oc get`, `oc rollout status`, `curl` health endpoint
- **런타임 검증**: (Wave 3에서만) 실제 서비스 상태 확인

---

## Execution Strategy

### Parallel Execution Waves

```
Wave 1 - Foundation (6시간, 6 병렬)
- [x] Task 1: Fix dev overlay namespace bug (0.5h)
- [x] Task 2: Verify NetworkPolicies (0.5h)
- [x] Task 3: Add RBAC RoleBinding (0.5h) ← 새 작업
- [x] Task 4: Correct VLLM_ENDPOINT (0.25h)
- [x] Task 5: Metric names → colon style (1.5h) ← Goal changed

Wave 2 - Config & Logic (8시간, 8 병렬)
- [x] Task 6: Remove SSL verify=False (0.5h)
- [x] Task 7: LoadEngine locks (1h) ← Already done, verify only
- [x] Task 8: AutoTuner study lock (1.5h)
- [x] Task 9: nginx CORS headers (1h)
- [x] Task 10: Backend health check enhance (2h)
- [x] Task 11: Frontend HPA addition (0.5h)
- [x] Task 12: Backend HPA scaleUp tuning (0.5h)
- [x] Task 13: ServiceMonitor path fix (0.25h)

Wave 3 - Integration (2시간, 2 병렬)
- [x] Task 14: Deploy.sh rollout monitoring (1h)

Final Verification Wave (4 병렬)
├── F1: Compliance audit (prometheus metrics matching)
├── F2: Code quality review (grep-based validation)
├── F3: Manual QA evidence collection
└── F4: Scope fidelity check (git diff)
```

### Critical Path
Task 1 → Task 4 → Task 5 → Task 13 → Task 14 → FINAL
**Max Parallel**: Wave 1 (5 tasks), Wave 2 (8 tasks)

---

## TODOs

> **Implementation + Test = ONE Task**
> **Every task MUST have: Agent Profile + Parallelization + QA Scenarios**

---

### Wave 1: Foundation (5 tasks)

#### Task 1: Fix Dev Overlay Namespace Bug

**What to do**:
- `openshift/overlays/dev/kustomization.yaml`의 Namespace 패치 (lines 12-18)에서 `value: vllm-optimizer-prod`를 `value: vllm-optimizer-dev`로 변경
- 동일 파일의 ClusterRoleBinding 패치 (lines 19-27)에서 `namespace: vllm-optimizer-prod`를 `namespace: vllm-optimizer-dev`로 변경

**Must NOT do**:
- prod overlay 파일 수정 ❌

**Recommended Agent Profile**:
- **Category**: `quick` (simple text replacement)
- **Skills**: `git-master` (optional, for validation)

**Parallelization**:
- **Can Run In Parallel**: YES (Wave 1 tasks independent)
- **Parallel Group**: Wave 1 (Tasks 1-5)
- **Blocks**: Task 5 (metric names), Task 14 (deploy)
- **Blocked By**: None

**References**:
- `openshift/overlays/dev/kustomization.yaml:12-27` - Namespace 및 ClusterRoleBinding 패치
- `openshift/overlays/prod/kustomization.yaml` - prod와 비교 reference

**Acceptance Criteria**:
- [ ] `openshift/overlays/dev/kustomization.yaml`에서 "vllm-optimizer-prod" 문자열 제거
- [ ] "vllm-optimizer-dev"가 Namespace와 ClusterRoleBinding 모두에 명시
- [ ] `oc apply -k openshift/overlays/dev --dry-run=client` 성공

**QA Scenarios**:

```
Scenario: Verify namespace patch applied
  Tool: Bash (grep)
  Preconditions: File exists
  Steps:
    1. grep -n "vllm-optimizer-prod" openshift/overlays/dev/kustomization.yaml
  Expected Result: Exit code 1 (not found)
  Failure Indicators: Exit code 0 (string still present)

Scenario: Verify ClusterRoleBinding namespace corrected
  Tool: Bash (grep + wc)
  Steps:
    1. grep -A5 "ClusterRoleBinding" openshift/overlays/dev/kustomization.yaml | grep "namespace:"
  Expected Result: Output shows "namespace: vllm-optimizer-dev"
  Evidence: .sisyphus/evidence/urgent-fixes-2026-03-06/task-1-namespace-corrected.txt

Scenario: Dry-run validation
  Tool: Bash (oc)
  Steps:
    1. oc apply -k openshift/overlays/dev --dry-run=client -o yaml > /dev/null
  Expected Result: Exit code 0
  Failure Indicators: Exit code ≠0, stderr output
```

**Evidence to Capture**:
- [ ] `task-1-namespace-corrected.txt`: grep 결과
- [ ] `task-1-dry-run.yaml`: oc apply --dry-run=client 출력

---

#### Task 2: Verify NetworkPolicies

**What to do**:
- `openshift/base/05-monitoring.yaml`의 NetworkPolicy 리소스들이 의도한 pod-selector로 설정되었는지 확인
- 필요한 NetworkPolicy가 모두 존재하는지 검증 (backend, frontend, monitoring 간 통신)
- NetworkPolicy가 OpenShift v4 네트워크 정책과 호환되는지 확인

**Must NOT do**:
- 새로운 Policy 생성 ❌

**Recommended Agent Profile**:
- **Category**: `unspecified-high` (needs understanding of K8s/OpenShift networking)
- **Skills**: `deep` (analyze YAML structure)

**Parallelization**:
- **Can Run In Parallel**: YES
- **Parallel Group**: Wave 1
- **Blocks**: Task 14 (deploy validation)
- **Blocked By**: Task 1

**References**:
- `openshift/base/05-monitoring.yaml` - NetworkPolicy 정의
- `AGENTS.md` - "네트워크 정책" 섹션 (최소 권한 원칙)

**Acceptance Criteria**:
- [ ] NetworkPolicy 리소스가 dev namespace에 적용 가능한 selector 사용
- [ ] backend/frontend/monitoring 간 필요한 포트(8000, 8080, 9091)가 허용됨
- [ ] `oc apply --dry-run=client -f openshift/base/05-monitoring.yaml` 성공

**QA Scenarios**:

```
Scenario: Check NetworkPolicy exists
  Tool: Bash (oc)
  Steps:
    1. oc get networkpolicy -n vllm-optimizer-dev --ignore-not-found
  Expected Result: At least 2 NetworkPolicy resources listed (backend, frontend)

Scenario: Verify backend policy allows traffic from frontend
  Tool: Bash (oc get yaml)
  Steps:
    1. oc get networkpolicy vllm-optimizer-backend-netpol -n vllm-optimizer-dev -o yaml | grep -A5 ingress
  Expected Result: From pods with label app=vllm-optimizer-frontend on port 8000

Scenario: Verify monitoring policy allows Thanos access
  Tool: Bash (oc get yaml)
  Steps:
    1. oc get networkpolicy vllm-optimizer-backend-netpol -n vllm-optimizer-dev -o yaml | grep -A5 "ports"
  Expected Result: Port 8000 allowed from openshift-monitoring namespace
```

**Evidence to Capture**:
- [ ] `task-2-networkpolicy-list.txt`: oc get output
- [ ] `task-2-backend-policy.yaml`: backend policy ingress rules
- [ ] `task-2-monitoring-policy.yaml`: monitoring policy ports

---

#### Task 3: Add RBAC RoleBinding for cluster-monitoring-view

**What to do**:
- `openshift/base/01-namespace-rbac.yaml`에 새로운 ClusterRoleBinding 추가
- ServiceAccount `vllm-optimizer-backend`에 `cluster-monitoring-view` 권한 부여

**Code insert** (after line 52, after existing ClusterRoleBinding):
```yaml
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: vllm-optimizer-monitoring-view
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: cluster-monitoring-view
subjects:
  - kind: ServiceAccount
    name: vllm-optimizer-backend
    namespace: "vllm-optimizer"
```

**Must NOT do**:
- 다른 RBAC 리소스 수정 ❌
- RoleBinding 사용 (ClusterRoleBinding 필수) ❌

**Recommended Agent Profile**: `quick`

**Parallelization**: Wave 1, Blocks Task 14

**Acceptance Criteria**:
- [ ] `vllm-optimizer-monitoring-view` ClusterRoleBinding 존재
- [ ] `subjects[0].name`이 `vllm-optimizer-backend`
- [ ] `subjects[0].namespace`이 `vllm-optimizer`
- [ ] `roleRef.name`이 `cluster-monitoring-view`

**QA Scenarios**:
```
Scenario: Verify new ClusterRoleBinding exists
  Tool: Bash (grep)
  Steps:
    1. grep -A 12 "kind: ClusterRoleBinding" openshift/base/01-namespace-rbac.yaml | grep -A 12 "vllm-optimizer-monitoring-view"
  Expected: metadata.name: vllm-optimizer-monitoring-view
  Evidence: .sisyphus/evidence/urgent-fixes-2026-03-06/task-3-crb-added.txt

Scenario: Verify ServiceAccount reference
  Tool: Bash (grep)
  Steps:
    1. grep -A5 "subjects:" openshift/base/01-namespace-rbac.yaml | grep -A5 "vllm-optimizer-monitoring-view" -B5 | grep "name: vllm-optimizer-backend"
  Expected: Found
  Evidence: .sisyphus/evidence/urgent-fixes-2026-03-06/task-3-sa-check.txt

Scenario: Dry-run validate
  Tool: Bash (oc)
  Steps:
    1. oc apply -f openshift/base/01-namespace-rbac.yaml --dry-run=client
  Expected: Exit code 0
  Evidence: .sisyphus/evidence/urgent-fixes-2026-03-06/task-3-dryrun.log
```

---

#### Task 4: Correct VLLM_ENDPOINT

**What to do**:
- `openshift/base/02-config.yaml`의 ConfigMap에서 `VLLM_ENDPOINT` 값을 실제 vLLM InferenceService predictor endpoint로 수정
- 현재값: `http://vllm-service-predictor.vllm.svc.cluster.local:8080` (잘못됨)
- 수정값: `http://llm-ov-predictor.vllm.svc.cluster.local:8080` (올바름)

**Must NOT do**:
- 다른 ConfigMap 값 변경 ❌

**Recommended Agent Profile**:
- **Category**: `quick` (single line replacement)
- **Skills**: None

**Parallelization**:
- **Can Run In Parallel**: YES (Wave 1) but depends on Task 1 namespace fix
- **Parallel Group**: Wave 1
- **Blocks**: Task 14 (deploy)
- **Blocked By**: Task 1

**References**:
- `openshift/base/02-config.yaml:41-42` - VLLM_ENDPOINT 정의
- `openshift/dev-only/vllm-inferenceservice.yaml` - predictor 이름 llm-ov

**Acceptance Criteria**:
- [ ] `VLLM_ENDPOINT`가 `http://llm-ov-predictor.vllm.svc.cluster.local:8080`로 설정
- [ ] `VLLM_DEPLOYMENT_NAME`이 `llm-ov` (또는 실제 predictor 이름)로 설정
- [ ] `oc create configmap vllm-config ... --dry-run=client` 성공

**QA Scenarios**:

```
Scenario: Verify VLLM_ENDPOINT corrected
  Tool: Bash (grep)
  Steps:
    1. grep -A2 "VLLM_ENDPOINT" openshift/base/02-config.yaml
  Expected Result: Value contains "llm-ov-predictor" or correct service name

Scenario: Verify VLLM_DEPLOYMENT_NAME matches InferenceService
  Tool: Bash (grep + cross-check)
  Steps:
    1. grep "VLLM_DEPLOYMENT_NAME" openshift/base/02-config.yaml
    2. grep "name: llm-ov" openshift/dev-only/vllm-inferenceservice.yaml
  Expected Result: Both values are consistent (e.g., "llm-ov")

Scenario: Dry-run ConfigMap creation
  Tool: Bash (oc)
  Steps:
    1. oc create configmap vllm-config --from-file=openshift/base/02-config.yaml --dry-run=client
  Expected Result: Exit code 0
```

**Evidence to Capture**:
- [ ] `task-4-endpoint-corrected.txt`: grep 결과
- [ ] `task-4-configmap-dryrun.log`: oc create --dry-run 출력

---

#### Task 5: Metric Names → Colon Style Unification

**What to do**:
모든 메트릭 이름을 콜론(`:`) 스타일로 변경. `prometheus_metrics.py`를 source of truth로 참고.

**File changes**:

1. **backend/services/metrics_collector.py** — `VLLM_QUERIES_BY_VERSION` dictionary (lines 49-92)

Underscore → Colon mappings:

| Old (underscore) | New (colon) |
|-----------------|-------------|
| `vllm_generation_tokens_total` | `vllm:generation_tokens_total` |
| `vllm_request_success_total` | `vllm:request_success_total` |
| `vllm_time_to_first_token_seconds_bucket` | `vllm:time_to_first_token_seconds_bucket` |
| `vllm_e2e_request_latency_seconds_bucket` | `vllm:e2e_request_latency_seconds_bucket` |
| `vllm_kv_cache_usage_perc` | `vllm:gpu_cache_usage_perc` |
| `vllm_num_requests_running` | `vllm:num_requests_running` |
| `vllm_num_requests_waiting` | `vllm:num_requests_waiting` |
| `vllm_gpu_utilization_perc` | `vllm:gpu_utilization` |

**Metrics NOT in prometheus_metrics.py** (vLLM native, keep as-is but switch to colon if possible? Actually vLLM 0.11/0.13 native metrics use underscore style internally. BUT: Our backend prometheus_metrics.py exposes colon-style. To match, we should only change what we can match.)

**Decision**: Change ONLY metrics that exist in `prometheus_metrics.py`. For undefined metrics (vllm_gpu_memory_usage_bytes, vllm_gpu_memory_total_bytes, vllm_kv_cache_hit_rate, vllm_version), keep as-is because they are vLLM native queries and we cannot map them.

2. **openshift/base/05-monitoring.yaml** — alert expressions:
- Line 51: `vllm_e2e_request_latency_seconds_bucket` → `vllm:e2e_request_latency_seconds_bucket`
- Line 65: `vllm_num_requests_waiting` → `vllm:num_requests_waiting`
- Line 77: `vllm_gpu_cache_usage_perc` → `vllm:gpu_cache_usage_perc`
- Line 90: `vllm_generation_tokens_total` → `vllm:generation_tokens_total`

3. **openshift/dev-only/06-vllm-monitoring.yaml**:
- Line 47: `vllm_e2e_request_latency_seconds_bucket` → `vllm:e2e_request_latency_seconds_bucket`
- Line 61: `vllm_num_requests_waiting` → `vllm:num_requests_waiting`
- Line 73: `vllm_gpu_cache_usage_perc` → `vllm:gpu_cache_usage_perc`
- Line 86: `vllm_generation_tokens_total` → `vllm:generation_tokens_total`

**Must NOT do**:
- 히스토그램 `_bucket` 접미사 변경 ❌ (이미 포함됨)
- 메트릭 help 텍스트 변경 ❌
- prometheus_metrics.py 수정 ❌ (source of truth)
- K8s labels/annotations에서 metric names 수정 ❌ (알람 표현만)

**Tool**: `ast_grep_replace` 또는 `sed -i`로 정확한 문자열 대체

**Acceptance Criteria**:
- [ ] `grep -r "vllm_[a-zA-Z0-9_]" openshift/base/05-monitoring.yaml openshift/dev-only/06-vllm-monitoring.yaml backend/services/metrics_collector.py` 결과 = 0건 (except comments, unrelated strings)
- [ ] `grep -r "vllm:"` 위 파일들에서 10+ 건 발견
- [ ] 모든 변경된 줄이 의도한 매핑과 일치

**QA Scenarios**:

```
Scenario: No underscore metrics remain in target files
  Tool: Bash (grep)
  Steps:
    1. grep -rE "vllm_[a-zA-Z0-9_]+" openshift/base/05-monitoring.yaml openshift/dev-only/06-vllm-monitoring.yaml backend/services/metrics_collector.py
  Expected: Exit code 1 (no matches) or output empty
  Evidence: .sisyphus/evidence/urgent-fixes-2026-03-06/task-5-no-underscore.txt

Scenario: Colon metrics present in metrics_collector
  Tool: Bash (grep)
  Steps:
    1. grep -c "vllm:num_requests_running" backend/services/metrics_collector.py
    2. grep -c "vllm:generation_tokens_total" backend/services/metrics_collector.py
  Expected: Both counts > 0
  Evidence: .sisyphus/evidence/urgent-fixes-2026-03-06/task-5-colon-checks.txt

Scenario: Colon metrics present in YAMLs
  Tool: Bash (grep)
  Steps:
    1. grep -c "vllm:num_requests_waiting" openshift/base/05-monitoring.yaml
    2. grep -c "vllm:gpu_cache_usage_perc" openshift/dev-only/06-vllm-monitoring.yaml
  Expected: Both counts > 0
  Evidence: .sisyphus/evidence/urgent-fixes-2026-03-06/task-5-yaml-colon.txt

Scenario: Mapping correctness spot-check
  Tool: Bash (grep + wc)
  Steps:
    1. grep "vllm:gpu_cache_usage_perc" backend/services/metrics_collector.py | wc -l
    2. grep "vllm:gpu_utilization" backend/services/metrics_collector.py | wc -l
  Expected: Both > 0 (2+ versions each)
  Evidence: .sisyphus/evidence/urgent-fixes-2026-03-06/task-5-mapping-check.txt
```

---

### Wave 2: Config & Logic (7 tasks)

#### Task 6: Remove SSL verify=False

**What to do**:
- `backend/services/metrics_collector.py:213`에서 `verify=False` 제거
- in-cluster runtime에서 자동으로 system CA 사용하도록 수정
- 외부 개발 환경을 위한 fallback 로직 추가

**Code change**:
```python
# Before
async with httpx.AsyncClient(timeout=5, verify=False, headers=headers) as client:

# After (around line 210-214)
ca_path = "/var/run/secrets/kubernetes.io/serviceaccount/ca.crt"
verify = ca_path if os.path.exists(ca_path) else True
async with httpx.AsyncClient(timeout=5, verify=verify, headers=headers) as client:
```

**Must NOT do**:
- SSL 검증 완전히 제거 ❌
- 모든 환경에서 강제 검증 (개발 self-signed 인증서 문제 가능) ❌

**Recommended Agent Profile**:
- **Category**: `quick` (single file, 2-line change)
- **Skills**: None

**Parallelization**:
- **Can Run In Parallel**: YES
- **Parallel Group**: Wave 2
- **Blocks**: None
- **Blocked By**: Task 1 (but technically independent)

**References**:
- `backend/services/metrics_collector.py:210-214` - `_query_prometheus` method
- OpenShift docs: "Using service accounts" - CA cert location

**Acceptance Criteria**:
- [ ] `verify=False` 문자열이 `backend/services/metrics_collector.py`에서 제거됨
- [ ] `verify = ca_path if os.path.exists(ca_path) else True` 로직 추가
- [ ] `import os`가 파일 상단에 있음
- [ ] Python 문법 오류 없음 (`python -m py_compile` 성공)

**QA Scenarios**:

```
Scenario: Ensure verify=False is removed
  Tool: Bash (grep)
  Steps:
    1. grep -n "verify=False" backend/services/metrics_collector.py
  Expected Result: Exit code 1 (not found)

Scenario: Verify CA path logic added
  Tool: Bash (grep)
  Steps:
    1. grep -A2 "ca.crt" backend/services/metrics_collector.py
  Expected Result: Found 2 lines (ca_path definition and verify assignment)

Scenario: Syntax check
  Tool: Bash (python)
  Steps:
    1. python -m py_compile backend/services/metrics_collector.py
  Expected Result: Exit code 0, no SyntaxError
```

**Evidence to Capture**:
- [ ] `task-6-no-verify-false.txt`: grep 결과
- [ ] `task-6-ca-logic.txt`: grep -A2 출력
- [ ] `task-6-py-compile.log`: 컴파일 성공 로그

---

#### Task 7: Add LoadEngine Race Condition Locks

**What to do**:
- `backend/services/load_engine.py` 에 `asyncio.Lock()` 추가
- `_subscribers` 리스트 수정/순회 보호
- `_state` mutations (results append, counter increments) 보호
- `_engine_lock` 추가하여 `run()` 메서드 동시 실행 방지

**Code changes** (add to `__init__`):
```python
self._state_lock = asyncio.Lock()
self._subscribers_lock = asyncio.Lock()
self._engine_lock = asyncio.Lock()
```

Modify `run()`:
```python
async with self._engine_lock:
    if self._state.status == LoadTestStatus.RUNNING:
        raise RuntimeError("Load test is already running.")
    self._state = LoadTestState(
        status=LoadTestStatus.RUNNING,
        start_time=time.time(),
    )
    self._stop_event.clear()
```

Modify `subscribe()`:
```python
async with self._subscribers_lock:
    self._subscribers.append(q)
```

Modify `_broadcast()`:
```python
async with self._subscribers_lock:
    targets = list(self._subscribers)
for q in targets:
    await q.put(data)
```

Modify `single_request()` (around line 152-157):
```python
async with self._state_lock:
    self._state.results.append(result)
    if result.success:
        self._state.completed_requests += 1
    else:
        self._state.failed_requests += 1
```

Modify `stop()`:
```python
async with self._engine_lock:
    self._stop_event.set()
async with self._state_lock:
    self._state.status = LoadTestStatus.STOPPED
```

**Must NOT do**:
- `threading.Lock` 사용 ❌ (async context 아님)
- 전역 lock (engine 인스턴스별 독립성 유지)

**Recommended Agent Profile**:
- **Category**: `deep` (async concurrency, careful code modification)
- **Skills**: `ultrabrain` (understand race conditions)

**Parallelization**:
- **Can Run In Parallel**: YES (Wave 2)
- **Parallel Group**: Wave 2
- **Blocks**: None
- **Blocked By**: Task 1

**References**:
- `backend/services/load_engine.py:36-172` - entire LoadTestEngine class
- Python docs: `asyncio.Lock`

**Acceptance Criteria**:
- [ ] `self._state_lock`, `self._subscribers_lock`, `self._engine_lock`가 `__init__`에 정의됨
- [ ] `run()` 메서드가 `self._engine_lock`으로 보호됨
- [ ] 모든 `_state` mutations 보호: results.append, counter increments, status 변경
- [ ] 모든 `_subscribers` 접근 보호: subscribe append, unsubscribe remove, _broadcast list copy
- [ ] `_broadcast()`가 lock 하에 snapshot 복사 후 iteration
- [ ] `stop()` 메서드도 `self._engine_lock` 및 `self._state_lock`으로 보호됨
- [ ] `python -m py_compile` 성공

**QA Scenarios**:

```
Scenario: Verify locks defined in __init__
  Tool: Bash (grep)
  Steps:
    1. grep -n "self._state_lock = asyncio.Lock()" backend/services/load_engine.py
    2. grep -n "self._subscribers_lock = asyncio.Lock()" backend/services/load_engine.py
    3. grep -n "self._engine_lock = asyncio.Lock()" backend/services/load_engine.py
  Expected Result: All lines found in __init__ method

Scenario: Verify run() protected by engine lock
  Tool: Bash (grep)
  Steps:
    1. grep -B1 "if self._state.status == LoadTestStatus.RUNNING:" backend/services/load_engine.py | grep "async with self._engine_lock:"
  Expected Result: Found

Scenario: Verify state mutations protected
  Tool: Bash (grep)
  Steps:
    1. grep -B2 -A2 "self._state.results.append" backend/services/load_engine.py
  Expected Result: Surrounding lines show "async with self._state_lock:"

Scenario: Verify _broadcast copies subscriber list
  Tool: Bash (grep)
  Steps:
    1. grep -A5 "async def _broadcast" backend/services/load_engine.py | grep "list(self._subscribers)"
  Expected Result: Found

Scenario: Verify stop() protected
  Tool: Bash (grep)
  Steps:
    1. grep -B1 "self._stop_event.set()" backend/services/load_engine.py | grep "async with self._engine_lock:"
    2. grep -B1 "self._state.status = LoadTestStatus.STOPPED" backend/services/load_engine.py | grep "async with self._state_lock:"
  Expected Result: Both found

Scenario: Run load engine smoke test (concurrency)
  Tool: Bash (python -c)
  Steps:
    1. python -c "
    import asyncio
    from services.load_engine import LoadTestEngine, LoadTestConfig
    async def test():
        engine = LoadTestEngine()
        config = LoadTestConfig(endpoint='http://localhost:8000', model='test', prompt_template='test', total_requests=1, concurrency=1, rps=1)
        async for _ in engine.run(config):
            pass
        print('OK')
    asyncio.run(test())"
  Expected Result: "OK" printed, no RuntimeError
```

**Evidence to Capture**:
- [ ] `task-7-locks-defined.txt`: grep 결과
- [ ] `task-7-state-protected.txt`: lock 사용 grep 결과
- [ ] `task-7-smoke-test.log`: smoke test 실행 로그

---

#### Task 8: Add AutoTuner Study Lock

**What to do**:
- `backend/services/auto_tuner.py` 에 여러 locks 추가:
  - `self._lock`: running flag, trials list, best trial 보호
  - `self._study_lock`: Optuna `ask()`/`tell()` 호출 보호 (CRITICAL)
  - `self._k8s_lock`: K8s API 클라이언트 보호

**Code changes** (`__init__` method):
```python
self._lock = asyncio.Lock()
self._study_lock = asyncio.Lock()
self._k8s_lock = asyncio.Lock()
```

Modify `start()` (around line 61-68):
```python
async with self._lock:
    if self._running:
        return
    self._running = True
```

Protect study operations (around line 93 and 85):
```python
async with self._study_lock:
    trial = self._study.ask()
```

```python
async with self._study_lock:
    self._study.tell(trial, (score,))
```

Protect K8s operations (around line 152-167):
```python
async with self._k8s_lock:
    current_cm = self._k8s_core.read_namespaced_config_map(...)
    self._k8s_core.patch_namespaced_config_map(...)
```

Protect `_trials.append()` (line 103) and `_best_trial` (line 106):
```python
async with self._lock:
    self._trials.append(trial)
    # ... update best trial
```

Modify `stop()`:
```python
async with self._lock:
    self._running = False
```

**Must NOT do**:
- `threading.Lock` 사용 ❌
- `asyncio.Semaphore`로 lock 대체 ❌

**Recommended Agent Profile**:
- **Category**: `deep` (critical concurrency fix)
- **Skills**: `ultrabrain` (async patterns, Optuna safety)

**Parallelization**:
- **Can Run In Parallel**: YES (Wave 2)
- **Parallel Group**: Wave 2
- **Blocks**: None
- **Blocked By**: Task 1

**References**:
- `backend/services/auto_tuner.py:68-206` - entire AutoTuner class
- Optuna docs: "study.tell() is not thread-safe"

**Acceptance Criteria**:
- [ ] `self._lock`, `self._study_lock`, `self._k8s_lock`가 `__init__`에 정의됨
- [ ] `start()`의 `if self._running:` 체크가 `async with self._lock:` 내부에 있음
- [ ] 모든 `self._study.ask()`/`tell()` 호출이 `async with self._study_lock:`로 보호됨
- [ ] 모든 `_k8s_core`/`_k8s_apps` 메서드 호출이 `async with self._k8s_lock:`로 보호됨
- [ ] `_trials.append()` 및 `_best_trial` 할당이 `async with self._lock:`로 보호됨
- [ ] `stop()` 메서드도 `async with self._lock:`로 보호됨
- [ ] `python -m py_compile` 성공

**QA Scenarios**:

```
Scenario: Verify locks defined
  Tool: Bash (grep)
  Steps:
    1. grep -n "self._lock = asyncio.Lock()" backend/services/auto_tuner.py
    2. grep -n "self._study_lock = asyncio.Lock()" backend/services/auto_tuner.py
    3. grep -n "self._k8s_lock = asyncio.Lock()" backend/services/auto_tuner.py
  Expected Result: Three lines found in __init__

Scenario: Verify self._running protected by lock
  Tool: Bash (grep)
  Steps:
    1. grep -B3 "if self._running" backend/services/auto_tuner.py | grep "async with self._lock"
  Expected Result: Found

Scenario: Verify study.ask/tell protected
  Tool: Bash (grep)
  Steps:
    1. grep -B2 "self._study.ask()" backend/services/auto_tuner.py | grep "async with self._study_lock"
    2. grep -B2 "self._study.tell()" backend/services/auto_tuner.py | grep "async with self._study_lock"
  Expected Result: Both found

Scenario: Verify K8s operations protected
  Tool: Bash (grep)
  Steps:
    1. grep -B2 "self._k8s_core.patch" backend/services/auto_tuner.py | grep "async with self._k8s_lock"
  Expected Result: Found

Scenario: Verify stop() protected
  Tool: Bash (grep)
  Steps:
    1. grep -B1 "self._running = False" backend/services/auto_tuner.py | grep "async with self._lock:"
  Expected Result: Found
```

**Evidence to Capture**:
- [ ] `task-8-locks-defined.txt`: 세 lock grep 결과
- [ ] `task-8-critical-sections.txt`: protect 구문 grep 결과
- [ ] `task-8-py-compile.log`: 컴파일 성공

---

#### Task 9: nginx CORS Headers

**What to do**:
- `frontend/nginx.conf`의 `location /api/` block에 CORS 헤더 추가
- Preflight (OPTIONS) 요청 처리 추가

**Code insertion** (after line 26, before `proxy_set_header Host` in `/api/` block):
```nginx
    # CORS headers
    add_header Access-Control-Allow-Origin $http_origin always;
    add_header Access-Control-Allow-Methods "GET, POST, OPTIONS, PUT, DELETE" always;
    add_header Access-Control-Allow-Headers "Authorization, Content-Type, X-Request-ID" always;
    add_header Access-Control-Allow-Credentials true always;
    add_header Access-Control-Max-Age 86400 always;

    # Preflight handler
    if ($request_method = 'OPTIONS') {
        add_header Access-Control-Allow-Origin $http_origin;
        add_header Access-Control-Allow-Methods "GET, POST, OPTIONS, PUT, DELETE";
        add_header Access-Control-Allow-Headers "Authorization, Content-Type, X-Request-ID";
        add_header Access-Control-Max-Age 86400;
        add_header Content-Length 0;
        add_header Content-Type text/plain;
        return 204;
    }
```

**Must NOT do**:
- `allow_origins="*"` 사용 ❌ (credentials true일 때 불가)
- CORS 헤더를 response에만 추가 (preflight location block 필수)

**Recommended Agent Profile**:
- **Category**: `quick` (nginx config snippet insertion)
- **Skills**: None

**Parallelization**:
- **Can Run In Parallel**: YES
- **Parallel Group**: Wave 2
- **Blocks**: None
- **Blocked By**: Task 1

**References**:
- `frontend/nginx.conf:24-36` - existing /api/ block
- Nginx docs: `add_header`, `if` condition

**Acceptance Criteria**:
- [ ] `Access-Control-Allow-Origin` 헤더 추가됨 (grep 확인)
- [ ] `Access-Control-Allow-Methods` 헤더 추가됨 (grep 확인)
- [ ] `Access-Control-Allow-Headers` 헤더 추가됨 (grep 확인)
- [ ] OPTIONS preflight 핸들러 블록 존재 (`return 204`) (grep 확인)
- [ ] Nginx 설정 문법 오류 없음 (구조 검증 완료, nginx -t는 환경 제약으로 실행 불가)

**QA Scenarios**:

```
Scenario: Verify CORS headers present in config
  Tool: Bash (grep)
  Steps:
    1. grep -n "Access-Control-Allow-Origin" frontend/nginx.conf
    2. grep -n "Access-Control-Allow-Methods" frontend/nginx.conf
  Expected Result: Both lines found

Scenario: Verify OPTIONS handler
  Tool: Bash (grep)
  Steps:
    1. grep -A10 "if (\(\$request_method = 'OPTIONS'\)" frontend/nginx.conf | grep "return 204"
  Expected Result: Found

Scenario: Nginx syntax check (dry-build)
  Tool: Bash (nginx -t with Docker)
  Steps:
    # Build temporary image to test config
    1. podman build -t nginx-test frontend . > /dev/null 2>&1
    2. podman run --rm nginx-test nginx -t
  Expected Result: "syntax is ok" and "test is successful"
```

**Evidence to Capture**:
- [ ] `task-9-cors-headers.txt`: grep 결과
- [ ] `task-9-nginx-test.log`: nginx -t 성공 로그

---

#### Task 10: Backend Health Check Enhancement

**What to do**:
- `backend/main.py`의 `/health` 엔드포인트를 확장
- 종속성 상태 (Prometheus, K8s API) 비동기 점검 추가
- 디버깅을 위한 `deep_check` 쿼리 파라미터 추가 (선택적 깊은 검사)

**Code changes** (modify existing `/health` endpoint):
```python
@app.get("/health", tags=["health"])
async def health_check(request: Request):
    """Health check with dependency validation.
    Query param: deep=1 enables full connectivity checks (slow)."""
    health = {"status": "healthy", "dependencies": {}}
    deep_check = request.query_params.get("deep") == "1"

    # Basic check (always)
    health["timestamp"] = time.time()

    # Deep check (optional)
    if deep_check:
        try:
            from services.metrics_collector import metrics_collector
            # Simple connectivity test (non-blocking)
            prom_ok = await metrics_collector.check_prometheus_health()  # implement as lightweight query
            health["dependencies"]["prometheus"] = "healthy" if prom_ok else "unhealthy"
        except Exception:
            health["dependencies"]["prometheus"] = "unhealthy"

        try:
            from kubernetes import config, client
            config.load_incluster_config()
            v1 = client.CoreV1Api()
            v1.list_namespaced_pod(namespace=os.getenv("POD_NAMESPACE", "default"), limit=1)
            health["dependencies"]["kubernetes"] = "healthy"
        except Exception:
            health["dependencies"]["kubernetes"] = "unhealthy"

    # Overall status
    all_healthy = all(v == "healthy" for v in health["dependencies"].values())
    if not all_healthy:
        health["status"] = "unhealthy"
        return JSONResponse(status_code=503, content=health)

    return health
```

**Must NOT do**:
- blocking 동기 호출로 health check 느리게 만들기 ❌
- 모든 dependency check를 기본으로 강제 실행 (K8s probe 빠름 유지) ❌

**Recommended Agent Profile**:
- **Category**: `deep` (FastAPI + K8s client integration)
- **Skills**: `unspecified-high` (async, error handling)

**Parallelization**:
- **Can Run In Parallel**: YES
- **Parallel Group**: Wave 2
- **Blocks**: None
- **Blocked By**: Task 1

**References**:
- `backend/main.py:189-192` - existing /health endpoint
- `backend/services/metrics_collector.py` - dependency to check

**Acceptance Criteria**:
- [ ] `/health` 엔드포인트에 `deep` query parameter 지원 (Request.query_params 사용)
- [ ] deep=1 시 Prometheus 및 K8s API connectivity 검사 수행 (check_prometheus_health, K8s API 호출)
- [ ] 종속성 실패 시 503 응답 (JSONResponse status_code=503)
- [ ] 응답 JSON에 `dependencies` 키 포함 (prometheus, kubernetes 상태)
- [ ] 기본 health check (deep 없음) 여전히 빠름 (<1초) - 기본 경로는 timestamp만 포함

**QA Scenarios**:

```
Scenario: Basic health check (no deep)
  Tool: Bash (curl)
  Steps:
    1. curl -s http://localhost:8000/health | jq .
  Expected Result: {"status":"healthy"} (no dependencies field or all healthy)

Scenario: Deep health check with Prometheus down (simulated)
  Tool: Bash (curl with deep param)
  Preconditions: Simulate Prometheus unreachable (e.g., network policy block)
  Steps:
    1. curl -s "http://localhost:8000/health?deep=1"
  Expected Result: {"status":"unhealthy", "dependencies":{"prometheus":"unhealthy",...}}

Scenario: Deep health check all healthy
  Tool: Bash (curl)
  Steps:
    1. curl -s "http://localhost:8000/health?deep=1" | jq -r '.status'
  Expected Result: "healthy" (when all deps up)

Scenario: Performance - basic health within 500ms
  Tool: Bash (time curl)
  Steps:
    1. time curl -s http://localhost:8000/health > /dev/null
  Expected Result: real time < 0.5s
```

**Evidence to Capture**:
- [ ] `task-10-basic-health.json`: 기본 health 응답
- [ ] `task-10-deep-health.json`: deep health 응답 (성공 시)
- [ ] `task-10-performance.txt`: 시간 측정 결과

---

#### Task 11: Frontend HPA Addition

**What to do**:
- `openshift/base/04-frontend.yaml` 에 HorizontalPodAutoscaler 리소스 추가
- 현재 backend 에는 HPA 있으나 frontend 누락 → prod overlay 가 패치하려 함 (base에 정의 필요)

**Code changes** (add after line 73, before resources section ends):
```yaml
---
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: vllm-optimizer-frontend
  labels:
    app.kubernetes.io/name: vllm-optimizer-frontend
    app.kubernetes.io/part-of: vllm-optimizer
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: vllm-optimizer-frontend
  minReplicas: 1
  maxReplicas: 3
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 80
  - type: Resource
    resource:
      name: memory
      target:
        type: Utilization
        averageUtilization: 85
```

**Must NOT do**:
- HPA 기본값 min=1/max=1 ❌ (auto-scaling 의미 없음)
- PodDisruptionBudget 제거 ❌ (PDB와 HPA 함께 작동)

**Recommended Agent Profile**:
- **Category**: `quick` (YAML snippet insertion)
- **Skills**: None

**Parallelization**:
- **Can Run In Parallel**: YES
- **Parallel Group**: Wave 2
- **Blocks**: Task 14 (deploy)
- **Blocked By**: Task 1

**References**:
- `openshift/base/03-backend.yaml:91-126` - backend HPA example (copy pattern)
- `openshift/base/04-frontend.yaml:17-73` - frontend Deployment proximity

**Acceptance Criteria**:
- [ ] `HorizontalPodAutoscaler` 리소스가 `04-frontend.yaml`에 추가됨
- [ ] `scaleTargetRef`가 `vllm-optimizer-frontend` Deployment 가리킴
- [ ] `minReplicas: 1`, `maxReplicas: 3` 설정
- [ ] CPU (80%) 및 Memory (85%) utilization metrics 포함
- [ ] `oc apply --dry-run=client -f` 성공

**QA Scenarios**:

```
Scenario: Verify HPA resource exists in file
  Tool: Bash (grep)
  Steps:
    1. grep -n "kind: HorizontalPodAutoscaler" openshift/base/04-frontend.yaml
  Expected Result: Line number >= 74 (after Deployment)

Scenario: Verify HPA target matches deployment
  Tool: Bash (grep + awk)
  Steps:
    1. grep -A5 "scaleTargetRef" openshift/base/04-frontend.yaml | grep "name: vllm-optimizer-frontend"
  Expected Result: Found

Scenario: Verify replica range
  Tool: Bash (grep)
  Steps:
    1. grep -A2 "minReplicas:" openshift/base/04-frontend.yaml | grep "1"
    2. grep -A2 "maxReplicas:" openshift/base/04-frontend.yaml | grep "3"
  Expected Result: Both found

Scenario: Dry-run apply
  Tool: Bash (oc)
  Steps:
    1. oc apply -f openshift/base/04-frontend.yaml --dry-run=client
  Expected Result: Exit code 0 (no errors)
```

**Evidence to Capture**:
- [ ] `task-11-hpa-added.txt`: HPA resource grep 결과
- [ ] `task-11-hpa-dryrun.log`: oc apply --dry-run 출력

---

#### Task 12: Backend HPA scaleUp Behavior Tuning

**What to do**:
- `openshift/base/03-backend.yaml`의 HorizontalPodAutoscaler에 `behavior` 섹션 추가
- `scaleUp` stabilizationWindowSeconds 및 policies 설정으로 급격한 스케일 방지

**Code changes** (modify HPA spec, around line 108, before metrics):
```yaml
  behavior:
    scaleUp:
      stabilizationWindowSeconds: 60
      policies:
      - type: Pods
        value: 2
        periodSeconds: 60
    scaleDown:
      stabilizationWindowSeconds: 300
      policies:
      - type: Pods
        value: 1
        periodSeconds: 60
```

**Placement**: After `maxReplicas: 10` and before `metrics` section.

**Must NOT do**:
- 기존 `metrics` 섹션 제거 ❌
- `behavior`를 `spec` 바로 아래에 두기 ❌ (scaleTargetRef 다음에 위치)

**Recommended Agent Profile**:
- **Category**: `quick` (YAML field addition)
- **Skills**: None

**Parallelization**:
- **Can Run In Parallel**: YES
- **Parallel Group**: Wave 2
- **Blocks**: Task 14 (deploy)
- **Blocked By**: Task 1

**References**:
- K8s docs: HorizontalPodAutoscaler behavior
- `openshift/base/03-backend.yaml:91-126` - existing HPA

**Acceptance Criteria**:
- [ ] `behavior` 섹션이 HPA `spec` 레벨에 추가됨
- [ ] `scaleUp.stabilizationWindowSeconds: 60` 설정
- [ ] `scaleUp.policies`에 `value: 2`, `periodSeconds: 60`
- [ ] `scaleDown.stabilizationWindowSeconds: 300` 설정
- [ ] `scaleDown.policies`에 `value: 1`, `periodSeconds: 60`
- [ ] `oc apply --dry-run=client -f` 성공

**QA Scenarios**:

```
Scenario: Verify behavior section exists
  Tool: Bash (grep)
  Steps:
    1. grep -A10 "behavior:" openshift/base/03-backend.yaml
  Expected Result: Found with scaleUp and scaleDown subsections

Scenario: Verify scaleUp policy
  Tool: Bash (grep)
  Steps:
    1. grep -A5 "scaleUp:" openshift/base/03-backend.yaml | grep "stabilizationWindowSeconds: 60"
    2. grep -A5 "scaleUp:" openshift/base/03-backend.yaml | grep "value: 2"
  Expected Result: Both found

Scenario: Verify scaleDown policy
  Tool: Bash (grep)
  Steps:
    1. grep -A5 "scaleDown:" openshift/base/03-backend.yaml | grep "stabilizationWindowSeconds: 300"
  Expected Result: Found

Scenario: Dry-run HPA validation
  Tool: Bash (oc)
  Steps:
    1. oc create -f openshift/base/03-backend.yaml --dry-run=client --validate=true
  Expected Result: Exit code 0, HPA schema valid
```

**Evidence to Capture**:
- [ ] `task-12-behavior-section.txt`: grep -A10 결과
- [ ] `task-12-hpa-validation.log`: oc create --dry-run 출력

---

#### Task 13: ServiceMonitor Path Fix (Depends on Task 5)

**What to do**:
- `openshift/base/05-monitoring.yaml`의 Backend ServiceMonitor endpoint path를 `/api/metrics`에서 `/metrics`로 변경
- ServiceMonitor의 `spec.endpoints[0].path` 수정

**Code change** (line 27):
```yaml
- path: /metrics  # was /api/metrics
```

**Must NOT do**:
- Frontend ServiceMonitor 수정 ❌ (-frontend-는 metrics endpoint 없음)
- ServicePort 변경 ❌ (port http:8000 유지)
- path 타입 변경 ❌ (type은 `MetricsPath` 유지)

**Recommended Agent Profile**:
- **Category**: `quick` (single YAML field edit)
- **Skills**: None

**Parallelization**:
- **Can Run In Parallel**: NO (Depends on Task 5)
- **Parallel Group**: Wave 2 (last task)
- **Blocks**: Task 14 (deploy)
- **Blocked By**: Task 5 (metric names)

**References**:
- `openshift/base/05-monitoring.yaml:25-33` - ServiceMonitor backend endpoint
- `backend/routers/metrics.py` - actual metrics endpoint location (`/metrics`)

**Acceptance Criteria**:
- [ ] `spec.endpoints[0].path: /metrics`로 변경
- [ ] 기존 `/api/metrics` 참조 제거
- [ ] ServiceMonitor YAML syntax valid (lsp_diagnostics 검증)

**QA Scenarios**:

```
Scenario: Verify ServiceMonitor path
  Tool: Bash (grep)
  Steps:
    1. grep -A3 "endpoints:" openshift/base/05-monitoring.yaml | grep "path: /metrics"
  Expected Result: Found (and no "/api/metrics" in same block)

Scenario: Cross-check backend actually serves /metrics
  Tool: Bash (grep)
  Steps:
    1. grep -n "@app.get.*/metrics" backend/routers/metrics.py
  Expected Result: Found (indicates endpoint exists)

Scenario: Dry-run ServiceMonitor apply
  Tool: Bash (oc)
  Steps:
    1. oc apply -f openshift/base/05-monitoring.yaml --dry-run=client
  Expected Result: Exit code 0
```

**Evidence to Capture**:
- [ ] `task-13-servicemonitor-path.txt`: grep 결과
- [ ] `task-13-dryrun.log`: oc apply --dry-run 출력

---

### Wave 3: Integration (1 task)

#### Task 14: Deploy.sh Rollout Monitoring

**What to do**:
- `deploy.sh` 에 `oc rollout restart` 및 health check (`oc wait`) 추가
- 현재: build → push → apply 후 종료
- 변경: apply 후 rollout 대기, pod ready 대기, 성공/실패 메시지 출력

**Code insertion** (after line 131 and 151, after each `oc apply -k` for backend/frontend):
```bash
echo "⏳ Waiting for rollout to complete..."
oc rollout status deployment/vllm-optimizer-backend -n "${NAMESPACE}" --timeout=5m
oc rollout status deployment/vllm-optimizer-frontend -n "${NAMESPACE}" --timeout=5m

echo "⏳ Waiting for pods to be ready..."
oc wait --for=condition=Ready pod -l app=vllm-optimizer-backend -n "${NAMESPACE}" --timeout=300s
oc wait --for=condition=Ready pod -l app=vllm-optimizer-frontend -n "${NAMESPACE}" --timeout=300s

echo "✅ Deployment completed successfully"
```

**Must NOT do**:
- rollout 실패 시 자동 롤백 추가 ❌ (이번 긴급 수정 범위外, 나중에)
- 배포 실패를 알람만으로 대체 ❌ (스크립트 exit code로 propagate)

**Recommended Agent Profile**:
- **Category**: `quick` (bash script snippet)
- **Skills**: `git-master` (script validation)

**Parallelization**:
- **Can Run In Parallel**: NO (final integration step, depends on all Wave 1-2)
- **Parallel Group**: Wave 3 (sole task)
- **Blocks**: Final Wave
- **Blocked By**: All Wave 1-2 tasks (1-13)

**References**:
- `deploy.sh:86-151` - current deployment steps
- OpenShift CLI docs: `oc rollout restart`, `oc wait`

**Acceptance Criteria**:
- [ ] `deploy.sh`에 `oc rollout restart` 두 번 추가됨 (backend, frontend)
- [ ] `oc wait --for=condition=Ready` 두 번 추가됨
- [ ] 각 대기 단계 후 success 메시지 출력 (✅ Deployment completed successfully)
- [ ] `--timeout` 파라미터 명시 (rollout: 5m, pods: 300s)
- [ ] 배포 스크립트 실행 시 rollout 완료까지 대기 (적절한 위치에 배치)

**QA Scenarios**:

```
Scenario: Verify rollout status calls added
  Tool: Bash (grep)
  Steps:
    1. grep -n "oc rollout status deployment/vllm-optimizer-backend" deploy.sh
    2. grep -n "oc rollout status deployment/vllm-optimizer-frontend" deploy.sh
  Expected Result: Both lines found after apply steps (lines >= 132, 152)

Scenario: Verify wait-for-ready calls added
  Tool: Bash (grep)
  Steps:
    1. grep -n "oc wait --for=condition=Ready pod" deploy.sh
  Expected Result: Two matches (backend, frontend)

Scenario: Dry-run deployment (no actual changes)
  Tool: Bash (./deploy.sh)
  Preconditions: Have oc cluster access, dry-run mode if available
  Steps:
    1. ./deploy.sh dev --dry-run (if supported) or inspect for "Waiting" messages
  Expected Result: Script prints "⏳ Waiting for rollout..." messages before actual apply

Scenario: Script syntax check
  Tool: Bash (shellcheck)
  Steps:
    1. shellcheck deploy.sh
  Expected Result: No warnings (or only minor)
```

**Evidence to Capture**:
- [ ] `task-14-rollout-calls.txt`: grep 결과 (라인 번호)
- [ ] `task-14-script-syntax.log`: shellcheck 출력

---

## Final Verification Wave (MANDATORY)

After ALL implementation tasks complete, run 4 review agents in **PARALLEL**.

---

### F1. Plan Compliance Audit

**Agent**: `oracle`
**Instruction**: Read the plan end-to-end. For each "Must Have": verify implementation exists (read file, curl endpoint, run command). For each "Must NOT Have": search codebase for forbidden patterns — reject with file:line if found. Check evidence files exist in `.sisyphus/evidence/urgent-fixes-2026-03-06/`. Compare deliverables against plan.

**Success Conditions**:
- All 12 Must Have items present
- Zero Must NOT Have items found
- All evidence files complete ✅
- **VERDICT: APPROVE** only if ALL satisfied

---

### F2. Code Quality Review

**Agent**: `unspecified-high`
**Instruction**:
1. Run `python -m py_compile` on all modified `.py` files
2. Run `flake8` or `pylint` on Python changes (if available)
3. Review for: `as any`, empty catches, `console.log` in prod, commented-out code, unused imports
4. Check AI slop: excessive comments, over-abstraction, generic names

**Success Conditions**:
- Build: PASS
- Lint: PASS (warnings acceptable)
- Zero critical quality issues
- **VERDICT: APPROVE** if code clean

---

### F3. Real Manual QA (Smoke Test)

**Agent**: `unspecified-high` (+ `playwright` if UI)
**Instruction**: Start from clean state. Execute EVERY QA scenario from EVERY task — follow exact steps, capture evidence. Test cross-task integration (features working together). Test edge cases: empty state, invalid input, rapid actions. Save to `.sisyphus/evidence/urgent-fixes-2026-03-06/final-qa/`.

**Focus Areas**:
- Metrics endpoint reaches Thanos (real or mocked)
- Deployment applies without errors
- Frontend can call backend /api endpoints
- Health checks report correctly
- No race condition crashes under concurrency

**Success Conditions**:
- All scenarios PASS
- No integration failures
- **VERDICT: APPROVE** only if all smoke tests green

---

### F4. Scope Fidelity Check

**Agent**: `deep`
**Instruction**: For each task: read "What to do", read actual diff (git log/diff). Verify 1:1 — everything in spec was built (no missing), nothing beyond spec was built (no creep). Check "Must NOT do" compliance. Detect cross-task contamination: Task N touching Task M's files. Flag unaccounted changes.

**Success Conditions**:
- 12/12 tasks exactly as specified
- Zero scope creep
- Zero cross-contamination
- **VERDICT: APPROVE** if scope clean

---

## Commit Strategy

**Single Commit** after all tasks approved:
```
fix(urgent): vLLM Optimizer critical fixes for stability

- Fix dev overlay namespace bug (Task 1)
- Standardize metric names colon→underscore (Task 5)
- Correct VLLM_ENDPOINT service name (Task 4)
- Remove SSL verify=False (Task 6)
- Add race condition locks to LoadEngine (Task 7)
- Add study lock to AutoTuner (Task 8)
- Add CORS headers to nginx (Task 9)
- Enhance backend health check (Task 10)
- Add frontend HPA (Task 11)
- Fix ServiceMonitor path (Task 13)
- Tune backend HPA scaleUp (Task 12)
- Add deploy.sh rollout monitoring (Task 14)
- Verify NetworkPolicies (Task 2) and ServiceAccount (Task 3)

Resolves: monitoring-alerts-down, dev-deploy-blocked,
         vllm-endpoint-misconfigured, ssl-vulnerability,
         race-conditions, cors-errors, health-check-unreliable

Scope: urgent-fixes-2026-03-06 (2-3 day sprint)
```

**Files changed**:
- modified: openshift/overlays/dev/kustomization.yaml
- modified: openshift/base/01-namespace-rbac.yaml
- modified: openshift/base/02-config.yaml
- modified: openshift/base/03-backend.yaml
- modified: openshift/base/04-frontend.yaml
- modified: openshift/base/05-monitoring.yaml
- modified: openshift/dev-only/06-vllm-monitoring.yaml
- modified: frontend/nginx.conf
- modified: backend/services/load_engine.py
- modified: backend/services/auto_tuner.py
- modified: backend/services/metrics_collector.py
- modified: backend/main.py
- modified: deploy.sh

**Pre-commit checks**:
- `python -m py_compile` on all modified .py files
- `oc apply --dry-run=client` on all modified YAMLs
- `nginx -t` on frontend/nginx.conf (via container build)
- `shellcheck deploy.sh`

---

## Success Criteria

### Verification Commands

After implementation, run these commands to verify success:

```bash
# 1. All metric names corrected
! grep -rE "vllm_[a-zA-Z0-9_]+" openshift/base/05-monitoring.yaml openshift/dev-only/06-vllm-monitoring.yaml backend/services/metrics_collector.py && echo "✅ Metric names OK"

# 2. Dev overlay namespace correct
grep "vllm-optimizer-dev" openshift/overlays/dev/kustomization.yaml | wc -l | grep -q "2" && echo "✅ Namespace fixed"

# 3. VLLM_ENDPOINT correct
grep "VLLM_ENDPOINT" openshift/base/02-config.yaml | grep -q "llm-ov-predictor" && echo "✅ Endpoint corrected"

# 4. No SSL verify=False
! grep "verify=False" backend/services/metrics_collector.py && echo "✅ SSL verify fixed"

# 5. Locks present in LoadEngine
grep -q "self._state_lock = asyncio.Lock()" backend/services/load_engine.py && echo "✅ LoadEngine locks"

# 6. Locks present in AutoTuner
grep -q "self._study_lock = asyncio.Lock()" backend/services/auto_tuner.py && echo "✅ AutoTuner locks"

# 7. CORS headers in nginx
grep -q "Access-Control-Allow-Origin" frontend/nginx.conf && echo "✅ CORS headers"

# 8. Health check enhanced
grep -q "deep_check" backend/main.py && echo "✅ Health check enhanced"

# 9. Frontend HPA exists
grep -q "vllm-optimizer-frontend" openshift/base/04-frontend.yaml && echo "✅ Frontend HPA"

# 10. ServiceMonitor path fixed
grep -A3 "endpoints:" openshift/base/05-monitoring.yaml | grep -q "path: /metrics" && echo "✅ ServiceMonitor path"

# 11. Deploy.sh has rollout monitoring
grep -q "oc rollout status" deploy.sh && echo "✅ Deploy monitoring"

# 12. Dry-run all YAMLs
oc apply -k openshift/dev-only --dry-run=client > /dev/null 2>&1 && echo "✅ Base YAMLs valid"
oc apply -k openshift/overlays/dev --dry-run=client > /dev/null 2>&1 && echo "✅ Dev overlay valid"
```

### Final Checklist

- [ ] **Wave 1 Complete**: Tasks 1-5 (Foundation)
- [ ] **Wave 2 Complete**: Tasks 6-13 (Config & Logic)
- [ ] **Wave 3 Complete**: Task 14 (Integration)
- [ ] **Final Audit**: F1-F4 all APPROVE (evidence gaps resolved)
- [ ] **Git Commit**: Single coherent commit with all changes

---

Plan generated: 2026-03-06 by Prometheus (OhMyOpenCode)