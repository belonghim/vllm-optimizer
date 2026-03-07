# Plan: Hotfix Deployment Error

This plan addresses the recurring "uvicorn: not found" error that is causing the backend container to crash-loop. The fix involves correcting the `CMD` instruction in the `backend/Dockerfile`.

## I. Correct Dockerfile

### 1. Modify `CMD` Instruction
The `CMD` instruction in `backend/Dockerfile` is currently in "exec" form, which does not invoke a shell and therefore does not process the `$PATH` variable. This will be changed to "shell" form to ensure `uvicorn` can be found.

**Task**: [x] Update the `CMD` instruction.
- **File**: `backend/Dockerfile`
- **Change From**: `CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]`
- **Change To**: `CMD uvicorn main:app --host 0.0.0.0 --port 8000 --workers 2`

## II. Redeploy Application

### 1. Execute Deployment Script
With the Dockerfile corrected, the application must be rebuilt and redeployed.

**Task**: [x] Run the deployment script.
- **Command**: `./deploy.sh dev`
- **Note**: Ensure environment variables (`REGISTRY`, `VLLM_NAMESPACE`, `DEPLOY_ENV`) are set.

## III. Verify Fix

### 1. Check Pod Status and Logs
After deployment, verify that the new backend pod starts successfully and no longer has the `uvicorn: not found` error.

**Task**: [x] Verify pod health.
- **Command 1**: `oc wait --for=condition=Ready pod -l app=vllm-optimizer-backend -n vllm-optimizer-dev --timeout=300s`
- **Command 2**: `oc logs -l app=vllm-optimizer-backend -n vllm-optimizer-dev | grep "Application startup complete"`
- **Expected Result**: The `oc wait` command should succeed, and the logs should show the application startup message.
