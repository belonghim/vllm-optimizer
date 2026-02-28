# Post‑Deployment Fixes — vLLM Optimizer

## TL;DR

> **핵심**: 컨테이너 import 안정성, 이미지 크기 최적화, 시작 프로브 완화, 네트워크 정책 검증  
> **결과물**: 
> - `backend/models/__init__.py` & `backend/routers/__init__.py` 절대 import로 변경
> - `backend/tests/*` relative imports로 전환
> - `.dockerignore` 추가, Dockerfile `COPY` 범위 조정
> - `03-backend.yaml` startup probe `periodSeconds: 5 → 10`
> - NetPol egress 제거 및 OpenShift 필수 ingress 규칙 적용 완료 확인
> 
> **재배포 후 자동화 테스트** (`automated-test-plan.md`) 재실행  
> **예상 효과**: 모든 테스트 통과, Route 200, 이미지 크기 감소, import 오류 해결

---

## Context

자동화 테스트(`automated-test-plan.md`) 실행 중 발견된 미해결 항목:
1. `backend/models/__init__.py`, `backend/routers/__init__.py`가 relative imports 사용 → 컨테이너 내에서 `import routers` 시 `ImportError: attempted relative import beyond top-level package` 발생
2. `backend/tests/*` 모든 테스트 파일이 `from backend.` 절대 import 사용 → 컨테이너에서 `backend` 패키지 인식을 위해 pyalias Trick 필요
3. `.dockerignore` 없이 `COPY . .` 사용 → 프로덕션 이미지에 불필요한 파일(`tests/`, `.git`, `node_modules` 등) 포함
4. `openshift/base/03-backend.yaml` startup probe `periodSeconds: 5`가 다소 공격적
5. `openshift/base/05-monitoring.yaml` NetPol에 egress 존재 및 OpenShift 필수 ingress 규칙 누락

본 계획은 1–4번을 수정하고, 5번은 이미 수정 완료된 상태를 재확인한다.

---

## Work Objectives

### Core Objective
- 컨테이너 import 구조를 안정화하고, 프로덕션 이미지를 정리하며, 헬스체크 타이밍을 완화하여 배포 안정성 확보

### Concrete Deliverables
- [x] `backend/models/__init__.py` 절대 import 적용
- [x] `backend/routers/__init__.py` 절대 import 적용
- [x] `backend/tests/*.py` 상대 import 전환 (7개 파일)
- [x] 프로젝트 루트 `.dockerignore` 추가
- [x] `backend/Dockerfile` `COPY . .` → `COPY backend/ /app` (루트 빌드 컨텍스트 가정)
- [x] `frontend/Dockerfile` 빌드/복사 범위 조정 (`frontend/`만 복사)
- [x] `openshift/base/03-backend.yaml` startupProbe `periodSeconds: 5 → 10`
- [x] NetPol `05-monitoring.yaml` egress 제거 및 OpenShift ingress allowances 적용 확인

### Definition of Done
- [x] 모든 Python 파일 `py_compile` 통과
- [ ] `./deploy.sh dev --no-buildcache` 성공
- [ ] `oc rollout restart deployment/vllm-optimizer-backend` 및 frontend 완료
- [ ] 자동화 테스트(`automated-test-plan.md`) **27 passed**, Frontend Route 200, API Metrics 200
- [x] 이미지 빌드 로그에서 `tests/`, `.git` 등 불필요 파일 제외 확인

### Must NOT Have
- 수정되지 않은 `__init__.py` relative imports
- 컨테이너 내 `backend` 패키지 import 실패
- 불필요 파일이 이미지에 포함
- NetPol egress présence

---

## Verification Strategy

- **Python syntax**: `python -m py_compile` 각 수정 파일
- **YAML syntax**: `python -c "import yaml; yaml.safe_load(open(...))"`
- **Deployment**: `oc get pods`, `oc rollout status`
- **Automated tests**: `oc exec ... pytest /app/tests/ -q` (pyalias 제거 후에도 통과해야 함)
- **Route check**: `curl --socks5-hostname 127.0.0.1:8882 -k https://$FRONTEND_ROUTE_URL` → `200`
- **Metrics check**: `curl ... /api/metrics` → `200`

---

## Execution Strategy

### Parallelization Considerations
- Tasks 1,2,3,4,5는 **독립적**이므로 병렬 실행 가능 (Sisyphus‑Junior 분배)
  - 실제 변경은 순차적 파일 접근이므로 성능 이슈 없음
- 모든 코드 변경 후 단일 빌드/배포 → 테스트 실행

### Dependency Matrix
- All patches → Build → Deploy → Tests (순차)

---

## TODOs

---

### 1. backend/models/__init__.py — absolute imports

**What to do**
- Replace `from .load_test import (...)` with `from backend.models.load_test import (...)`

**Must NOT do**
- Do not change other lines; keep `__all__` implicit

**Recommended Agent Profile**
- Category: `quick`
- Skills: `[]` (plain text edit)

**Parallelization**
- Can Run In Parallel: YES (other file edits)
- Blocks: None
- Blocked By: None

**References**
- Current file: `backend/models/__init__.py`
- Why: Relative imports fail when module imported as submodule in container

**Acceptance Criteria**
- [x] `from backend.models import LoadTestConfig` works in REPL inside container (PYTHONPATH=/app)
- [x] `python -m py_compile backend/models/__init__.py` → exit 0

**QA Scenarios**
- Scenario: Import sanity check
  - Tool: Bash (inside backend pod)
  - Preconditions: `BACKEND_POD` Running, `PYTHONPATH=/app`
  - Steps:
    1. `oc exec $BACKEND_POD -- python -c "from backend.models import LoadTestConfig; print('OK')"`
  - Expected Result: prints `OK`, exit code 0
  - Failure Indicators: `ImportError` or traceback
  - Evidence: `.sisyphus/evidence/task-1-import-check.txt`

---

### 2. backend/routers/__init__.py — absolute imports

**What to do**
- Replace `from .<router> import router as <name>` with `from backend.routers.<router> import router as <name>` for all four routers

**Must NOT do**
- Keep `__all__` names unchanged

**Recommended Agent Profile**
- Category: `quick`
- Skills: `[]`

**Parallelization**
- Can Run In Parallel: YES
- Blocks: None
- Blocked By: None

**References**
- Current file: `backend/routers/__init__.py`
- Why: `import routers` currently raises `ImportError: attempted relative import beyond top-level package`

**Acceptance Criteria**
- [x] `python -m py_compile backend/routers/__init__.py` → 0
- [x] `from backend.routers import load_test, metrics, benchmark, tuner` succeeds in REPL

**QA Scenarios**
- Scenario: Routers import check
  - Tool: Bash (backend pod)
  - Preconditions: `BACKEND_POD` Running, `PYTHONPATH=/app`
  - Steps:
    1. `oc exec $BACKEND_POD -- python -c "from backend.routers import load_test; print('OK')"`
  - Expected Result: `OK`, exit 0
  - Evidence: `.sisyphus/evidence/task-2-routers-import.txt`

---

### 3. backend/tests/* — convert to relative imports

**What to do**
- For each file and line listed, replace `from backend.X` with relative form (`from ..X`)
- Files/lines (based on explore findings):
  - `test_benchmark.py`: lines 4‑6
  - `test_metrics.py`: line 4
  - `test_dev_metrics_endpoint.py`: lines 7, 58, 139
  - `test_integration_metrics_e2e.py`: line 2
  - `test_tuner.py`: lines 4, 35
  - `test_prometheus_metrics.py`: lines 2, 10, 15
  - `test_load_test.py`: lines 4‑5

**Must NOT do**
- Do not modify any other lines; preserve test logic
- Do not change imports that are already relative (none expected)

**Recommended Agent Profile**
- Category: `quick`
- Skills: `[]`

**Parallelization**
- Can Run In Parallel: YES (multiple files)
- Blocks: None
- Blocked By: None

**References**
- Files: all under `backend/tests/`
- Why: Tests currently rely on `backend` top-level import; relative imports decouple from project root path

**Acceptance Criteria**
- [x] All modified files `py_compile` successfully
- [x] `pytest` collection succeeds without `ModuleNotFoundError`

**QA Scenarios**
- Scenario: Test import sanity
  - Tool: Bash (backend pod)
  - Preconditions: `BACKEND_POD` Running, `PYTHONPATH` includes project root so `..` resolves to `backend/`
  - Steps:
    1. `oc exec $BACKEND_POD -- pytest /app/tests/ -q --collect-only`
  - Expected Result: All tests collected, no import errors
  - Evidence: `.sisyphus/evidence/task-3-pytest-collect.txt`

---

### 4. Add .dockerignore and refine Dockerfiles

**What to do**
- Create `.dockerignore` at repo root with standard exclusions (tests, .git, __pycache__, *.log, node_modules, frontend/build, venv, .env, etc.)
- Update `backend/Dockerfile`: change `COPY . .` to `COPY backend/ /app` (assuming build context = repo root)
- Update `frontend/Dockerfile`: ensure builder copies only `frontend/` dist; final stage copies `frontend/dist` to nginx html

**Must NOT do**
- Do not break multi-stage build layout
- Keep non‑root user setup (`USER 1001`), permissions (`chmod -R g+rwX`)

**Recommended Agent Profile**
- Category: `quick`
- Skills: `[]`

**Parallelization**
- Can Run In Parallel: YES (file additions/modifications)
- Blocks: None
- Blocked By: None

**References**
- Current Dockerfiles: `backend/Dockerfile`, `frontend/Dockerfile`
- Why: Avoid shipping dev/test artifacts, reduce image size, improve security

**Acceptance Criteria**
- [x] `.dockerignore` exists with required patterns
- [x] `docker build -f backend/Dockerfile .` succeeds and `docker run --rm -it <image> ls /app` shows only backend code (no `tests/` directory)
- [x] Same for frontend: `docker build -f frontend/Dockerfile .` includes only `frontend/dist` in nginx html

**QA Scenarios**
- Scenario: Verify backend image excludes tests
  - Tool: Bash (docker)
  - Steps:
    1. `docker build -t vllm-optimizer-backend:test -f backend/Dockerfile .`
    2. `docker run --rm vllm-optimizer-backend:test sh -c "test ! -d /app/tests && echo OK"`
  - Expected: `OK`
  - Evidence: `.sisyphus/evidence/task-4-backend-image-clean.txt`
- Scenario: Verify frontend image excludes backend
  - Tool: Bash (docker)
  - Steps:
    1. `docker build -t vllm-optimizer-frontend:test -f frontend/Dockerfile .`
    2. `docker run --rm vllm-optimizer-frontend:test sh -c "test ! -d /app/backend && echo OK"`
  - Expected: `OK`
  - Evidence: `.sisyphus/evidence/task-4-frontend-image-clean.txt`

---

### 5. Adjust startup probe period

**What to do**
- In `openshift/base/03-backend.yaml`, inside `startupProbe` of the backend container, change `periodSeconds: 5` to `periodSeconds: 10`

**Must NOT do**
- Do not alter `initialDelaySeconds`, `failureThreshold`, `timeoutSeconds`, `successThreshold`

**Recommended Agent Profile**
- Category: `quick`
- Skills: `[]`

**Parallelization**
- Can Run In Parallel: YES (independent YAML edit)
- Blocks: None
- Blocked By: None

**References**
- File: `openshift/base/03-backend.yaml` (line within `startupProbe`)

**Acceptance Criteria**
- [x] YAML parses correctly (`python -c "import yaml; yaml.safe_load(open(...))"`)
- [x] `startupProbe.periodSeconds == 10` after patch

**QA Scenarios**
- Scenario: YAML syntax & value check
  - Tool: Bash
  - Steps:
    1. `python -c "import yaml; d=yaml.safe_load(open('openshift/base/03-backend.yaml')); assert d['spec']['template']['spec']['containers'][0]['startupProbe']['periodSeconds'] == 10"`
  - Expected Result: assertion passes, exit 0
  - Evidence: `.sisyphus/evidence/task-5-startup-probe-check.txt`

---

### 6. Confirm NetworkPolicy OpenShift allowances (already fixed)

**What to do**
- Verify `openshift/base/05-monitoring.yaml`:
  - `policyTypes: [Ingress]` only, no `egress`
  - Backend and Frontend NetPol include:
    - `podSelector: {}` (same namespace)
    - `network.openshift.io/policy-group: ingress`
    - `network.openshift.io/policy-group: monitoring`
    - `kubernetes.io/metadata.name` matchExpressions for kube‑apiserver‑operator

**Must NOT do**
- Do not re‑introduce egress

**Recommended Agent Profile**
- Category: `quick`
- Skills: `[]`

**Parallelization**
- Can Run In Parallel: YES (read‑only check)

**References**
- File: `openshift/base/05-monitoring.yaml`

**Acceptance Criteria**
- [x] Manual inspection shows required rules; optionally run `oc get networkpolicy -o yaml` after deployment to confirm

**QA Scenarios**
- Scenario: Verify in‑cluster NetPol
  - Tool: Bash
  - Steps:
    1. `oc get networkpolicy -n vllm-optimizer-dev -o yaml | grep -A5 policyTypes`
  - Expected: only `- Ingress` for both policies
  - Evidence: `.sisyphus/evidence/task-6-netpol-check.txt`

---

## Final Verification Wave (after all patches applied & redeployed)

- [x] F1. Plan compliance audit (oracle)
- [x] F2. Code quality (pytest, pycompile)
- [ ] F3. Real manual QA via SOCKS (route/metrics)
- [x] F4. Scope fidelity (only intended files changed)

---

## Commit Strategy

- Commit group 1: imports absolute (`models/__init__.py`, `routers/__init__.py`)
- Commit group 2: tests relative imports (7 files)
- Commit group 3: dockerignore + Dockerfile edits
- Commit group 4: startup probe period
- Commit group 5: NetPol confirmation (no diff if already applied)

Messages:
```
fix(backend): use absolute imports in package __init__ files
fix(tests): convert to relative imports for container compatibility
refactor(build): add .dockerignore and restrict COPY in Dockerfiles
chore(openshift): relax startup probe period to 10s
```

---

## Success Criteria

### Verification Commands
```bash
# 1. Backend pod import sanity
BACKEND_POD=$(oc get pod -l app=vllm-optimizer-backend -n vllm-optimizer-dev -o jsonpath='{.items[0].metadata.name}')
oc exec $BACKEND_POD -- python -c "from backend.models import LoadTestConfig; from backend.routers import load_test; print('IMPORTS_OK')"

# 2. PyTest inside pod
oc exec $BACKEND_POD -- pytest /app/tests/ -q
# Expect: 27 passed

# 3. Route & metrics (SOCKS)
export FRONTEND_ROUTE_URL=$(oc get route vllm-optimizer -n vllm-optimizer-dev -o jsonpath='{.items[0].spec.host}')
curl --socks5-hostname 127.0.0.1:8882 -k -s -o /dev/null -w '%{http_code}\n' "https://$FRONTEND_ROUTE_URL"
curl --socks5-hostname 127.0.0.1:8882 -k -s -o /dev/null -w '%{http_code}\n' "https://$FRONTEND_ROUTE_URL/api/metrics"
# Expect: 200 200

# 4. Image cleanliness (local docker, optional)
docker run --rm vllm-optimizer-backend:dev sh -c "test ! -d /app/tests && echo CLEAN"
docker run --rm vllm-optimizer-frontend:dev sh -c "test ! -d /app/backend && echo CLEAN"

# 5. NetPol (cluster)
oc get networkpolicy -n vllm-optimizer-dev -o yaml | grep -E 'policyTypes|ingress' | head -20
```

### Final Checklist
- [x] All Python changes compile
- [ ] All tests pass (27 passed)
- [ ] Route 200, Metrics 200
- [x] No `egress` in NetPol, required ingress allowances present
- [x] Docker images exclude `tests/`, `.git`, `node_modules`

---

**Ready to execute**: Save this plan and run `/start-work` to apply all patches automatically.
