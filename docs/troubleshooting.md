---
title: "vLLM Optimizer Troubleshooting Guide"
date: 2026-03-08
updated: 2026-03-08
tags: [troubleshooting, openshift, debugging]
status: published
---

# vLLM Optimizer Troubleshooting Guide

This guide provides solutions to common issues encountered when deploying and operating the vLLM Optimizer on OpenShift. Each entry follows a Symptom → Cause → Diagnosis → Fix structure.

## Quick Diagnosis Checklist

Before diving into specific issues, use this checklist to quickly narrow down the problem:

1.  **Pod Status**: Are all `vllm-optimizer-backend` and `vllm-optimizer-frontend` pods in a `Running` state?
    -   `oc get pods -n vllm-optimizer-dev`
    -   If not, check pod events: `oc get events -n vllm-optimizer-dev --sort-by=.lastTimestamp | tail -20`
2.  **Backend Logs**: Are there any errors in the backend logs?
    -   `oc logs -l app=vllm-optimizer-backend -n vllm-optimizer-dev -f`
3.  **Metrics Endpoint**: Is the backend's `/api/metrics` endpoint accessible and returning data?
    -   `oc exec -it $(oc get pod -l app=vllm-optimizer-backend -n vllm-optimizer-dev -o name | head -1) -n vllm-optimizer-dev -- curl localhost:8000/api/metrics`
4.  **Thanos Connectivity**: Can the backend connect to Thanos Querier?
    -   Check backend logs for `Thanos connection failed` or `403` errors.
    -   Manually test Thanos query: See "Useful Debug Commands" section.
5.  **vLLM Pods**: Are the vLLM inference pods running and healthy in the `vllm` namespace?
    -   `oc get pods -n vllm`

---

## Common Troubleshooting Scenarios

### 1. SCC Error on Pod Startup

**Symptom**: Backend or frontend pods fail to start with `Error: container has runAsNonRoot and image has non-numeric user (user: root)` or similar `securityContext` related errors.

**Cause**: The OpenShift Security Context Constraints (SCC) are preventing the container from running with the necessary permissions. The `vllm-optimizer-scc` is not bound to the service account.

**Diagnosis**:
1.  Check pod logs for `permission denied` or `runAsNonRoot` errors.
2.  Describe the failing pod and look for `securityContext` related warnings or errors:
    `oc describe pod -l app=vllm-optimizer-backend -n vllm-optimizer-dev | grep -i scc`

**Fix**: Bind the custom SCC to the service account used by the backend.
```bash
oc adm policy add-scc-to-user vllm-optimizer-scc \
  -z vllm-optimizer-backend -n vllm-optimizer-dev
```
(Replace `vllm-optimizer-backend` with `vllm-optimizer-frontend` if the frontend pod is affected.)

### 2. Image Pull Failure

**Symptom**: Pods remain in `ImagePullBackOff` or `ErrImagePull` status.

**Cause**: OpenShift cannot pull the container image from Quay.io. This can be due to incorrect image stream configuration, missing pull secret, or the image not being pushed to Quay.io.

**Diagnosis**:
1.  Check pod events for details on the pull failure:
    `oc get events -n vllm-optimizer-dev --field-selector reason=Failed,reason=ErrImagePull`
2.  Verify the image stream exists and points to the correct Quay.io repository.

**Fix**: Manually import the image into OpenShift's internal registry. This ensures OpenShift knows about the image and can pull it.
```bash
oc import-image vllm-optimizer-backend:latest \
  --from=quay.io/joopark/vllm-optimizer-backend:latest \
  --confirm -n vllm-optimizer-dev
```
(Adjust image name and namespace as needed for frontend.)

### 3. Thanos Access Denied (403 Forbidden)

**Symptom**: Backend logs show `httpx.HTTPStatusError: Client error '403 Forbidden'` when trying to query Thanos Querier. MetricsCollector reports `collector_version=unknown`.

**Cause**: The service account used by the `vllm-optimizer-backend` pod does not have the necessary permissions to access the OpenShift Monitoring Stack (Thanos Querier). Specifically, it lacks the `cluster-monitoring-view` ClusterRole.

**Diagnosis**:
1.  Check backend logs for `403 Forbidden` errors from Thanos.
2.  Verify the `cluster-monitoring-view` ClusterRoleBinding for the backend service account.

**Fix**: Ensure the `cluster-monitoring-view` ClusterRole is bound to the `vllm-optimizer-backend` service account. This binding is typically defined in `openshift/base/05-monitoring.yaml`. Re-apply the monitoring configuration if necessary.
```bash
oc apply -f openshift/base/05-monitoring.yaml -n vllm-optimizer-dev
```

### 4. MetricsCollector Shows All-Zero Metrics

**Symptom**: The dashboard displays all zeros for vLLM-related metrics (throughput, latency, KV cache, GPU usage), even when vLLM is active. The `/api/metrics` endpoint might show `vllm:` metrics, but their values are zero or missing.

**Cause**: This can stem from several issues related to how MetricsCollector identifies and queries vLLM pods or connects to Thanos.

**Diagnosis**:
1.  **Check MetricsCollector status**:
    `oc exec -it $(oc get pod -l app=vllm-optimizer-backend -n vllm-optimizer-dev -o name | head -1) -n vllm-optimizer-dev -- curl -X POST localhost:8000/startup_metrics`
    -   If `collector_version` is `unknown`, Thanos connection failed (see issue 3).
    -   If `pods=0`, MetricsCollector cannot find vLLM pods.
2.  **Verify `K8S_DEPLOYMENT_NAME`**: The `K8S_DEPLOYMENT_NAME` environment variable might be set incorrectly. KServe creates a Deployment with a specific naming convention.
    -   `oc get deployment -n vllm`
    -   Look for the deployment name corresponding to your KServe InferenceService (e.g., `llm-ov-predictor` for `llm-ov`).
    -   The `K8S_DEPLOYMENT_NAME` should be `llm-ov-predictor`, not `llm-ov`.

**Fix**:
1.  **Correct `K8S_DEPLOYMENT_NAME`**: Update the `vllm-optimizer-backend` deployment to use the correct KServe-generated deployment name.
    -   Edit `openshift/base/03-backend.yaml` or the relevant overlay to set `K8S_DEPLOYMENT_NAME` to the correct value (e.g., `llm-ov-predictor`).
    -   Re-apply the deployment: `oc apply -k openshift/overlays/dev` (or prod).
2.  **Trigger vLLM traffic**: If metrics are still zero, ensure there is active inference traffic to the vLLM endpoint. MetricsCollector only reports observed values. Send a test request to the vLLM endpoint.

### 5. Integration Tests `skip` After Auto Tuner Test

**Symptom**: During integration test runs, tests following the `test_auto_tuner` often get skipped with a message indicating high latency or system overload.

**Cause**: The `auto_tuner` test performs inference requests to the vLLM, which can temporarily increase the p99 latency. The integration test suite includes a `skip_if_overloaded` fixture that checks for elevated p99 latency. If the latency remains high, subsequent tests are skipped to prevent false failures. The Thanos rate window (1 minute) needs time to roll over.

**Diagnosis**:
1.  Observe test output for `SKIPPED` messages related to `skip_if_overloaded`.
2.  Check the health and resource usage of the vLLM pods in the `vllm` namespace.
    `oc get pods -n vllm`

**Fix**:
1.  **Wait**: The `skip_if_overloaded` fixture waits up to 120 seconds for the latency to normalize. If tests are consistently skipped, ensure the vLLM cluster has sufficient resources and is not genuinely overloaded.
2.  **Verify vLLM health**: Confirm that the vLLM pods are `Running` and not experiencing issues. If vLLM pods are restarting or unhealthy, address those issues first.

### 6. Backend Crash on Startup (Import Errors)

**Symptom**: The `vllm-optimizer-backend` pod crashes on startup with `ModuleNotFoundError` or `ImportError` messages, often related to internal project modules.

**Cause**: Incorrect import statements within the backend Python code. Specifically, using `backend.` as a prefix for internal imports (e.g., `from backend.services.shared import ...`) when the code is already running within the `backend` package. Python's module resolution expects bare imports in such cases.

**Diagnosis**:
1.  Check backend logs for `ModuleNotFoundError` or `ImportError` messages.
2.  Look for import statements that include `backend.` as a prefix for modules within the `backend` directory.

**Fix**: Remove the `backend.` prefix from internal import statements.
-   **Incorrect**: `from backend.services.shared import metrics_collector`
-   **Correct**: `from services.shared import metrics_collector`
This applies to all internal imports (e.g., `from models.load_test import ...`, `from routers.load_test import ...`).

### 7. Thanos TLS Certificate Error

**Symptom**: Backend logs show `httpx.ConnectError: [SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed` when connecting to Thanos Querier.

**Cause**: Thanos Querier in OpenShift typically uses self-signed certificates, which are not trusted by default by `httpx`.

**Diagnosis**:
1.  Check backend logs for `CERTIFICATE_VERIFY_FAILED` errors.
2.  Verify the `PROMETHEUS_URL` environment variable is correctly set to the Thanos Querier endpoint.

**Fix**: The `MetricsCollector` is designed to handle this by setting `verify=False` in `httpx.AsyncClient`. Ensure this setting is active. If the error persists, double-check the `PROMETHEUS_URL` environment variable for typos or incorrect values.
-   **Correct `PROMETHEUS_URL`**: `https://thanos-querier.openshift-monitoring.svc.cluster.local:9091`

### 8. `oc create token` vs `oc serviceaccounts get-token`

**Symptom**: Attempts to generate a service account token using `oc serviceaccounts get-token` fail or return a warning about deprecation.

**Cause**: The `oc serviceaccounts get-token` command is deprecated in newer versions of OpenShift/Kubernetes. The recommended method is `oc create token`.

**Diagnosis**:
1.  Command line output indicates deprecation or failure for `oc serviceaccounts get-token`.

**Fix**: Always use `oc create token` to generate service account tokens.
```bash
TOKEN=$(oc create token vllm-optimizer-backend -n vllm-optimizer-dev)
```

### 9. Dashboard Shows Pod Metrics but No Request/Token Metrics

**Symptom**: The dashboard correctly displays the number of vLLM pods, but throughput (requests/tokens per second) and latency metrics remain at zero.

**Cause**: The vLLM inference service is running, but no actual inference requests have been sent to it. MetricsCollector relies on Prometheus metrics, which are only updated when vLLM processes requests.

**Diagnosis**:
1.  Verify vLLM pods are running: `oc get pods -n vllm`.
2.  Check vLLM logs for any incoming request activity.
3.  Manually send a test inference request to the vLLM endpoint.

**Fix**: Trigger a test request to the vLLM endpoint. This will "warm up" the MetricsCollector and Prometheus, causing vLLM to emit metrics. The load test feature of the vLLM Optimizer itself can be used for this.

### 10. Kustomize Apply Fails (Namespace Not Found)

**Symptom**: Running `oc apply -k openshift/overlays/dev` (or prod) fails with errors like `Error from server (NotFound): namespaces "vllm-optimizer-dev" not found`.

**Cause**: The target namespace for the deployment does not exist. Kustomize overlays often assume the base resources, including the namespace, have already been applied.

**Diagnosis**:
1.  Command line output clearly states `namespace "..." not found`.
2.  Check if the namespace exists: `oc get namespace vllm-optimizer-dev`

**Fix**: Apply the base Kustomize configuration first, which includes the namespace and RBAC setup, before applying the overlays.
```bash
oc apply -k openshift/base -n vllm-optimizer-dev # Apply base resources including namespace
oc apply -k openshift/overlays/dev -n vllm-optimizer-dev # Then apply the overlay
```
(Ensure `vllm-optimizer-dev` is the correct namespace.)

---

## Useful Debug Commands

These commands can help diagnose issues in your OpenShift cluster.

-   **Pod Status**: `oc get pods -n vllm-optimizer-dev`
-   **Route URL**: `oc get route vllm-optimizer -n vllm-optimizer-dev`
-   **Backend Logs**: `oc logs -l app=vllm-optimizer-backend -n vllm-optimizer-dev -f`
-   **SCC Application Check**: `oc describe pod -l app=vllm-optimizer-backend -n vllm-optimizer-dev | grep -i scc`
-   **OpenShift Events**: `oc get events -n vllm-optimizer-dev --sort-by=.lastTimestamp | tail -20`
-   **Prometheus Metrics Endpoint (from inside pod)**:
    ```bash
    oc exec -it $(oc get pod -l app=vllm-optimizer-backend -n vllm-optimizer-dev -o name | head -1) \
      -n vllm-optimizer-dev -- curl localhost:8000/api/metrics
    ```
-   **Thanos Querier Direct Query (with token)**:
    ```bash
    TOKEN=$(oc create token vllm-optimizer-backend -n vllm-optimizer-dev)
    curl --socks5-hostname 127.0.0.1:8882 -H "Authorization: Bearer $TOKEN" \
      https://thanos-querier-openshift-monitoring.apps.compact.jooan.local/api/v1/query \
      --data-urlencode 'query=vllm:num_requests_running' -k
    ```
-   **MetricsCollector Internal Status**:
    ```bash
    oc exec -it $(oc get pod -l app=vllm-optimizer-backend -n vllm-optimizer-dev -o name | head -1) \
      -n vllm-optimizer-dev -- curl -X POST localhost:8000/startup_metrics
    ```
-   **vLLM Deployment Name Verification**: `oc get deployment -n vllm`
-   **vLLM Pod Status**: `oc get pods -n vllm`
