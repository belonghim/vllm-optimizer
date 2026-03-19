# Learnings — fix-pod-restart-rbac

## [2026-03-15] Session ses_30fc979fdffePlo4wKaFgg3DmX — Orchestrator analysis

### Current state at session start:
- T1 (auto_tuner.py IS annotation): ALREADY DONE — git commit e1186fe
- T3 (RBAC + AGENTS.md): ALREADY DONE — git commit e1186fe
- T2 (test_tuner.py): 4 failing tests, all use old Deployment-based mocks

### 4 failing tests in backend/tests/test_tuner.py:
1. `test_wait_for_ready_times_out` — Uses `mock_apps_api.read_namespaced_deployment_status` but `_wait_for_ready` now uses IS CustomObjectsApi
2. `test_start_reapplies_best_params_at_end` — Asserts `mock_apps_api.patch_namespaced_deployment.call_count` but `_apply_params` now patches IS
3. `test_apply_params_returns_failure_when_is_patch_throws` — Sets `mock_apps_api.patch_namespaced_deployment.side_effect` but code uses `patch_namespaced_custom_object`
4. `test_rollback_uses_deployment_restart` — Asserts `patch_namespaced_deployment` but rollback now uses IS annotation

### auto_tuner.py current implementation:
- `_wait_for_ready`: uses `_k8s_custom.get_namespaced_custom_object` (IS polling) ✓
- `_apply_params`: uses `_k8s_custom.patch_namespaced_custom_object` with `serving.kserve.io/restartedAt` annotation ✓
- `_rollback_to_snapshot`: uses `_k8s_custom.patch_namespaced_custom_object` with same IS annotation ✓

### mock_k8s_clients fixture (in test_tuner.py):
```python
mock_custom_api.return_value.get_namespaced_custom_object.return_value = {
    "status": {"conditions": [{"type": "Ready", "status": "True"}]}
}
mock_custom_api.return_value.patch_namespaced_custom_object = MagicMock()
```
IS patch is already set up as a MagicMock (doesn't throw). To test failures, need to set side_effect.

### VLLM_IS_NAME: `VLLM_DEPLOYMENT_NAME` env var, defaults to `"llm-ov"`
### K8S_NAMESPACE: `K8S_NAMESPACE` env var, defaults to `"default"`

## [2026-03-15] Deployment verification
- Recorded pre-flight pod `vllm-optimizer-backend-844dc544cd-gdz4k` (UID `a098e7d8-f2fb-4558-ad3f-8760431ffd40`).
- Ran `./deploy.sh dev` to rebuild/push `quay.io/joopark/vllm-optimizer-backend:dev` and reapply overlays; rollout log shows backend image switched from `sha256:4e11993694f6211dca9524a115ee97f7dc26018e67797c2383f9ecbeef6adc6e` to `sha256:d8f5795c6ab1fc0329dc85efd483134901fba9b3a59ba5ff3acb13997b0abc63`.
- Post-deploy pod `vllm-optimizer-backend-76fd787995-glbjb` Running with image ID `quay.io/joopark/vllm-optimizer-backend@sha256:d8f5795c6ab1fc0329dc85efd483134901fba9b3a59ba5ff3acb13997b0abc63` and rollout status successful.
- Logs show successful Thanos queries and only the expected `MetricsCollector` warnings about missing `p99_e2e_latency_ms` data, no startup errors.
- `vllm-optimizer-controller` clusterrole has only `get/list/watch` on `deployments` (no patch/update), so it cannot touch deployments/status.

## [2026-03-15T07:05:37Z] T5 E2E Result
- BEFORE IS annotation: `2026-03-07T15:23:37.378705Z`
- AFTER IS annotation: `2026-03-15T07:04:42.917136+00:00`
- BEFORE pod UID: `49815014-c5be-4dba-bf0c-6c28ff67de90`
- AFTER pod UID: `49815014-c5be-4dba-bf0c-6c28ff67de90 7903a7c7-2509-43e3-87fc-a667cf25090d`
- IS annotation changed: PASS
- Deployment pod template annotation matches IS annotation value: PASS
- vLLM pod restarted (UID changed): PASS
- Backend logs contain no 403/forbidden/"InferenceService restart failed" entries: PASS
- Notes: Route host `vllm-optimizer-vllm-optimizer-dev.apps.compact.jooan.local` was not DNS-resolvable from this environment, so I port-forwarded the backend service locally (http://localhost:8000) to hit `/api/tuner/*`.
