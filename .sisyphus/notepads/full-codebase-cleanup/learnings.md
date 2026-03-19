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
