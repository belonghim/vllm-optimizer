---
title: OpenShift Deployment Guide
date: 2026-03-08
updated: 2026-03-08
tags: [deployment, openshift, kustomize]
status: published
---

# OpenShift Deployment Guide for vLLM Optimizer

This guide provides comprehensive instructions for deploying the vLLM Optimizer application on an OpenShift 4.x cluster.

## Prerequisites

To deploy the vLLM Optimizer, ensure you have the following tools and access configured:

*   **OpenShift CLI (`oc`)**: Installed and configured to connect to your OpenShift 4.x cluster.
*   **Podman**: Installed for building container images locally.
*   **Kustomize Binary**: The `kustomize` executable should be present in the project root directory.
*   **OpenShift Cluster Access**: You need appropriate permissions to create namespaces, deploy applications, and manage RBAC within your OpenShift cluster.
*   **Quay.io Credentials**: Access to a Quay.io repository for pushing built container images. Ensure your `podman` is logged in to Quay.io or that your OpenShift cluster has image pull secrets configured for Quay.io.

## Environment Variables

The vLLM Optimizer uses several environment variables for configuration. These are typically set before running deployment scripts or within your OpenShift manifests.

| Variable Name | Description | Example |
| :------------ | :---------- | :------ |
| `REGISTRY` | The container image registry where images are stored. | `quay.io/joopark` |
| `IMAGE_TAG` | The tag to apply to the built container images. | `1.0.0` |
| `VLLM_NAMESPACE` | The OpenShift namespace where the vLLM service is deployed. | `vllm` |
| `PROMETHEUS_URL` | The internal URL for the Thanos Querier service within OpenShift Monitoring. This is used by the backend to query metrics. | `https://thanos-querier.openshift-monitoring.svc.cluster.local:9091` |
| `K8S_NAMESPACE` | The Kubernetes namespace where vLLM pods are to be queried. | `vllm` |
| `K8S_DEPLOYMENT_NAME` | **Crucial**: This must be the actual Deployment name created by KServe for your vLLM InferenceService (e.g., `llm-ov-predictor`), not the InferenceService name itself (`llm-ov`). | `llm-ov-predictor` |
| `K8S_CONFIGMAP_NAME` | The name of the ConfigMap used by the vLLM service. | `vllm-config` |
| `VLLM_ENDPOINT` | The internal inference endpoint for the vLLM service, used for testing and load generation. | `http://llm-ov-predictor.vllm.svc.cluster.local:8080` |
| `VLLM_MODEL` | The name of the vLLM model being used for testing. | `Qwen2.5-Coder-3B-Instruct-int4-ov` |

## Build & Push Images

The vLLM Optimizer consists of a backend and a frontend component, each requiring its own container image. Images are built using Podman and pushed to Quay.io.

1.  **Build Backend Image:**
    ```bash
    podman build -t ${REGISTRY}/vllm-optimizer-backend:${IMAGE_TAG} ./backend
    ```

2.  **Build Frontend Image:**
    ```bash
    podman build -t ${REGISTRY}/vllm-optimizer-frontend:${IMAGE_TAG} ./frontend
    ```

3.  **Push Images to Quay.io:**
    ```bash
    podman push ${REGISTRY}/vllm-optimizer-backend:${IMAGE_TAG}
    podman push ${REGISTRY}/vllm-optimizer-frontend:${IMAGE_TAG}
    ```

    *Replace `${REGISTRY}` and `${IMAGE_TAG}` with your actual values.*

## Deploy to OpenShift

Deployment to OpenShift can be done using the provided `deploy.sh` script or directly with `oc apply` and Kustomize.

### Using `deploy.sh` Script

The `deploy.sh` script simplifies the build, push, and deployment process.

1.  **Set Environment Variables:**
    ```bash
    export REGISTRY="quay.io/joopark"
    export IMAGE_TAG="1.0.0"
    export VLLM_NAMESPACE="vllm"
    ```

2.  **Deploy to Development Environment:**
    This command builds images, pushes them to the registry, and then applies the Kustomize overlay for the `dev` environment.
    ```bash
    ./deploy.sh dev
    ```

3.  **Development Deployment Options:**
    *   **Dry Run (Preview Changes):**
        ```bash
        ./deploy.sh dev --dry-run
        ```
    *   **Deploy Without Rebuilding Images:**
        ```bash
        ./deploy.sh dev --skip-build
        ```

4.  **Deploy to Production Environment:**
    For production, ensure `IMAGE_TAG` is set to the desired version.
    ```bash
    IMAGE_TAG="1.0.0" ./deploy.sh prod
    ```

### Direct Kustomize Deployment

You can also apply the Kustomize overlays directly using `oc apply`.

1.  **Deploy to Development Environment:**
    ```bash
    oc apply -k openshift/overlays/dev
    ```

2.  **Deploy to Production Environment:**
    ```bash
    oc apply -k openshift/overlays/prod
    ```

## Post-Deploy Verification

After deployment, verify the application's health and accessibility using the following commands. Replace `vllm-optimizer-dev` with your actual namespace if different.

```bash
NS=vllm-optimizer-dev

# Check Pod status
oc get pods -n $NS

# Get the Route URL for the frontend
oc get route vllm-optimizer -n $NS

# Stream logs from the backend pod
oc logs -l app=vllm-optimizer-backend -n $NS -f

# Verify Security Context Constraints (SCC) application
oc describe pod -l app=vllm-optimizer-backend -n $NS | grep -i scc

# Check recent OpenShift events for any issues
oc get events -n $NS --sort-by=.lastTimestamp | tail -20

# Access the backend''s Prometheus metrics endpoint
oc exec -it $(oc get pod -l app=vllm-optimizer-backend -n $NS -o name | head -1) \
  -n $NS -- curl localhost:8000/metrics
```

## RBAC & SCC Configuration

The vLLM Optimizer requires specific Role-Based Access Control (RBAC) and Security Context Constraints (SCC) to operate correctly within OpenShift.

*   **ServiceAccount**: The `vllm-optimizer-backend` ServiceAccount is defined in `openshift/base/01-namespace-rbac.yaml`.
*   **Custom SCC**: A custom SCC named `vllm-optimizer-scc` is also defined in `01-namespace-rbac.yaml` to ensure non-root execution and other security best practices.
*   **ClusterRoleBinding for Thanos**: To allow the vLLM Optimizer backend to query the OpenShift Monitoring Stack (Thanos Querier), a `ClusterRoleBinding` for the `cluster-monitoring-view` ClusterRole is applied in `openshift/base/05-monitoring.yaml`.

**Troubleshooting SCC Issues:**
If you encounter SCC-related errors, you might need to manually add the SCC to the ServiceAccount:
```bash
oc adm policy add-scc-to-user vllm-optimizer-scc \
  -z vllm-optimizer-backend -n vllm-optimizer-dev
```

## Tekton CI/CD Pipeline

The project includes Tekton Pipelines for automated CI/CD workflows.

*   **Pipeline Definition**: The main pipeline is defined in `openshift/tekton/pipeline.yaml`.
*   **Pipeline Stages**: The pipeline typically includes stages for:
    1.  Git Clone
    2.  Test
    3.  Buildah Build
    4.  Quay.io Push
    5.  Kustomize Deploy
*   **Performance Pipeline**: A dedicated pipeline for performance testing is located at `openshift/tekton/performance-pipeline.yaml`.
*   **Secrets**:
    *   **Webhook Secret**: `github-webhook-secret` is used for triggering pipelines via GitHub webhooks.
    *   **Push Secret**: `quay-push-secret` is used for authenticating with Quay.io to push images.

### Managing Tekton Pipelines

1.  **Deploy Pipeline Resources:**
    ```bash
    oc apply -f openshift/tekton/pipeline.yaml -n vllm-optimizer
    ```

2.  **Manually Start a Pipeline Run:**
    ```bash
    tkn pipeline start vllm-optimizer-pipeline -n vllm-optimizer
    ```

3.  **Monitor Pipeline Logs:**
    ```bash
    tkn pipelinerun logs -f -n vllm-optimizer
    ```
