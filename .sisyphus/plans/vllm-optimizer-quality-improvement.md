# vLLM Optimizer Quality Improvement Plan

## 1. Executive Summary
This plan addresses OpenShift compliance gaps and project quality improvements for the `vllm-optimizer` service. It replaces all base images with Red Hat UBI9, hardens internal TLS communication with Thanos, and automates SecurityContextConstraints (SCC) bindings to prevent deployment failures.

## 2. Scope Boundaries
- **IN SCOPE**:
  - Updating `backend/Dockerfile` and `frontend/Dockerfile` to use UBI9 images (`registry.access.redhat.com/ubi9/python-311` & `nginx-116`).
  - Fixing default Thanos Querier URL, Token Auth, and TLS (`verify=False`) in `backend/services/metrics_collector.py`.
  - Fixing `namespace: ""` bug in `openshift/base/01-namespace-rbac.yaml`.
  - Adding `oc adm policy add-scc-to-user` to `deploy.sh`.
- **OUT OF SCOPE**:
  - Modifying Tekton CI/CD pipeline.
  - Modifying the React frontend source code or adding new UI features.
  - Adding new Prometheus monitoring rules.

## 3. Technical Approach
- **Dockerfiles**: We will switch to Red Hat UBI9 images. Note that package managers change from `apt-get` (Debian) to `microdnf` (UBI).
- **Thanos API**: `httpx.AsyncClient(verify=False)` will be configured. We will read the ServiceAccount token from `/var/run/secrets/kubernetes.io/serviceaccount/token` to properly authenticate as required by OpenShift.
- **RBAC**: The `ClusterRoleBinding` subject namespace will be fixed to `vllm-optimizer` or explicitly omitted depending on Kustomize overlay logic, but since it's hardcoded as `""`, we will remove the explicit namespace override so it takes the default context or explicitly patch it.
- **Deploy Script**: `deploy.sh` will auto-run `oc adm policy add-scc-to-user vllm-optimizer-scc -z vllm-optimizer-backend -n "${NAMESPACE}"` after applying overlays.

## 4. Execution Tasks

- [x] **Task 1: Update Dockerfiles (UBI9 Base)**
  - **What**: Change `backend/Dockerfile` to use `registry.access.redhat.com/ubi9/python-311` (or similar UBI9 Python image). Change `frontend/Dockerfile` to use `registry.access.redhat.com/ubi9/nginx-116` (or similar UBI9 nginx image). Replace `apt-get` with `microdnf`.
  - **QA**: Run `podman build` locally to ensure the new base images pull correctly and the build succeeds.

- [x] **Task 2: Fix metrics_collector.py (Thanos Auth & TLS)**
  - **What**: In `backend/services/metrics_collector.py`:
    1. Change default `PROMETHEUS_URL` to `https://thanos-querier.openshift-monitoring.svc.cluster.local:9091`.
    2. Add logic to read the token from `/var/run/secrets/kubernetes.io/serviceaccount/token`.
    3. Update `httpx.AsyncClient(timeout=5)` to `httpx.AsyncClient(timeout=5, verify=False, headers={"Authorization": f"Bearer {token}"})`.
  - **QA**: Check for syntax errors with `python -m py_compile backend/services/metrics_collector.py`.

- [x] **Task 3: Fix RBAC YAML (Namespace correction)**
  - **What**: In `openshift/base/01-namespace-rbac.yaml`, find the `ClusterRoleBinding` named `vllm-optimizer-controller` and change `namespace: ""` to `namespace: "vllm-optimizer"` (or remove the namespace override).
  - **QA**: Run `oc apply --dry-run=client -k openshift/base` to ensure valid YAML structure.

- [x] **Task 4: Automate SCC Policy in deploy.sh**
  - **What**: In `deploy.sh`, locate the `oc apply` kustomize block. Immediately after it, add `oc adm policy add-scc-to-user vllm-optimizer-scc -z vllm-optimizer-backend -n "${NAMESPACE}" || warn "SCC assignment failed."` and same for frontend if needed.
  - **QA**: Run `bash -n deploy.sh` to ensure no syntax errors.

## Final Verification Wave
- [x] Verify `podman build` succeeds for both images using UBI9.
- [x] Verify `metrics_collector.py` correctly reads the token and passes it to the `httpx` client.
- [x] Run a dry-run of the deployment script (`./deploy.sh dev --dry-run`) to ensure no syntax errors.