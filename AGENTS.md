# AGENTS.md — vLLM Optimizer (OpenShift Deployment)

Guide for AI coding agents working on this project. Refer to `~/.config/opencode/AGENTS.md` first.

---

## Project Overview

**vLLM Optimizer** — Load testing, real-time monitoring, benchmark comparison, and automatic parameter tuning for vLLM services on OpenShift 4.x.

- **Backend**: FastAPI (Python), port `8000`
- **Frontend**: React + nginx, port `8080`
- **Deployment**: `deploy.sh` (Buildah → Quay.io → Kustomize)
- **Monitoring**: OpenShift Monitoring Stack (Thanos Querier)
- **Storage**: SQLite + PVC (no external DB)

**Design Principles**: Compact 2-Pod architecture. Maximize OpenShift infrastructure reuse. Do not split features into microservices. Closed-loop: Measure → Analyze → Optimize → Apply → Re-measure.

**Dual CR Architecture**: The project supports both KServe InferenceService and LLMInferenceService (LLMIS) through an adapter pattern in `backend/services/cr_adapter.py`. All components (auto_tuner, vllm_config, metrics collector, etc.) must work with both CR types.

---

## Directory Structure

```
vllm-optimizer/
├── deploy.sh                    # OpenShift deployment (build + push + deploy)
├── baseline.dev.json            # Performance test baseline
├── pyproject.toml               # pytest config (markers, asyncio)
├── scripts/                     # Test/baseline helper scripts
│
├── backend/
│   ├── Dockerfile               # UBI9 Python, non-root
│   ├── main.py                  # FastAPI entrypoint
│   ├── requirements.txt
│   ├── routers/
│   │   ├── load_test.py         # Load test API + SSE stream
│   │   ├── metrics.py           # Thanos Querier queries
│   │   ├── benchmark.py         # Benchmark save/compare
│   │   ├── tuner.py             # Bayesian Optimization API
│   │   ├── sla.py               # SLA CRUD + judgment
│   │   └── vllm_config.py       # IS args + resources GET/PATCH
│   ├── services/
│   │   ├── shared.py            # Singleton (metrics_collector, load_engine)
│   │   ├── load_engine.py       # Async load generation
│   │   ├── metrics_collector.py # Prometheus + K8s API collector
│   │   ├── auto_tuner.py        # Facade (K8sOperator + EventBroadcaster + TunerLogic)
│   │   ├── k8s_operator.py      # IS patch, readiness wait, rollback
│   │   ├── event_broadcaster.py # SSE broadcast + Prometheus metrics
│   │   └── tuner_logic.py       # Optuna study, parameter search
│   ├── models/                  # Pydantic request/response models
│   ├── metrics/prometheus_metrics.py
│   └── tests/                   # Unit + integration/performance/
│
├── frontend/
│   ├── Dockerfile               # UBI9 nginx-124, port 8080, non-root
│   ├── nginx.conf               # SPA routing, /api/* proxy
│   ├── vite.config.js
│   └── src/
│       ├── App.jsx              # 5-tab Dashboard
│       ├── contexts/ClusterConfigContext.tsx  # Global IS endpoint/namespace state
│       ├── pages/               # MonitorPage, LoadTestPage, BenchmarkPage, TunerPage, SlaPage
│       └── components/          # Chart, MetricCard, ClusterConfigBar, TunerConfigForm
│
└── openshift/
    ├── base/                    # Namespace, RBAC, ConfigMap, Deployments, Monitoring
    ├── vllm-dependency/         # vLLM Kustomize overlay (base, dev, prod) + llmis-rbac
    └── overlays/{dev,prod}/     # Environment-specific Kustomize
```

---

## Environment Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `VLLM_NAMESPACE` | LLM inference namespace (Pod lookup, MetricsCollector, auto-tuner) | `vllm-lab-dev` |
| `VLLM_CR_TYPE` | CR type: `inferenceservice` (KServe) or `llminferenceservice` (LLMIS) | `inferenceservice` |
| `PROMETHEUS_URL` | Thanos Querier URL | `https://thanos-querier.openshift-monitoring.svc:9091` |
| `K8S_DEPLOYMENT_NAME` | LLM Deployment name (KServe: `{name}-predictor`) | `llm-ov-predictor` |
| `VLLM_DEPLOYMENT_NAME` | InferenceService name (not Deployment!) | `llm-ov` |
| `VLLM_ENDPOINT` | LLM inference endpoint | `http://llm-ov-predictor.vllm-lab-dev.svc:8080` |
| `VLLM_MODEL` | Model name | `OpenVINO/Phi-4-mini-instruct-int4-ov` |
| `LOAD_ENGINE_TIMEOUT` | Load test timeout (default: 120s) | `120` |
| `STORAGE_PATH` | SQLite database file path | `/data/app.db` |

---

## Build & Deployment

```bash
# Local build (Podman)
podman build -t vllm-optimizer-backend:dev ./backend
podman build -t vllm-optimizer-frontend:dev ./frontend

# OpenShift deployment
./deploy.sh dev              # Build + push + deploy
./deploy.sh dev --dry-run    # Preview changes
./deploy.sh dev --skip-build # Deploy only

# Kustomize (validate with oc, not local binary)
oc apply -k openshift/overlays/dev --dry-run=client
oc kustomize openshift/overlays/dev
```

---

## Development Commands

```bash
# Backend
cd backend && uvicorn main:app --reload --port 8000
cd backend && python3 -m pytest tests/ -x -q -m "not integration"
cd backend && python3 -m ruff check . --fix && python3 -m ruff format .

# Frontend
cd frontend && npm run dev        # Port 5173, /api → localhost:8000 proxy
cd frontend && npm run build
cd frontend && npm run test
```

**Test markers**: `integration` (requires cluster), `performance`, `slow` (>30s). Excluded by default.

---

## Linting & Code Style

- **Python**: Ruff (E, F, I, UP, B, SIM), line length 120. `ruff format`.
- **TypeScript**: ESLint + Prettier, strict mode.
- **Pre-commit**: ruff format/check, trailing-whitespace, end-of-file-fixer, check-yaml.

---

## Code Writing Guidelines

### Backend (FastAPI)
- **Async First**: `async/await` for all I/O.
- **Singleton**: Always `from services.shared import metrics_collector`. Never instantiate directly.
- **Imports**: Bare imports without `backend.` prefix (`from services.xxx`).
- **K8s API in async**: Wrap sync client with `asyncio.to_thread()`.
- **Thanos TLS**: `httpx.AsyncClient(verify=False)` required (self-signed certs).
- **auto_tuner**: Prohibit `model="auto"`. Use `/v1/models` dynamic resolution.
- **Dual CR Support**: 
  - Always use `CRAdapter` abstraction (`from services.cr_adapter import get_cr_adapter`)
  - Never access CR-specific fields directly (e.g., `spec.predictor.model.args`)
  - Use adapter methods: `read_args()`, `build_args_patch()`, `read_resources()`, etc.
  - For model name: use `resolve_model_name(spec, fallback_name)`
  - Unit tests must validate both CR types

```python
# Thanos query example
async with httpx.AsyncClient(verify=False) as client:
    resp = await client.get(f"{THANOS_URL}/api/v1/query",
        headers={"Authorization": f"Bearer {token}"}, params={"query": query})
```

### Frontend (React)
- `/api/*` proxied by nginx. Use absolute paths.
- SSE: `EventSource` API.
- Global config: `useClusterConfig()` from `ClusterConfigContext`.
- Resource edit key: `resources.{tier}.{key}` (e.g., `resources.limits.cpu`).

### OpenShift YAML
- Use OpenShift `apiVersion` (`route.openshift.io/v1`, etc.).
- All Deployments: `resources.requests/limits`, `livenessProbe`/`readinessProbe`.
- Security: `runAsNonRoot: true`, `allowPrivilegeEscalation: false`, `capabilities.drop: ["ALL"]`.

---

## Dual CR Compatibility

Both `InferenceService` (KServe) and `LLMInferenceService` (LLMIS) must be equally supported via `CRAdapter` adapter pattern (`backend/services/cr_adapter.py`).

| | InferenceService (KServe) | LLMInferenceService (LLMIS) |
|---|---|---|
| **Namespace** | `vllm-lab-dev` / `vllm-lab-prod` | `llm-d-demo` (managed by llm-d, direct creation prohibited) |
| **Deployment** | `{name}-predictor` | `{name}-kserve` |
| **Pod label** | `app=isvc.{name}-predictor` | `app.kubernetes.io/name={name}` |
| **Endpoint** | `http://{name}-predictor.{ns}.svc:8080` | `http://openshift-ai-inference-openshift-default.openshift-ingress.svc/{ns}/{name}` |
| **Model name** | `--served-model-name` from args | `.spec.model.name` |

- Default: KServe. Switch with `VLLM_CR_TYPE=llminferenceservice`.
- New features must implement both adapters. Unit tests must validate both CR types.

---

## Integration Tests

8 tests run on real OpenShift cluster. Run from backend Pod:

```bash
NS=vllm-optimizer-dev
BACKEND_POD=$(oc get pod -n $NS -l app=vllm-optimizer-backend -o name | head -1)
oc exec -n $NS $BACKEND_POD -- env \
  PERF_TEST_BACKEND_URL=http://localhost:8000 \
  VLLM_ENDPOINT=http://llm-ov-predictor.vllm-lab-dev.svc:8080 \
  VLLM_MODEL=OpenVINO/Phi-4-mini-instruct-int4-ov VLLM_NAMESPACE=vllm-lab-dev \
  OPTIMIZER_NAMESPACE=vllm-optimizer-dev \
  python3 -m pytest /app/tests/integration/performance/ -v --tb=short -m "integration"
```

---

## E2E Validation Rules

When modifying auto_tuner, load tests, RBAC, or ConfigMap:
1. Deploy with `./deploy.sh dev`.
2. Verify on actual cluster with `oc` commands.
3. Verify Pod replacement after tuning (`oc get pods -n vllm-lab-dev`).
4. Agent must verify directly — do not ask user for results.

**Dual CR Validation**: For changes affecting CR-specific behavior, validate both `InferenceService` and `LLMInferenceService` by:
- Setting `VLLM_CR_TYPE=inferenceservice` for KServe validation
- Setting `VLLM_CR_TYPE=llminferenceservice` for LLMIS validation
- Checking CR-specific endpoint patterns and deployment names

```bash
NS=vllm-optimizer-dev
./deploy.sh dev
oc get pods -n $NS
oc logs -l app=vllm-optimizer-backend -n $NS --tail=50 | grep -i "403\|forbidden"
# Verify vLLM Pod restart (KServe)
oc get pods -n vllm-lab-dev -l app=isvc.llm-ov-predictor
# For LLMIS validation (if applicable):
# oc get pods -n llm-d-demo -l app.kubernetes.io/name=small-llm-d
```

---

## Test Execution Policy

- ALWAYS run tests in single-run mode (e.g., `vitest run`).
- DO NOT spawn multiple test processes in parallel unless explicitly instructed.

## Process Management

- Any process started by the agent MUST be terminated after task completion.
- NEVER leave background processes running.
- If a process is started, the agent MUST:
  1. Track its PID
  2. Ensure it is killed before finishing the task
- Use non-interactive commands only.

---

## Troubleshooting Quick Reference

| Issue | Resolution |
|-------|-----------|
| **SCC error** | Uses default `restricted-v2`. Check: `oc describe pod -l app=vllm-optimizer-backend -n $NS \| grep -i scc` |
| **Image pull fail** | `oc import-image vllm-optimizer-backend:latest --from=quay.io/joopark/vllm-optimizer-backend:latest --confirm -n vllm-optimizer-dev` |
| **Thanos inaccessible** | Check `cluster-monitoring-view` ClusterRoleBinding. Reapply `05-monitoring.yaml`. |
| **MetricsCollector all-zero** | `collector_version=unknown` → Thanos connection failed. `pods=0` → `K8S_DEPLOYMENT_NAME` mismatch. |
| **auto_tuner skips tests** | vLLM overloaded → `skip_if_overloaded` waits 120s. Check vLLM pod status. |
| **auto_tuner Pod not restarting** | Verify `K8S_DEPLOYMENT_NAME` matches actual Deployment (not IS name). Manual: `oc rollout restart deployment/{name} -n {ns}` |
| **SLA 422 error** | At least one threshold required. `SlaThresholds` model_validator enforces this. |
| **CR type mismatch** | Verify `VLLM_CR_TYPE` matches actual deployment (`inferenceservice` or `llminferenceservice`). Check adapter methods. |
| **Endpoint 404** | Check CR-specific endpoint patterns: KServe uses `{name}-predictor.{ns}.svc:8080`, LLMIS uses ingress gateway. |
| **Model name resolution failure** | Check `resolve_model_name()` implementation for both CR types. Ensure `/v1/models` API is accessible. |
| **Resource patch not applying** | Verify resources are under correct path: `spec.predictor.model.resources` (KServe) or `spec.template.containers[0].resources` (LLMIS). |

### IS Architecture Notes
- **args PATCH**: `vllm_config` = dict-merge (safe partial). `auto_tuner._apply_params` = full replacement (do not modify).
- **resources**: `ALLOWED_RESOURCE_KEYS = {"cpu", "memory", "nvidia.com/gpu"}`. GPU only in `limits`. Empty string removes key.

---

## Playwright — Token Saving Rules

Minimize `browser_snapshot` calls — they consume excessive tokens.

- **Prohibited**: Snapshot immediately after click/type/navigation.
- **Use instead**: `playwright_browser_evaluate` for state verification, `playwright_browser_console_messages` for errors.
- **Allowed**: One snapshot on initial load, explicit snapshots for debugging.
