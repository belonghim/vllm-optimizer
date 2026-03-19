# Learnings — Full Codebase Cleanup

## Project Structure
- Backend: FastAPI Python at `backend/`, tests at `backend/tests/`
- Frontend: React/Vite at `frontend/src/`, tests at `frontend/src/pages/*.test.jsx`
- Infra: OpenShift Kustomize at `openshift/base/` and `openshift/overlays/`
- Kustomize binary: `./kustomize` (local, in project root)

## Test Commands
- Backend: `cd backend && python3 -m pytest tests/ -x -q -m "not integration"`
- Frontend: `cd frontend && npx vitest run`
- Kustomize: `./kustomize build openshift/overlays/dev && ./kustomize build openshift/overlays/prod`

## Key Guardrails
- G1: Preserve K8s side-effect order in auto_tuner.start()
- G2: Keep asyncio.wait(FIRST_COMPLETED) in load_engine.run()
- G3: Never touch test files for exception narrowing
- G4: Never narrow main.py:73 (intentionally broad startup guard)
- G13: Ports 8000/8080 are architectural constants — don't parameterize
- G14: Never change CSS values during migration — only move location

## T7: TunerPage Decomposition Pattern
- showAdvanced UI state stays in TunerPage (per "retain all useState" rule); passed down as prop + onToggleAdvanced handler
- onChange(field, value) handler implemented as handleConfigChange in TunerPage using setConfig(c => ({ ...c, [field]: value }))
- Complex array field (block_size_options) handled in TunerConfigForm: component computes new array, calls onChange("block_size_options", newArray)
- scatterData computation moved into TunerResults since both trials + bestParams live there
- fmt helper and PHASE_LABELS constant defined locally in the files that use them
- TunerPage.jsx: 181 lines (was 441); TunerConfigForm.jsx: 197 lines; TunerResults.jsx: 111 lines
- 45/45 tests pass unchanged — tests find buttons/inputs through TunerPage → TunerConfigForm render tree

## [2026-03-19] Task 4 — except Exception narrowing in auto_tuner.py

### Mapping applied
- `k8s_config.load_incluster_config()` → `k8s_config.ConfigException` (inner init)
- `_init_k8s` outer → `k8s_config.ConfigException` (wraps config loading)
- `_wait_for_ready` K8s GET → `ApiException` (import: `from kubernetes.client.exceptions import ApiException`)
- `_apply_params` IS restart inner → `ApiException`
- `_rollback_to_snapshot` → `ApiException`
- `get_importance` Optuna checks → `optuna.exceptions.OptunaError`

### Kept broad with `# intentional`
- Line 260: SQLite/Optuna storage init — SQLAlchemy errors too diverse
- Lines 319/354: Prometheus metrics emit — non-critical, any type can fail
- Line 364: Pareto front update — non-critical internal
- Line 536: `_apply_params` outer fallback — test mock uses `Exception`, must stay broad
- Line 612: warmup load engine — non-critical, various error types possible

### Key gotcha: test compatibility
`test_apply_params_returns_failure_when_is_patch_throws` uses `side_effect = Exception(...)` 
(not ApiException). Narrowing line 531 (inner IS restart) to `ApiException` is safe because
the plain `Exception` propagates to the outer line 536 `except Exception`, which still returns
`{"success": False, "error": "..."}`. Test still passes because "InferenceService" is in the error string.

### Import added
`from kubernetes.client.exceptions import ApiException` — `k8s_client.exceptions.ApiException` 
submodule not auto-loaded by `from kubernetes import client as k8s_client`.
