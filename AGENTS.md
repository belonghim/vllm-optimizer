# AGENTS.md — vLLM Optimizer (OpenShift Deployment)

This file serves as a guide for AI coding agents (opencode.ai) to understand and correctly work on this project.

---

## Global AGENTS.md Inheritance

Refer to ~/.config/opencode/AGENTS.md first.

---

## Project Overview

**vLLM Optimizer** is a container application that provides load testing, real-time monitoring, benchmark comparison, and automatic parameter tuning for vLLM services. It is designed to be fully compatible with OpenShift 4.x.

- **Backend**: FastAPI (Python), port `8000`
- **Frontend**: React + nginx, port `8080`
- **Deployment Platform**: OpenShift 4.x (Kubernetes-based)
- **CI/CD**: deploy.sh (Buildah build → Quay.io push → Kustomize deployment)
- **Monitoring**: OpenShift Monitoring Stack (Thanos Querier)

### Project Positioning and Differentiation

vLLM Optimizer **does not compete** with benchmark tools like Red Hat GuideLLM. Instead, it complements them.

| Aspect | GuideLLM (Benchmark) | vLLM Optimizer (Operational Optimization) |
|------|-------------------|--------------------------|
| Core Question | "How fast is this model?" | "How can we make this model faster?" |
| Usage Timing | Performance measurement before deployment | Continuous operational optimization after deployment |
| Execution Method | CLI / K8s Job (one-time) | Resident service (FastAPI + React) |
| Output | JSON/HTML Report (static) | Real-time dashboard + automatic tuning |

**Key Differentiator — Closed-Loop Optimization:**
- Measure (load test) → Analyze (benchmark comparison + SLA judgment) → Optimize (Optuna automatic tuning) → Apply (KServe IS patch) → Re-measure
- GuideLLM only handles "measurement." vLLM Optimizer **provides the entire loop within a single platform.**

**Advantages of Compact Architecture:**
- Backend (FastAPI) + Frontend (React) 2-Pod configuration maintains deployment simplicity
- Persistent data storage with **SQLite + PVC** without an external DB (minimizing operational complexity)
- Reuse of OpenShift Monitoring Stack — no separate Prometheus installation required
- Single `deploy.sh` enables full dev/prod deployment

**Design Principles to Adhere To:**
- Maintain a compact structure. Do not separate new features into separate microservices.
- Maximize the use of existing OpenShift infrastructure (Monitoring Stack, KServe, RBAC).
- Evolve in a direction that strengthens differentiation from benchmark tools (automatic tuning, real-time monitoring, KServe integration).
- Consider extensibility to import and integrate analysis of benchmark tool (GuideLLM, etc.) results.

---

## Directory Structure

```
vllm-optimizer/
├── AGENTS.md
├── CHANGELOG.md
├── deploy.sh                    # OpenShift deployment script
├── nginx.conf                   # Root level nginx configuration (for frontend)
├── baseline.dev.json            # Performance test baseline values
├── pyproject.toml               # pytest configuration (markers, asyncio)
│
├── scripts/
│   ├── run_performance_tests.sh # Integrated test execution script
│   └── collect_baseline.sh      # Baseline collection script
│
├── backend/
│   ├── __init__.py
│   ├── Dockerfile              # UBI9 Python based, non-root, arbitrary UID
│   ├── main.py                 # FastAPI entrypoint
│   ├── requirements.txt
│   ├── startup_metrics_shim.py # MetricsCollector background start
│   ├── routers/
│   │   ├── __init__.py
│   │   ├── load_test.py        # Load test API + SSE stream
│   │   ├── metrics.py          # Thanos Querier metric query
│   │   ├── benchmark.py        # Benchmark save/compare
│   │   ├── tuner.py            # Bayesian Optimization Tuner API
│   │   ├── sla.py              # SLA profile CRUD + judgment API
│   │   └── vllm_config.py      # IS tuning args + resources GET/PATCH
│   ├── services/
│   │   ├── __init__.py
│   │   ├── shared.py           # Singleton instance (MetricsCollector, load_engine)
│   │   ├── load_engine.py      # Asynchronous load generation engine
│   │   ├── metrics_collector.py # Prometheus + K8s API collector
│   │   ├── auto_tuner.py       # Thin facade (K8sOperator + EventBroadcaster + TunerLogic combination)
│   │   ├── k8s_operator.py     # K8s API operations (IS patch, readiness wait, rollback)
│   │   ├── event_broadcaster.py # SSE event broadcast + Prometheus metrics
│   │   └── tuner_logic.py      # Optuna study management, parameter search, trial evaluation
│   ├── models/
│   │   ├── __init__.py
│   │   ├── load_test.py        # Pydantic request/response models
│   │   └── sla.py              # SLA Pydantic model
│   ├── metrics/
│   │   ├── __init__.py
│   │   └── prometheus_metrics.py # Prometheus metric definitions
│   └── tests/
│       ├── __init__.py
│       ├── conftest.py          # Unit test fixtures
│       ├── test_load_test.py
│       ├── test_benchmark.py
│       ├── test_tuner.py
│       ├── test_metrics.py
│       ├── test_metrics_collector.py
│       ├── test_prometheus_metrics.py
│       ├── test_sla.py
│       └── integration/
│           └── performance/     # OpenShift cluster integration tests
│               ├── conftest.py  # Cluster connection fixtures
│               ├── test_cluster_health.py
│               ├── test_load_test_throughput.py
│               ├── test_sse_streaming.py
│               ├── test_metrics_collection.py
│               ├── test_auto_tuner.py
│               └── utils/
│                   └── baseline.py
│
├── frontend/
│   ├── Dockerfile              # UBI9 nginx-124, 8080 port, non-root
│   ├── nginx.conf              # SPA routing, /api/* proxy configuration
│   ├── package.json
│   ├── vite.config.js          # Vite build configuration
│   ├── index.html              # HTML entrypoint
│   └── src/
│       ├── main.jsx            # React entrypoint
│       ├── index.css           # Global styles
│       ├── App.jsx             # React Dashboard (5 tabs)
│       ├── constants.js        # Constant definitions
│       ├── mockData.js         # Mock data
│       ├── mocks/
│       │   └── handlers.js        # MSW mock handlers (for testing)
│       ├── contexts/
│       │   └── ClusterConfigContext.tsx  # IS endpoint/namespace global state
│       ├── pages/
│       │   ├── MonitorPage.jsx    # Metric monitoring tab
│       │   ├── LoadTestPage.jsx   # Load test tab
│       │   ├── BenchmarkPage.jsx  # Benchmark comparison tab
│       │   ├── TunerPage.jsx      # Auto Tuner tab (vllm-config current value + edit)
│       │   └── SlaPage.tsx        # SLA Dashboard tab
│       └── components/
│           ├── Chart.jsx         # Chart component
│           ├── MetricCard.jsx    # Metric card component
│           ├── ClusterConfigBar.tsx  # Cluster configuration bar (IS endpoint/namespace edit)
│           └── TunerConfigForm.tsx   # Tuner parameters + CPU/Memory/GPU resource edit form
│
└── openshift/
    ├── base/
    │   ├── 01-namespace-rbac.yaml  # Namespace + ServiceAccount + ClusterRole + SCC
    │   ├── 02-config.yaml          # ConfigMap + Secret
    │   ├── 03-backend.yaml        # Deployment + Service + HPA
    │   ├── 04-frontend.yaml      # Deployment + Service + Route
    │   ├── 05-monitoring.yaml    # ServiceMonitor + PrometheusRule + PDB + NetworkPolicy
    │   └── kustomization.yaml
    ├── vllm-dependency/             # vLLM dependency Kustomize overlay (base, dev, prod)
    ├── overlays/
    │   ├── dev/kustomization.yaml   # Dev: Reduced resources, 1 replica
    │   └── prod/kustomization.yaml  # Prod: 3 replicas, increased resources
```

---

## Core Design Principles (OpenShift Compliance Requirements)

Agents **must** follow these principles when writing and modifying code.

### 1. Container Image
- Base image must be **Red Hat UBI9** (`registry.access.redhat.com/ubi9/...`)
- Direct reference to DockerHub images is prohibited. Production images are hosted on **Quay.io**.

### 2. Port Rules
- Backend: **8000** (non-root port)
- Frontend/nginx: **8080** (non-root port)
- Prohibited from using privileged ports like 80, 443.

### 3. User Permissions (SCC)
- Containers **must** run as **non-root**.
- OpenShift assigns arbitrary UIDs.
- OpenShift assigns to the root group by default.

```dockerfile
# Correct example
RUN chgrp -R 0 . && chmod -R g+rwX .
USER 1001
```

### 4. Ingress → OpenShift Route
- Use **OpenShift Route** (Edge TLS termination)

```yaml
# Correct example
apiVersion: route.openshift.io/v1
kind: Route
spec:
  tls:
    termination: edge
```

### 5. Image Registry
- Images must use **Quay.io** or an internal registry.

### 6. Monitoring
- Direct Prometheus installation is prohibited.
- Utilize **OpenShift Monitoring Stack (Thanos Querier)**.
- Thanos Querier service endpoint (internal): `https://thanos-querier.openshift-monitoring.svc.cluster.local:9091`
- Thanos Querier route endpoint (external): `https://thanos-querier-openshift-monitoring.apps.compact.jooan.local` (socks5 proxy required)
- Expose metrics on the `/metrics` endpoint.

### 7. Network Policy
- Apply the principle of least privilege with **NetworkPolicy**.
- Block unnecessary communication between Pods.

---

## Environment Variables

| Variable Name | Description | Example |
|--------|------|------|
| `REGISTRY` | Container registry | `quay.io/joopark` |
| `IMAGE_TAG` | Image tag | `1.0.0` |
| `VLLM_NAMESPACE` | LLM inference service namespace. **Pod lookup, MetricsCollector, and auto-tuner all use this variable.** | `vllm-lab-dev` (dev), `vllm-lab-prod` (prod) |
| `VLLM_CR_TYPE` | LLM resource type. `inferenceservice` (KServe) or `llminferenceservice` (LLMIS). **Dynamic switching at runtime with `cr_adapter.py`'s adapter pattern** — auto-tuner, vllm-config, metrics, rollback all fully support both types. | `inferenceservice` (default) |
| `PROMETHEUS_URL` | Thanos Querier URL | `https://thanos-querier.openshift-monitoring.svc.cluster.local:9091` |
| `K8S_DEPLOYMENT_NAME` | LLM Deployment name (KServe: `{name}-predictor`). **Used for MetricsCollector's pod listing and auto-tuner's Deployment rollout restart.** | `llm-ov-predictor` |
| `VLLM_DEPLOYMENT_NAME` | InferenceService name. **Used for auto-tuner's resource name reference.** Do not confuse with `K8S_DEPLOYMENT_NAME`. | `llm-ov` |
| `VLLM_ENDPOINT` | LLM inference endpoint (for testing). KServe service internal address or external address. | `http://llm-ov-predictor.vllm-lab-dev.svc.cluster.local:8080` |
| `VLLM_MODEL` | LLM model name | `qwen2-5-7b-instruct` |
| `LOAD_ENGINE_TIMEOUT` | Load test HTTP request timeout (default: 120 seconds) | `120` |
| `LOAD_ENGINE_SHORT_TIMEOUT` | Load test short request timeout (default: 5 seconds) | `5` |
| `SELF_METRICS_URL` | Self-metrics collection URL (default: http://localhost:8000/metrics) | `http://localhost:8000/metrics` |
| `MODEL_RESOLVE_TIMEOUT` | Model name resolution HTTP timeout (default: 10 seconds) | `10` |

---

## Build and Deployment

### Local Build (Podman recommended, Docker possible)
```bash
# Backend
podman build -t vllm-optimizer-backend:dev ./backend

# Frontend
podman build -t vllm-optimizer-frontend:dev ./frontend
```

### OpenShift Deployment (Air-gapped)
```bash
# After setting environment variables
export REGISTRY="quay.io/joopark"
export IMAGE_TAG="1.0.0"
export VLLM_NAMESPACE="vllm-lab-dev"  # Dev: vllm-lab-dev, Prod: vllm-lab-prod
# Note: The default value for the shell variable VLLM_NAMESPACE in deploy.sh is llm-d-demo (for LLMIS RBAC deployment),
# and is separate from the VLLM_NAMESPACE in the backend ConfigMap.

# Dev deployment (build + push + deploy)
./deploy.sh dev

# Dry run (preview changes)
./deploy.sh dev --dry-run

# Deploy only, without building
./deploy.sh dev --skip-build

# Prod deployment
IMAGE_TAG="1.0.0" ./deploy.sh prod
```

### Kustomize Direct Deployment
```bash
# Dev
oc apply -k openshift/overlays/dev

# Prod
oc apply -k openshift/overlays/prod
```

### Kustomize Validation (Prohibit local kustomize binary usage)
Do not use the local `./kustomize` binary. Kustomization changes must be validated with the `oc` command.
```bash
# Validate YAML rendering with dry-run (no cluster connection required)
oc apply -k openshift/overlays/dev --dry-run=client
oc apply -k openshift/overlays/prod --dry-run=client

# Or just view rendered output
oc kustomize openshift/overlays/dev
oc kustomize openshift/overlays/prod
```

---

## Development Commands

### Backend (Local Development)
```bash
# Local execution
cd backend && uvicorn main:app --reload --port 8000

# Unit tests (excluding integration/slow)
cd backend && python3 -m pytest tests/ -x -q

# Specific test
cd backend && python3 -m pytest tests/test_load_test.py -x -q
cd backend && python3 -m pytest tests/test_load_test.py::test_function_name -x -q

# Lint + format
cd backend && python3 -m ruff check . --fix && python3 -m ruff format .
```

### Frontend (Local Development)
```bash
cd frontend
npm run dev          # Vite development server (port 5173, /api → localhost:8000 proxy)
npm run build        # Production build
npm run test         # Vitest unit tests
npm run test:e2e     # Playwright E2E tests
npm run lint         # ESLint
npm run type-check   # TypeScript type check
```

### Test Markers (pytest)
| Marker | Description |
|------|------|
| `@pytest.mark.integration` | Requires OpenShift cluster |
| `@pytest.mark.performance` | Performance measurement |
| `@pytest.mark.slow` | Takes more than 30 seconds |

By default, `pytest` execution excludes integration and slow tests (`pyproject.toml` configuration).

---

## Linting and Code Style

- **Python**: Ruff (rules: E, F, I, UP, B, SIM). Line length 120. Format with `ruff format`.
- **TypeScript**: ESLint + Prettier. Strict TypeScript (`tsconfig.json` strict mode).
- **Pre-commit**: ruff format + check, trailing-whitespace, end-of-file-fixer, check-yaml.


## Code Writing Guidelines

### Backend (Python / FastAPI)

- **Async First**: Use `async/await` for all I/O operations.
- **Pydantic Models**: Define Pydantic models in `models/` for all requests/responses.
- **SSE Stream**: Deliver real-time load test results via Server-Sent Events.
- **K8s API Calls**: Use the `kubernetes` Python client, ServiceAccount token authentication.
- **Prometheus Query**: Call Thanos Querier API with Bearer token.
- **MetricsCollector Singleton**: Always use `from services.shared import metrics_collector`. Do not instantiate directly.
- **Import Rules**: Use bare imports without the `backend.` prefix (`from services.xxx`, `from models.xxx`).
- **K8s API (async)**: When using a synchronous K8s client in async code, always wrap it with `asyncio.to_thread()`.
- **Thanos TLS**: Use self-signed certificates → `httpx.AsyncClient(verify=False)` is required.
- **auto_tuner Model Name**: Prohibit `model="auto"`. Dynamic resolution from `/v1/models` endpoint is required.

```python
# Example of Thanos Querier call
import httpx

async def query_thanos(query: str, token: str) -> dict:
    async with httpx.AsyncClient(verify=False) as client:
        resp = await client.get(
            f"{THANOS_URL}/api/v1/query",
            headers={"Authorization": f"Bearer {token}"},
            params={"query": query},
        )
        resp.raise_for_status()
        return resp.json()
```

- **ConfigMap Update** (Auto Tuner): Patch the ConfigMap in the vLLM namespace using the `kubernetes` client.

```python
from kubernetes import client, config

config.load_incluster_config()  # When running inside a Pod
v1 = client.CoreV1Api()
v1.patch_namespaced_config_map(name="vllm-config", namespace=VLLM_NAMESPACE, body=patch)
```

### Frontend (React)

- `/api/*` requests are proxied to the Backend by nginx (use absolute paths).
- SSE reception: Use `EventSource` API.
- 5 tab configuration: **Load Test / Metric Monitoring / Benchmark Comparison / Auto Tuner / SLA**.
- Manage IS endpoint/namespace globally with `ClusterConfigContext` — use `useClusterConfig()` hook.
- `TunerPage`'s vllm-config fetch `useEffect` dependencies must include `namespace`, `inferenceservice` (re-fetch on IS change).
- Resource edit key format: `resources.{tier}.{key}` (e.g., `resources.limits.cpu`) — separate from tuning args with `resources.` prefix in `editedValues`.

### OpenShift YAML

- Use OpenShift-specific resources for `apiVersion` (`route.openshift.io/v1`, `security.openshift.io/v1`, etc.).
- Specify `resources.requests` / `resources.limits` for all Deployments.
- `livenessProbe` / `readinessProbe` must be configured.
- Specify `runAsNonRoot: true`, `allowPrivilegeEscalation: false` in `securityContext`.

```yaml
securityContext:
  runAsNonRoot: true
  allowPrivilegeEscalation: false
  capabilities:
    drop: ["ALL"]
  seccompProfile:
    type: RuntimeDefault
```

---

## Dual CR Compatibility Principle

Both `InferenceService` (KServe) and `LLMInferenceService` (LLMIS) CR types must be **equally supported**.

### Core Rules

- **Adhere to Adapter Pattern**: Both types are abstracted through the `CRAdapter` abstract interface in `backend/services/cr_adapter.py`. When adding new features, both `InferenceServiceAdapter` and `LLMInferenceServiceAdapter` must implement the interface.
- **Environment Variable Defaults**: Code-level fallback values are KServe-based (`inferenceservice`, `vllm-lab-dev`, `llm-ov`). To switch to LLMIS, set `VLLM_CR_TYPE=llminferenceservice`.
- **Testing Rules**: Unit tests for new features must validate both CR types. Existing `test_cr_adapter.py`, `test_llmis_integration.py` validate the LLMIS path, while default tests validate the KServe path.
- **Test Data Rules**: When unit tests do not validate specific CR type behavior, neutral names (`test-ns`, `test-isvc`) are recommended. Use actual LLMIS names like `small-llm-d` only when validating LLMIS adapter behavior.

### Model Name Resolution Rules (per CR type)

| CR Type | Primary Model Name Source | Fallback | Code Location |
|---------|-------------------|----------|-----------|
| `InferenceService` (isvc) | `--served-model-name` (extracted from args) | isvc name (`fallback_name`) | `InferenceServiceAdapter.resolve_model_name()` |
| `LLMInferenceService` (llmisvc) | `.spec.model.name` | llmisvc name (`fallback_name`) | `LLMInferenceServiceAdapter.resolve_model_name()` |

- **Runtime Dynamic Resolution**: `model_resolver.py`'s `resolve_model_name()` calls the `/v1/models` API to get the actual serving model name. CR spec-based resolution (`CRAdapter.resolve_model_name`) determines the name solely from the spec without an API call.
- auto_tuner must use `/v1/models` dynamic resolution (prohibit `model="auto"`).

### Default Endpoint Patterns (per CR type)

| CR Type | Endpoint Pattern | Example |
|---------|----------------|------|
| `InferenceService` (isvc) | `http://{name}-predictor.{namespace}.svc.cluster.local:8080` | `http://llm-ov-predictor.vllm-lab-dev.svc.cluster.local:8080` |
| `LLMInferenceService` (llmisvc) | `http://openshift-ai-inference-openshift-default.openshift-ingress.svc/{namespace}/{name}` | `http://openshift-ai-inference-openshift-default.openshift-ingress.svc/llm-d-demo/small-llm-d` |

- isvc services have unique DNS (`{name}-predictor.{ns}.svc`). Port `8080`.
- llmisvc services are routed through a shared Gateway (`openshift-ingress.svc/{ns}/{name}`). Port omitted (default 80).

---

## vLLM Cluster Architecture (Dev Environment)

The current Dev environment's vLLM is deployed with the **KServe InferenceService** architecture. The LLMIS + Gateway method is supported in parallel as an alternative/future direction.

> **CR Adapter Pattern**: The `VLLM_CR_TYPE` environment variable switches the CR type at runtime. Since `InferenceServiceAdapter` and `LLMInferenceServiceAdapter` in `backend/services/cr_adapter.py` implement the same abstract interface (`CRAdapter`), auto-tuner, vllm-config, metrics collector, and rollback all fully support both types.

### Primary Deployment Model: KServe InferenceService

- **InferenceService**: `llm-ov` (namespace: `vllm-lab-dev`)
- **Deployment**: `llm-ov-predictor` (automatically generated)
- **Pod label**: `app=isvc.llm-ov-predictor`
- **Model**: `qwen2-5-7b-instruct`
- **Inference Endpoint**: `http://llm-ov-predictor.vllm-lab-dev.svc.cluster.local:8080`
- **API**: `/v1/completions`, `/v1/models` (OpenAI compatible)

### KServe Naming Rules
| Resource | Name Pattern | Example |
|--------|-----------|------|
| InferenceService | `{name}` | `llm-ov` |
| Deployment | `{name}-predictor` | `llm-ov-predictor` |
| Pod label | `app=isvc.{name}-predictor` | `app=isvc.llm-ov-predictor` |
| Service | `{name}-predictor` | `llm-ov-predictor` |

The `K8S_DEPLOYMENT_NAME` environment variable must be set to the Deployment name generated by KServe (`{name}-predictor`).

### Namespace Separation Principle (Important)

| CR Type | Namespace | Notes |
|---------|------------|------|
| `LLMInferenceService` (llmisvc) | `llm-d-demo` | Managed by the llm-d platform. **Direct creation prohibited.** |
| `InferenceService` (isvc) | `vllm-lab-dev` / `vllm-lab-prod` | KServe. Managed by vllm-dependency Kustomize. |

- `llm-d-demo` only deploys RBAC + NetworkPolicy (`openshift/vllm-dependency/llmis-rbac/`).
- The `vllm-dependency/dev` Kustomize overlay must maintain `namespace: vllm-lab-dev`.
- `deploy.sh dev` has two stages: ① `vllm-dependency/dev` → `vllm-lab-dev`, ② `llmis-rbac/` → `llm-d-demo`.

### Alternative/Future Direction: LLMInferenceService (LLMIS)

The structure of LLMInferenceService used in previous environments is as follows (for reference):

- **LLMInferenceService**: `small-llm-d` (namespace: `llm-d-demo`)
- **Deployment**: `small-llm-d-kserve` (automatically generated)
- **Pod label**: `app.kubernetes.io/name=small-llm-d`
- **Gateway Internal Endpoint**: `http://openshift-ai-inference-openshift-default.openshift-ingress.svc/llm-d-demo/small-llm-d`
- **API**: `/v1/completions`, `/v1/models` (OpenAI compatible)

#### LLMIS Naming Rules
| Resource | Name Pattern | Example |
|--------|-----------|------|
| LLMInferenceService | `{name}` | `small-llm-d` |
| Deployment | `{name}-kserve` | `small-llm-d-kserve` |
| Pod label | `app.kubernetes.io/name={name}` | `app.kubernetes.io/name=small-llm-d` |
| Gateway endpoint | `{gateway}/{namespace}/{name}/v1/...` | `.../llm-d-demo/small-llm-d/v1/models` |

---

## Integration Tests

There are 8 integration tests that run on a real OpenShift cluster.

### Test List
| Test | Description |
|--------|------|
| `test_backend_health_deep` | Backend /health endpoint (including deep check) |
| `test_metrics_endpoint_accessible` | Verify /api/metrics/latest response |
| `test_prometheus_metrics_plaintext` | Validate Prometheus text format |
| `test_metrics_response_time` | Metric collection response time |
| `test_prometheus_scrape_format_valid` | Validate Prometheus scrape format validity |
| `test_load_test_completes_successfully` | Execute load test + validate results |
| `test_load_test_sse_events` | Verify SSE streaming event reception |
| `test_auto_tuner_completes_with_results` | Execute Auto Tuner 2-trial + validate results |

### Running on Cluster
```bash
NS=vllm-optimizer-dev
BACKEND_POD=$(oc get pod -n $NS -l app=vllm-optimizer-backend -o name | head -1)
oc exec -n $NS $BACKEND_POD -- env \
  PERF_TEST_BACKEND_URL=http://localhost:8000 \
  VLLM_ENDPOINT=http://llm-ov-predictor.vllm-lab-dev.svc.cluster.local:8080 \
  VLLM_MODEL=qwen2-5-7b-instruct \
  VLLM_NAMESPACE=vllm-lab-dev \
  OPTIMIZER_NAMESPACE=vllm-optimizer-dev \
  python3 -m pytest /app/tests/integration/performance/ -v --tb=short -m "integration"
```

### Unit Tests (Local)
```bash
cd backend && python3 -m pytest tests/ -x -q -m "not integration"
```

---

## Debugging and Validation

These commands are used when the agent needs to validate after deployment.

```bash
NS=vllm-optimizer-dev

# Check Pod status
oc get pods -n $NS

# Check Route URL
oc get route vllm-optimizer -n $NS

# Stream Backend logs
oc logs -l app=vllm-optimizer-backend -n $NS -f

# Check SCC application
oc describe pod -l app=vllm-optimizer-backend -n $NS | grep -i scc

# Check events (diagnose issues)
oc get events -n $NS --sort-by=.lastTimestamp | tail -20

# Check Prometheus metrics endpoint
oc exec -it $(oc get pod -l app=vllm-optimizer-backend -n $NS -o name | head -1) \
  -n $NS -- curl localhost:8000/metrics

# Test Thanos Querier direct query
TOKEN=$(oc create token vllm-optimizer-backend -n vllm-optimizer-dev)
curl --socks5-hostname 127.0.0.1:8882 -H "Authorization: Bearer $TOKEN" \
  https://thanos-querier-openshift-monitoring.apps.compact.jooan.local/api/v1/query \
  --data-urlencode 'query=vllm:num_requests_running' -k

# Check LLM Pod status (KServe)
oc get pods -n vllm-lab-dev -l app=isvc.llm-ov-predictor
```

---

## E2E Cluster Validation Essential Rules

When modifying auto_tuner, load tests, RBAC, or ConfigMap related code/YAML, you must perform the following:

1. Deploy to the OpenShift cluster with `./deploy.sh dev`.
2. Directly verify normal operation of features using `oc` commands on the actual cluster.
3. For changes requiring Pod restart: Verify Pod replacement with `oc get pods -n vllm-lab-dev`.
4. Do not ask the user for results; the agent must verify and report directly.

**Violation Case**: RBAC 403 errors are not detected by unit tests alone. If code is modified and marked complete without cluster deployment, Pods may not restart at all.

```bash
# Basic E2E validation procedure
NS=vllm-optimizer-dev
BACKEND_POD=$(oc get pod -n $NS -l app=vllm-optimizer-backend -o name | head -1)

# 1. Deployment
./deploy.sh dev

# 2. Record Pod UID (KServe)
BEFORE_UID=$(oc get pods -n vllm-lab-dev -l app=isvc.llm-ov-predictor -o jsonpath='{.items[*].metadata.uid}')

# 3. Check InferenceService status
oc get inferenceservice llm-ov -n vllm-lab-dev -o jsonpath='{.status.conditions}'

# 4. Verify Pod UID change after tuning completion
AFTER_UID=$(oc get pods -n vllm-lab-dev -l app=isvc.llm-ov-predictor -o jsonpath='{.items[*].metadata.uid}')
[ "$BEFORE_UID" != "$AFTER_UID" ] && echo "PASS: pod restarted" || echo "FAIL: pod NOT restarted"

# 5. Verify no 403 errors in logs
oc logs -l app=vllm-optimizer-backend -n $NS --tail=50 | grep -i "403\|forbidden"
```

## Frequently Encountered Issues (Agent Reference)

### When SCC Error Occurs

vLLM Optimizer uses the default OpenShift SCC, `restricted-v2`.
No separate SCC binding is required. If a Pod fails due to an SCC issue:

```bash
# Check currently applied SCC
oc describe pod -l app=vllm-optimizer-backend -n vllm-optimizer-dev | grep -i scc
# Expected result: openshift.io/scc: restricted-v2
```

### When Image Pull Fails
```bash
oc import-image vllm-optimizer-backend:latest \
  --from=quay.io/joopark/vllm-optimizer-backend:latest \
  --confirm -n vllm-optimizer-dev
```

### When Thanos is Inaccessible
- Check `cluster-monitoring-view` ClusterRole binding for ServiceAccount.
- Reapply ClusterRoleBinding from `05-monitoring.yaml`.

### MetricsCollector All-Zero Metrics
- Check collector status with `curl -X POST localhost:8000/startup_metrics`.
- If `collector_version` is `unknown`, Thanos connection failed → check token/URL.
- If `pods=0`, `K8S_DEPLOYMENT_NAME` does not match the actual Deployment name → check KServe/LLMIS pattern.

### auto_tuner Skips Other Tests After Execution
- auto_tuner makes inference requests to vLLM → p99 latency increases → `skip_if_overloaded` triggers.
- `skip_if_overloaded` waits up to 120 seconds before skipping (waiting for Thanos 1-minute rate window rollover).
- If skipping persists: Check vLLM pod status (`oc get pods -n vllm-lab-dev -l app=isvc.llm-ov-predictor`).

### auto_tuner vLLM Pod Not Restarting
- auto_tuner directly performs a rollout restart on the `K8S_DEPLOYMENT_NAME` Deployment (e.g., `llm-ov-predictor`).
- If the Pod does not restart: Check backend logs for `Deployment restart failed` errors.
- Verify `K8S_DEPLOYMENT_NAME` matches the actual Deployment name: `oc get deployment -n vllm-lab-dev`.
- Manual verification: `oc rollout restart deployment/llm-ov-predictor -n vllm-lab-dev`.
- **Caution**: InferenceService name (`llm-ov`, `VLLM_DEPLOYMENT_NAME`) and Deployment name (`llm-ov-predictor`, `K8S_DEPLOYMENT_NAME`) are different. Use the Deployment name for Pod restarts.
- When using LLMIS: Deployment name follows the `{name}-kserve` pattern (e.g., `small-llm-d-kserve`, namespace: `llm-d-demo`).

### IS args Architecture
- Both auto_tuner and vllm_config API directly patch IS `spec.predictor.model.args`.
- **vllm_config PATCH**: dict-merge method — preserves existing args and overwrites only changed keys. Safe for partial updates.
- **auto_tuner._apply_params**: Full replacement method (intended design) — do not modify.
- Sending boolean `false` removes the corresponding flag (e.g., `{"enable_chunked_prefill": "false"}` → removes `--enable-chunked-prefill` from args).

### IS resources Architecture
- IS resources path: `spec.predictor.model.resources.{requests,limits}`
- `ALLOWED_RESOURCE_KEYS = {"cpu", "memory", "nvidia.com/gpu"}` — Allowed resource keys (backend validation).
- GPU is set only in `limits` (K8s automatically copies to `requests`).
- Sending an empty string value removes the corresponding key (to prevent affecting K8s scheduling).
- `vllm_config.py` PATCH request: `data` (tuning args) and `resources` are processed independently as separate fields.

### Prohibit auto_tuner model="auto"
- Dynamic resolution from `/v1/models` endpoint is required.
- Use the `resolve_model_name()` function from `model_resolver.py` (already integrated into auto_tuner).

### SLA Profile Creation 422
- `SlaThresholds` has an `at_least_one_threshold` model_validator — 422 if all thresholds are null.
- Frontend already has validation requiring at least one threshold input.
- Do not modify backend `SlaProfile`/`SlaThresholds` models (validation logic is correct).
- For 422 errors, the `detail` field in the response body includes the Pydantic validation message.

---

## Playwright Usage Guide — Token Saving Rules

When an AI agent manipulates the browser with Playwright, unnecessary snapshot requests consume excessive tokens. You must adhere to the following rules.

### Essential Rule: Minimize Snapshot Calls

The Playwright skill automatically calling `browser_snapshot` after every interaction is a **huge** token waste. Converting every page state to text consumes thousands of tokens.

**Correct Usage:**
```typescript
// ✅ GOOD: Use explicit tools only — no snapshot calls
await playwright_browser_click({ element: "theme toggle switch", ref: "e14" });
// Directly check if the state has changed with a specific element
const isLight = await playwright_browser_evaluate({ 
  function: "() => document.documentElement.getAttribute('data-theme')" 
});

// ❌ BAD: Snapshot immediately after click (unnecessarily captures the entire DOM)
await playwright_browser_click({ ... });
await playwright_browser_snapshot(); // ← Token explosion, prohibited!
```

**Prohibited Patterns:**
- `playwright_browser_click` → immediate `playwright_browser_snapshot` **prohibited**
- `playwright_browser_type` → immediate `playwright_browser_snapshot` **prohibited**
- Snapshot at every step **prohibited**
- Use `playwright_browser_evaluate` instead of snapshots for change verification.

**Allowed Patterns:**
- One snapshot on initial page load (for initial state verification).
- Explicit snapshots for debugging (only when issues arise).
- Use `playwright_browser_evaluate` to check specific values (direct DOM element query).
- Use `playwright_browser_console_messages` to check for errors.

### Token Saving Checklist

Before using Playwright, the agent must verify:

1. **Is a snapshot necessary?** → No. `evaluate`, `click`, `type` are sufficient.
2. **Am I using a snapshot instead of `console_messages`?** → `console_messages` is more efficient for error checking.
3. **Is a screenshot necessary?** → Only for visual verification. Most cases can use `evaluate`.
4. **Snapshot immediately after navigation?** → Not essential. Verify key elements with `evaluate`.

---

## Prohibited Actions

The agent must not perform the following actions:

- Run containers as `root` user.
- Directly bind to ports `80` or `443`.
- Create Kubernetes `Ingress` objects (use OpenShift Route).
- Directly reference DockerHub images.
- Use `docker` (this project is based on `podman`).
- Use `kubectl` (this project is based on `oc`).
- Leave temporary issues as Blocked without clear proof, or complete the plan with Blocked issues.

---

## Reference Documents

- [OpenShift 4.x Official Documentation](https://docs.openshift.com)
- [vLLM Official Documentation](https://docs.vllm.ai)
- [Optuna Official Documentation](https://optuna.readthedocs.io)
- [Kustomize Documentation](https://kubectl.docs.kubernetes.io/guides/introduction/kustomize/)