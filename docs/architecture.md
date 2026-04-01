---
title: vLLM Optimizer System Architecture
date: 2026-03-08
updated: 2026-04-01
tags: [architecture, vllm, openshift]
status: published
---

# vLLM Optimizer System Architecture

This document outlines the system architecture of the vLLM Optimizer, a containerized application designed for OpenShift 4.x. It provides load testing, real-time monitoring, benchmark comparison, and automated parameter tuning for vLLM services.

## Quick Start

### Backend
```bash
# Run locally
cd backend && uvicorn main:app --reload --port 8000

# Unit tests (excludes integration/slow)
cd backend && python3 -m pytest tests/ -x -q

# Single test
cd backend && python3 -m pytest tests/test_load_test.py::test_name -x -q

# Integration tests (requires OpenShift cluster)
cd backend && python3 -m pytest tests/integration/performance/ -v --tb=short -m integration

# Lint and format
cd backend && python3 -m ruff check . --fix && python3 -m ruff format .
```

### Frontend
```bash
cd frontend
npm run dev          # Vite dev server (port 5173)
npm run build        # Production build
npm run test         # Vitest unit tests
npm run lint         # ESLint
npm run type-check   # TypeScript type checking
```

### Deployment
```bash
./deploy.sh dev              # Build + deploy to vllm-optimizer-dev
./deploy.sh dev --skip-build # Deploy only
./deploy.sh dev --dry-run    # Preview changes
```

## Key Design Decisions

- **Dual CR support**: `VLLM_CR_TYPE` env var switches between `inferenceservice` (KServe, default) and `llminferenceservice` (LLMIS). The `CRAdapter` pattern in `backend/services/cr_adapter.py` abstracts endpoint resolution, model name extraction, and spec patching for both types.
- **Async-first**: All backend I/O is async (httpx, aiosqlite, K8s via `asyncio.to_thread()`).
- **OpenShift Monitoring Stack**: Queries go to Thanos Querier (in-cluster), not an external Prometheus. `httpx.AsyncClient(verify=False)` is required for self-signed certs.
- **No external DB**: SQLite + PVC keeps deployment simple — single PVC, no database operator.
- **MetricsCollector singleton**: Accessed via `from services.shared import multi_target_collector`. Never instantiate directly.
- **Auto-tuner facade**: `auto_tuner.py` is a thin facade composing K8sOperator, EventBroadcaster, and TunerLogic. Lock-free services receive locks as parameters from the facade.

## Common Pitfalls

### Naming Confusion
- `VLLM_DEPLOYMENT_NAME` = InferenceService name (`llm-ov`) — used for resource references
- `K8S_DEPLOYMENT_NAME` = Deployment name (`llm-ov-predictor`) — used for pod listing and rollout restart
- **Do not confuse these two.** KServe auto-generates the Deployment name as `{isvc_name}-predictor`.

### IS args Patching
- `vllm_config PATCH`: dict-merge — preserves existing args, overwrites only changed keys
- `auto_tuner._apply_params`: full replacement — intentional design, do not modify
- boolean `false` removes the flag (e.g., `{"enable_chunked_prefill": "false"}` → removes `--enable-chunked-prefill`)

### IS Resources
- Path: `spec.predictor.model.resources.{requests,limits}`
- `ALLOWED_RESOURCE_KEYS = {"cpu", "memory", "nvidia.com/gpu"}`
- GPU: set in `limits` only (K8s auto-copies to `requests`)
- Empty string value removes the key (prevents K8s scheduling issues)

### model="auto" Forbidden
- Auto-tuner must use `/v1/models` dynamic resolution via `model_resolver.resolve_model_name()`
- Never hardcode `model="auto"` in auto-tuner code

### SLA Profile 422
- `SlaThresholds` has `at_least_one_threshold` validator — all thresholds null → 422
- Frontend enforces this, but backend will reject if bypassed

## Environment Variables

| Variable | Purpose | Default |
|---|---|---|
| `VLLM_ENDPOINT` | vLLM inference URL | required |
| `VLLM_MODEL` | Model name | `OpenVINO/Phi-4-mini-instruct-int4-ov` |
| `VLLM_NAMESPACE` | vLLM workload namespace (pod listing, metrics, tuner) | `vllm-lab-dev` |
| `VLLM_DEPLOYMENT_NAME` | InferenceService name | `llm-ov` |
| `K8S_DEPLOYMENT_NAME` | Deployment name (KServe: `{name}-predictor`) | `llm-ov-predictor` |
| `VLLM_CR_TYPE` | `inferenceservice` or `llminferenceservice` | `inferenceservice` |
| `PROMETHEUS_URL` | Thanos Querier URL | internal SVC |
| `STORAGE_PATH` | SQLite DB path | `/data/app.db` |
| `REGISTRY` | Container registry | `quay.io/joopark` |
| `IMAGE_TAG` | Image tag | `1.0.0` |

## Overall System Topology

The vLLM Optimizer consists of a React-based frontend and a FastAPI backend, deployed on OpenShift. It interacts with external services like Thanos Querier for metrics and the vLLM instance (deployed via KServe) for inference and tuning.

```
+-------------------+       +-------------------+       +-------------------+
|   User Browser    | <---> |      React        | <---> |       nginx       |
|                   |       |     Frontend      |       |                   |
+-------------------+       +-------------------+       +-------------------+
                                      | (HTTP/S)
                                      v
+---------------------------------------------------------------------------+
|                            OpenShift Route (Edge TLS)                     |
+---------------------------------------------------------------------------+
                                      |
                                      v
+-------------------+       +-------------------+       +-------------------+
|    FastAPI        | <---> |    FastAPI        | <---> |    FastAPI        |
|     Backend       |       |     Backend       |       |     Backend       |
|    (Pod 1)        |       |    (Pod 2)        |       |    (Pod N)        |
+-------------------+       +-------------------+       +-------------------+
          |                           |                           |
          |                           v                           |
          |             +---------------------------------+       |
          |             |         K8s API Server          |       |
          |             +---------------------------------+       |
          |                           |                           |
          |                           v                           |
          |             +---------------------------------+       |
          |             |         Thanos Querier          |       |
          |             | (OpenShift Monitoring Stack)    |       |
          |             +---------------------------------+       |
          |                           |                           |
          |                           v                           |
          |             +---------------------------------+       |
          +-----------> |         vLLM Instance           | <-----------+
                        |      (KServe Deployment)        |
                        +---------------------------------+
```

## Component Responsibilities

### Frontend (React + nginx)

The frontend is a React application served by nginx. It runs on port `8080` and provides a user interface with five main tabs: Load Test, Metric Monitoring, Benchmark Comparison, Auto Tuner, and SLA. nginx handles static file serving and proxies `/api/*` requests to the FastAPI backend.

### Backend (FastAPI)

The backend is a FastAPI application written in Python, running on port `8000`. It is built on a Red Hat UBI9 Python base image and runs as a non-root user. It exposes various API endpoints for managing load tests, fetching metrics, comparing benchmarks, and tuning vLLM parameters.

#### Key Backend Components:

-   **`main.py`**: This is the entry point for the FastAPI application. It initializes the application, registers routers for different functionalities (load test, metrics, benchmark, tuner), and starts background services like the `MetricsCollector`.
-   **`services/load_engine.py`**: This module contains the asynchronous engine responsible for generating load against the vLLM endpoint. It handles concurrent requests and collects response statistics during load tests.
-   **`services/metrics_collector.py`**: This critical background service periodically collects metrics from the OpenShift cluster. It performs two main tasks:
    1.  **Thanos Querier Integration**: Queries the Thanos Querier (part of the OpenShift Monitoring Stack) for vLLM-specific metrics (e.g., `vllm:num_requests_running`, `vllm:num_requests_waiting`, token counters, latency histograms). It uses a Bearer token for authentication and `verify=False` for self-signed certificates.
    2.  **Kubernetes API Interaction**: Queries the Kubernetes API for vLLM pod counts and readiness status. It uses dynamic label selectors derived from the vLLM Deployment's `matchLabels` to identify relevant pods.
    The collected metrics are then used to update Prometheus client gauges, counters, and histograms, which are exposed via the `/metrics` endpoint.
-   **`services/auto_tuner.py`**: Thin facade that composes K8sOperator, EventBroadcaster, and TunerLogic. Manages the tuning loop, state, and public API (start, stop, subscribe, unsubscribe, get_importance). Owns all asyncio.Lock instances.
-   **`services/k8s_operator.py`**: Handles all Kubernetes API operations — InferenceService readiness checks, args patching, rollback, and preflight permission validation. Lock-free; receives locks as parameters from AutoTuner.
-   **`services/event_broadcaster.py`**: Manages SSE event queues (subscribe/unsubscribe/broadcast) and Prometheus metrics emission. Includes one-time persistence warning broadcast.
-   **`services/tuner_logic.py`**: Contains Optuna study management, parameter search space definition, trial evaluation (warmup + probe + full), score computation, and FAnova importance analysis. Stateless; receives study/trial as parameters.
-   **`metrics/prometheus_metrics.py`**: This module defines custom Prometheus metrics (gauges, counters, histograms) used by the vLLM Optimizer. It also exposes the `/metrics` endpoint, which Prometheus can scrape.

#### Singleton Pattern for `MetricsCollector`:

The `MetricsCollector` is designed as a singleton to ensure only one instance runs and manages metric collection. It is accessed throughout the application using `from services.shared import metrics_collector`, preventing direct instantiation.

## Data Flows

### Metrics Flow

1.  The `MetricsCollector` runs as a background loop, periodically querying:
    -   Thanos Querier for vLLM performance metrics.
    -   Kubernetes API for vLLM pod status.
2.  The collected data updates internal Prometheus client metrics within the FastAPI backend.
3.  OpenShift's Prometheus (via a `ServiceMonitor`) scrapes the `/metrics` endpoint of the FastAPI backend.
4.  The scraped metrics are stored in Thanos.
5.  The frontend queries the FastAPI backend's `/api/metrics/latest` endpoint to retrieve the most recent metrics for dashboard display.

### Load Test Data Flow

1.  The frontend initiates a load test via the FastAPI backend.
2.  The `load_engine.py` service generates asynchronous load against the vLLM endpoint.
3.  Real-time load test results (e.g., requests per second, latency) are streamed back to the frontend using Server-Sent Events (SSE).

### Auto-Tuner Data Flow

1.  The frontend initiates an auto-tuning process via the FastAPI backend.
2.  The `auto_tuner.py` service uses Optuna to determine optimal vLLM parameters for each trial.
3.  For each trial, the service patches the vLLM InferenceService `spec.predictor.model.args` with new parameter values via the Kubernetes CustomObjects API.
4.  The service triggers a **Deployment rollout restart** by patching the `llm-ov-predictor` Deployment's pod template annotation (`kubectl.kubernetes.io/restartedAt`). This is equivalent to `kubectl rollout restart deployment/llm-ov-predictor`.
5.  The service polls the Deployment rollout status (`readyReplicas == replicas`) until the new pod is ready (up to 300 seconds).
6.  A 30-second cooldown is applied after the pod becomes ready to allow Prometheus metrics to stabilize.
7.  Once ready and cooled down, the service runs a load test against the vLLM endpoint to measure performance, and Optuna uses the result to guide the next trial.
7.  Real-time phase events (`applying_config`, `restarting`, `waiting_ready`, `warmup`, `evaluating`) are streamed to the frontend via SSE.
8.  After all trials complete, the best parameters are applied and the vLLM pod is restarted one final time with the optimal configuration.

> **Note**: The auto-tuner patches InferenceService args directly, which triggers KServe to update the Deployment spec. The Deployment rollout restart mechanism (step 4) ensures the pod picks up the new configuration.

## KServe Integration and Naming Convention

The vLLM instance is deployed on OpenShift using KServe. KServe follows a specific naming convention that the vLLM Optimizer must adhere to for proper interaction.

-   **InferenceService Name**: If the KServe `InferenceService` is named `llm-ov`, configured via `VLLM_DEPLOYMENT_NAME` environment variable.
-   **Deployment Name**: KServe automatically creates a Deployment named `{InferenceService_name}-predictor`, e.g., `llm-ov-predictor`. This is the value used for the `K8S_DEPLOYMENT_NAME` environment variable (used by `MetricsCollector` for pod listing).
-   **Pod Label**: KServe assigns a pod label `app=isvc.{Deployment_name}`, e.g., `app=isvc.llm-ov-predictor`. This label is crucial for the `MetricsCollector` to identify and monitor the correct vLLM pods.
-   **vLLM Endpoint**: The internal service endpoint for the vLLM instance will be `http://llm-ov-predictor.vllm-lab-dev.svc.cluster.local:8080`.
-   **Auto-Tuner Restart**: The auto-tuner uses `K8S_DEPLOYMENT_NAME` (Deployment name, `llm-ov-predictor`) for pod restarts, and `VLLM_DEPLOYMENT_NAME` (InferenceService name, `llm-ov`) is kept separate. Do not confuse the two.

#### New API Endpoints

-   **`GET /api/vllm-config`**: Returns the current vLLM configuration by reading `InferenceService.spec.predictor.model.args` from Kubernetes, parsing the args list into a dictionary. Returns 503 if Kubernetes is not available.
-   **`PATCH /api/vllm-config`**: Updates the vLLM configuration by writing to `InferenceService.spec.predictor.model.args`. Converts the provided dictionary to a command-line args list and patches the InferenceService. Only keys in `ALLOWED_CONFIG_KEYS` are accepted (422 for invalid keys). Returns 409 if the auto-tuner is currently running.
-   **`GET /api/config`**: Returns frontend configuration including `vllm_endpoint`, `vllm_model_name` (from `VLLM_MODEL` env), and `resolved_model_name` (queried from vLLM `/v1/models` API with 3-second timeout).

## Thanos Querier Integration

The vLLM Optimizer integrates with the OpenShift Monitoring Stack's Thanos Querier to retrieve cluster-wide metrics.

-   **Internal Endpoint**: The internal service endpoint for Thanos Querier is `https://thanos-querier.openshift-monitoring.svc.cluster.local:9091`. This URL is configured via the `PROMETHEUS_URL` environment variable.
-   **Authentication**: Requests to Thanos Querier require a Bearer token, obtained from the ServiceAccount associated with the vLLM Optimizer backend.
-   **TLS Verification**: Due to self-signed certificates in OpenShift environments, `httpx.AsyncClient(verify=False)` is used when making requests to Thanos Querier.

## OpenShift Deployment Topology

The vLLM Optimizer is designed for deployment on OpenShift 4.x, leveraging its native features.

-   **Optimizer Namespace**: The vLLM Optimizer components (backend, frontend) are typically deployed in a dedicated namespace, for example, `vllm-optimizer-dev`.
-   **vLLM Namespace**: The vLLM instance itself resides in a separate namespace, commonly `vllm-lab-dev` (dev) or `vllm-lab-prod` (prod).
-   **OpenShift Route**: Frontend access is exposed via an OpenShift Route, which handles Edge TLS termination. This means the frontend `nginx` and backend `FastAPI` services listen on non-privileged ports (`8080` and `8000` respectively), and the Route manages external access and TLS.
-   **Container Images**: All container images are based on Red Hat UBI9 and run as non-root users with arbitrary UIDs, adhering to OpenShift's security context constraints (SCCs). Images are hosted on Quay.io.
-   **NetworkPolicy**: Strict `NetworkPolicy` rules are applied to ensure minimal necessary communication between pods, adhering to the principle of least privilege.
