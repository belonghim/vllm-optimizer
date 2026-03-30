# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

vLLM Optimizer is a full-stack application for monitoring, load-testing, benchmarking, and auto-tuning vLLM inference deployments on OpenShift. It consists of a **FastAPI backend** (Python 3.11) and a **React + Vite frontend** (TypeScript), deployed via Kustomize on OpenShift 4.x.

## Commands

### Backend
```bash
# Run backend locally
cd backend && uvicorn main:app --reload --port 8000

# Unit tests (excludes integration/slow by default via pyproject.toml)
cd backend && python3 -m pytest tests/ -x -q

# Run a single test file or test
cd backend && python3 -m pytest tests/test_load_test.py -x -q
cd backend && python3 -m pytest tests/test_load_test.py::test_function_name -x -q

# Integration tests (requires OpenShift cluster access)
cd backend && python3 -m pytest tests/integration/performance/ -v --tb=short -m integration

# Lint and format
cd backend && python3 -m ruff check . --fix && python3 -m ruff format .
```

### Frontend
```bash
cd frontend
npm run dev          # Vite dev server (port 5173, proxies /api to localhost:8000)
npm run build        # Production build
npm run test         # Vitest unit tests
npm run test:e2e     # Playwright E2E tests
npm run lint         # ESLint
npm run format       # Prettier
npm run type-check   # TypeScript type checking
```

### Deployment
```bash
./deploy.sh dev              # Build + deploy to vllm-optimizer-dev
./deploy.sh prod             # Build + deploy to vllm-optimizer-prod
./deploy.sh dev --skip-build # Deploy only (no image build)
./deploy.sh dev --dry-run    # Preview what would be applied
```

## Architecture

### Backend (`backend/`)

**Entry point**: `main.py` — FastAPI app with lifespan management, CORS, rate limiting (slowapi).

**Routers** (all prefixed `/api`):
- `load_test` — Load test execution with SSE streaming, sweep mode
- `metrics` — Prometheus/Thanos metrics fetching
- `benchmark` — Benchmark CRUD, comparison, GuideLLM import
- `tuner` — Auto-tuner orchestration (Optuna-based Bayesian optimization)
- `vllm_config` — Read/patch InferenceService tuning args and resources
- `sla` — SLA profile CRUD and verdict evaluation
- `alerts` — Alert rule management
- `status` — Health checks
- `config` — Runtime configuration

**Services** (business logic):
- `shared.py` — Singletons: storage, load_engine, httpx clients, multi_target_collector
- `load_engine.py` — Async HTTP load generation with RPS/concurrency control
- `auto_tuner.py` + `tuner_logic.py` — Optuna study management, trial execution with load test + metrics scoring
- `k8s_operator.py` — K8s API: patch InferenceService, monitor rollout, rollback on failure
- `cr_adapter.py` — Abstraction over InferenceService vs LLMInferenceService (runtime-switchable via `VLLM_CR_TYPE`)
- `storage.py` — Async SQLite (aiosqlite) CRUD with WAL mode
- `model_resolver.py` — Dynamic model name detection via `/v1/models`

**Models**: Pydantic schemas in `models/load_test.py` and `models/sla.py`.

**Storage**: SQLite at `STORAGE_PATH` (default `/data/app.db`), PVC-mounted in OpenShift.

### Frontend (`frontend/src/`)

**5 tab pages** (lazy-loaded in `App.tsx`): Monitor, LoadTest, Benchmark, Tuner, SLA.

**State management**: React Context (no Redux) — `ClusterConfigContext` (IS endpoint/namespace/CR type), `BenchmarkSelectionContext`, `MockDataContext`, `ThemeContext`.

**API integration**: Fetch to `/api/...` (Vite proxies to backend in dev), SSE EventSource for load test streaming, polling for metrics/tuner status. MSW mock handlers for dev/test mode.

### Deployment (`openshift/`)

Kustomize base + overlays (dev/prod). UBI9 container images, non-root (UID 1001). Backend Dockerfile has a 2-stage build. Frontend uses Nginx with SPA routing and `/api/*` reverse proxy.

## Key Design Decisions

- **Dual CR support**: `VLLM_CR_TYPE` env var switches between `inferenceservice` (KServe, default) and `llminferenceservice` (LLMIS). The `CRAdapter` pattern abstracts endpoint resolution, model name extraction, and spec patching.
- **Async-first**: All backend I/O is async (httpx, aiosqlite, K8s via asyncio.to_thread).
- **OpenShift Monitoring Stack**: Queries go to Thanos Querier (in-cluster), not an external Prometheus.
- **No external DB**: SQLite keeps deployment simple — single PVC, no database operator.

## Environment Variables (Backend)

| Variable | Purpose | Default |
|---|---|---|
| `VLLM_ENDPOINT` | vLLM inference URL | required |
| `VLLM_MODEL` | Model name | required |
| `PROMETHEUS_URL` | Thanos Querier URL | internal SVC |
| `K8S_NAMESPACE` | vLLM workload namespace | `vllm-lab-dev` |
| `VLLM_DEPLOYMENT_NAME` | InferenceService name | `llm-ov` |
| `VLLM_CR_TYPE` | `inferenceservice` or `llminferenceservice` | `inferenceservice` |
| `STORAGE_PATH` | SQLite DB path | `/data/app.db` |
| `ALLOWED_ORIGINS` | CORS origins (comma-separated) | — |

## Linting & Code Style

- **Python**: Ruff with rules E, F, I, UP, B, SIM. Line length 120. Format with `ruff format`.
- **TypeScript**: ESLint + Prettier. Strict TypeScript (`tsconfig.json` strict mode).
- **Pre-commit**: ruff format + check, trailing-whitespace, end-of-file-fixer, check-yaml.

## Test Markers (pytest)

- `@pytest.mark.integration` — Requires OpenShift cluster
- `@pytest.mark.performance` — Performance measurement
- `@pytest.mark.slow` — Tests taking >30 seconds

Default `pytest` runs exclude integration and slow tests (configured in `pyproject.toml`).
