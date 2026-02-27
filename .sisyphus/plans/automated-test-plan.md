## Test Plan: vLLM Optimizer OpenShift Deployment (Automated Focus)

This plan outlines the steps for comprehensively testing the `vllm-optimizer` application in an OpenShift environment, with a strong focus on automation using `deploy.sh`, `oc` commands, and `curl` for verification. It builds upon the manual testing guide from `.sisyphus/testing_guide.md` and extends it to incorporate automated checks.

## I. Preparation and Environment Setup

### 1. Prerequisite Checks
- Verify `oc` CLI is installed and configured for the target OpenShift cluster.
- Verify `podman` is installed for building container images.

### 2. Environment Variable Configuration
Set the following environment variables. The `REGISTRY` and `VLLM_NAMESPACE` should be configured according to your OpenShift environment. `DEPLOY_ENV` will be set to `dev` for testing, which will result in a target namespace of `vllm-optimizer-dev`.

```bash
export REGISTRY="quay.io/joopark" # Replace with your registry, e.g., quay.io/your-org
export VLLM_NAMESPACE="vllm"      # Replace with the namespace where vLLM service is deployed
export DEPLOY_ENV="dev"           # Using 'dev' environment for testing
```

## II. Automated Application Deployment

### 1. Deploy the Application
Execute the `deploy.sh` script from the project root to build, push, and deploy the `vllm-optimizer`.

**Action**: Run the deployment script.
```bash
./deploy.sh $DEPLOY_ENV
```

## III. Automated Deployment Verification

### 1. Pod Status Check
Verify that all `vllm-optimizer` pods are running and ready.

**Action**: Check pod status and wait for readiness.
```bash
# Wait for pods to be ready (timeout after 5 minutes)
oc wait --for=condition=Ready pod -l app=vllm-optimizer-backend -n "vllm-optimizer-${DEPLOY_ENV}" --timeout=300s
oc wait --for=condition=Ready pod -l app=vllm-optimizer-frontend -n "vllm-optimizer-${DEPLOY_ENV}" --timeout=300s
oc get pods -n "vllm-optimizer-${DEPLOY_ENV}"
```
**Expected Result**: All pods should have `STATUS` as `Running` and `READY` as `1/1`. The `oc wait` commands should exit with code 0.

### 2. Set Static Route URL
Set the static frontend URL provided by the user.
Retrieve the frontend URL for subsequent tests.

**Action**: Export the static URL as an environment variable.
```bash
export FRONTEND_ROUTE_URL="vllm-optimizer-vllm-optimizer-dev.apps.compact.jooan.local"
echo "Frontend Route URL: https://$FRONTEND_ROUTE_URL"
```
```bash
export FRONTEND_ROUTE_URL="vllm-optimizer-vllm-optimizer-dev.apps.compact.jooan.local"
echo "Frontend Route URL: https://$FRONTEND_ROUTE_URL"
```
echo "Frontend Route URL: https://$FRONTEND_ROUTE_URL"
```
**Expected Result**: The `FRONTEND_ROUTE_URL` environment variable is populated.

### 3. Backend Log Review
Programmatically check the backend logs to ensure the application started without errors.

**Action**: Check backend logs for the startup message.
```bash
oc logs -l app=vllm-optimizer-backend -n "vllm-optimizer-${DEPLOY_ENV}" --tail=100 | grep "vLLM Optimizer API"
```
**Expected Result**: The command should find and print the "vLLM Optimizer API" startup message.

## IV. Automated Testing

### 1. Automated Backend Tests (Pytest)
Run the `pytest` suite within a backend pod to test the API logic.

**Action**: Execute backend tests using `oc rsh`.
```bash
oc rsh $(oc get pod -l app=vllm-optimizer-backend -n "vllm-optimizer-${DEPLOY_ENV}" -o name | head -1) pytest /app/tests/
```
**Expected Result**: All `pytest` tests should pass.

### 2. Automated Frontend & API Verification (`curl`)
Verify basic accessibility of the frontend and a key API endpoint.

**Note**: This `curl` check is a basic "smoke test." It confirms the services are reachable but does not verify UI content or complex functionality. A browser automation tool like Playwright would be needed for that.

**Action**: Access the frontend and `/api/metrics` endpoint via `curl`.
```bash
# Verify frontend root page returns 200 OK
curl --socks5-hostname 127.0.0.1:8882 -k "https://$FRONTEND_ROUTE_URL" -o /dev/null -w "%{http_code}\n"
# Verify the /api/metrics endpoint returns 200 OK
curl --socks5-hostname 127.0.0.1:8882 -k "https://$FRONTEND_ROUTE_URL/api/metrics" -o /dev/null -w "%{http_code}\n"
```
**Expected Result**: Both `curl` commands should output `200`.

### 3. Automated Functional Tests (Placeholder)
This section is a placeholder for more advanced functional tests. Automating the verification of the `Load Test` and `Auto Tuner` tabs would require parsing SSE events and specific log messages, or using a browser automation tool.

**Action**: (To be defined)
**Expected Result**: (To be defined)

## V. Troubleshooting

If issues arise:
- **Logs**: `oc logs -l <label> -n <namespace> -f`
- **Events**: `oc get events -n <namespace> --sort-by=.lastTimestamp`
- **Pod Details**: `oc describe pod <pod-name> -n <namespace>`
- **Proxy Issues**: Confirm the proxy on port 8882 is active and accessible.
