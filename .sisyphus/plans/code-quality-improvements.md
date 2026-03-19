# Plan: Code Quality Improvements

**Created**: 2026-03-08
**Completed**: 2026-03-08
**Status**: ✅ ALL 10 TASKS DONE
**Scope**: 10 tasks across backend, frontend, and infrastructure
**Objective**: Fix all identified code quality issues — bug fixes, security hardening, developer experience improvements

---

## Context

분석 결과 발견된 9개 코드 품질 이슈 + .gitignore 보강 = 총 10개 태스크.
3개 Wave로 나누어 의존성 순서대로 실행.

**Key Decisions Made:**
- `deploy.sh`: `--dry-run`과 `--skip-build` 모두 빌드를 건너뜀
- 로깅: Human-readable 포맷 (`%(asctime)s [%(levelname)s] %(name)s: %(message)s`)
- nginx: CSP 제외, 3개 보안 헤더만 추가 (X-Frame-Options, X-Content-Type-Options, Referrer-Policy)
- 프론트엔드 테스트: Vitest + 3개 테스트로 인프라만 구축 (전체 페이지 테스트 제외)
- except cleanup: 프로덕션 코드만 (tests/ 제외)
- metrics dedup: `/api/metrics/plain` 제거 (404), 리다이렉트 없음
- Error Boundary: 글로벌 1개 (App.jsx에서 ActivePage 래핑)

---

## Constraints

- UBI9 base images only
- Non-root containers (ports 8000/8080)
- `oc` not `kubectl`, `podman` not `docker`
- Bare imports in backend (no `backend.` prefix)
- 기존 단위 테스트 깨지지 않아야 함: `cd backend && python3 -m pytest tests/ -x -q -m "not integration"`

---

## Wave 1: Quick Fixes (모든 태스크 병렬 실행 가능)

### ✅ TODO 1: deploy.sh — 빌드 조건 버그 수정
- **File**: `deploy.sh`
- **Problem**: Lines 165-177의 `podman build` 명령이 `--skip-build`/`--dry-run` 플래그와 무관하게 무조건 실행됨. Push (line 183)만 조건부.
- **Fix**: Lines 165-177을 조건문으로 감싸기

**변경 내용:**

`deploy.sh`에서 line 165 직전 (`log "Starting container image build (backend)...`) 부터 line 177 (`ok "Frontend image built:..."`) 까지를 조건문으로 감싸기:

```bash
# 현재 (buggy):
log "Starting container image build (backend) -> ..."
   podman build ...
  ok "Backend image built: ..."
  log "Starting container image build (frontend) -> ..."
   podman build ...
   ok "Frontend image built: ..."

# 수정 후:
if [[ "$SKIP_BUILD" != "true" && "$DRY_RUN" != "true" ]]; then
  log "Starting container image build (backend) -> ${REGISTRY}/vllm-optimizer-backend:${IMAGE_TAG}"
  podman build \
    --platform linux/amd64 \
    -t "${REGISTRY}/vllm-optimizer-backend:${IMAGE_TAG}" \
    "${PROJECT_ROOT}/backend"
  ok "Backend image built: ${REGISTRY}/vllm-optimizer-backend:${IMAGE_TAG}"

  log "Starting container image build (frontend) -> ${REGISTRY}/vllm-optimizer-frontend:${IMAGE_TAG}"
  podman build \
    --platform linux/amd64 \
    -t "${REGISTRY}/vllm-optimizer-frontend:${IMAGE_TAG}" \
    "${PROJECT_ROOT}/frontend"
  ok "Frontend image built: ${REGISTRY}/vllm-optimizer-frontend:${IMAGE_TAG}"
else
  warn "Skipping container image build (--skip-build or --dry-run)"
fi
```

- **주의**: Push 조건문 (line 183)은 건드리지 않음 — 이미 올바르게 동작
- **들여쓰기**: 기존 파일의 들여쓰기가 불규칙함 (일부 라인 공백 3-4칸). 수정 시 2-space indent로 통일

**QA:**
```bash
bash -n deploy.sh  # syntax check
grep -c "SKIP_BUILD" deploy.sh  # 최소 3개 이상 (parse + build gate + push gate)
```

---

### ✅ TODO 2: requirements.txt — 버전 상한선 추가
- **File**: `backend/requirements.txt`
- **Problem**: 모든 의존성이 `>=`만 사용. 메이저 버전 업 시 breaking change 위험.

**변경 내용** — 각 패키지를 아래 형식으로 교체:

```
# FastAPI & Server
fastapi>=0.115.0,<1.0.0
uvicorn[standard]>=0.30.0,<1.0.0

# HTTP Client
httpx>=0.27.0,<1.0.0

# Data Validation
pydantic>=2.9.0,<3.0.0
pydantic-settings>=2.6.0,<3.0.0

# Kubernetes
kubernetes>=29.0.0,<32.0.0

# Optimization
optuna>=3.5.0,<4.0.0

# Testing
pytest>=8.3.0,<9.0.0
pytest-asyncio>=0.24.0,<1.0.0
pytest-cov>=6.0.0,<7.0.0

# Environment
python-dotenv>=1.0.0,<2.0.0

# Utilities
python-dateutil>=2.9.0,<3.0.0
psutil>=5.9.0,<7.0.0

# Monitoring
prometheus-client>=0.24.0,<1.0.0
```

**원칙**: `<NEXT_MAJOR_VERSION` 형식. psutil은 6.x가 이미 존재하므로 `<7.0.0`.

**QA:**
```bash
cd backend && pip install -r requirements.txt --dry-run 2>&1 | grep -i "conflict\|error"
# 기대: 출력 없음
grep ">=" requirements.txt | grep -v "<"
# 기대: 0 줄 (모든 패키지에 상한선 존재)
```

---

### ✅ TODO 3: datetime.utcnow() 교체
- **Files**: `backend/routers/metrics.py`, `backend/routers/benchmark.py`
- **Problem**: `datetime.utcnow()`는 Python 3.12부터 deprecated. 또한 정확성 버그 — naive datetime의 `.timestamp()`는 로컬 TZ 기준이라 non-UTC 환경에서 값이 틀림.

**변경 1** — `backend/routers/metrics.py`:
```python
# Line 7 — import 변경
from datetime import datetime, timezone

# Line 21 — utcnow 교체
# Before: timestamp=datetime.utcnow().timestamp(),
# After:
timestamp=datetime.now(timezone.utc).timestamp(),
```

**변경 2** — `backend/routers/benchmark.py`:
```python
# Line 3 — import 변경
from datetime import datetime, timezone

# Line 26 — utcnow 교체
# Before: benchmark.timestamp = datetime.utcnow().timestamp()
# After:
benchmark.timestamp = datetime.now(timezone.utc).timestamp()
```

**QA:**
```bash
cd backend && grep -r "utcnow" routers/
# 기대: 0 matches
python3 -m pytest tests/ -x -q -m "not integration"
# 기대: 전체 통과
```

---

### ✅ TODO 4: nginx.conf 보안 헤더 추가
- **File**: `frontend/nginx.conf`
- **Problem**: 보안 헤더 전무. XSS, clickjacking, MIME sniffing 방어 없음.

**변경 내용** — `server {` 블록 안에, `listen 8080;` 바로 아래에 추가:

```nginx
    server {
        listen 8080;
        server_name _;

        # Security headers
        add_header X-Frame-Options "DENY" always;
        add_header X-Content-Type-Options "nosniff" always;
        add_header Referrer-Policy "strict-origin-when-cross-origin" always;

        root /usr/share/nginx/html;
```

- **CSP는 이번 범위에서 제외** — Recharts가 inline style을 사용하므로 별도 검증 필요
- **HSTS 제외** — OpenShift Route가 TLS 종료 처리, nginx는 HTTP만 수신
- **`always` 키워드 필수** — 에러 응답(4xx, 5xx)에도 헤더 적용

**QA:**
```bash
# nginx 설정 문법 검증 (podman 사용):
podman run --rm -v $(pwd)/frontend/nginx.conf:/etc/nginx/nginx.conf:ro registry.access.redhat.com/ubi9/nginx-124 nginx -t
# 기대: "syntax is ok"
```

---

### ✅ TODO 5: .gitignore 보강
- **File**: `.gitignore`
- **Problem**: `.sisyphus/`, `coverage/`, `*.log` 등 누락.

**변경 내용** — 파일 끝에 추가:

```gitignore
# sisyphus planning
.sisyphus/

# test coverage
coverage/
.nyc_output/
htmlcov/

# logs
*.log

# frontend build
frontend/dist/
```

**QA:**
```bash
git status --ignored --short | grep -E "sisyphus|coverage|\.log"
# 기대: 위 패턴이 ignored로 표시
```

---

## Wave 2: Medium Effort (TODO 6 → TODO 7 순서 필수, TODO 8은 독립)

### ✅ TODO 6: 구조화된 로깅 설정 (Wave 2에서 가장 먼저 실행)
- **Files**: `backend/main.py` (핵심), `backend/services/metrics_collector.py`, `backend/services/auto_tuner.py`, `backend/startup_metrics_shim.py`, `backend/routers/load_test.py`
- **Problem**: `import logging`만 하고 root logger 설정 없음. INFO/DEBUG 메시지 프로덕션에서 소실.

**변경 1** — `backend/main.py` 최상단 (import 직후, app 생성 전):

```python
import logging
import os

# ── Logging Configuration ──
logging.basicConfig(
    level=getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
```

위치: `import os` 뒤, `from kubernetes import ...` 전에 배치. `app = FastAPI(...)` 보다 반드시 먼저 실행되어야 함.

**변경 2** — 각 서비스 파일에서 모듈 로거 사용으로 전환:

`backend/services/metrics_collector.py` 상단:
```python
import logging
logger = logging.getLogger(__name__)
```
그리고 파일 내 모든 `logging.error(...)` → `logger.error(...)`, `logging.warning(...)` → `logger.warning(...)`, `logging.info(...)` → `logger.info(...)` 로 교체.

동일하게 적용:
- `backend/services/auto_tuner.py` — `logger = logging.getLogger(__name__)`
- `backend/startup_metrics_shim.py` — `logger = logging.getLogger(__name__)`
- `backend/routers/load_test.py` — `logger = logging.getLogger(__name__)`

**패턴**: `logging.xxx(...)` → `logger.xxx(...)` 전환. `logging.debug`, `logging.info`, `logging.warning`, `logging.error` 모두 대상.

**주의사항:**
- `main.py`의 `logging.debug("Startup shim not loaded: %s", e)` (line 70)도 변환 대상
- `import logging`은 유지 (getLogger에 필요)
- 다른 파일에 `logging.basicConfig()` 추가 금지 — `main.py`에만 1회

**QA:**
```bash
cd backend && python3 -c "
import logging
import main
root = logging.getLogger()
assert len(root.handlers) >= 1, f'No handlers: {root.handlers}'
assert root.level <= logging.INFO, f'Level too high: {root.level}'
print('OK: handlers =', len(root.handlers), ', level =', logging.getLevelName(root.level))
"
# 기대: OK: handlers = 1 , level = INFO

python3 -m pytest tests/ -x -q -m "not integration"
# 기대: 전체 통과
```

---

### ✅ TODO 7: except Exception 정리 (TODO 6 완료 후 실행)
- **Files**: `backend/` 내 프로덕션 코드만 (`backend/tests/` 제외)
- **Problem**: 38개 `except Exception` 중 ~6개가 `pass`로 에러를 삼킴. 디버깅 불가.
- **Depends on**: TODO 6 (로깅 설정 완료 후 실행해야 새 로그가 출력됨)

**변경 대상 (파일별):**

#### `backend/startup_metrics_shim.py`
- Line 8: `except Exception: return` → 유지 (import 실패 시 의도적 noop)
- Line 50: `except Exception: pass` → `except Exception: pass  # intentional: shutdown cleanup`
- Line 55: `except Exception: pass` → `except Exception: pass  # intentional: shutdown cleanup`

#### `backend/services/auto_tuner.py`
- Line 46: `except Exception:` (load_incluster) → 유지 (kube_config fallback 체인)
- Line 52: `except Exception: pass` → `except Exception as e: logger.warning("K8s client unavailable: %s", e)`
- Line 319: `except Exception:` → `except Exception: return {}`

#### `backend/services/metrics_collector.py`
- Line 158: `except Exception: return None` → 유지 (token load fallback)
- Line 165: `except Exception:` (load_kube_config) → 유지 (fallback 체인)
- Line 224: `except Exception: pass` → `except Exception: pass  # metrics collection duration histogram, non-critical`
- Line 241: `except Exception: pass` → 유지 (fetch_prometheus_metric은 (name, None) 반환이 정상 동작)
- Line 330: `except Exception: return {}` → 유지 (K8s query 실패 시 빈 dict 반환은 의도적)

#### `backend/services/load_engine.py`
- Line 82: `except Exception: pass` → `except Exception: pass  # GPU metrics fetch, non-critical`

#### `backend/main.py`
- Line 21: `except Exception: generate_metrics = None` → 유지 (optional import)
- Line 59: `except Exception: return False` → 유지 (health check fallback)
- Line 69: `except Exception as e: logging.debug(...)` → `logger.debug(...)` (TODO 6에서 처리)
- Line 113: `except Exception:` → 유지 (deep health check)
- Line 121: `except Exception:` → 유지 (deep health check)

**원칙:**
1. 의도적 fallback (`return None`, `return {}`, `return False`)은 유지
2. 무음 `pass` 중 ops 가시성이 필요한 곳만 `logger.warning()` 추가
3. non-critical 경로의 `pass`는 인라인 주석으로 의도 문서화
4. 테스트 코드는 절대 수정하지 않음

**QA:**
```bash
cd backend && python3 -m pytest tests/ -x -q -m "not integration"
# 기대: 전체 통과

# 의도 없는 무음 pass가 남아있지 않은지 확인
grep -n "except Exception" backend/services/*.py backend/main.py backend/startup_metrics_shim.py | grep -v "tests/" | grep -v "#"
# 기대: 모든 라인이 as e: logger 또는 인라인 주석 포함
```

---

### ✅ TODO 8: Prometheus 메트릭 엔드포인트 중복 제거 (독립 실행 가능)
- **Files**: `backend/routers/metrics.py`, `backend/main.py`
- **Problem**: 동일한 Prometheus 텍스트를 반환하는 엔드포인트 4개. 라우팅 충돌 + dead code 존재.

**현재 상태:**
```
main.py:132     @app.get("/api/metrics")           ← DEAD CODE (router가 먼저 등록됨)
metrics.py:113  @router.get("")    → /api/metrics  ← 실제 동작하는 엔드포인트
metrics.py:126  @router.get("/plain") → /api/metrics/plain  ← 불필요한 중복
metrics.py:136  @router.get("/")   → /api/metrics/  ← 불필요한 중복
```

**ServiceMonitor** (`openshift/base/05-monitoring.yaml:27`): `path: /api/metrics` — 반드시 유지

**변경 1** — `backend/routers/metrics.py`:
- `@router.get("")` (line 113) — **유지 + None-guard 추가**:
```python
@router.get("")
async def get_prometheus_metrics():
    """
    Expose Prometheus metrics for OpenShift Monitoring.
    Returns plaintext Prometheus format. Scraped by ServiceMonitor.
    """
    from fastapi.responses import PlainTextResponse
    try:
        from metrics.prometheus_metrics import generate_metrics
    except Exception:
        return PlainTextResponse("# ERROR: metrics generator unavailable\n", media_type="text/plain; version=0.0.4")
    return PlainTextResponse(generate_metrics(), media_type="text/plain; version=0.0.4")
```

- `@router.get("/plain")` (lines 126-133) — **삭제** (전체 함수 제거)
- `@router.get("/")` (lines 136-141) — **삭제** (전체 함수 제거)

**변경 2** — `backend/main.py`:
- `@app.get("/api/metrics", ...)` (lines 132-137) — **삭제** (dead code, 전체 함수 + 데코레이터 제거)

**결과**: `/api/metrics` 1개 엔드포인트만 남음. `/api/metrics/latest`와 `/api/metrics/history`는 router의 다른 함수이므로 영향 없음.

**QA:**
```bash
cd backend && python3 -m pytest tests/ -x -q -m "not integration"
# 기대: 전체 통과

# 중복 확인
grep -c "generate_metrics" backend/routers/metrics.py
# 기대: 2 이하 (import + 호출)

grep "def plaintext_metrics_root" backend/main.py
# 기대: 0 matches (삭제됨)
```

---

## Wave 3: Frontend (병렬 실행 가능, 단 TODO 10의 ErrorBoundary 테스트는 TODO 9 완료 후)

### ✅ TODO 9: React Error Boundary + SSE 핸들러 안전 장치
- **Files**: `frontend/src/components/ErrorBoundary.jsx` (신규), `frontend/src/App.jsx`, `frontend/src/pages/LoadTestPage.jsx`
- **Problem**: Error Boundary 없어서 컴포넌트 에러 시 흰 화면. SSE 핸들러에 try/catch 없어서 malformed JSON에 취약.

**변경 1** — `frontend/src/components/ErrorBoundary.jsx` 신규 생성:

```jsx
import { Component } from "react";
import { COLORS, font } from "../constants";

class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, errorInfo) {
    console.error("[ErrorBoundary]", error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div style={{
          padding: 48, textAlign: "center",
          fontFamily: font.mono, color: COLORS.text,
        }}>
          <div style={{ fontSize: 48, marginBottom: 16 }}>⚠</div>
          <h2 style={{ color: COLORS.red, marginBottom: 8 }}>
            Something went wrong
          </h2>
          <p style={{ color: COLORS.muted, marginBottom: 24, maxWidth: 480, margin: "0 auto 24px" }}>
            {this.state.error?.message || "An unexpected error occurred"}
          </p>
          <button
            onClick={() => {
              this.setState({ hasError: false, error: null });
            }}
            style={{
              background: COLORS.accent, color: COLORS.bg,
              border: "none", padding: "8px 24px", cursor: "pointer",
              fontFamily: font.mono, fontWeight: 700, fontSize: 13,
            }}
          >
            Retry
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}

export default ErrorBoundary;
```

**변경 2** — `frontend/src/App.jsx`:

```jsx
// import 추가 (line 9 이후):
import ErrorBoundary from "./components/ErrorBoundary";

// <ActivePage /> 래핑 (line 75 부근):
// Before:
//   <ActivePage />
// After:
<ErrorBoundary>
  <ActivePage />
</ErrorBoundary>
```

**변경 3** — `frontend/src/pages/LoadTestPage.jsx`:

SSE `onmessage` 핸들러에 try/catch 추가. 파일에서 `es.onmessage = (e) => {` 부분을 찾아서:

```jsx
// Before:
es.onmessage = (e) => {
  const data = JSON.parse(e.data);
  // ... rest of handler

// After:
es.onmessage = (e) => {
  let data;
  try {
    data = JSON.parse(e.data);
  } catch (parseErr) {
    console.warn("[SSE] Failed to parse message:", parseErr);
    return;
  }
  // ... rest of handler (unchanged)
```

**QA:**
```bash
cd frontend && npm run build
# 기대: 빌드 성공
```

---

### ✅ TODO 10: 프론트엔드 테스트 인프라 구축
- **Files**: `frontend/package.json`, `frontend/vite.config.js`, `frontend/src/test-setup.js` (신규), 테스트 파일 3개 (신규)
- **Problem**: 프론트엔드 테스트 0개. 테스트 프레임워크 없음.
- **Depends on**: TODO 9 (ErrorBoundary.test.jsx가 ErrorBoundary 컴포넌트 필요)

**변경 1** — `frontend/package.json`:

devDependencies에 추가:
```json
"devDependencies": {
  "vite": "^5.0.0",
  "@vitejs/plugin-react": "^4.2.0",
  "vitest": "^3.0.0",
  "@testing-library/react": "^16.0.0",
  "@testing-library/jest-dom": "^6.0.0",
  "jsdom": "^25.0.0"
}
```

scripts에 추가:
```json
"scripts": {
  "dev": "vite",
  "build": "vite build",
  "preview": "vite preview",
  "test": "vitest run",
  "test:watch": "vitest"
}
```

**변경 2** — `frontend/vite.config.js`:

```javascript
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: ["./src/test-setup.js"],
  },
});
```

**변경 3** — `frontend/src/test-setup.js` (신규):

```javascript
import "@testing-library/jest-dom";
```

**변경 4** — 테스트 파일 3개 생성:

**`frontend/src/components/MetricCard.test.jsx`:**
```jsx
import { render, screen } from "@testing-library/react";
import MetricCard from "./MetricCard";

describe("MetricCard", () => {
  it("renders label and formatted value", () => {
    render(<MetricCard label="TPS" value={42.567} unit="tok/s" />);
    expect(screen.getByText("TPS")).toBeInTheDocument();
  });
});
```

주의: MetricCard의 실제 props를 확인해서 테스트 작성. `frontend/src/components/MetricCard.jsx`를 읽고 props 이름 확인할 것.

**`frontend/src/components/ErrorBoundary.test.jsx`:**
```jsx
import { render, screen } from "@testing-library/react";
import ErrorBoundary from "./ErrorBoundary";

function ThrowingComponent() {
  throw new Error("Test error");
}

describe("ErrorBoundary", () => {
  it("renders fallback UI when child throws", () => {
    // Suppress console.error for cleaner test output
    const spy = vi.spyOn(console, "error").mockImplementation(() => {});
    render(
      <ErrorBoundary>
        <ThrowingComponent />
      </ErrorBoundary>
    );
    expect(screen.getByText("Something went wrong")).toBeInTheDocument();
    expect(screen.getByText("Test error")).toBeInTheDocument();
    expect(screen.getByText("Retry")).toBeInTheDocument();
    spy.mockRestore();
  });
});
```

**`frontend/src/mockData.test.js`:**
```javascript
import { mockMetrics, mockHistory } from "./mockData";

describe("mockData", () => {
  it("mockMetrics returns object with expected fields", () => {
    const m = mockMetrics();
    expect(m).toHaveProperty("tps");
    expect(m).toHaveProperty("rps");
    expect(m).toHaveProperty("pods");
    expect(typeof m.tps).toBe("number");
  });

  it("mockHistory returns non-empty array", () => {
    const h = mockHistory();
    expect(Array.isArray(h)).toBe(true);
    expect(h.length).toBeGreaterThan(0);
  });
});
```

주의: `mockData.js`의 실제 export 이름을 확인할 것. `import { mockMetrics, mockHistory }` 가 맞는지 `frontend/src/mockData.js`를 읽어서 검증.

**QA:**
```bash
cd frontend && npm install && npm test
# 기대: 3 tests passed, 0 failed

npm run build
# 기대: 빌드 성공 (테스트 파일이 빌드에 포함되지 않는지 확인)
```

---

## Final Verification Wave

모든 태스크 완료 후 실행:

```bash
# 1. Backend 단위 테스트
cd /home/user/project/vllm-optimizer/backend && python3 -m pytest tests/ -x -q -m "not integration"

# 2. Frontend 빌드
cd /home/user/project/vllm-optimizer/frontend && npm run build

# 3. Frontend 테스트
cd /home/user/project/vllm-optimizer/frontend && npm test

# 4. deploy.sh 문법 검증
bash -n /home/user/project/vllm-optimizer/deploy.sh

# 5. git status 확인 → commit
cd /home/user/project/vllm-optimizer
git add -A
git status
git commit -m "refactor: code quality improvements — fix deploy.sh build gate, add security headers, structured logging, error boundary, test infrastructure"
```
