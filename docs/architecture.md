---
title: vLLM Optimizer System Architecture
date: 2026-03-08
updated: 2026-03-15
tags: [architecture, vllm, openshift]
status: published
---

# vLLM Optimizer System Architecture

This document outlines the system architecture of the vLLM Optimizer, a containerized application designed for OpenShift 4.x. It provides load testing, real-time monitoring, benchmark comparison, and automated parameter tuning for vLLM services.

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

The frontend is a React application served by nginx. It runs on port `8080` and provides a user interface with four main tabs: Load Test, Metric Monitoring, Benchmark Comparison, and Auto Tuner. nginx handles static file serving and proxies `/api/*` requests to the FastAPI backend.

### Backend (FastAPI)

The backend is a FastAPI application written in Python, running on port `8000`. It is built on a Red Hat UBI9 Python base image and runs as a non-root user. It exposes various API endpoints for managing load tests, fetching metrics, comparing benchmarks, and tuning vLLM parameters.

#### Key Backend Components:

-   **`main.py`**: This is the entry point for the FastAPI application. It initializes the application, registers routers for different functionalities (load test, metrics, benchmark, tuner), and starts background services like the `MetricsCollector`.
-   **`services/load_engine.py`**: This module contains the asynchronous engine responsible for generating load against the vLLM endpoint. It handles concurrent requests and collects response statistics during load tests.
-   **`services/metrics_collector.py`**: This critical background service periodically collects metrics from the OpenShift cluster. It performs two main tasks:
    1.  **Thanos Querier Integration**: Queries the Thanos Querier (part of the OpenShift Monitoring Stack) for vLLM-specific metrics (e.g., `vllm:num_requests_running`, `vllm:num_requests_waiting`, token counters, latency histograms). It uses a Bearer token for authentication and `verify=False` for self-signed certificates.
    2.  **Kubernetes API Interaction**: Queries the Kubernetes API for vLLM pod counts and readiness status. It uses dynamic label selectors derived from the vLLM Deployment's `matchLabels` to identify relevant pods.
    The collected metrics are then used to update Prometheus client gauges, counters, and histograms, which are exposed via the `/metrics` endpoint.
-   **`services/auto_tuner.py`**: This module implements the auto-tuning functionality using Optuna. It interacts with the Kubernetes API to update vLLM configuration parameters stored in a ConfigMap, then triggers a **Deployment rollout restart** (`patch_namespaced_deployment` with pod template annotation) to apply the new configuration. It polls Deployment rollout completion status before running the evaluation load test.
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
3.  For each trial, the service patches the vLLM ConfigMap (`vllm-config`) with new parameter values via the Kubernetes CoreV1 API.
4.  The service triggers a **Deployment rollout restart** by patching the `llm-ov-predictor` Deployment's pod template annotation (`kubectl.kubernetes.io/restartedAt`). This is equivalent to `kubectl rollout restart deployment/llm-ov-predictor`.
5.  The service polls the Deployment rollout status (`readyReplicas == replicas`) until the new pod is ready (up to 300 seconds).
6.  Once ready, the service runs a load test against the vLLM endpoint to measure performance, and Optuna uses the result to guide the next trial.
7.  Real-time phase events (`applying_config`, `restarting`, `waiting_ready`, `warmup`, `evaluating`) are streamed to the frontend via SSE.
8.  After all trials complete, the best parameters are applied and the vLLM pod is restarted one final time with the optimal configuration.

> **Note**: ConfigMap changes alone do not trigger pod restarts. Since vllm-config is mounted as `envFrom`, the pod must be restarted to pick up new environment variables. The Deployment rollout restart mechanism (step 4) ensures this.

## KServe Integration and Naming Convention

The vLLM instance is deployed on OpenShift using KServe. KServe follows a specific naming convention that the vLLM Optimizer must adhere to for proper interaction.

-   **InferenceService Name**: If the KServe `InferenceService` is named `llm-ov`, configured via `VLLM_DEPLOYMENT_NAME` environment variable.
-   **Deployment Name**: KServe automatically creates a Deployment named `{InferenceService_name}-predictor`, e.g., `llm-ov-predictor`. This is the value used for the `K8S_DEPLOYMENT_NAME` environment variable (used by `MetricsCollector` for pod listing).
-   **Pod Label**: KServe assigns a pod label `app=isvc.{Deployment_name}`, e.g., `app=isvc.llm-ov-predictor`. This label is crucial for the `MetricsCollector` to identify and monitor the correct vLLM pods.
-   **vLLM Endpoint**: The internal service endpoint for the vLLM instance will be `http://llm-ov-predictor.vllm.svc.cluster.local:8080`.
-   **Auto-Tuner Restart**: The auto-tuner uses `K8S_DEPLOYMENT_NAME` (Deployment name, `llm-ov-predictor`) for pod restarts, and `VLLM_DEPLOYMENT_NAME` (InferenceService name, `llm-ov`) is kept separate. Do not confuse the two.

#### New API Endpoints

-   **`GET /api/vllm-config`**: Returns the current `vllm-config` ConfigMap data from Kubernetes. Returns 503 if Kubernetes is not available.
-   **`PATCH /api/vllm-config`**: Updates specific keys in the `vllm-config` ConfigMap. Only keys in `ALLOWED_CONFIG_KEYS` are accepted (422 for invalid keys). Returns 409 if the auto-tuner is currently running.
-   **`GET /api/config`**: Returns frontend configuration including `vllm_endpoint`, `vllm_model_name` (from `VLLM_MODEL` env), and `resolved_model_name` (queried from vLLM `/v1/models` API with 3-second timeout).

## Thanos Querier Integration

The vLLM Optimizer integrates with the OpenShift Monitoring Stack's Thanos Querier to retrieve cluster-wide metrics.

-   **Internal Endpoint**: The internal service endpoint for Thanos Querier is `https://thanos-querier.openshift-monitoring.svc.cluster.local:9091`. This URL is configured via the `PROMETHEUS_URL` environment variable.
-   **Authentication**: Requests to Thanos Querier require a Bearer token, obtained from the ServiceAccount associated with the vLLM Optimizer backend.
-   **TLS Verification**: Due to self-signed certificates in OpenShift environments, `httpx.AsyncClient(verify=False)` is used when making requests to Thanos Querier.

## OpenShift Deployment Topology

The vLLM Optimizer is designed for deployment on OpenShift 4.x, leveraging its native features.

-   **Optimizer Namespace**: The vLLM Optimizer components (backend, frontend) are typically deployed in a dedicated namespace, for example, `vllm-optimizer-dev`.
-   **vLLM Namespace**: The vLLM instance itself resides in a separate namespace, commonly `vllm`.
-   **OpenShift Route**: Frontend access is exposed via an OpenShift Route, which handles Edge TLS termination. This means the frontend `nginx` and backend `FastAPI` services listen on non-privileged ports (`8080` and `8000` respectively), and the Route manages external access and TLS.
-   **Container Images**: All container images are based on Red Hat UBI9 and run as non-root users with arbitrary UIDs, adhering to OpenShift's security context constraints (SCCs). Images are hosted on Quay.io.
-   **NetworkPolicy**: Strict `NetworkPolicy` rules are applied to ensure minimal necessary communication between pods, adhering to the principle of least privilege.
