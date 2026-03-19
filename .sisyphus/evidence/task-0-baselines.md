# Task 0 Baselines — Captured 2026-03-19

## Backend Tests
```
    @app.on_event("shutdown")

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
117 passed, 10 deselected, 52 warnings in 42.52s
```
Pass count: **117 passed, 0 failed** (10 deselected integration tests)

## Frontend Tests
```
 ✓ src/pages/LoadTestPage.test.jsx (15 tests) 1613ms
   ✓ LoadTestPage > renders without crashing  303ms

 Test Files  8 passed (8)
      Tests  45 passed (45)
   Start at  14:28:25
   Duration  8.93s (transform 2.70s, setup 3.58s, collect 13.38s, tests 4.16s, environment 20.05s, prepare 4.00s)
```
Pass count: **8 test files passed, 45 tests passed, 0 failed**

## Kustomize
```
DEV: FAIL — kustomize binary not found at ./kustomize or in PATH
PROD: FAIL — kustomize binary not found at ./kustomize or in PATH
```
Note: Binary `./kustomize` referenced in project docs does not exist on this system.

## Code Metrics

### File line counts
- `backend/services/auto_tuner.py`: **671 lines**
- `backend/services/load_engine.py`: **305 lines**
- Total of the two files: **976 lines**

### Monster function definitions (grep output)
```
backend/services/auto_tuner.py:157:    async def start(self, config: TuningConfig, vllm_endpoint: str) -> dict:
backend/services/auto_tuner.py:574:    async def _evaluate(
backend/services/load_engine.py:90:    async def run(self, config: LoadTestConfig) -> dict:
```
Three large async functions identified at lines 157, 574, and 90.

### except Exception in production code (backend, excluding tests)
**39 occurrences**

### Inline `style={{` in frontend (excluding tests/node_modules)
**107 occurrences**

### ARIA attributes in frontend (excluding tests)
**2 occurrences**

### index.css lines
**138 lines**

## Notes
- Kustomize binary is missing — `./kustomize` file and `kustomize` in PATH do not exist. This is a pre-existing issue unrelated to the cleanup plan.
- Backend tests: 117 passed cleanly.
- Frontend tests: 45 passed across 8 test files.
- Both `except Exception` count (39) and inline style count (107) are high — these are the primary targets for the cleanup plan.
- ARIA attribute count is very low (2), indicating accessibility is an area for improvement in the frontend.
