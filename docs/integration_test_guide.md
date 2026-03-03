# vLLM Optimizer Integration Test Guide

This guide outlines the steps to deploy the vLLM service and verify its integration with the vLLM Optimizer.

## Prerequisites

- OpenShift cluster (4.x) access
- `oc` CLI tool configured
- `podman` or `docker` installed (for local builds, if needed)

## 1. Deploy vLLM Resources (Performed by AI Agent)

The `vllm-optimizer` client is designed to interact with an *already deployed* vLLM service. The AI Agent will now deploy the vLLM ServingRuntime and InferenceService resources into the `vllm` namespace.



The AI Agent will apply the Kustomize manifest from the root of your `vllm-optimizer-vllm-integration` project clone:

```bash
oc apply -k openshift/overlays/dev
```

This command will deploy the following resources to the `vllm` namespace:

- **Namespace**: The `vllm` namespace itself (defined in `openshift/base/00-vllm-namespace.yaml`).
- **PersistentVolumeClaim**: `vllm-model-pvc` (defined in `openshift/base/07-model-pvc.yaml`).
- **Model Downloader Job**: `vllm-model-downloader` (defined in `openshift/base/08-model-download-job.yaml`).
- **Service Account, Role, RoleBinding**: Defined in `openshift/dev-only/vllm-rbac.yaml`.
- **ServingRuntime**: Defined in `openshift/dev-only/vllm-runtime.yaml` for the OpenVINO-based vLLM.
- **InferenceService**: Defined in `openshift/dev-only/vllm-inferenceservice.yaml` for the Qwen2.5-Coder-3B-Instruct-int4-ov model.
- **ServiceMonitor & PrometheusRule**: Defined in `openshift/dev-only/06-vllm-monitoring.yaml` for monitoring vLLM metrics.
- **NetworkPolicy**: Defined in `openshift/dev-only/vllm-networkpolicy.yaml` to allow communication between `vllm-optimizer-dev` and `vllm` namespaces, and with `openshift-monitoring`.

The AI Agent will verify the deployment status using:

```bash
oc get all -n vllm
oc get inferenceservice -n vllm
oc get service llm-ov -n vllm # Verify the vLLM service is named 'llm-ov'
```

## 2. Deploy vLLM Optimizer

Ensure your `vllm-optimizer` is deployed in the `vllm-optimizer-dev` namespace.

```bash
export REGISTRY="quay.io/your-org" # Replace with your Quay.io registry
export IMAGE_TAG="1.0.0"
export VLLM_NAMESPACE="vllm" # The namespace where vLLM is deployed

./deploy.sh dev
```

You can verify the deployment status using:

```bash
oc get all -n vllm-optimizer-dev
```

## 3. Verify Integration (Performed by AI Agent)

Once both vLLM and vLLM Optimizer are deployed, the AI Agent will automatically verify the integration.

### Task 9: Verify vLLM ServiceMonitor Scraping

The AI Agent will check if the OpenShift Monitoring stack (Prometheus) is scraping metrics from the vLLM service.

Example command the AI Agent will use:
```bash
TOKEN=$(oc create token vllm-optimizer-backend -n vllm-optimizer-dev)
THANOS_URL=$(oc get route thanos-querier -n openshift-monitoring -o jsonpath='{"https://"}{.spec.host}')
curl -k -H "Authorization: Bearer $TOKEN" "$THANOS_URL/api/v1/query?query=vllm_total_requests"
```
The AI Agent expects to see metrics being returned, indicating successful scraping.

### Task 10: Verify Backend → vLLM Connectivity

The AI Agent will test direct connectivity from the `vllm-optimizer-backend` pod to the vLLM service's API endpoint.

Example command the AI Agent will use:
```bash
BACKEND_POD=$(oc get pod -n vllm-optimizer-dev -l app=vllm-optimizer-backend -o jsonpath='{.items[0].metadata.name}')
oc exec -n vllm-optimizer-dev $BACKEND_POD -- curl -sS http://llm-ov-predictor.vllm.svc.cluster.local:8080/v1/models
```
The AI Agent expects to receive a JSON response listing the available models. If a DNS error is encountered, the AI Agent will attempt to diagnose the issue (e.g., verify service name and namespace).

### Task 11: Verify Optimizer API Returns vLLM Metrics

The AI Agent will check if the vLLM Optimizer backend's `/metrics` endpoint is exposing vLLM metrics.

Example command the AI Agent will use:
```bash
OPTIMIZER_ROUTE=$(oc get route vllm-optimizer -n vllm-optimizer-dev -o jsonpath='{"http://"}{.spec.host}{"\n"}')
curl -sS "$OPTIMIZER_ROUTE/api/metrics" | grep "vllm_"
```
The AI Agent expects to see output containing `vllm_` prefixed metrics.

### Task 12: Verify Auto Tuner ConfigMap Patch

The AI Agent will verify that the `vllm-config` ConfigMap in the `vllm` namespace has been patched with new values after the auto-tuner is triggered.

Example command the AI Agent will use (after triggering the auto-tuner):
```bash
oc get cm vllm-config -n vllm -o yaml | grep -E "MAX_NUM_SEQS|GPU_MEMORY_UTILIZATION|MAX_MODEL_LEN|ENABLE_CHUNKED_PREFILL"
```
The AI Agent expects to see updated values for the vLLM configuration parameters.

If any of these verification steps fail, the AI Agent will report the issue and attempt to diagnose.
