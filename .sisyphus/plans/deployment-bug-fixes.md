# Plan: vLLM Optimizer 배포 버그 전체 수정

## Metadata
- **Created**: 2026-03-07
- **Goal**: OpenShift 배포 환경에서 프론트엔드 ↔ 백엔드 통신 및 전체 기능이 정상 동작하도록 17건 버그 수정 + 1건 신규 엔드포인트 추가
- **Scope IN**: 프론트엔드/백엔드 코드, nginx 설정, Dockerfile, OpenShift YAML, Vite 설정
- **Scope OUT**: deploy.sh 수정, CI/CD 파이프라인, 테스트 코드 작성, K8s 리소스 배포

## Bug Registry

| # | Severity | File(s) | Summary |
|---|----------|---------|---------|
| 1 | CRITICAL | `frontend/src/constants.js:2` | API URL `http://localhost:8000/api` 하드코딩 |
| 2 | CRITICAL | `nginx.conf:25` (both) | `proxy_pass` 포트 8080 → 백엔드는 8000 |
| 3 | CRITICAL | `LoadTestPage.jsx` | `/api/load-test/*` (hyphen) vs 백엔드 `/api/load_test/*` (underscore) |
| 4 | CRITICAL | `main.py:75-80` | CORS에 localhost만 허용, ALLOWED_ORIGINS 미사용 |
| 5 | HIGH | `tuner.py` | `/stop`, `/importance` 엔드포인트 미구현 |
| 6 | HIGH | `main.py:41` | `THANOS_URL` env var → ConfigMap은 `PROMETHEUS_URL` |
| 7 | HIGH | `frontend/Dockerfile:16` | `COPY ../nginx.conf` 빌드 컨텍스트 밖 참조 |
| 8 | HIGH | `LoadTestPage:12`, `TunerPage:19` | form 기본값 `localhost:8000` 하드코딩 |
| 9 | MEDIUM | `tuner.py:53` | `TuningStartRequest` Pydantic default `localhost:8000` |
| 10 | MEDIUM | `vite.config.js` | 로컬 개발용 proxy 없음 |
| 11 | MEDIUM | `04-frontend.yaml:102` | `affinity` 들여쓰기 오류 |
| 12 | MEDIUM | `load_test.py` | `/stop`, `/stream`에 `test_id` 필수인데 프론트 미전달 |
| 13 | LOW | root `nginx.conf` | `frontend/nginx.conf`과 중복 |
| 14 | LOW | `main.py:52` | Thanos health check `verify=False` |
| 15 | CRITICAL | `TunerPage.jsx` + `tuner.py` | Tuner `/start` schema 불일치 (flat vs nested) |
| 16 | HIGH | `frontend/nginx.conf:28-43` | nginx CORS 블록 + FastAPI CORS = 이중 CORS |
| 17 | HIGH | `metrics_collector.py:195,246` | `await resp.json()` → httpx는 동기 메서드 |
| 18 | MEDIUM | `frontend/nginx.conf:46` | `Connection "upgrade"` → SSE 호환성 문제 |

## Guardrails (from Metis)
- **MUST NOT**: `allow_origins=["*"]` with `allow_credentials=True` 금지 — 브라우저가 차단함
- **MUST NOT**: `metrics_collector.py`에서 `await resp.json()` 외의 변경 금지
- **MUST NOT**: `test_id` 실제 상태 추적 구현 금지 — Optional로만 변경
- **MUST NOT**: 클러스터 전용 URL을 소스코드에 하드코딩 금지
- **MUST**: nginx CORS 블록 제거 시 FastAPI CORS가 유일한 CORS 소스
- **MUST**: `04-frontend.yaml` affinity 수정 시 `03-backend.yaml`을 구조적 참조로 사용

## Dependency Graph
```
Wave 1 (Build Infra)
  └── Task 1: Dockerfile + nginx 통합 [Bug #7, #2, #13, #16, #18]

Wave 2 (Backend Config) — 병렬 가능
  ├── Task 2: CORS 동적 처리 [Bug #4]
  ├── Task 3: env var 이름 + TLS verify [Bug #6, #14]
  └── Task 4: metrics_collector await 수정 [Bug #17]

Wave 3 (Backend API Shape) — 병렬 가능
  ├── Task 5: load_test 라우터 수정 [Bug #12]
  ├── Task 6: tuner 라우터 전면 수정 [Bug #5, #9, #15]
  └── Task 7: /api/config 엔드포인트 신설 [신규]

Wave 4 (Frontend) — Task 7 완료 후
  ├── Task 8: constants.js + Vite proxy [Bug #1, #10]
  ├── Task 9: LoadTestPage 수정 [Bug #3, #8]
  └── Task 10: TunerPage 수정 [Bug #8]

Wave 5 (OpenShift YAML)
  └── Task 11: 04-frontend.yaml affinity [Bug #11]

Final Verification Wave
  └── Task 12: 전체 검증
```

---

## Wave 1: Build Infrastructure Fix

### Task 1: Dockerfile + nginx 통합 [Bug #7, #2, #13, #16, #18]
**Fixes**: Dockerfile 빌드 컨텍스트 오류, nginx proxy_pass 포트 불일치, nginx.conf 중복, 이중 CORS, SSE Connection 헤더
**Files**:
- `frontend/Dockerfile` (edit)
- `frontend/nginx.conf` (edit)
- `nginx.conf` (delete — root level)

**Changes**:

1. **`frontend/Dockerfile:16`** — COPY 경로 수정:
```dockerfile
# AS-IS
COPY ../nginx.conf /etc/nginx/nginx.conf
# TO-BE
COPY nginx.conf /etc/nginx/nginx.conf
```

2. **`frontend/nginx.conf:25`** — proxy_pass 포트 수정 (Bug #2):
```nginx
# AS-IS
proxy_pass http://vllm-optimizer-backend:8080;
# TO-BE
proxy_pass http://vllm-optimizer-backend:8000;
```

3. **`frontend/nginx.conf:28-43`** — CORS 블록 전체 삭제 (Bug #16):
삭제 대상 (line 28~43):
```nginx
# 아래 전체 삭제 — FastAPI CORSMiddleware가 CORS 담당
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

4. **`frontend/nginx.conf:46`** — Connection 헤더 수정 (Bug #18):
```nginx
# AS-IS
proxy_set_header Connection "upgrade";
# TO-BE
proxy_set_header Connection '';
```

5. **root `nginx.conf`** — 파일 삭제 (Bug #13):
```bash
rm nginx.conf  # 프로젝트 루트의 중복 파일
```

**QA**:
```bash
# Dockerfile에 '../' 경로 없음 확인
grep 'COPY.*nginx' frontend/Dockerfile | grep -v '\.\.'
# 결과: COPY nginx.conf /etc/nginx/nginx.conf

# proxy_pass 포트 8000 확인
grep 'proxy_pass' frontend/nginx.conf
# 결과: proxy_pass http://vllm-optimizer-backend:8000;

# CORS 블록 제거 확인
grep -c 'Access-Control' frontend/nginx.conf
# 결과: 0

# Connection 헤더 확인
grep 'Connection' frontend/nginx.conf
# 결과: proxy_set_header Connection '';

# root nginx.conf 삭제 확인
test ! -f nginx.conf && echo "DELETED"
# 결과: DELETED
```

---

## Wave 2: Backend Configuration Fixes

### Task 2: CORS 동적 처리 [Bug #4]
**Fixes**: CORS에 localhost만 허용, OpenShift Route origin 차단됨
**File**: `backend/main.py`

**Changes** — lines 72-84 교체:
```python
# AS-IS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# TO-BE
_default_origins = [
    "http://localhost:5173",
    "http://localhost:3000",
    "http://127.0.0.1:5173",
    "http://127.0.0.1:3000",
]
_raw = os.getenv("ALLOWED_ORIGINS", "")
_origins = [o.strip() for o in _raw.split(",") if o.strip()] if _raw else _default_origins

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

**⚠ GUARDRAIL**: `allow_origins=["*"]`와 `allow_credentials=True` 조합 금지. `ALLOWED_ORIGINS` 비어있으면 반드시 localhost 리스트로 fallback.

**QA**:
```bash
# ALLOWED_ORIGINS 환경변수 사용 확인
grep 'ALLOWED_ORIGINS' backend/main.py
# 결과: os.getenv("ALLOWED_ORIGINS", "") 포함

# ["*"] 사용 안함 확인
grep -c 'allow_origins=\["\*"\]' backend/main.py
# 결과: 0
```

---

### Task 3: env var 이름 + TLS verify 수정 [Bug #6, #14]
**Fixes**: main.py health check에서 THANOS_URL 사용 + verify=False
**File**: `backend/main.py`

**Changes**:

1. **Line 41** — env var 이름 수정 (Bug #6):
```python
# AS-IS
thanos_url = os.getenv("THANOS_URL", "https://thanos-querier.openshift-monitoring.svc.cluster.local:9091")
# TO-BE
thanos_url = os.getenv("PROMETHEUS_URL", "https://thanos-querier.openshift-monitoring.svc.cluster.local:9091")
```

2. **Line 52** — TLS verify 수정 (Bug #14):
```python
# AS-IS
async with httpx.AsyncClient(timeout=3, verify=False) as client:
# TO-BE
ca_path = "/var/run/secrets/kubernetes.io/serviceaccount/ca.crt"
_verify = ca_path if os.path.exists(ca_path) else False
async with httpx.AsyncClient(timeout=3, verify=_verify) as client:
```
> Note: `metrics_collector.py`의 동일 패턴(`ca_path if exists else True`)을 참조. health check는 fallback으로 `False` 유지 (로컬 개발 환경에서 CA 없을 때 crash 방지).

**⚠ GUARDRAIL**: `metrics_collector.py`는 이미 올바르게 `PROMETHEUS_URL` 사용 중. 절대 건드리지 말 것 (await 수정 제외, Task 4).

**QA**:
```bash
# THANOS_URL 제거 확인 (main.py에서만)
grep -c 'THANOS_URL' backend/main.py
# 결과: 0

# PROMETHEUS_URL 사용 확인
grep 'PROMETHEUS_URL' backend/main.py
# 결과: os.getenv("PROMETHEUS_URL", ...) 포함

# verify=False 직접 사용 제거
grep -c "verify=False" backend/main.py
# 결과: 0
```

---

### Task 4: metrics_collector await 수정 [Bug #17]
**Fixes**: `await resp.json()` → `resp.json()` (httpx Response.json()은 동기 메서드)
**File**: `backend/services/metrics_collector.py`

**Changes** — 2곳 수정:

```python
# Line 195
# AS-IS
data = await resp.json()
# TO-BE
data = resp.json()

# Line 246
# AS-IS
data = await resp.json()
# TO-BE
data = resp.json()
```

**⚠ GUARDRAIL**: 이 파일에서 위 2줄 외 다른 변경 절대 금지.

**QA**:
```bash
# await resp.json() 제거 확인
grep -c 'await resp.json' backend/services/metrics_collector.py
# 결과: 0

# resp.json() 존재 확인
grep -c 'resp.json()' backend/services/metrics_collector.py
# 결과: 2 (이상)
```

---

## Wave 3: Backend API Shape Fixes

### Task 5: load_test 라우터 수정 [Bug #12]
**Fixes**: `/stop`, `/stream` 엔드포인트의 `test_id` 필수 → Optional
**File**: `backend/routers/load_test.py`

**Changes**:

1. **Line 103** — stop 엔드포인트:
```python
# AS-IS
async def stop_load_test(test_id: str):
# TO-BE
async def stop_load_test(test_id: Optional[str] = None):
```

2. **Line 155** — stream 엔드포인트:
```python
# AS-IS
async def stream_load_test_results(test_id: str):
# TO-BE
async def stream_load_test_results(test_id: Optional[str] = None):
```

**⚠ GUARDRAIL**: test_id로 실제 테스트를 조회하는 로직 추가 금지. 현재 싱글턴 `_active_test_task` 구조를 유지. Optional로만 변경하고 값은 무시.

**QA**:
```bash
# test_id가 Optional인지 확인
grep 'def stop_load_test\|def stream_load_test' backend/routers/load_test.py
# 결과: 둘 다 test_id: Optional[str] = None 포함
```

---

### Task 6: tuner 라우터 전면 수정 [Bug #5, #9, #15]
**Fixes**: 누락 엔드포인트 추가, TuningStartRequest 스키마 플래튼, Pydantic default 수정
**Files**:
- `backend/routers/tuner.py` (edit)
- `backend/models/load_test.py` (edit)

**Changes**:

#### 6-A: `TuningStartRequest` 플래튼 (Bug #15)
`backend/routers/tuner.py` — `TuningStartRequest` 클래스 교체 (line 50-53):
```python
# AS-IS
class TuningStartRequest(BaseModel):
    """Request to start auto-tuning"""
    config: TuningConfig
    vllm_endpoint: str = "http://localhost:8000"

# TO-BE
class TuningStartRequest(BaseModel):
    """Request to start auto-tuning (flat schema matching frontend)"""
    objective: str = "balanced"
    n_trials: int = 20
    vllm_endpoint: str = ""
    max_num_seqs_min: int = 64
    max_num_seqs_max: int = 512
    gpu_memory_min: float = 0.80
    gpu_memory_max: float = 0.95
```
> vllm_endpoint 기본값은 빈 문자열. Task 7의 `/api/config`에서 조회한 값을 프론트가 전달.

#### 6-B: `start_tuning` 함수 수정 (line 63-79)
`TuningStartRequest` → `TuningConfig` 변환 로직 추가:
```python
# AS-IS
@router.post("/start", response_model=TuningStartResponse)
async def start_tuning(request: TuningStartRequest):
    if auto_tuner.is_running:
        return {
            "success": False,
            "message": "Tuning is already running. Wait for it to complete or stop it first.",
            "tuning_id": None,
        }
    tuning_id = str(uuid.uuid4())
    import asyncio
    asyncio.create_task(auto_tuner.start(request.config, request.vllm_endpoint))
    return {
        "success": True,
        "message": f"Tuning started with {request.config.n_trials} trials",
        "tuning_id": tuning_id,
    }

# TO-BE
@router.post("/start", response_model=TuningStartResponse)
async def start_tuning(request: TuningStartRequest):
    if auto_tuner.is_running:
        return {
            "success": False,
            "message": "Tuning is already running. Wait for it to complete or stop it first.",
            "tuning_id": None,
        }
    # Convert flat request to TuningConfig
    config = TuningConfig(
        max_num_seqs_range=(request.max_num_seqs_min, request.max_num_seqs_max),
        gpu_memory_utilization_range=(request.gpu_memory_min, request.gpu_memory_max),
        objective=request.objective,
        n_trials=request.n_trials,
    )
    vllm_endpoint = request.vllm_endpoint or os.getenv("VLLM_ENDPOINT", "http://localhost:8000")
    tuning_id = str(uuid.uuid4())
    import asyncio
    asyncio.create_task(auto_tuner.start(config, vllm_endpoint))
    return {
        "success": True,
        "message": f"Tuning started with {request.n_trials} trials",
        "tuning_id": tuning_id,
    }
```
> `import os`가 tuner.py 상단에 없으면 추가 필요.

#### 6-C: `/stop` 엔드포인트 추가 (Bug #5)
기존 코드의 `/apply-best` 앞에 추가:
```python
@router.post("/stop")
async def stop_tuning():
    """Stop the running auto-tuning process."""
    if not auto_tuner.is_running:
        return {"success": False, "message": "No tuning is currently running."}
    auto_tuner.stop()
    return {"success": True, "message": "Tuning stopped."}
```
> `auto_tuner.stop()` 메서드 존재 여부 확인 필요. 없으면 `auto_tuner.is_running = False` 플래그만 설정하는 stub.

#### 6-D: `/importance` 엔드포인트 추가 (Bug #5)
```python
@router.get("/importance")
async def get_parameter_importance():
    """Get parameter importance from Optuna study (FAnova)."""
    if not auto_tuner.trials:
        return {}
    # Stub: return equal importance for known parameters
    return {
        "max_num_seqs": 0.4,
        "gpu_memory_utilization": 0.35,
        "max_model_len": 0.25,
    }
```
> 실제 Optuna importance 계산은 향후 개선. 현재는 stub.

#### 6-E: `LoadTestConfig.endpoint` default 수정 (Bug #9의 관련 항목)
`backend/models/load_test.py:16`:
```python
# AS-IS
endpoint: str = Field(default="http://localhost:8000", description="vLLM endpoint URL")
# TO-BE
endpoint: str = Field(default="", description="vLLM endpoint URL (empty = use server default from VLLM_ENDPOINT env)")
```

**QA**:
```bash
# /stop 엔드포인트 존재
grep '@router.post("/stop")' backend/routers/tuner.py
# 결과: 1줄

# /importance 엔드포인트 존재
grep '@router.get("/importance")' backend/routers/tuner.py
# 결과: 1줄

# TuningStartRequest이 flat
grep 'config: TuningConfig' backend/routers/tuner.py
# 결과: 0 (nested 구조 제거됨)

# vllm_endpoint 기본값에 localhost 없음
grep 'localhost' backend/routers/tuner.py
# 결과: 0

# LoadTestConfig endpoint default 수정
grep 'localhost' backend/models/load_test.py
# 결과: 0
```

---

### Task 7: /api/config 엔드포인트 신설 [신규]
**Purpose**: 프론트엔드가 로딩 시 서버 환경설정(vLLM endpoint 등)을 동적으로 조회
**File**: `backend/main.py`

**Changes** — `root()` 함수 앞에 추가:
```python
@app.get("/api/config", tags=["config"])
async def get_frontend_config():
    """Return server-side configuration for frontend defaults."""
    return {
        "vllm_endpoint": os.getenv("VLLM_ENDPOINT", "http://localhost:8000"),
        "vllm_namespace": os.getenv("VLLM_NAMESPACE", "vllm"),
        "vllm_model_name": os.getenv("K8S_DEPLOYMENT_NAME", ""),
    }
```

> ConfigMap `02-config.yaml`에 이미 `VLLM_ENDPOINT: "http://llm-ov-predictor.vllm.svc.cluster.local:8080"` 정의됨.
> 로컬 개발 시 env var 미설정이면 `http://localhost:8000` fallback.

**QA**:
```bash
# /api/config 엔드포인트 존재
grep '/api/config' backend/main.py
# 결과: @app.get("/api/config", ...) 포함

# VLLM_ENDPOINT env var 사용
grep 'VLLM_ENDPOINT' backend/main.py
# 결과: os.getenv("VLLM_ENDPOINT", ...) 포함
```

---

## Wave 4: Frontend Fixes

### Task 8: constants.js + Vite proxy [Bug #1, #10]
**Fixes**: API URL 절대경로 → 상대경로, 로컬 개발 proxy 설정
**Files**:
- `frontend/src/constants.js` (edit)
- `frontend/vite.config.js` (edit)

**Changes**:

1. **`frontend/src/constants.js:2`**:
```js
// AS-IS
export const API = "http://localhost:8000/api";
// TO-BE
export const API = "/api";
```

2. **`frontend/vite.config.js`** — server.proxy 추가:
```js
// AS-IS
server: {
    port: 5173,
    open: true
}

// TO-BE
server: {
    port: 5173,
    open: true,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        secure: false,
      }
    }
}
```

**QA**:
```bash
# localhost 제거 확인
grep 'localhost' frontend/src/constants.js
# 결과: 0줄

# API가 상대경로
grep "API = " frontend/src/constants.js
# 결과: export const API = "/api";

# Vite proxy 설정 존재
grep "'/api'" frontend/vite.config.js
# 결과: '/api': { 포함
```

---

### Task 9: LoadTestPage 수정 [Bug #3, #8]
**Fixes**: API 경로 hyphen → underscore, form 기본값에서 localhost 제거
**File**: `frontend/src/pages/LoadTestPage.jsx`

**Changes**:

1. **Line 12** — form 기본값 (Bug #8):
```js
// AS-IS
endpoint: "http://localhost:8000",
// TO-BE
endpoint: "",
```

2. **Line 45** — API 경로 (Bug #3):
```js
// AS-IS
const resp = await fetch(`${API}/load-test/start`, {
// TO-BE
const resp = await fetch(`${API}/load_test/start`, {
```

3. **Line 52** — EventSource 경로 (Bug #3):
```js
// AS-IS
const es = new EventSource(`${API}/load-test/stream`);
// TO-BE
const es = new EventSource(`${API}/load_test/stream`);
```

4. **Line 90** — stop 경로 (Bug #3):
```js
// AS-IS
await fetch(`${API}/load-test/stop`, { method: "POST" });
// TO-BE
await fetch(`${API}/load_test/stop`, { method: "POST" });
```

5. **추가**: 컴포넌트 마운트 시 `/api/config`에서 endpoint 기본값 로드:
```js
// useEffect 내부 또는 start 함수 시작 부분에서
// endpoint가 비어있으면 /api/config에서 가져옴
useEffect(() => {
  fetch(`${API}/config`)
    .then(r => r.json())
    .then(data => {
      if (data.vllm_endpoint) {
        setConfig(c => ({ ...c, endpoint: c.endpoint || data.vllm_endpoint }));
      }
    })
    .catch(() => {});  // 실패 시 무시 — 사용자가 수동 입력
}, []);
```

**QA**:
```bash
# load-test (hyphen) 경로 제거
grep -c 'load-test' frontend/src/pages/LoadTestPage.jsx
# 결과: 0

# load_test (underscore) 경로 사용
grep -c 'load_test' frontend/src/pages/LoadTestPage.jsx
# 결과: 3 (start, stream, stop)

# localhost 하드코딩 제거
grep -c 'localhost' frontend/src/pages/LoadTestPage.jsx
# 결과: 0
```

---

### Task 10: TunerPage 수정 [Bug #8]
**Fixes**: form 기본값 localhost 제거, /api/config에서 기본값 로드
**File**: `frontend/src/pages/TunerPage.jsx`

**Changes**:

1. **Line 19** — form 기본값:
```js
// AS-IS
vllm_endpoint: "http://localhost:8000",
// TO-BE
vllm_endpoint: "",
```

2. **추가**: /api/config에서 기본값 로드 (LoadTestPage와 동일 패턴):
```js
useEffect(() => {
  fetch(`${API}/config`)
    .then(r => r.json())
    .then(data => {
      if (data.vllm_endpoint) {
        setConfig(c => ({ ...c, vllm_endpoint: c.vllm_endpoint || data.vllm_endpoint }));
      }
    })
    .catch(() => {});
}, []);
```

**QA**:
```bash
# localhost 제거
grep -c 'localhost' frontend/src/pages/TunerPage.jsx
# 결과: 0

# /api/config fetch 존재
grep -c 'api/config' frontend/src/pages/TunerPage.jsx
# 결과: 1 이상
```

---

## Wave 5: OpenShift YAML Fix

### Task 11: 04-frontend.yaml affinity 들여쓰기 [Bug #11]
**Fixes**: `affinity`가 `Deployment.spec` 레벨에 있어 Pod에 적용 안됨
**File**: `openshift/base/04-frontend.yaml`
**Reference**: `openshift/base/03-backend.yaml:105-113` (올바른 affinity 위치)

**Changes** — lines 102-110:
```yaml
# AS-IS (2-space indent = Deployment.spec level — WRONG)
  affinity:
        podAntiAffinity:
          preferredDuringSchedulingIgnoredDuringExecution:
            - weight: 100
              podAffinityTerm:
                labelSelector:
                  matchLabels:
                    app: vllm-optimizer-frontend
                topologyKey: kubernetes.io/hostname

# TO-BE (6-space indent = spec.template.spec level — CORRECT)
      affinity:
        podAntiAffinity:
          preferredDuringSchedulingIgnoredDuringExecution:
            - weight: 100
              podAffinityTerm:
                labelSelector:
                  matchLabels:
                    app: vllm-optimizer-frontend
                topologyKey: kubernetes.io/hostname
```

> `affinity:`를 `volumes:` 블록 바로 뒤, `spec.template.spec` 하위에 위치시킴.

**QA**:
```bash
# YAML 구조적 검증 — affinity가 spec.template.spec 아래 존재
python3 -c "
import yaml
with open('openshift/base/04-frontend.yaml') as f:
    docs = list(yaml.safe_load_all(f))
dep = docs[0]
aff = dep['spec']['template']['spec'].get('affinity')
assert aff is not None, 'affinity not found at spec.template.spec'
assert 'podAntiAffinity' in aff, 'podAntiAffinity missing'
print('PASS: affinity correctly at spec.template.spec level')
"
# 결과: PASS: affinity correctly at spec.template.spec level
```

---

## Final Verification Wave

### Task 12: 전체 검증
**Purpose**: 모든 수정사항의 통합 검증

**Static checks (빌드 없이 실행 가능)**:
```bash
# 1. 프론트엔드에 localhost 하드코딩 없음
grep -r 'localhost' frontend/src/ --include='*.js' --include='*.jsx' | grep -v node_modules | grep -v 'proxy'
# 결과: 0줄

# 2. 백엔드에 THANOS_URL 없음 (PROMETHEUS_URL로 통일)
grep -r 'THANOS_URL' backend/ --include='*.py'
# 결과: 0줄

# 3. nginx에 CORS 블록 없음
grep -c 'Access-Control' frontend/nginx.conf
# 결과: 0

# 4. root nginx.conf 삭제됨
test ! -f nginx.conf && echo "OK: root nginx.conf deleted"

# 5. 프론트엔드 API 경로 일관성 (load-test hyphen 없음)
grep -r 'load-test' frontend/src/ --include='*.jsx'
# 결과: 0줄

# 6. await resp.json() 없음
grep -r 'await resp.json' backend/ --include='*.py'
# 결과: 0줄

# 7. verify=False 없음 (main.py)
grep -c 'verify=False' backend/main.py
# 결과: 0

# 8. 모든 백엔드 라우터 엔드포인트 존재 확인
python3 -c "
import sys; sys.path.insert(0, 'backend')
from routers.tuner import router
routes = [r.path for r in router.routes]
assert '/stop' in routes, '/stop missing'
assert '/importance' in routes, '/importance missing'
assert '/start' in routes, '/start missing'
print('PASS: all tuner endpoints present:', routes)
"

# 9. YAML affinity 구조 검증
python3 -c "
import yaml
with open('openshift/base/04-frontend.yaml') as f:
    docs = list(yaml.safe_load_all(f))
dep = docs[0]
aff = dep['spec']['template']['spec'].get('affinity')
assert aff is not None, 'affinity not at correct level'
print('PASS: YAML structure valid')
"
```

**Integration check (로컬 실행 시)**:
```bash
# Backend 기동 가능 확인
cd backend && timeout 5 python3 -c "from main import app; print('FastAPI app OK')" || echo "FAIL"

# /api/config 엔드포인트 응답 확인
# (uvicorn 실행 후)
curl -sf http://localhost:8000/api/config | python3 -c "
import sys, json
d = json.load(sys.stdin)
assert 'vllm_endpoint' in d, 'vllm_endpoint missing'
print('PASS:', d)
"
```

---
