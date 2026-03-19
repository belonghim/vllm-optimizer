# Plan: CPU/OpenVINO Integration Tests — Rebase + Bug Fix + Cluster Execution

**Created**: 2026-03-07
**Status**: Ready for execution
**Estimated Tasks**: 10
**Scope**: enhanced-perf-tests-v2 branch rebase → auto_tuner sync K8s 버그 수정 → CPU/OpenVINO 호환성 → 클러스터 통합 테스트 5개 통과
**Target**: main branch, OpenShift 4.x dev cluster (vLLM 0.13.0 CPU/OpenVINO)

---

## TL;DR

> `enhanced-perf-tests-v2` 브랜치를 main에 rebase하고, auto_tuner의 sync K8s 버그를 수정하고,
> CPU/OpenVINO vLLM에 맞게 통합 테스트를 조정한 뒤 **실제 클러스터에서 5개 통합 테스트를 통과**시킨다.

---

## Cluster Facts (verified 2026-03-07)

| 항목 | 값 |
|------|------|
| vLLM 버전 | 0.13.0 (CPU/OpenVINO) |
| 모델명 | `Qwen2.5-Coder-3B-Instruct-int4-ov` |
| vLLM 엔드포인트 | `http://llm-ov-predictor.vllm.svc.cluster.local:8080` |
| API 서버 | `vllm.entrypoints.openai.api_server` → `/v1/completions` 지원 |
| Optimizer 네임스페이스 | `vllm-optimizer-dev` |
| vLLM 네임스페이스 | `vllm` |
| ConfigMap | `vllm-config` (MAX_NUM_SEQS, GPU_MEMORY_UTILIZATION, MAX_MODEL_LEN, ENABLE_ENFORCE_EAGER) |
| Thanos | `verify=False` (self-signed cert), Bearer token auth |
| MetricsCollector 버전 감지 | `0.13.x-cpu` |

---

## Scope

### IN
- `enhanced-perf-tests-v2` → main rebase (7개 충돌 파일 해결)
- `backend/services/auto_tuner.py` — sync K8s 버그 수정 (`asyncio.to_thread`)
- `backend/tests/integration/performance/conftest.py` — 엔드포인트/모델명/타임아웃 조정
- `backend/tests/integration/performance/test_load_test_throughput.py` — CPU 타임아웃 조정
- `backend/tests/integration/performance/test_auto_tuner.py` — CPU 파라미터 조정
- `backend/tests/integration/performance/test_sse_streaming.py` — CPU 타임아웃 조정
- `backend/requirements.txt` — `psutil` 추가 (branch의 load_engine에서 사용)
- 클러스터 배포 + 5개 통합 테스트 실행

### OUT
- 프론트엔드 코드 변경
- nginx, CORS, API 경로 변경
- Tekton 파이프라인 수정
- 새 통합 테스트 추가 (기존 5개만 통과시킴)
- `gpu_memory_utilization` 파라미터 제거 (CPU에서 무의미하지만 ConfigMap에 존재, vLLM이 무시함)

### MUST NOT
- 엔드포인트 경로, 응답 스키마 변경 금지
- main의 singleton MetricsCollector 구조를 되돌리지 않음
- main의 0.13.x-cpu 쿼리 셋을 되돌리지 않음
- main의 SSL verify=False를 되돌리지 않음

---

## Pre-Wave: Conventions & Patterns

### Rebase 충돌 해결 원칙
- **main 우선**: metrics_collector.py, tuner.py, startup_metrics_shim.py, conftest.py → main의 singleton + 0.13.x-cpu 코드 유지
- **branch 코드 수용**: integration/ 디렉토리, load_engine.py 확장, models 확장
- **양쪽 병합**: auto_tuner.py (main의 구조 + branch의 KServe 지원)

### asyncio.to_thread 패턴 (신규)
```python
# sync K8s 호출을 non-blocking으로 만드는 패턴
result = await asyncio.to_thread(
    self._k8s_core.read_namespaced_config_map,
    name=K8S_CONFIGMAP, namespace=K8S_NAMESPACE
)
```
- `asyncio.to_thread`는 Python 3.9+ 내장 (외부 의존성 없음)
- K8s 클라이언트는 thread-safe → `asyncio.to_thread`로 감싸기 안전
- 기존 `_k8s_lock`은 유지 (동시 ConfigMap 수정 방지)

### 모델명 주의사항
- `--served-model-name=Qwen2.5-Coder-3B-Instruct-int4-ov` → 이 이름으로 요청해야 함
- 테스트의 `model: "default"` → `model: "Qwen2.5-Coder-3B-Instruct-int4-ov"` 로 변경
- 또는 환경변수 `VLLM_MODEL`로 주입

---

## Wave 1 — Rebase

### Task 1: enhanced-perf-tests-v2를 main에 rebase

**Category**: `deep`
**Skills**: `["git-master"]`
**Files**: 7개 충돌 파일
**Depends**: None

#### What to do

```bash
git checkout enhanced-perf-tests-v2
git rebase main
```

충돌 해결 전략 (파일별):

**1. `backend/services/metrics_collector.py`** — **main 코드 유지** (ACCEPT THEIRS = main)
- main에 0.13.x-cpu 쿼리 셋, SSL fix, deque, singleton 저장 로직이 있음
- branch의 변경은 이미 main에 더 발전된 형태로 포함됨

**2. `backend/routers/tuner.py`** — **main 코드 유지** (singleton import)
- branch: `from services.metrics_collector import MetricsCollector` + `MetricsCollector()`
- main: `from services.shared import metrics_collector, load_engine`
- branch의 추가 엔드포인트 (status, trials 등)는 main 기반으로 재적용
- branch에서 추가된 endpoint 로직만 cherry-pick 스타일로 병합

**3. `backend/services/auto_tuner.py`** — **양쪽 병합**
- main 구조 유지 + branch의 KServe InferenceService 관련 코드 유지
- sync K8s 버그는 Task 3에서 별도 수정

**4. `backend/services/load_engine.py`** — **branch 코드 수용**
- branch에 psutil 메트릭 샘플링, _sample_metrics 등 추가됨
- main과 충돌 없는 추가 기능

**5. `backend/models/load_test.py`** — **branch 코드 수용**
- branch에 필드 추가됨
- main과 충돌 없는 추가 기능

**6. `backend/startup_metrics_shim.py`** — **main 코드 유지** (singleton)
- branch의 변경은 main에 이미 포함됨

**7. `backend/tests/conftest.py`** — **main 코드 유지** (shared stub)
- branch의 변경은 main에 이미 포함됨

**새 파일 (충돌 없음, 자동 추가):**
- `backend/tests/integration/` 전체 디렉토리
- `baseline.dev.json`, `pyproject.toml`, `scripts/`, `docs/integration_test_guide.md`

#### ⚠️ 주의사항
- rebase 중 `--ours`/`--theirs` 방향이 rebase에서는 반대: rebase 시 theirs = main (upstream)
- 4개 커밋을 하나씩 rebase → 각 커밋마다 충돌 해결
- squash하지 않음 (커밋 히스토리 유지)

#### QA

```bash
# 1. rebase 완료 확인
git log --oneline enhanced-perf-tests-v2 --not main | head -10
# MUST: branch 커밋이 main 위에 위치

# 2. 단위 테스트 통과
python3 -m pytest backend/tests/ -x -q -m "not integration" 2>&1 | tail -3
# MUST: 40+ passed

# 3. singleton 구조 유지 확인
grep -rn 'MetricsCollector()' backend/ --include='*.py' | grep -v test | grep -v __pycache__
# MUST: backend/services/shared.py만 출력

# 4. shared.py 존재 확인
test -f backend/services/shared.py && echo "OK"
# MUST: OK

# 5. integration 테스트 파일 존재
ls backend/tests/integration/performance/test_*.py | wc -l
# MUST: 5
```

---

## Wave 2 — auto_tuner sync K8s 버그 수정

### Task 2: `_wait_for_ready()` — sync K8s → asyncio.to_thread

**Category**: `deep`
**Skills**: `[]`
**Files**: `backend/services/auto_tuner.py`
**Depends**: Task 1

#### What to do

`_wait_for_ready()` (line 56):
```python
# AS-IS (TypeError: object dict can't be used in 'await')
inferenceservice = await self._k8s_custom.get_namespaced_custom_object(
    group="serving.kserve.io", version="v1beta1",
    name=K8S_DEPLOYMENT, namespace=K8S_NAMESPACE, plural="inferenceservices",
)

# TO-BE
inferenceservice = await asyncio.to_thread(
    self._k8s_custom.get_namespaced_custom_object,
    group="serving.kserve.io", version="v1beta1",
    name=K8S_DEPLOYMENT, namespace=K8S_NAMESPACE, plural="inferenceservices",
)
```

#### QA
```bash
grep -n 'asyncio.to_thread' backend/services/auto_tuner.py
# MUST: 1줄 (line ~56)

grep -n 'await self._k8s_custom.get_namespaced' backend/services/auto_tuner.py
# MUST: 0줄 (직접 await 제거됨)

python3 -m pytest backend/tests/ -x -q -m "not integration" 2>&1 | tail -3
# MUST: passed
```

---

### Task 3: `_apply_params()` — sync K8s → asyncio.to_thread (3곳)

**Category**: `deep`
**Skills**: `[]`
**Files**: `backend/services/auto_tuner.py`
**Depends**: Task 2

#### What to do

`_apply_params()` 내 3개 sync K8s 호출:

**Line 195** — ConfigMap 읽기:
```python
# AS-IS
current_cm = self._k8s_core.read_namespaced_config_map(
    name=K8S_CONFIGMAP, namespace=K8S_NAMESPACE
)
# TO-BE
current_cm = await asyncio.to_thread(
    self._k8s_core.read_namespaced_config_map,
    name=K8S_CONFIGMAP, namespace=K8S_NAMESPACE,
)
```

**Line 208** — ConfigMap 패치:
```python
# AS-IS
self._k8s_core.patch_namespaced_config_map(
    name=K8S_CONFIGMAP, namespace=K8S_NAMESPACE, body=patch_body
)
# TO-BE
await asyncio.to_thread(
    self._k8s_core.patch_namespaced_config_map,
    name=K8S_CONFIGMAP, namespace=K8S_NAMESPACE, body=patch_body,
)
```

**Line 231** — InferenceService 패치:
```python
# AS-IS
k8s_custom_api.patch_namespaced_custom_object(
    group=group, version=version, namespace=K8S_NAMESPACE,
    plural=plural, name=name, body=restart_body
)
# TO-BE
await asyncio.to_thread(
    k8s_custom_api.patch_namespaced_custom_object,
    group=group, version=version, namespace=K8S_NAMESPACE,
    plural=plural, name=name, body=restart_body,
)
```

#### QA
```bash
# sync K8s 호출이 없는지 확인 (test 제외)
grep -n 'self._k8s_core\.\|self._k8s_custom\.\|k8s_custom_api\.' backend/services/auto_tuner.py | grep -v 'to_thread\|_init_k8s\|Api()\|_k8s_available\|_k8s_lock'
# MUST: 0줄

# asyncio.to_thread 사용 확인
grep -c 'asyncio.to_thread' backend/services/auto_tuner.py
# MUST: 4 (1 in _wait_for_ready + 3 in _apply_params)

python3 -m pytest backend/tests/ -x -q -m "not integration" 2>&1 | tail -3
# MUST: passed
```

---

## Wave 3 — CPU/OpenVINO 호환성 수정

### Task 4: requirements.txt에 psutil 추가

**Category**: `quick`
**Skills**: `[]`
**Files**: `backend/requirements.txt`
**Depends**: Task 1

#### What to do

branch의 `load_engine.py`에서 `import psutil`을 사용. main의 requirements.txt에 추가:

```
psutil>=6.0.0
```

#### QA
```bash
grep 'psutil' backend/requirements.txt
# MUST: 1줄
```

---

### Task 5: 통합 테스트 conftest — 엔드포인트/모델명/타임아웃 조정

**Category**: `deep`
**Skills**: `[]`
**Files**: `backend/tests/integration/performance/conftest.py`
**Depends**: Task 1

#### What to do

**5-A. BACKEND_URL 기본값** — 이미 올바름 (그대로 유지):
```python
BACKEND_URL = os.getenv("PERF_TEST_BACKEND_URL", "http://vllm-optimizer-backend.vllm-optimizer-dev.svc.cluster.local:8000")
```

**5-B. VLLM_ENDPOINT 기본값 추가** (conftest에 없으면 추가):
```python
VLLM_ENDPOINT = os.getenv("VLLM_ENDPOINT", "http://llm-ov-predictor.vllm.svc.cluster.local:8080")
VLLM_MODEL = os.getenv("VLLM_MODEL", "Qwen2.5-Coder-3B-Instruct-int4-ov")
```

**5-C. `warm_up_vllm` fixture 타임아웃 확대** — CPU 추론 cold start가 오래 걸림:
```python
@pytest.fixture(scope="module", autouse=True)
def warm_up_vllm(http_client: httpx.Client) -> None:
    for _ in range(5):
        try:
            resp = http_client.get("/health", timeout=120)  # 60 → 120
            ...
```

**5-D. vllm_endpoint / vllm_model fixture 추가**:
```python
@pytest.fixture(scope="session")
def vllm_endpoint() -> str:
    return VLLM_ENDPOINT

@pytest.fixture(scope="session")
def vllm_model() -> str:
    return VLLM_MODEL
```

**5-E. `skip_if_overloaded` fixture assertion 수정** (Metis 발견):
현재 `backup_restore_vllm_config`와 `skip_if_overloaded`를 `assert ... is None`으로 체크하는데, fixture가 `yield`하면 `None`이 아닐 수 있음. 이 부분은 테스트 파일에서 수정 (Task 7-8).

#### QA
```bash
grep 'VLLM_MODEL' backend/tests/integration/performance/conftest.py
# MUST: 1줄 이상

grep 'llm-ov-predictor' backend/tests/integration/performance/conftest.py
# MUST: 1줄

python3 -m pytest backend/tests/ -x -q -m "not integration" 2>&1 | tail -3
# MUST: passed
```

---

### Task 6: test_load_test_throughput — CPU 호환 수정

**Category**: `deep`
**Skills**: `[]`
**Files**: `backend/tests/integration/performance/test_load_test_throughput.py`
**Depends**: Task 5

#### What to do

```python
# AS-IS
config = {
    "endpoint": os.getenv("VLLM_ENDPOINT", "http://vllm.vllm.svc.cluster.local:8000"),
    "model": os.getenv("VLLM_MODEL", "default"),
    ...
    "total_requests": 20,
    "concurrency": 4,
    "rps": 2,
    "max_tokens": 50,
    ...
}

# TO-BE — conftest의 fixture 사용 + CPU 타임아웃
def test_load_test_completes_successfully(self, http_client, skip_if_overloaded, vllm_endpoint, vllm_model):
    config = {
        "endpoint": vllm_endpoint,
        "model": vllm_model,
        ...
        "total_requests": 5,      # 20 → 5 (CPU 추론 느림)
        "concurrency": 2,          # 4 → 2
        "rps": 1,                   # 2 → 1
        "max_tokens": 20,           # 50 → 20
        ...
    }
```

또한 `for _ in range(24): time.sleep(5)` 폴링 → CPU에서는 더 오래 대기:
```python
for _ in range(60):  # 24 → 60 (최대 300초)
    time.sleep(5)
```

`skip_if_overloaded` 사용 수정:
```python
# AS-IS
assert skip_if_overloaded is None
# TO-BE (fixture가 None을 반환하지 않을 수 있음 — skip은 내부에서 처리)
# 이 줄 삭제
```

#### QA
```bash
grep 'vllm_endpoint' backend/tests/integration/performance/test_load_test_throughput.py
# MUST: 1줄 이상

grep 'total_requests.*5' backend/tests/integration/performance/test_load_test_throughput.py
# MUST: 1줄
```

---

### Task 7: test_sse_streaming — CPU 호환 수정

**Category**: `quick`
**Skills**: `[]`
**Files**: `backend/tests/integration/performance/test_sse_streaming.py`
**Depends**: Task 5

#### What to do

conftest의 `vllm_endpoint`, `vllm_model` fixture 사용으로 변경:
```python
async def test_load_test_sse_events(self, async_http_client, skip_if_overloaded, vllm_endpoint, vllm_model):
    ...
    config = {
        "endpoint": vllm_endpoint,
        "model": vllm_model,
        ...
        "total_requests": 3,   # 10 → 3 (CPU)
        "concurrency": 1,      # 2 → 1
        "max_tokens": 10,       # 20 → 10
        ...
    }
```

`skip_if_overloaded` assert 삭제 (위와 동일).

#### QA
```bash
grep 'vllm_endpoint' backend/tests/integration/performance/test_sse_streaming.py
# MUST: 1줄 이상
```

---

### Task 8: test_auto_tuner — CPU 파라미터 + sync 버그 수정 반영

**Category**: `deep`
**Skills**: `[]`
**Files**: `backend/tests/integration/performance/test_auto_tuner.py`
**Depends**: Task 3, Task 5

#### What to do

```python
# AS-IS
start_resp = http_client.post("/api/tuner/start", json={
    "config": {
        "n_trials": 2,
        "eval_requests": 10,
        "objective": "tps",
        "max_num_seqs_range": [64, 512],
        "gpu_memory_utilization_range": [0.80, 0.95],
        "max_model_len_range": [2048, 8192],
    },
    "vllm_endpoint": os.getenv("VLLM_ENDPOINT", "http://vllm.vllm.svc.cluster.local:8000"),
}, timeout=10)

# TO-BE
def test_auto_tuner_completes_with_results(self, http_client, backup_restore_vllm_config, skip_if_overloaded, vllm_endpoint):
    start_resp = http_client.post("/api/tuner/start", json={
        "config": {
            "n_trials": 2,
            "eval_requests": 3,  # 10 → 3 (CPU)
            "objective": "tps",
            "max_num_seqs_range": [64, 256],  # 512 → 256 (CPU 메모리 한계)
            "gpu_memory_utilization_range": [0.80, 0.95],  # 유지 (vLLM이 CPU에서 무시)
            "max_model_len_range": [2048, 4096],  # 8192 → 4096 (CPU 메모리 한계)
        },
        "vllm_endpoint": vllm_endpoint,
    }, timeout=30)
```

타임아웃 확대:
```python
for _ in range(120):  # 60 → 120 (최대 600초)
    time.sleep(5)
```

`backup_restore_vllm_config`과 `skip_if_overloaded` assert 삭제.

#### QA
```bash
grep 'vllm_endpoint' backend/tests/integration/performance/test_auto_tuner.py
# MUST: 1줄 이상

grep 'eval_requests.*3' backend/tests/integration/performance/test_auto_tuner.py
# MUST: 1줄
```

---

## Wave 4 — 배포 + 클러스터 사전 검증

### Task 9: 이미지 빌드 + 배포 + 사전 검증

**Category**: `deep`
**Skills**: `[]`
**Files**: 없음 (deploy + verify)
**Depends**: Task 4, Task 8

#### What to do

**9-A. 배포:**
```bash
REGISTRY=quay.io/joopark IMAGE_TAG=latest ./deploy.sh dev
oc rollout restart deployment/vllm-optimizer-backend -n vllm-optimizer-dev
oc rollout status deployment/vllm-optimizer-backend -n vllm-optimizer-dev --timeout=120s
```

**9-B. 사전 검증 체크리스트:**
```bash
NS=vllm-optimizer-dev
BACKEND_POD=$(oc get pod -n $NS -l app=vllm-optimizer-backend -o name | head -1)

# 1. Pod Running 확인
oc get pods -n $NS --no-headers

# 2. MetricsCollector 버전 확인
oc exec -n $NS $BACKEND_POD -- curl -sf -X POST http://localhost:8000/startup_metrics
# MUST: collector_version = "0.13.x-cpu"

# 3. vLLM 엔드포인트 접근 확인 (optimizer pod → vLLM pod)
oc exec -n $NS $BACKEND_POD -- curl -sf http://llm-ov-predictor.vllm.svc.cluster.local:8080/v1/models
# MUST: 모델 목록 반환 (Qwen2.5-Coder-3B-Instruct-int4-ov 포함)

# 4. vLLM ConfigMap 확인
oc get cm vllm-config -n vllm -o yaml
# MUST: MAX_NUM_SEQS, MAX_MODEL_LEN, ENABLE_ENFORCE_EAGER key 존재

# 5. vLLM Pod Running 확인
oc get pods -n vllm --no-headers
# MUST: llm-ov-predictor-* Running

# 6. 간단한 completions 요청 테스트
oc exec -n $NS $BACKEND_POD -- curl -sf -X POST \
  http://llm-ov-predictor.vllm.svc.cluster.local:8080/v1/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"Qwen2.5-Coder-3B-Instruct-int4-ov","prompt":"Hello","max_tokens":5}'
# MUST: JSON 응답 (choices 배열 포함)
```

#### QA

위 6개 체크리스트 모두 통과해야 Wave 5 진행 가능.

---

## Wave 5 — 통합 테스트 실행

### Task 10: 5개 통합 테스트 실행 + 결과 보고

**Category**: `deep`
**Skills**: `[]`
**Files**: 없음 (verify only)
**Depends**: Task 9

#### What to do

통합 테스트는 **클러스터 내부에서 실행**해야 함 (backend pod에서 vLLM에 접근 가능). 
두 가지 방법:
1. **로컬에서 환경변수 설정 후 실행** (oc port-forward 필요)
2. **backend pod에 test runner 포함** (Dockerfile에 pytest 있으므로 가능)

**Method 2 권장 — oc exec로 실행:**

```bash
NS=vllm-optimizer-dev
BACKEND_POD=$(oc get pod -n $NS -l app=vllm-optimizer-backend -o name | head -1)

# 환경변수 설정 + pytest 실행
oc exec -n $NS $BACKEND_POD -- env \
  PERF_TEST_BACKEND_URL=http://localhost:8000 \
  VLLM_ENDPOINT=http://llm-ov-predictor.vllm.svc.cluster.local:8080 \
  VLLM_MODEL=Qwen2.5-Coder-3B-Instruct-int4-ov \
  VLLM_NAMESPACE=vllm \
  OPTIMIZER_NAMESPACE=vllm-optimizer-dev \
  python3 -m pytest tests/integration/performance/ -v --tb=short -m "integration" 2>&1
```

**예상 소요 시간**: CPU 추론 기준 10-30분 (test_auto_tuner가 가장 오래 걸림)

#### QA (= 이 Task의 전체 내용)

```
5 passed (integration tests on real cluster)
```

**하나라도 실패하면 로그를 분석하고 해당 테스트의 Task로 돌아가서 수정.**

---

## Final Verification Wave

이 계획의 모든 Task 완료 후 아래 조건을 최종 확인:

1. ✅ enhanced-perf-tests-v2가 main 위에 rebase됨
2. ✅ singleton MetricsCollector 구조 유지
3. ✅ 0.13.x-cpu 쿼리 셋 유지
4. ✅ auto_tuner sync K8s 버그 수정 (asyncio.to_thread 4곳)
5. ✅ 통합 테스트 CPU/OpenVINO 호환
6. ✅ 로컬 단위 테스트 40+ passed
7. ✅ 클러스터에서 5개 통합 테스트 passed
8. ✅ psutil 의존성 추가됨

## Definition of Done

- [x] enhanced-perf-tests-v2 → main rebase 완료
- [x] `auto_tuner.py` — `_wait_for_ready()` asyncio.to_thread 적용
- [x] `auto_tuner.py` — `_apply_params()` asyncio.to_thread 3곳 적용
- [x] `requirements.txt` — psutil 추가
- [x] 통합 테스트 conftest — 엔드포인트/모델명/타임아웃 조정
- [x] `test_load_test_throughput` — CPU 호환 수정
- [x] `test_sse_streaming` — CPU 호환 수정
- [x] `test_auto_tuner` — CPU 파라미터 + 타임아웃 수정
- [x] 로컬 단위 테스트 40+ passed
- [x] 클러스터 사전 검증 6개 체크리스트 통과
- [x] 클러스터에서 5개 통합 테스트 passed

## Follow-Up (별도 계획으로 추적)

- `deploy.sh` — `compare_and_rollout()` digest 비교 로직이 rollout을 skip하는 문제
- `ENABLE_ENFORCE_EAGER` vs `enable_chunked_prefill` ConfigMap key 의미론적 불일치 검증
- GPU 노드 배포 시 0.13.x 쿼리 셋 검증
- enhanced-perf-tests-v2 branch를 main에 merge (rebase 후 PR)
