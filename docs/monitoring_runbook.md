---
title: "Monitoring Runbook - vLLM Optimizer Prometheus Integration"
date: 2026-02-24
updated: 2026-03-08
author: GPS Consultant
tags: [monitoring, prometheus, vllm, runbook]
status: published
aliases: []
---

## Executive Summary

This runbook provides operating procedures for the Prometheus-based monitoring integration of the vLLM Optimizer backend on OpenShift. It covers verification, troubleshooting, and maintenance of the `/api/metrics` endpoint and the associated ServiceMonitor configuration.

**Scope**: Tasks 4–9 of the vLLM monitoring integration — exposing metrics, wiring the MetricsCollector, testing, OpenShift alignment, and documentation.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│  OpenShift Monitoring (Thanos/ Prometheus)                 │
│         ▲                                                  │
│         │ scrape /api/metrics                              │
│  ServiceMonitor (vllm-optimizer-backend)                  │
│         │                                                  │
│  Backend Deployment (FastAPI)                              │
│  ┌─────────────────────────────────────────────────────┐  │
│  │ GET /api/metrics → generate_metrics()               │  │
│  │   - reads from prometheus_client REGISTRY          │  │
│  │   - returns text/plain; version=0.0.4              │  │
│  └─────────────────────────────────────────────────────┘  │
│         ▲                                                  │
│  MetricsCollector (background)                            │
│  - updates gauges/histograms from vLLM data               │
└─────────────────────────────────────────────────────────────┘
```

## Metric Definitions

The backend exposes 8 vLLM-specific metrics:

| Name | Type | Labels | Description |
|------|------|--------|-------------|
| `vllm:request_success_total` | Counter | `model` | Total successful vLLM requests |
| `vllm:generation_tokens_total` | Counter | `model` | Total tokens generated |
| `vllm:num_requests_running` | Gauge | - | Currently running requests |
| `vllm:num_requests_waiting` | Gauge | - | Requests in queue |
| `vllm:gpu_cache_usage_perc` | Gauge | - | GPU KV cache usage % |
| `vllm:gpu_utilization` | Gauge | - | GPU utilization % |
| `vllm:time_to_first_token_seconds` | Histogram | `model` | TTFT distribution (seconds) |
| `vllm:e2e_request_latency_seconds` | Histogram | `model` | End-to-end latency (seconds) |

## Verification Procedures

### 1. Local Unit Tests (Pre-commit)

Run the comprehensive unit tests for the backend, excluding integration tests:

```bash
cd backend && python3 -m pytest tests/ -x -q -m "not integration"
```

**Expected**: All tests pass. These tests mock `generate_metrics()` and validate Prometheus format, metric presence, and histogram structure.

**Evidence**: Capture output to `.sisyphus/evidence/task-6-pytest-output.txt`

### 2. Integration Test (No Mocks, In-cluster)

Verify the full stack without mocking by running the integration tests inside a deployed backend pod:

```bash
NS=vllm-optimizer-dev
BACKEND_POD=$(oc get pod -n $NS -l app=vllm-optimizer-backend -o name | head -1)
oc exec -n $NS $BACKEND_POD -- env \
  PERF_TEST_BACKEND_URL=http://localhost:8000 \
  VLLM_ENDPOINT=http://llm-ov-predictor.vllm-lab-dev.svc.cluster.local:8080 \
  VLLM_MODEL=OpenVINO/Phi-4-mini-instruct-int4-ov \
  VLLM_NAMESPACE=vllm-lab-dev \
  OPTIMIZER_NAMESPACE=vllm-optimizer-dev \
  python3 -m pytest /app/tests/integration/performance/ -v --tb=short -m "integration"
```

**Expected**: Tests pass, confirming that:
- The `/api/metrics` endpoint returns 200.
- Content-Type is `text/plain`.
- All 8 metric HELP/TYPE lines are present.
- MetricsCollector successfully collects and exposes vLLM metrics.

**Note**: Histogram bucket lines may not appear until the MetricsCollector has made observations. This is acceptable for a fresh app.

### 3. Manual Endpoint Validation

Start the backend locally:

```bash
cd backend
uvicorn main:app --reload --port 8000
```

Query the metrics endpoint:

```bash
curl -s http://localhost:8000/api/metrics | head -30
```

**Expected**: Output starts with `# HELP vllm:...` and `# TYPE vllm:...`. Content-Type header: `text/plain; version=0.0.4`.

**Check all metrics**:

```bash
curl -s http://localhost:8000/api/metrics | grep '^vllm:' | awk '{print $1}' | sort -u
```

Should list all 8 base metric base names (without suffixes).



### 5. Deployment Verification (Dev)

If OpenShift cluster is available:

```bash
# Deploy to dev namespace
./deploy.sh dev

# Wait for pods
oc rollout status deployment/vllm-optimizer-backend -n vllm-optimizer-dev

# Port-forward to test endpoint from inside cluster
oc port-forward svc/vllm-optimizer-backend 8000:8000 -n vllm-optimizer-dev &
curl -s http://localhost:8000/api/metrics | head -20
```

**Expected**: Prometheus output accessible through the service. No 404s.

### 6. ServiceMonitor Scrape Verification

Once deployed, check Prometheus targets:

```bash
# Get Thanos Querier route
THANOS_URL=$(oc get route thanos-querier -n openshift-monitoring -o jsonpath='{.spec.host}')

# Use backend service account token to query
TOKEN=$(oc create token vllm-optimizer-backend -n vllm-optimizer-dev)
curl -k -H "Authorization: Bearer $TOKEN" \
  "https://$THANOS_URL/api/v1/targets" | jq '.data.activeTargets[] | select(.labels.job=="vllm-optimizer-backend")'
```

**Expected**: Target state `up == 1` and last scrape successful.

### 7. Log Inspection

Check that MetricsCollector started via shim:

```bash
oc logs -l app=vllm-optimizer-backend -n vllm-optimizer-dev | grep "StartupShim"
```

**Expected**: `[StartupShim] MetricsCollector started (background)`

## Troubleshooting

### Symptom: `/api/metrics` returns 404

**Possible causes**:
- Metrics router not loaded due to import errors in other routers.
- Endpoint path misconfigured (should be `/api/metrics`, not `/metrics`).

**Steps**:
1. Check app logs for import errors on startup.
2. Verify that `backend/routers/metrics.py` defines `@router.get("")` (empty string) and that the router is included with `prefix="/api/metrics"`.
3. Run `oc exec -it $(oc get pod -l app=vllm-optimizer-backend -n vllm-optimizer-dev -o name | head -1) -n vllm-optimizer-dev -- python3 -c "from backend.main import app; print(app.routes)"` to list all registered routes; ensure `/api/metrics` appears.
4. Fix any `ModuleNotFoundError` by correcting relative imports (use `from ..models.load_test import ...` instead of `from models...`).

### Symptom: Dashboard shows all-zero metrics (throughput, tokens, pods)

**Possible causes**:
- `K8S_DEPLOYMENT_NAME` environment variable is set to the KServe `InferenceService` name (e.g., `llm-ov`) instead of the actual KServe-generated `Deployment` name (e.g., `llm-ov-predictor`). The MetricsCollector uses this variable to select the correct vLLM pods.

**Fix**:
1. Verify the actual Deployment name generated by KServe for your `InferenceService`. For an `InferenceService` named `llm-ov`, the Deployment will typically be `llm-ov-predictor`.
2. Ensure the `K8S_DEPLOYMENT_NAME` environment variable in the `vllm-optimizer-backend` deployment is set to the KServe-generated Deployment name (e.g., `llm-ov-predictor`).
3. The label selector for pods is derived dynamically from the Deployment's `spec.selector.matchLabels`, so setting the correct `K8S_DEPLOYMENT_NAME` is crucial for the MetricsCollector to find the vLLM pods.

### Symptom: Prometheus scrapes but no vLLM metrics appear

**Possible causes**:
- MetricsCollector not running or not updating the REGISTRY.
- Metrics not being observed (zero values may not be emitted depending on prometheus_client configuration).

**Steps**:
1. Check that the shim is loaded: `StartupShim` message in logs.
2. Verify collector loop is running (no exceptions).
3. Confirm that `update_metrics()` is called and sets gauge values; histograms require `.observe()` calls to create bucket samples.
4. If metrics still absent, manually trigger a scrape by calling `/api/metrics` and inspect output for `vllm:` lines. Zero-value gauges are emitted; histograms with no observations emit only HELP/TYPE.

### Symptom: ServiceMonitor not scraping

**Possible causes**:
- ServiceMonitor path mismatch (`/metrics` vs `/api/metrics`).
- Service port name mismatch (should be `http`).
- Missing `openshift.io/cluster-monitoring: "true"` label on ServiceMonitor.

**Steps**:
1. Inspect `openshift/base/05-monitoring.yaml` and confirm `path: /api/metrics` is set under `spec.endpoints`.
2. Ensure backend Service (`03-backend.yaml`) port name is `http`.
3. Check ServiceMonitor selector matches backend service labels (`app: vllm-optimizer-backend`).
4. Use `oc get servicemonitor -n vllm-optimizer` and inspect `.spec.endpoints[0].path`.

### Symptom: Tests fail with `NameError: name 'app' is not defined` from `startup_metrics_shim.py`

**Cause**: The `@app.on_event("shutdown")` decorator was mistakenly placed at module level instead of inside `register(app)`.

**Fix**: Move the `@app.on_event("shutdown")` handler inside the `register` function (as already fixed). Re-run tests.

## Cross-References

- [[AGENTS]] — OpenCode agent orchestration guidelines and behavior contracts.
- [[AGENTS#delegation-protocol]] — Delegation protocol for agent-based task execution.
- [[AGENTS#tool-usage-discipline]] — Tool usage discipline and best practices.
- `.sisyphus/plans/vllm-monitoring-integration.md` — Master plan for monitoring integration (Tasks 1–9).
- `openshift/base/05-monitoring.yaml` — ServiceMonitor and alerting rules.
- `backend/services/metrics_collector.py` — Background collector that updates Prometheus metrics.
- `backend/metrics/prometheus_metrics.py` — Metric definitions and `generate_metrics()`.

## Maintenance Notes

- **Adding new metrics**: Define in `prometheus_metrics.py` and update `update_metrics()` accordingly. Extend tests to verify presence.
- **Changing endpoint path**: Update `routers/metrics.py`, ServiceMonitor path, and validation script together.
- **Metric retention**: Prometheus determines retention via `--storage.tsdb.retention.time`. Application does not store history.

## Appendix: Quick Reference Commands

| Action | Command |
|--------|---------|
| Run unit tests | `cd backend && python3 -m pytest tests/ -x -q -m "not integration"` |
| Run integration test (in-cluster) | `NS=vllm-optimizer-dev; BACKEND_POD=$(oc get pod -n $NS -l app=vllm-optimizer-backend -o name | head -1); oc exec -n $NS $BACKEND_POD -- env PERF_TEST_BACKEND_URL=http://localhost:8000 VLLM_ENDPOINT=http://llm-ov-predictor.vllm-lab-dev.svc.cluster.local:8080 VLLM_MODEL=OpenVINO/Phi-4-mini-instruct-int4-ov VLLM_NAMESPACE=vllm-lab-dev OPTIMIZER_NAMESPACE=vllm-optimizer-dev python3 -m pytest /app/tests/integration/performance/ -v --tb=short -m "integration"` |
| Local endpoint check | `curl -s http://localhost:8000/api/metrics | head -30` |
| Get Thanos token | `TOKEN=$(oc create token vllm-optimizer-backend -n vllm-optimizer-dev)` |
