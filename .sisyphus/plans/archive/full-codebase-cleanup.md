# Full Codebase Tech Debt Cleanup

## TL;DR

> **Quick Summary**: Comprehensive tech debt cleanup across backend (Python/FastAPI), frontend (React), and infrastructure (OpenShift YAML) — decomposing monster functions, narrowing exceptions, extracting components, migrating inline styles, adding accessibility, and parameterizing Kustomize configs.
> 
> **Deliverables**:
> - 3 backend monster functions decomposed into ≤60-line methods
> - ~14 broad `except Exception` blocks narrowed to specific types
> - ~12 missing return type annotations added
> - 2 oversized React pages decomposed into sub-components + custom hook
> - All inline `style={}` migrated to CSS classes in `index.css`
> - ErrorAlert reusable component extracted
> - ARIA labels + aria-live regions added to all interactive elements
> - Kustomize configs parameterized with overlays
> 
> **Estimated Effort**: Large
> **Parallel Execution**: YES — 3 independent paths (backend / frontend / infra)
> **Critical Path**: T0 → T7/T8 → T9/T10/T11 → T12 → F1-F4 (frontend path, longest)

---

## Context

### Original Request
User requested comprehensive tech debt cleanup after a full codebase audit identified 8 areas (A-H) spanning 3 severity levels across backend, frontend, and infrastructure.

### Interview Summary
**Key Discussions**:
- Audit revealed 3 high-severity (monster functions, broad exceptions, oversized components), 5 medium-severity items
- User selected ALL items for cleanup
- Test strategy: existing tests only — no new test files
- Strategy: safe/conservative — behavior preservation

**Research Findings**:
- Backend exception count is ~14 (not 35+); type annotation gap is ~12 (not 40+)
- Frontend error handling is already consistent — merge Item F into Item E
- Accessibility baseline is near-zero (1 ARIA attribute in entire app)
- `main.py:73` startup exception is intentionally broad — exclude from scope
- Ordering constraint discovered: C → E → G (DOM restructuring invalidates ARIA targets)
- `LoadTestPage.jsx` uses refs for EventSource — requires custom hook extraction
- `SECRET_KEY` in plaintext in YAML — security issue addressed with documentation

### Metis Review
**Identified Gaps** (addressed):
- 4 count mismatches corrected (exceptions, types, error handling, accessibility)
- 10 guardrails established (K8s side-effect order, async shape, test file exclusion, etc.)
- 6 edge cases documented (SSE refs, 12-field form state, warmup timing, etc.)
- Item F merged into Item E (same CSS problem, not separate concern)
- Baseline capture added as mandatory Task 0

---

## Work Objectives

### Core Objective
Eliminate tech debt across all layers of the vLLM Optimizer application while preserving all existing behavior, ensuring zero test regressions, and maintaining OpenShift 4.x deployment compatibility.

### Concrete Deliverables
- `backend/services/auto_tuner.py` — `start()` ≤60 lines, `_evaluate()` ≤60 lines, 9 exceptions narrowed, return types added
- `backend/services/load_engine.py` — `run()` ≤60 lines, 1 exception narrowed, return types added
- `backend/services/metrics_collector.py` — 3 exceptions narrowed, return types added
- `backend/routers/` — exceptions narrowed, return types added
- `frontend/src/components/TunerConfigForm.jsx` — new extracted component
- `frontend/src/components/TunerResults.jsx` — new extracted component
- `frontend/src/components/LoadTestConfig.jsx` — new extracted component
- `frontend/src/hooks/useLoadTestSSE.js` — new custom hook for SSE
- `frontend/src/components/ErrorAlert.jsx` — new reusable error component
- `frontend/src/index.css` — all inline styles migrated to named classes
- All `<button>` and `<input>` elements have ARIA labels
- All dynamic content has `aria-live` regions
- `openshift/base/02-config.yaml` — env vars moved to ConfigMap refs
- `openshift/overlays/dev/` and `prod/` — environment-specific values

### Definition of Done
- [x] `cd backend && python3 -m pytest tests/ -x -q -m "not integration"` — same pass count as baseline
- [x] `cd frontend && npx vitest run` — same pass count as baseline
- [x] `./kustomize build openshift/overlays/dev > /dev/null` — exit 0
- [x] `./kustomize build openshift/overlays/prod > /dev/null` — exit 0
- [x] `grep -r "except Exception" backend/routers/ backend/services/ --include="*.py" | grep -v test | grep -v "# intentional"` — 0 matches (excluding main.py startup)
- [x] No function in auto_tuner.py or load_engine.py exceeds 60 lines
- [x] `grep -r 'style={{' frontend/src/ --include="*.jsx" --include="*.js"` — 0 matches

### Must Have
- Zero test regressions (existing pass count preserved)
- All existing API contracts unchanged
- All existing UI behavior and appearance unchanged
- OpenShift overlay builds succeed
- K8s side-effect order preserved in auto_tuner.start()
- asyncio.wait(FIRST_COMPLETED) loop shape preserved in load_engine.run()

### Must NOT Have (Guardrails)
- **G1**: No reordering of K8s side effects in auto_tuner.start() (ConfigMap patch → IS wait → evaluate → tell → rollback)
- **G2**: No conversion of asyncio.wait(FIRST_COMPLETED) to asyncio.gather() in load_engine.run()
- **G3**: No modification of test files for exception narrowing (tests/test_tuner.py, tests/test_load_test.py excluded)
- **G4**: No narrowing of main.py:73 startup shim guard (intentionally broad)
- **G5**: No new state management libraries (Zustand, Redux, Context) during frontend decomposition
- **G6**: No CSS frameworks (Tailwind, styled-components, Emotion, Material UI)
- **G7**: No new UI features, visual states, or API calls during decomposition
- **G8**: No parameter type changes or docstrings during type annotation task
- **G9**: No Optuna config changes, scoring formula changes, or parameter space changes
- **G10**: No SSE retry behavior changes — only move code
- **G11**: No keyboard shortcuts or focus management during accessibility
- **G12**: No Helm, ArgoCD, or overlay hierarchy restructuring for Kustomize
- **G13**: No parameterization of ports 8000/8080 (architectural constants)
- **G14**: No color, font, or spacing value changes during CSS migration — only location moves

---

## Verification Strategy

> **ZERO HUMAN INTERVENTION** — ALL verification is agent-executed. No exceptions.

### Test Decision
- **Infrastructure exists**: YES (both backend and frontend)
- **Automated tests**: Existing tests only — run after each change, no new test files
- **Backend**: `cd backend && python3 -m pytest tests/ -x -q -m "not integration"`
- **Frontend**: `cd frontend && npx vitest run`

### QA Policy
Every task MUST include agent-executed QA scenarios.
Evidence saved to `.sisyphus/evidence/task-{N}-{scenario-slug}.{ext}`.

- **Backend refactoring**: Use Bash — run pytest, grep for patterns, count lines
- **Frontend components**: Use Bash — run vitest, grep for patterns
- **Infrastructure**: Use Bash — kustomize build, grep for hardcoded values
- **Accessibility**: Use Bash — ast-grep to find elements without ARIA attrs

---

## Execution Strategy

### Parallel Execution Waves

> Three independent paths (Backend, Frontend, Infra) run in parallel.
> Within each path, tasks follow dependency chains.
> Maximum parallelism: 7 concurrent tasks.

```
Wave 0 (Baseline — must complete first):
└── T0: Capture test baselines [quick]

Wave 1 (Foundation — 7 parallel tasks after T0):
├── T1: auto_tuner start() decomposition (depends: T0) [deep]
├── T2: auto_tuner _evaluate() decomposition (depends: T0) [deep]
├── T3: load_engine run() decomposition (depends: T0) [deep]
├── T7: TunerPage.jsx decomposition (depends: T0) [unspecified-high]
├── T8: LoadTestPage.jsx decomposition (depends: T0) [unspecified-high]
├── T13: Kustomize env vars + ALLOWED_ORIGINS (depends: T0) [quick]
└── T14: Kustomize SECRET_KEY resolution (depends: T0) [quick]

Wave 2 (Backend cleanup + CSS — 6 parallel tasks):
├── T4: Exception narrowing auto_tuner.py (depends: T1, T2) [unspecified-high]
├── T5: Exception narrowing rest of backend (depends: T3) [unspecified-high]
├── T6: Type annotations all backend (depends: T1, T2, T3) [quick]
├── T9: Extract ErrorAlert component (depends: T7, T8) [quick]
├── T10: CSS migration TunerPage + LoadTestPage (depends: T7, T8) [unspecified-high]
└── T11: CSS migration remaining files (depends: T9) [unspecified-high]

Wave 3 (Accessibility — after CSS complete):
└── T12: ARIA labels + aria-live regions (depends: T10, T11) [unspecified-high]

Wave FINAL (After ALL tasks — 4 parallel reviews, then user okay):
├── F1: Plan compliance audit (oracle)
├── F2: Code quality review (unspecified-high)
├── F3: Real manual QA (unspecified-high)
└── F4: Scope fidelity check (deep)
→ Present results → Get explicit user okay
```

Critical Paths:
- Backend: T0 → T1/T2/T3 → T4/T5/T6 (3 waves)
- Frontend: T0 → T7/T8 → T9/T10/T11 → T12 (4 waves — longest)
- Infra: T0 → T13/T14 (2 waves — shortest)
Parallel Speedup: ~65% faster than sequential
Max Concurrent: 7 (Wave 1)

### Dependency Matrix

| Task | Blocked By | Blocks | Wave |
|------|-----------|--------|------|
| T0 | — | T1-T14 | 0 |
| T1 | T0 | T4, T6 | 1 |
| T2 | T0 | T4, T6 | 1 |
| T3 | T0 | T5, T6 | 1 |
| T4 | T1, T2 | — | 2 |
| T5 | T3 | — | 2 |
| T6 | T1, T2, T3 | — | 2 |
| T7 | T0 | T9, T10 | 1 |
| T8 | T0 | T9, T10 | 1 |
| T9 | T7, T8 | T11 | 2 |
| T10 | T7, T8 | T12 | 2 |
| T11 | T9 | T12 | 2 |
| T12 | T10, T11 | — | 3 |
| T13 | T0 | — | 1 |
| T14 | T0 | — | 1 |

### Agent Dispatch Summary

- **Wave 0**: **1** — T0 → `quick`
- **Wave 1**: **7** — T1-T3 → `deep`, T7-T8 → `unspecified-high`, T13-T14 → `quick`
- **Wave 2**: **6** — T4-T5 → `unspecified-high`, T6 → `quick`, T9 → `quick`, T10-T11 → `unspecified-high`
- **Wave 3**: **1** — T12 → `unspecified-high`
- **FINAL**: **4** — F1 → `oracle`, F2-F3 → `unspecified-high`, F4 → `deep`

---

## TODOs

- [x] 0. Capture Test Baselines

  **What to do**:
  - Run backend unit tests and record exact pass/fail count
  - Run frontend vitest and record exact pass/fail count
  - Run kustomize build for both dev and prod overlays and confirm success
  - Record line counts for target functions: `auto_tuner.py:start()`, `auto_tuner.py:_evaluate()`, `load_engine.py:run()`
  - Count current `except Exception` occurrences in production code
  - Count current inline `style={{` occurrences in frontend
  - Count current ARIA attributes in frontend
  - Save all baselines to `.sisyphus/evidence/task-0-baselines.md`

  **Must NOT do**:
  - Change any code
  - Install any packages
  - Modify any configuration

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Pure data collection, no code changes, short execution
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Wave 0 (solo)
  - **Blocks**: T1, T2, T3, T4, T5, T6, T7, T8, T9, T10, T11, T12, T13, T14
  - **Blocked By**: None (start immediately)

  **References**:
  **Pattern References**:
  - `backend/services/auto_tuner.py:157-382` — `start()` method (225 lines to measure)
  - `backend/services/auto_tuner.py:574-655` — `_evaluate()` method (81 lines to measure)
  - `backend/services/load_engine.py:90-251` — `run()` method (161 lines to measure)

  **Test References**:
  - `pyproject.toml` — pytest configuration with markers
  - `frontend/package.json:9` — `"test": "vitest run"` command
  - `backend/tests/` — all test files for baseline pass count

  **External References**:
  - None needed

  **WHY Each Reference Matters**:
  - `auto_tuner.py` line ranges define the 3 monster functions to measure before/after
  - Test configs tell you exact commands to run for baseline capture

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Backend test baseline captured
    Tool: Bash
    Preconditions: Working directory is project root
    Steps:
      1. Run: cd backend && python3 -m pytest tests/ -x -q -m "not integration" 2>&1 | tail -5
      2. Extract pass count from output (e.g., "23 passed")
      3. Write to .sisyphus/evidence/task-0-baselines.md under "## Backend Tests"
    Expected Result: Pass count recorded (e.g., "23 passed, 0 failed")
    Failure Indicators: pytest returns non-zero exit code, or "error" in output
    Evidence: .sisyphus/evidence/task-0-baselines.md

  Scenario: Frontend test baseline captured
    Tool: Bash
    Preconditions: frontend/node_modules exists (run npm install if needed)
    Steps:
      1. Run: cd frontend && npx vitest run 2>&1 | tail -10
      2. Extract pass count from output
      3. Write to .sisyphus/evidence/task-0-baselines.md under "## Frontend Tests"
    Expected Result: Pass count recorded
    Failure Indicators: vitest returns non-zero exit code
    Evidence: .sisyphus/evidence/task-0-baselines.md

  Scenario: Kustomize build baseline verified
    Tool: Bash
    Preconditions: ./kustomize binary exists
    Steps:
      1. Run: ./kustomize build openshift/overlays/dev > /dev/null 2>&1 && echo "DEV: PASS" || echo "DEV: FAIL"
      2. Run: ./kustomize build openshift/overlays/prod > /dev/null 2>&1 && echo "PROD: PASS" || echo "PROD: FAIL"
      3. Write results to .sisyphus/evidence/task-0-baselines.md under "## Kustomize"
    Expected Result: Both show PASS
    Failure Indicators: Either shows FAIL
    Evidence: .sisyphus/evidence/task-0-baselines.md

  Scenario: Code metrics baseline captured
    Tool: Bash
    Preconditions: None
    Steps:
      1. Count lines in start(): awk '/async def start/,/^    async def |^    def |^class /' backend/services/auto_tuner.py | wc -l
      2. Count except Exception: grep -rn "except Exception" backend/routers/ backend/services/ --include="*.py" | grep -v test | wc -l
      3. Count inline styles: grep -rn 'style={{' frontend/src/ --include="*.jsx" --include="*.js" | grep -v node_modules | grep -v test | wc -l
      4. Count ARIA attrs: grep -rn 'aria-' frontend/src/ --include="*.jsx" | wc -l
      5. Write all counts to .sisyphus/evidence/task-0-baselines.md under "## Code Metrics"
    Expected Result: All counts captured as integers
    Evidence: .sisyphus/evidence/task-0-baselines.md
  ```

  **Evidence to Capture:**
  - [x] .sisyphus/evidence/task-0-baselines.md — all baseline measurements

  **Commit**: YES
  - Message: `chore: capture test and code quality baselines before cleanup`
  - Files: `.sisyphus/evidence/task-0-baselines.md`
  - Pre-commit: none

---

- [x] 1. Decompose auto_tuner.py start() Method

  **What to do**:
  - Read `auto_tuner.py:start()` (lines 157-382, 225 lines) and understand the sequential flow
  - Extract these private methods (each ≤60 lines):
    - `_apply_trial_params(trial, params)` — Applies trial parameters to ConfigMap, patches K8s
    - `_wait_for_isvc_ready()` — Waits for InferenceService readiness after config change
    - `_run_trial_evaluation(trial_number)` — Runs the load test evaluation for a trial
    - `_handle_trial_result(trial, score, params)` — Processes trial result, updates best, broadcasts SSE
    - `_rollback_config(original_config)` — Rolls back ConfigMap on failure
  - The main `start()` method becomes an orchestrator calling these in sequence
  - **CRITICAL**: Preserve exact K8s side-effect order: ConfigMap patch → IS readiness wait → evaluate → Optuna tell → rollback (if fail)
  - **CRITICAL**: Do NOT change Optuna configuration, trial logic, parameter spaces, or scoring formula

  **Must NOT do**:
  - Reorder K8s side effects (G1)
  - Change Optuna config or scoring (G9)
  - Add new functionality or features (G7)
  - Change public API or method signatures
  - Modify test files

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: Complex async method with K8s side effects and Optuna integration — requires deep understanding of sequential dependencies
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with T2, T3, T7, T8, T13, T14)
  - **Blocks**: T4, T6
  - **Blocked By**: T0

  **References**:
  **Pattern References**:
  - `backend/services/auto_tuner.py:157-382` — Full `start()` method to decompose
  - `backend/services/auto_tuner.py:1-156` — Class init, imports, helper methods — understand existing method extraction patterns
  - `backend/services/auto_tuner.py:383-570` — Other methods in class — follow naming/style conventions

  **API/Type References**:
  - `backend/services/auto_tuner.py:_broadcast()` — SSE broadcast pattern to preserve
  - `backend/services/auto_tuner.py:subscribe()/unsubscribe()` — Subscriber pattern context

  **Test References**:
  - `backend/tests/test_tuner.py` — All tuner tests that exercise start() behavior — must pass before AND after

  **External References**:
  - Optuna docs: `https://optuna.readthedocs.io/en/stable/reference/generated/optuna.study.Study.html` — Study.optimize() and Trial API
  - K8s Python client: `kubernetes.client.CoreV1Api.patch_namespaced_config_map` — ConfigMap patching

  **WHY Each Reference Matters**:
  - Lines 157-382 are the code to decompose — understand the full flow before extracting
  - Lines 1-156 show existing helper patterns (naming, parameter style) to match
  - test_tuner.py is the safety net — run before and after each extraction step
  - Optuna docs clarify Trial API to ensure extracted methods handle trial state correctly

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: start() method reduced to orchestrator
    Tool: Bash
    Preconditions: Task T0 baseline captured
    Steps:
      1. Count lines in start(): awk '/    async def start/,/^    async def [^_]|^    def [^_]/' backend/services/auto_tuner.py | wc -l
      2. Assert line count ≤ 60
      3. Count new private methods: grep -c "async def _apply_trial_params\|async def _wait_for_isvc_ready\|async def _run_trial_evaluation\|async def _handle_trial_result\|async def _rollback_config" backend/services/auto_tuner.py
      4. Assert count ≥ 4
    Expected Result: start() ≤ 60 lines, ≥ 4 new private methods exist
    Failure Indicators: start() > 60 lines or missing expected methods
    Evidence: .sisyphus/evidence/task-1-start-decomposed.txt

  Scenario: All tuner tests still pass
    Tool: Bash
    Preconditions: Backend dependencies installed
    Steps:
      1. Run: cd backend && python3 -m pytest tests/test_tuner.py -v --tb=short 2>&1
      2. Compare pass count with baseline from task-0-baselines.md
    Expected Result: Same pass count as baseline, 0 failures
    Failure Indicators: Any test failure or reduced pass count
    Evidence: .sisyphus/evidence/task-1-tests.txt

  Scenario: K8s side-effect order preserved
    Tool: Bash
    Preconditions: Decomposition complete
    Steps:
      1. Read start() method body
      2. Verify call order: _apply_trial_params → _wait_for_isvc_ready → _run_trial_evaluation → _handle_trial_result
      3. Verify _rollback_config is in except/finally block
      4. grep -n "_apply_trial_params\|_wait_for_isvc_ready\|_run_trial_evaluation\|_handle_trial_result\|_rollback_config" backend/services/auto_tuner.py
    Expected Result: Methods called in correct sequential order within start()
    Failure Indicators: Methods called out of order or missing from start() body
    Evidence: .sisyphus/evidence/task-1-sideeffect-order.txt
  ```

  **Evidence to Capture:**
  - [x] .sisyphus/evidence/task-1-start-decomposed.txt
  - [x] .sisyphus/evidence/task-1-tests.txt
  - [x] .sisyphus/evidence/task-1-sideeffect-order.txt

  **Commit**: YES
  - Message: `refactor(auto-tuner): decompose start() into focused private methods`
  - Files: `backend/services/auto_tuner.py`
  - Pre-commit: `cd backend && python3 -m pytest tests/test_tuner.py -v --tb=short`

---

- [x] 2. Decompose auto_tuner.py _evaluate() Method

  **What to do**:
  - Read `auto_tuner.py:_evaluate()` (lines 574-655, 81 lines) and understand the warmup + probe flow
  - Extract these private methods (each ≤60 lines):
    - `_run_warmup_load(endpoint, model)` — Runs the warmup load test phase
    - `_run_probe_load(endpoint, model)` — Runs the evaluation probe phase
    - `_compute_trial_score(results)` — Computes the optimization score from probe results
  - **CRITICAL**: Warmup MUST run BEFORE the timing window for scoring
  - **CRITICAL**: Do NOT change scoring formula or evaluation phases

  **Must NOT do**:
  - Change scoring formula (G9)
  - Reorder warmup/probe sequence
  - Add new functionality (G7)

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: Evaluation logic with warmup timing dependencies — requires understanding of score computation
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with T1, T3, T7, T8, T13, T14)
  - **Blocks**: T4, T6
  - **Blocked By**: T0

  **References**:
  **Pattern References**:
  - `backend/services/auto_tuner.py:574-655` — Full `_evaluate()` method to decompose
  - `backend/services/auto_tuner.py:157-382` — `start()` method shows how _evaluate() is called (context)
  - `backend/services/load_engine.py:run()` — Load engine that _evaluate() invokes for warmup/probe

  **Test References**:
  - `backend/tests/test_tuner.py` — Tests that verify warmup runs before evaluation

  **WHY Each Reference Matters**:
  - Lines 574-655 are the decomposition target
  - start() context shows _evaluate() call site and expected return values
  - load_engine.run() is the underlying engine — understand its API contract

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: _evaluate() decomposed and ≤60 lines
    Tool: Bash
    Preconditions: Task T0 baseline captured
    Steps:
      1. Count lines in _evaluate(): awk '/    async def _evaluate/,/^    async def |^    def |^class /' backend/services/auto_tuner.py | wc -l
      2. Assert line count ≤ 60
      3. Verify new methods exist: grep -c "_run_warmup_load\|_run_probe_load\|_compute_trial_score" backend/services/auto_tuner.py
    Expected Result: _evaluate() ≤ 60 lines, ≥ 2 new methods exist
    Failure Indicators: _evaluate() > 60 lines or missing methods
    Evidence: .sisyphus/evidence/task-2-evaluate-decomposed.txt

  Scenario: All tuner tests still pass after _evaluate() changes
    Tool: Bash
    Steps:
      1. Run: cd backend && python3 -m pytest tests/test_tuner.py -v --tb=short 2>&1
      2. Compare pass count with baseline
    Expected Result: Same pass count as baseline, 0 failures
    Evidence: .sisyphus/evidence/task-2-tests.txt
  ```

  **Evidence to Capture:**
  - [x] .sisyphus/evidence/task-2-evaluate-decomposed.txt
  - [x] .sisyphus/evidence/task-2-tests.txt

  **Commit**: YES
  - Message: `refactor(auto-tuner): decompose _evaluate() into warmup and probe phases`
  - Files: `backend/services/auto_tuner.py`
  - Pre-commit: `cd backend && python3 -m pytest tests/test_tuner.py -v --tb=short`

---

- [x] 3. Decompose load_engine.py run() Method

  **What to do**:
  - Read `load_engine.py:run()` (lines 90-251, 161 lines) and understand the async request dispatch flow
  - Extract these private methods (each ≤60 lines):
    - `_init_run_state(config)` — Initializes run state, stats tracking, result containers
    - `_dispatch_request(session, semaphore, request_id)` — Sends a single async request
    - `_process_completed_tasks(done_tasks)` — Processes completed asyncio tasks, collects results
    - `_finalize_results(stats, results)` — Computes final statistics, builds response
  - **CRITICAL**: Preserve the `asyncio.wait(return_when=FIRST_COMPLETED)` loop shape — do NOT convert to `asyncio.gather()`
  - The main `run()` method becomes the orchestrator with the asyncio.wait loop

  **Must NOT do**:
  - Convert asyncio.wait to asyncio.gather (G2)
  - Change concurrency semantics
  - Add new functionality (G7)
  - Change SSE broadcast behavior (G10)

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: Complex async concurrency with asyncio.wait — must preserve exact task scheduling semantics
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with T1, T2, T7, T8, T13, T14)
  - **Blocks**: T5, T6
  - **Blocked By**: T0

  **References**:
  **Pattern References**:
  - `backend/services/load_engine.py:90-251` — Full `run()` method to decompose
  - `backend/services/load_engine.py:1-89` — Class init, imports, existing helper methods
  - `backend/services/load_engine.py:252-end` — `_compute_stats()` and other helpers — follow patterns

  **Test References**:
  - `backend/tests/test_load_test.py` — Load test tests that exercise run() behavior

  **WHY Each Reference Matters**:
  - Lines 90-251 are the decomposition target — focus on the asyncio.wait loop
  - Existing helpers show the class's naming and parameter conventions
  - test_load_test.py validates the async behavior — must pass before and after

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: run() decomposed and ≤60 lines
    Tool: Bash
    Steps:
      1. Count lines in run(): awk '/    async def run/,/^    async def |^    def [^_]|^class /' backend/services/load_engine.py | wc -l
      2. Assert ≤ 60
      3. Verify new methods: grep -c "_init_run_state\|_dispatch_request\|_process_completed\|_finalize_results" backend/services/load_engine.py
    Expected Result: run() ≤ 60 lines, ≥ 3 new methods
    Evidence: .sisyphus/evidence/task-3-run-decomposed.txt

  Scenario: asyncio.wait FIRST_COMPLETED preserved
    Tool: Bash
    Steps:
      1. grep -n "asyncio.wait" backend/services/load_engine.py
      2. grep -n "FIRST_COMPLETED" backend/services/load_engine.py
      3. Verify asyncio.wait with FIRST_COMPLETED still exists
      4. grep -n "asyncio.gather" backend/services/load_engine.py — must return 0 matches
    Expected Result: asyncio.wait(FIRST_COMPLETED) present, asyncio.gather absent
    Failure Indicators: asyncio.gather found, or asyncio.wait removed
    Evidence: .sisyphus/evidence/task-3-async-shape.txt

  Scenario: All load test tests pass
    Tool: Bash
    Steps:
      1. Run: cd backend && python3 -m pytest tests/test_load_test.py -v --tb=short 2>&1
      2. Compare pass count with baseline
    Expected Result: Same pass count as baseline, 0 failures
    Evidence: .sisyphus/evidence/task-3-tests.txt
  ```

  **Evidence to Capture:**
  - [x] .sisyphus/evidence/task-3-run-decomposed.txt
  - [x] .sisyphus/evidence/task-3-async-shape.txt
  - [x] .sisyphus/evidence/task-3-tests.txt

  **Commit**: YES
  - Message: `refactor(load-engine): decompose run() into init, process, finalize methods`
  - Files: `backend/services/load_engine.py`
  - Pre-commit: `cd backend && python3 -m pytest tests/test_load_test.py -v --tb=short`

- [x] 4. Narrow Exception Handling in auto_tuner.py

  **What to do**:
  - Identify all `except Exception` blocks in `auto_tuner.py` (~9 blocks, excluding test files)
  - For each block, determine the specific operation and replace with appropriate exception types using this mapping:
    - K8s API calls → `kubernetes.client.exceptions.ApiException`
    - httpx/HTTP calls → `httpx.HTTPStatusError`, `httpx.ConnectError`, `httpx.TimeoutException`
    - Optuna operations → `optuna.exceptions.TrialPruned` (verify already specific before changing)
    - JSON parsing → `json.JSONDecodeError`
    - asyncio operations → `asyncio.TimeoutError`, `asyncio.CancelledError`
    - General I/O → `OSError`, `IOError`
  - For blocks that genuinely need to catch any error (e.g., top-level try in orchestrator), add comment `# intentional: catch-all for [reason]`
  - Preserve existing error logging and fallback behavior — only change the exception type
  - Import any new exception classes at the top of the file

  **Must NOT do**:
  - Modify test files (G3)
  - Change error handling behavior (log messages, fallback values, re-raises)
  - Narrow to types so specific they miss real production errors
  - Change function signatures or logic

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
    - Reason: Requires reading each except block's context, understanding what operations can fail, and selecting correct exception types
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 (with T5, T6, T9, T10, T11)
  - **Blocks**: None
  - **Blocked By**: T1, T2 (function decomposition may move code)

  **References**:
  **Pattern References**:
  - `backend/services/auto_tuner.py:68,74,102,205,292,337,347,526,531,570,601,665,670` — All `except Exception` locations
  - `backend/services/auto_tuner.py:1-30` — Existing imports — add new exception imports here

  **API/Type References**:
  - `kubernetes.client.exceptions.ApiException` — K8s API error type
  - `httpx.HTTPStatusError`, `httpx.ConnectError`, `httpx.TimeoutException` — HTTP error types
  - `optuna.exceptions` — Optuna-specific exception types

  **Test References**:
  - `backend/tests/test_tuner.py` — Must pass after all changes

  **WHY Each Reference Matters**:
  - Exception line numbers tell you exactly where to look (note: line numbers may shift after T1/T2 decomposition)
  - Import section is where new exception classes must be added
  - K8s and httpx exception classes are the primary replacements

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Zero broad exceptions in auto_tuner.py (production code)
    Tool: Bash
    Steps:
      1. grep -n "except Exception" backend/services/auto_tuner.py | grep -v "# intentional"
      2. Count matches
    Expected Result: 0 matches (all narrowed or marked intentional)
    Failure Indicators: Any unmarked "except Exception" remaining
    Evidence: .sisyphus/evidence/task-4-exceptions.txt

  Scenario: All tuner tests pass after narrowing
    Tool: Bash
    Steps:
      1. Run: cd backend && python3 -m pytest tests/test_tuner.py -v --tb=short 2>&1
      2. Compare pass count with baseline
    Expected Result: Same pass count, 0 failures
    Evidence: .sisyphus/evidence/task-4-tests.txt

  Scenario: Specific exception types imported
    Tool: Bash
    Steps:
      1. grep -n "ApiException\|HTTPStatusError\|ConnectError\|TimeoutException" backend/services/auto_tuner.py
      2. Verify at least 2 specific exception types are imported and used
    Expected Result: ≥2 specific exception types in use
    Evidence: .sisyphus/evidence/task-4-imports.txt
  ```

  **Evidence to Capture:**
  - [x] .sisyphus/evidence/task-4-exceptions.txt
  - [x] .sisyphus/evidence/task-4-tests.txt
  - [x] .sisyphus/evidence/task-4-imports.txt

  **Commit**: YES
  - Message: `refactor(auto-tuner): narrow except Exception to specific types`
  - Files: `backend/services/auto_tuner.py`
  - Pre-commit: `cd backend && python3 -m pytest tests/test_tuner.py -v --tb=short`

---

- [x] 5. Narrow Exception Handling in Remaining Backend Files

  **What to do**:
  - Narrow `except Exception` blocks in these files using the same exception type mapping as T4:
    - `backend/services/metrics_collector.py` — 3 blocks (K8s API + Thanos/httpx calls)
    - `backend/services/load_engine.py` — 1 block (async HTTP calls)
    - `backend/routers/load_test.py` — 1 block (route handler)
    - `backend/routers/vllm_config.py` — 5 blocks (K8s API calls)
    - `backend/startup_metrics_shim.py` — 3 blocks (startup initialization)
    - `backend/services/model_resolver.py` — 1 block (HTTP call)
  - **EXCLUDE**: `backend/main.py:73` — intentionally broad startup shim guard. Add comment: `# intentional: fail-open for optional startup module`
  - **EXCLUDE**: All files in `backend/tests/` — test exception handling is out of scope
  - Import new exception classes at the top of each file
  - Preserve error logging and fallback behavior

  **Must NOT do**:
  - Modify test files (G3)
  - Narrow main.py:73 startup guard (G4)
  - Change error handling behavior or logic

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
    - Reason: Multiple files with different exception contexts — needs careful per-block analysis
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 (with T4, T6, T9, T10, T11)
  - **Blocks**: None
  - **Blocked By**: T3 (load_engine decomposition may move code)

  **References**:
  **Pattern References**:
  - `backend/services/metrics_collector.py:145,152,157,166,211,231,277,289,320` — Exception locations
  - `backend/services/load_engine.py:81,157,206` — Exception locations
  - `backend/routers/load_test.py:90` — Exception location
  - `backend/routers/vllm_config.py:36,39,56,79,95` — Exception locations
  - `backend/startup_metrics_shim.py:10,52,58` — Exception locations
  - `backend/services/model_resolver.py:29` — Exception location
  - `backend/main.py:73` — EXCLUDE this line (intentionally broad)

  **Test References**:
  - `backend/tests/test_metrics_collector.py` — Tests for metrics_collector
  - `backend/tests/test_load_test.py` — Tests for load_engine and load_test router
  - `backend/tests/test_metrics.py` — Tests for metrics router

  **WHY Each Reference Matters**:
  - Each exception location needs individual context analysis
  - main.py:73 exclusion prevents breaking startup resilience
  - Test files verify behavior preservation after narrowing

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Zero broad exceptions in production backend (except intentional)
    Tool: Bash
    Steps:
      1. grep -rn "except Exception" backend/routers/ backend/services/ backend/startup_metrics_shim.py backend/main.py --include="*.py" | grep -v "# intentional" | grep -v test
      2. Count matches
    Expected Result: 0 matches
    Failure Indicators: Any unmarked "except Exception" in production code
    Evidence: .sisyphus/evidence/task-5-all-exceptions.txt

  Scenario: main.py:73 preserved with intentional comment
    Tool: Bash
    Steps:
      1. grep -n "except Exception.*# intentional" backend/main.py
    Expected Result: At least 1 match with "intentional" comment
    Evidence: .sisyphus/evidence/task-5-main-preserved.txt

  Scenario: Full backend test suite passes
    Tool: Bash
    Steps:
      1. Run: cd backend && python3 -m pytest tests/ -x -q -m "not integration" 2>&1
      2. Compare pass count with baseline
    Expected Result: Same pass count as baseline, 0 failures
    Evidence: .sisyphus/evidence/task-5-tests.txt
  ```

  **Evidence to Capture:**
  - [x] .sisyphus/evidence/task-5-all-exceptions.txt
  - [x] .sisyphus/evidence/task-5-main-preserved.txt
  - [x] .sisyphus/evidence/task-5-tests.txt

  **Commit**: YES
  - Message: `refactor(backend): narrow remaining broad exception blocks`
  - Files: `backend/services/metrics_collector.py`, `backend/services/load_engine.py`, `backend/routers/load_test.py`, `backend/routers/vllm_config.py`, `backend/startup_metrics_shim.py`, `backend/services/model_resolver.py`, `backend/main.py`
  - Pre-commit: `cd backend && python3 -m pytest tests/ -x -q -m "not integration"`

---

- [x] 6. Add Return Type Annotations to All Backend Functions

  **What to do**:
  - Add return type annotations to all backend functions that are missing them (~12 functions)
  - Target files: `main.py`, `routers/load_test.py`, `routers/tuner.py`, `routers/vllm_config.py`, `routers/metrics.py`, `startup_metrics_shim.py`, `services/auto_tuner.py`, `services/load_engine.py`, `services/metrics_collector.py`
  - Common patterns:
    - FastAPI route handlers → `-> dict`, `-> JSONResponse`, `-> StreamingResponse`, `-> Response`
    - `__init__` methods → `-> None`
    - `subscribe/unsubscribe` → `-> None`
    - `stop` → `-> None`
    - `_broadcast` → `-> None`
    - `start_collection` → `-> None`
    - `register` → `-> None`
  - Use proper typing imports (`from typing import Optional`, `from fastapi.responses import JSONResponse`, etc.)
  - **ONLY add return types** — do NOT change parameter types, add docstrings, or refactor function bodies

  **Must NOT do**:
  - Change parameter types (G8)
  - Add docstrings (G8)
  - Refactor function bodies or signatures
  - Add type stubs or py.typed marker

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Mechanical addition of type annotations — no logic changes, straightforward
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 (with T4, T5, T9, T10, T11)
  - **Blocks**: None
  - **Blocked By**: T1, T2, T3 (decomposition may add new methods needing types)

  **References**:
  **Pattern References**:
  - `backend/routers/benchmark.py` — Example of well-typed router (if exists, use as reference)
  - `backend/models/load_test.py` — Pydantic models showing return types for responses

  **Test References**:
  - `backend/tests/` — Full test suite must pass after annotations

  **WHY Each Reference Matters**:
  - Existing typed functions show the project's annotation conventions
  - Pydantic models define the response shapes used in return type annotations

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: No missing return type annotations in backend
    Tool: Bash
    Steps:
      1. Use grep to find functions without return type: grep -rn "def .*):$" backend/ --include="*.py" | grep -v test | grep -v __pycache__ | grep -v ".pyc"
      2. Count functions missing "-> " before the colon
    Expected Result: 0 functions missing return types (or only __init__ with -> None)
    Failure Indicators: Functions found without -> annotation
    Evidence: .sisyphus/evidence/task-6-annotations.txt

  Scenario: Full backend test suite passes
    Tool: Bash
    Steps:
      1. Run: cd backend && python3 -m pytest tests/ -x -q -m "not integration" 2>&1
      2. Compare pass count with baseline
    Expected Result: Same pass count, 0 failures
    Evidence: .sisyphus/evidence/task-6-tests.txt
  ```

  **Evidence to Capture:**
  - [x] .sisyphus/evidence/task-6-annotations.txt
  - [x] .sisyphus/evidence/task-6-tests.txt

  **Commit**: YES
  - Message: `refactor(backend): add return type annotations to all functions`
  - Files: All backend .py files with missing annotations
  - Pre-commit: `cd backend && python3 -m pytest tests/ -x -q -m "not integration"`

- [x] 7. Decompose TunerPage.jsx into Sub-Components

  **What to do**:
  - Read `TunerPage.jsx` (441 lines) and identify logical sections
  - Extract these components:
    - `frontend/src/components/TunerConfigForm.jsx` — Configuration form with all parameter inputs. Receives `config` object + `onChange` handler + `onSubmit` as props. Manages no internal state.
    - `frontend/src/components/TunerResults.jsx` — Results display showing trials, best parameters, optimization history. Receives `trials`, `bestParams`, `status` as props.
  - TunerPage.jsx becomes the orchestrator: holds all state, passes props to children
  - **Config state pattern**: Pass entire `config` object + single `onChange(field, value)` handler (NOT 12 individual props)
  - Import new components in TunerPage.jsx
  - Ensure all existing inline styles travel with their JSX to the extracted components

  **Must NOT do**:
  - Add new UI features or visual states (G7)
  - Use Context, Redux, or Zustand (G5)
  - Change SSE subscription behavior
  - Change API call patterns
  - Change visual appearance

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
    - Reason: Component decomposition requires understanding state flow, prop threading, and event handling
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with T1, T2, T3, T8, T13, T14)
  - **Blocks**: T9, T10
  - **Blocked By**: T0

  **References**:
  **Pattern References**:
  - `frontend/src/pages/TunerPage.jsx` — Full 441-line component to decompose
  - `frontend/src/components/MetricCard.jsx` — Existing component pattern (props style, export pattern)
  - `frontend/src/components/Chart.jsx` — Another component pattern reference
  - `frontend/src/components/ErrorBoundary.jsx` — Error handling component pattern
  - `frontend/src/constants.js` — COLORS and other constants used by TunerPage

  **Test References**:
  - `frontend/src/pages/TunerPage.test.jsx` — Existing tests that must pass after decomposition

  **WHY Each Reference Matters**:
  - TunerPage.jsx is the decomposition target — read entirely before extracting
  - MetricCard.jsx and Chart.jsx show the project's component conventions (export style, prop naming)
  - constants.js is imported by TunerPage — extracted components need the same imports
  - TunerPage.test.jsx is the safety net

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: TunerPage reduced to orchestrator
    Tool: Bash
    Steps:
      1. wc -l frontend/src/pages/TunerPage.jsx
      2. Assert ≤ 200 lines (from 441)
      3. ls frontend/src/components/TunerConfigForm.jsx frontend/src/components/TunerResults.jsx
      4. Assert both files exist
    Expected Result: TunerPage ≤ 200 lines, both new component files exist
    Failure Indicators: TunerPage still > 200 lines or missing component files
    Evidence: .sisyphus/evidence/task-7-tuner-decomposed.txt

  Scenario: Config prop pattern correct
    Tool: Bash
    Steps:
      1. grep -n "config" frontend/src/components/TunerConfigForm.jsx | head -5
      2. Verify component receives config object as prop (not 12 individual props)
      3. grep -n "onChange" frontend/src/components/TunerConfigForm.jsx | head -5
    Expected Result: TunerConfigForm receives config + onChange props
    Evidence: .sisyphus/evidence/task-7-prop-pattern.txt

  Scenario: Frontend tests pass after decomposition
    Tool: Bash
    Steps:
      1. Run: cd frontend && npx vitest run 2>&1
      2. Compare pass count with baseline
    Expected Result: Same pass count, 0 failures
    Evidence: .sisyphus/evidence/task-7-tests.txt
  ```

  **Evidence to Capture:**
  - [x] .sisyphus/evidence/task-7-tuner-decomposed.txt
  - [x] .sisyphus/evidence/task-7-prop-pattern.txt
  - [x] .sisyphus/evidence/task-7-tests.txt

  **Commit**: YES
  - Message: `refactor(frontend): decompose TunerPage into sub-components`
  - Files: `frontend/src/pages/TunerPage.jsx`, `frontend/src/components/TunerConfigForm.jsx`, `frontend/src/components/TunerResults.jsx`
  - Pre-commit: `cd frontend && npx vitest run`

---

- [x] 8. Decompose LoadTestPage.jsx with useLoadTestSSE Hook

  **What to do**:
  - Read `LoadTestPage.jsx` (337 lines) and identify logical sections
  - Extract these pieces:
    - `frontend/src/components/LoadTestConfig.jsx` — Configuration form for load test parameters. Receives config + onChange + onSubmit as props.
    - `frontend/src/hooks/useLoadTestSSE.js` — Custom hook encapsulating EventSource management, reconnection logic, retry tracking. Returns `{ status, events, connect, disconnect }`. **Moves `esRef` and `retryCountRef` into the hook** so parent doesn't manage refs directly.
  - LoadTestPage.jsx becomes the orchestrator: uses `useLoadTestSSE()` hook + passes config to LoadTestConfig
  - **CRITICAL**: The EventSource reconnection logic and retry behavior must be preserved exactly — only move code, don't change behavior
  - Ensure all existing inline styles travel with their JSX

  **Must NOT do**:
  - Change SSE retry behavior or reconnection logic (G10)
  - Add new features (G7)
  - Use state management libraries (G5)
  - Change visual appearance

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
    - Reason: Custom hook extraction with ref management is tricky — EventSource lifecycle must be preserved
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with T1, T2, T3, T7, T13, T14)
  - **Blocks**: T9, T10
  - **Blocked By**: T0

  **References**:
  **Pattern References**:
  - `frontend/src/pages/LoadTestPage.jsx` — Full 337-line component to decompose
  - `frontend/src/pages/TunerPage.jsx` — Similar SSE pattern for comparison (if SSE is used there too)
  - `frontend/src/components/MetricCard.jsx` — Component convention reference

  **Test References**:
  - `frontend/src/pages/LoadTestPage.test.jsx` — Existing tests that must pass

  **WHY Each Reference Matters**:
  - LoadTestPage.jsx contains the EventSource refs that must be correctly migrated to hook
  - TunerPage may have a similar SSE pattern — consistency in extraction approach
  - LoadTestPage.test.jsx validates the refactoring

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: LoadTestPage decomposed with hook
    Tool: Bash
    Steps:
      1. wc -l frontend/src/pages/LoadTestPage.jsx
      2. Assert ≤ 200 lines (from 337)
      3. ls frontend/src/components/LoadTestConfig.jsx frontend/src/hooks/useLoadTestSSE.js
      4. Assert both files exist
    Expected Result: LoadTestPage ≤ 200 lines, both new files exist
    Failure Indicators: LoadTestPage > 200 lines or files missing
    Evidence: .sisyphus/evidence/task-8-loadtest-decomposed.txt

  Scenario: SSE hook contains EventSource logic
    Tool: Bash
    Steps:
      1. grep -c "EventSource\|esRef\|retryCount" frontend/src/hooks/useLoadTestSSE.js
      2. Assert ≥ 3 occurrences (EventSource management moved to hook)
      3. grep -c "EventSource" frontend/src/pages/LoadTestPage.jsx
      4. Assert 0 (EventSource no longer in page component — only in hook)
    Expected Result: EventSource logic in hook, not in page
    Failure Indicators: EventSource still in LoadTestPage.jsx
    Evidence: .sisyphus/evidence/task-8-sse-hook.txt

  Scenario: Frontend tests pass
    Tool: Bash
    Steps:
      1. Run: cd frontend && npx vitest run 2>&1
      2. Compare pass count with baseline
    Expected Result: Same pass count, 0 failures
    Evidence: .sisyphus/evidence/task-8-tests.txt
  ```

  **Evidence to Capture:**
  - [x] .sisyphus/evidence/task-8-loadtest-decomposed.txt
  - [x] .sisyphus/evidence/task-8-sse-hook.txt
  - [x] .sisyphus/evidence/task-8-tests.txt

  **Commit**: YES
  - Message: `refactor(frontend): decompose LoadTestPage with useLoadTestSSE hook`
  - Files: `frontend/src/pages/LoadTestPage.jsx`, `frontend/src/components/LoadTestConfig.jsx`, `frontend/src/hooks/useLoadTestSSE.js`
  - Pre-commit: `cd frontend && npx vitest run`

---

- [x] 9. Extract ErrorAlert Component and Begin CSS Migration

  **What to do**:
  - Create `frontend/src/components/ErrorAlert.jsx` — A reusable error display component
    - Accepts `message` prop (string)
    - Renders the error div with border styling using CSS class from `index.css`
    - Replaces the duplicated inline error `<div style={{border: ...COLORS.red...}}>` pattern in all 4 page components
  - Add `.error-alert` CSS class to `frontend/src/index.css`:
    ```css
    .error-alert {
      border: 1px solid var(--color-red, #ff4444);
      /* Copy exact styles from existing inline pattern */
      padding: 12px;
      border-radius: 4px;
      margin: 8px 0;
      color: var(--color-red, #ff4444);
    }
    ```
  - Replace all 4 inline error div patterns in `TunerPage.jsx`, `LoadTestPage.jsx`, `MonitorPage.jsx`, `BenchmarkPage.jsx` with `<ErrorAlert message={error} />`
  - Import ErrorAlert in each page file
  - **This merges Items E and F** — the "inconsistent error handling" is actually just duplicated inline-styled error divs

  **Must NOT do**:
  - Change error handling logic (when errors are set/cleared)
  - Change visual appearance (copy exact color/spacing values)
  - Introduce CSS frameworks (G6)
  - Add new error types or error messages

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Small, well-defined extraction — one component + 4 replacements
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 (with T4, T5, T6, T10, T11)
  - **Blocks**: T11
  - **Blocked By**: T7, T8 (decomposition changes the page files)

  **References**:
  **Pattern References**:
  - `frontend/src/pages/TunerPage.jsx` — Find the error div pattern (search for `COLORS.red` or `error &&`)
  - `frontend/src/pages/LoadTestPage.jsx` — Same error pattern
  - `frontend/src/pages/MonitorPage.jsx` — Same error pattern
  - `frontend/src/pages/BenchmarkPage.jsx` — Same error pattern
  - `frontend/src/components/MetricCard.jsx` — Component conventions to follow
  - `frontend/src/index.css` — Existing CSS classes to extend
  - `frontend/src/constants.js` — COLORS object with color values

  **WHY Each Reference Matters**:
  - All 4 page files contain the duplicated error pattern to replace
  - MetricCard shows component export conventions
  - index.css is where the new .error-alert class goes
  - constants.js has COLORS.red value to match in CSS

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: ErrorAlert component exists and is used
    Tool: Bash
    Steps:
      1. ls frontend/src/components/ErrorAlert.jsx
      2. grep -l "ErrorAlert" frontend/src/pages/*.jsx | wc -l
      3. Assert ≥ 3 pages import ErrorAlert
    Expected Result: ErrorAlert.jsx exists, imported by ≥3 pages
    Evidence: .sisyphus/evidence/task-9-erroralert.txt

  Scenario: No duplicate inline error divs remain
    Tool: Bash
    Steps:
      1. grep -rn "COLORS.red" frontend/src/pages/ --include="*.jsx" | grep "style=" | wc -l
      2. Assert 0 (all inline error styles replaced with ErrorAlert component)
    Expected Result: 0 inline error div patterns in page files
    Evidence: .sisyphus/evidence/task-9-no-inline-error.txt

  Scenario: Frontend tests pass
    Tool: Bash
    Steps:
      1. Run: cd frontend && npx vitest run 2>&1
      2. Compare pass count with baseline
    Expected Result: Same pass count, 0 failures
    Evidence: .sisyphus/evidence/task-9-tests.txt
  ```

  **Evidence to Capture:**
  - [x] .sisyphus/evidence/task-9-erroralert.txt
  - [x] .sisyphus/evidence/task-9-no-inline-error.txt
  - [x] .sisyphus/evidence/task-9-tests.txt

  **Commit**: YES
  - Message: `refactor(frontend): extract ErrorAlert component, remove duplicate inline error divs`
  - Files: `frontend/src/components/ErrorAlert.jsx`, `frontend/src/pages/TunerPage.jsx`, `frontend/src/pages/LoadTestPage.jsx`, `frontend/src/pages/MonitorPage.jsx`, `frontend/src/pages/BenchmarkPage.jsx`, `frontend/src/index.css`
  - Pre-commit: `cd frontend && npx vitest run`

- [x] 10. Migrate Inline Styles to CSS — TunerPage and LoadTestPage

  **What to do**:
  - In `TunerPage.jsx` (and extracted TunerConfigForm.jsx, TunerResults.jsx):
    - Find all `style={{...}}` attributes
    - Create corresponding CSS classes in `frontend/src/index.css` with descriptive names (e.g., `.tuner-config-section`, `.tuner-param-input`, `.tuner-trial-row`)
    - Replace inline styles with `className="tuner-..."` 
    - Copy exact CSS property values (colors, spacing, fonts) — do NOT change them
  - In `LoadTestPage.jsx` (and extracted LoadTestConfig.jsx):
    - Same process: create CSS classes (`.loadtest-config-form`, `.loadtest-progress-bar`, `.loadtest-results-table`)
    - Replace inline styles with className
  - Naming convention: `{page}-{element}` (e.g., `.tuner-trial-row`, `.loadtest-config-input`)
  - Use CSS custom properties for shared values where they already exist (e.g., `var(--color-red)`)
  - Check `constants.js` COLORS values and use matching CSS custom properties

  **Must NOT do**:
  - Change color, font, or spacing values (G14)
  - Introduce CSS frameworks (G6, G9)
  - Introduce CSS Modules (use plain classes in index.css)
  - Change component behavior or layout

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
    - Reason: Many inline styles to systematically convert across multiple files — requires careful value preservation
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 (with T4, T5, T6, T9, T11)
  - **Blocks**: T12
  - **Blocked By**: T7, T8 (component decomposition changes the files)

  **References**:
  **Pattern References**:
  - `frontend/src/pages/TunerPage.jsx` — All inline `style={{` attributes to migrate
  - `frontend/src/pages/LoadTestPage.jsx` — All inline `style={{` attributes to migrate
  - `frontend/src/components/TunerConfigForm.jsx` — Extracted component (from T7) with inline styles
  - `frontend/src/components/TunerResults.jsx` — Extracted component (from T7) with inline styles
  - `frontend/src/components/LoadTestConfig.jsx` — Extracted component (from T8) with inline styles
  - `frontend/src/index.css` — Existing CSS classes to follow pattern (`.btn`, `.metric-card`, `.table`)
  - `frontend/src/constants.js` — COLORS values to match in CSS

  **WHY Each Reference Matters**:
  - Page and component files are the migration targets
  - index.css existing classes show naming and style conventions
  - constants.js COLORS values should map to CSS custom properties

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Zero inline styles in TunerPage and LoadTestPage trees
    Tool: Bash
    Steps:
      1. grep -c 'style={{' frontend/src/pages/TunerPage.jsx frontend/src/pages/LoadTestPage.jsx frontend/src/components/TunerConfigForm.jsx frontend/src/components/TunerResults.jsx frontend/src/components/LoadTestConfig.jsx 2>/dev/null
      2. Sum all counts
    Expected Result: 0 total inline styles across all 5 files
    Failure Indicators: Any file has style={{ remaining
    Evidence: .sisyphus/evidence/task-10-inline-styles.txt

  Scenario: CSS classes added to index.css
    Tool: Bash
    Steps:
      1. grep -c "\.tuner-\|\.loadtest-" frontend/src/index.css
      2. Assert ≥ 8 new CSS class definitions
    Expected Result: ≥8 new CSS classes for tuner and loadtest components
    Evidence: .sisyphus/evidence/task-10-css-classes.txt

  Scenario: Frontend tests pass
    Tool: Bash
    Steps:
      1. Run: cd frontend && npx vitest run 2>&1
      2. Compare pass count with baseline
    Expected Result: Same pass count, 0 failures
    Evidence: .sisyphus/evidence/task-10-tests.txt
  ```

  **Evidence to Capture:**
  - [x] .sisyphus/evidence/task-10-inline-styles.txt
  - [x] .sisyphus/evidence/task-10-css-classes.txt
  - [x] .sisyphus/evidence/task-10-tests.txt

  **Commit**: YES
  - Message: `refactor(frontend): migrate TunerPage and LoadTestPage inline styles to CSS`
  - Files: `frontend/src/pages/TunerPage.jsx`, `frontend/src/pages/LoadTestPage.jsx`, `frontend/src/components/TunerConfigForm.jsx`, `frontend/src/components/TunerResults.jsx`, `frontend/src/components/LoadTestConfig.jsx`, `frontend/src/index.css`
  - Pre-commit: `cd frontend && npx vitest run`

---

- [x] 11. Migrate Inline Styles to CSS — Remaining Components

  **What to do**:
  - Migrate all remaining inline `style={{}}` to CSS classes in `index.css`:
    - `frontend/src/App.jsx` — Navigation tabs, layout container styles → `.app-nav`, `.app-tab`, `.app-tab-active`, `.app-container`
    - `frontend/src/pages/MonitorPage.jsx` — Metric grid, refresh controls → `.monitor-grid`, `.monitor-refresh-btn`
    - `frontend/src/pages/BenchmarkPage.jsx` — Table styles, comparison display → `.benchmark-table`, `.benchmark-comparison`
    - `frontend/src/components/Chart.jsx` — Chart container styling → `.chart-container`, `.chart-legend`
    - `frontend/src/components/MetricCard.jsx` — Card styling → `.metric-card-value`, `.metric-card-label` (extend existing `.metric-card`)
    - `frontend/src/components/MockDataSwitch.jsx` — Toggle styling → `.mock-switch`, `.mock-switch-label`
    - `frontend/src/components/ErrorBoundary.jsx` — Error display styling → `.error-boundary`, `.error-boundary-message`
  - Same rules as T10: copy exact values, descriptive class names, no visual changes

  **Must NOT do**:
  - Change any visual properties (G14)
  - Introduce CSS frameworks (G6)
  - Change component behavior
  - Conflict with existing CSS class names (check index.css before adding)

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
    - Reason: 7 files to migrate — systematic but requires careful value matching
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 (with T4, T5, T6, T9, T10)
  - **Blocks**: T12
  - **Blocked By**: T9 (ErrorAlert changes some pages)

  **References**:
  **Pattern References**:
  - `frontend/src/App.jsx` — Navigation inline styles
  - `frontend/src/pages/MonitorPage.jsx` — Monitor page inline styles
  - `frontend/src/pages/BenchmarkPage.jsx` — Benchmark page inline styles
  - `frontend/src/components/Chart.jsx` — Chart inline styles
  - `frontend/src/components/MetricCard.jsx` — MetricCard inline styles
  - `frontend/src/components/MockDataSwitch.jsx` — Switch inline styles
  - `frontend/src/components/ErrorBoundary.jsx` — Error boundary inline styles
  - `frontend/src/index.css` — Existing classes to extend, avoid name conflicts

  **WHY Each Reference Matters**:
  - Each file is a migration target — read current inline styles before creating CSS classes
  - index.css must be checked for existing class names to avoid conflicts

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Zero inline styles in entire frontend (non-test)
    Tool: Bash
    Steps:
      1. grep -rn 'style={{' frontend/src/ --include="*.jsx" --include="*.js" | grep -v node_modules | grep -v test | grep -v ".test." | wc -l
      2. Assert 0
    Expected Result: 0 inline styles remaining in any production frontend file
    Failure Indicators: Any style={{ found in production code
    Evidence: .sisyphus/evidence/task-11-zero-inline.txt

  Scenario: index.css has comprehensive class coverage
    Tool: Bash
    Steps:
      1. wc -l frontend/src/index.css
      2. Compare with baseline line count (should be significantly larger)
      3. grep -c "\." frontend/src/index.css (count total class selectors)
    Expected Result: Significantly more CSS classes than baseline
    Evidence: .sisyphus/evidence/task-11-css-coverage.txt

  Scenario: Frontend tests pass
    Tool: Bash
    Steps:
      1. Run: cd frontend && npx vitest run 2>&1
      2. Compare pass count with baseline
    Expected Result: Same pass count, 0 failures
    Evidence: .sisyphus/evidence/task-11-tests.txt
  ```

  **Evidence to Capture:**
  - [x] .sisyphus/evidence/task-11-zero-inline.txt
  - [x] .sisyphus/evidence/task-11-css-coverage.txt
  - [x] .sisyphus/evidence/task-11-tests.txt

  **Commit**: YES
  - Message: `refactor(frontend): migrate remaining inline styles to CSS classes`
  - Files: `frontend/src/App.jsx`, `frontend/src/pages/MonitorPage.jsx`, `frontend/src/pages/BenchmarkPage.jsx`, `frontend/src/components/Chart.jsx`, `frontend/src/components/MetricCard.jsx`, `frontend/src/components/MockDataSwitch.jsx`, `frontend/src/components/ErrorBoundary.jsx`, `frontend/src/index.css`
  - Pre-commit: `cd frontend && npx vitest run`

---

- [x] 12. Add Accessibility — ARIA Labels and Live Regions

  **What to do**:
  - Add ARIA attributes across ALL frontend components following this checklist:
    - **Every `<button>`**: Add `aria-label` if button has no visible text (icon-only buttons), or verify text content is descriptive
    - **Every `<input>`**: Add `aria-label` or associate with `<label htmlFor="...">` element
    - **Every `<select>`**: Add `aria-label` describing the selection purpose
    - **Loading/progress states**: Wrap in `<div aria-live="polite">` so screen readers announce changes
    - **SSE connection status** (reconnecting/connected/disconnected): Add `aria-live="assertive"` for important status changes
    - **Error displays** (ErrorAlert component): Add `role="alert"` and `aria-live="assertive"`
    - **Metric cards**: Add `aria-label` describing the metric (e.g., `aria-label="Current TPS: 150"`)
    - **Chart components**: Add `aria-label` describing chart purpose (e.g., `aria-label="Request latency over time"`)
    - **Tab navigation** (App.jsx): Add `role="tablist"`, `role="tab"`, `aria-selected` attributes
  - Target all files:
    - `App.jsx` — Tab navigation a11y
    - `TunerPage.jsx`, `TunerConfigForm.jsx`, `TunerResults.jsx` — Form + results a11y
    - `LoadTestPage.jsx`, `LoadTestConfig.jsx` — Form + status a11y
    - `MonitorPage.jsx` — Metrics display a11y
    - `BenchmarkPage.jsx` — Table + comparison a11y
    - `ErrorAlert.jsx` — Alert role
    - `MetricCard.jsx` — Metric label a11y
    - `Chart.jsx` — Chart description a11y
    - `MockDataSwitch.jsx` — Toggle a11y (already has 1 aria-label — verify and extend)
    - `ErrorBoundary.jsx` — Error boundary a11y

  **Must NOT do**:
  - Add keyboard shortcuts or focus management (G11)
  - Change visual appearance (no contrast ratio changes)
  - Add `role=` attributes to non-interactive elements without specific need
  - Change component behavior or state management

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
    - Reason: Touches all frontend files — needs systematic approach to hit every interactive element
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Wave 3 (solo — after all CSS is done)
  - **Blocks**: None
  - **Blocked By**: T10, T11 (CSS migration may add/move elements — ARIA must target final DOM)

  **References**:
  **Pattern References**:
  - `frontend/src/components/MockDataSwitch.jsx` — Has existing `aria-label` — follow this pattern
  - `frontend/src/components/ErrorAlert.jsx` — Created in T9, needs `role="alert"`
  - `frontend/src/App.jsx` — Tab navigation pattern
  - All page and component files listed above

  **External References**:
  - WAI-ARIA Authoring Practices: `https://www.w3.org/WAI/ARIA/apg/` — Tab pattern, alert pattern
  - MDN ARIA: `https://developer.mozilla.org/en-US/docs/Web/Accessibility/ARIA` — Label and live region usage

  **WHY Each Reference Matters**:
  - MockDataSwitch has the only existing ARIA attr — match its pattern
  - WAI-ARIA Authoring Practices define correct role/property combinations for tabs
  - ErrorAlert needs role="alert" per the alert pattern

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: ARIA coverage significantly increased
    Tool: Bash
    Steps:
      1. grep -rn 'aria-label\|aria-live\|aria-selected\|aria-labelledby\|role="alert"\|role="tab"' frontend/src/ --include="*.jsx" | wc -l
      2. Compare with baseline count (was 1)
      3. Assert ≥ 15 ARIA attributes across codebase
    Expected Result: ≥15 ARIA attributes (from baseline of 1)
    Failure Indicators: Fewer than 15 ARIA attributes
    Evidence: .sisyphus/evidence/task-12-aria-count.txt

  Scenario: All buttons have labels
    Tool: Bash
    Steps:
      1. Use ast-grep to find buttons without aria-label or text content
      2. grep -rn '<button' frontend/src/ --include="*.jsx" | grep -v aria-label | grep -v test
      3. For each match, verify it has visible text content
    Expected Result: Every button has either aria-label or visible text
    Failure Indicators: Buttons found with neither aria-label nor text
    Evidence: .sisyphus/evidence/task-12-buttons.txt

  Scenario: ErrorAlert has role="alert"
    Tool: Bash
    Steps:
      1. grep 'role="alert"' frontend/src/components/ErrorAlert.jsx
    Expected Result: role="alert" found in ErrorAlert component
    Failure Indicators: Missing role="alert"
    Evidence: .sisyphus/evidence/task-12-erroralert-role.txt

  Scenario: Tab navigation has ARIA roles
    Tool: Bash
    Steps:
      1. grep -n 'role="tab\|role="tablist\|aria-selected' frontend/src/App.jsx
      2. Assert ≥ 2 matches (tablist + at least one tab)
    Expected Result: Tab navigation has proper ARIA roles
    Evidence: .sisyphus/evidence/task-12-tabs.txt

  Scenario: Frontend tests pass
    Tool: Bash
    Steps:
      1. Run: cd frontend && npx vitest run 2>&1
      2. Compare pass count with baseline
    Expected Result: Same pass count, 0 failures
    Evidence: .sisyphus/evidence/task-12-tests.txt
  ```

  **Evidence to Capture:**
  - [x] .sisyphus/evidence/task-12-aria-count.txt
  - [x] .sisyphus/evidence/task-12-buttons.txt
  - [x] .sisyphus/evidence/task-12-erroralert-role.txt
  - [x] .sisyphus/evidence/task-12-tabs.txt
  - [x] .sisyphus/evidence/task-12-tests.txt

  **Commit**: YES
  - Message: `feat(a11y): add ARIA labels and live regions across all components`
  - Files: All frontend component and page files
  - Pre-commit: `cd frontend && npx vitest run`

- [x] 13. Kustomize: Parameterize Environment Variables and ALLOWED_ORIGINS

  **What to do**:
  - Move `ALLOWED_ORIGINS` from `openshift/base/02-config.yaml` ConfigMap to overlay-specific patches:
    - `openshift/overlays/dev/kustomization.yaml` — Add patch with dev domain (`https://vllm-optimizer-dev.apps.compact.jooan.local`)
    - `openshift/overlays/prod/kustomization.yaml` — Add patch with prod domain (placeholder or actual prod URL)
  - Move K8s env vars from inline Deployment spec to ConfigMap reference:
    - `K8S_NAMESPACE`, `K8S_DEPLOYMENT_NAME`, `K8S_CONFIGMAP_NAME` — These are in `openshift/base/03-backend.yaml` Deployment env section
    - Create ConfigMap entries for these in `02-config.yaml` (or reference existing entries)
    - Change Deployment env from `value:` to `valueFrom: configMapKeyRef:`
  - **EXCLUDE from parameterization**: Ports 8000/8080 (architectural constants per G13)
  - After each change, verify: `./kustomize build openshift/overlays/dev` and `./kustomize build openshift/overlays/prod` both succeed

  **Must NOT do**:
  - Parameterize ports 8000/8080 (G13)
  - Introduce Helm or restructure overlays (G12)
  - Change deploy.sh workflow
  - Break existing `oc apply -k` commands

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Well-defined YAML changes — move values between files, add ConfigMap refs
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with T1, T2, T3, T7, T8, T14)
  - **Blocks**: None
  - **Blocked By**: T0

  **References**:
  **Pattern References**:
  - `openshift/base/02-config.yaml` — ConfigMap with ALLOWED_ORIGINS and env vars
  - `openshift/base/03-backend.yaml` — Deployment with inline env vars to convert to ConfigMap refs
  - `openshift/overlays/dev/kustomization.yaml` — Dev overlay to add ALLOWED_ORIGINS patch
  - `openshift/overlays/prod/kustomization.yaml` — Prod overlay to add ALLOWED_ORIGINS patch

  **External References**:
  - Kustomize docs: `https://kubectl.docs.kubernetes.io/references/kustomize/` — Patch and ConfigMap strategies

  **WHY Each Reference Matters**:
  - 02-config.yaml is where ALLOWED_ORIGINS currently lives — needs to be removed/replaced
  - 03-backend.yaml has the Deployment env section to convert
  - Overlay kustomizations are where environment-specific patches go

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: ALLOWED_ORIGINS moved to overlays
    Tool: Bash
    Steps:
      1. grep "ALLOWED_ORIGINS" openshift/base/02-config.yaml | wc -l
      2. Assert 0 (removed from base)
      3. grep "ALLOWED_ORIGINS" openshift/overlays/dev/kustomization.yaml | wc -l
      4. Assert ≥ 1 (present in dev overlay)
    Expected Result: ALLOWED_ORIGINS in overlays, not in base
    Failure Indicators: Still in base or missing from overlays
    Evidence: .sisyphus/evidence/task-13-allowed-origins.txt

  Scenario: K8s env vars reference ConfigMap
    Tool: Bash
    Steps:
      1. grep -A2 "K8S_NAMESPACE\|K8S_DEPLOYMENT_NAME\|K8S_CONFIGMAP_NAME" openshift/base/03-backend.yaml | grep "configMapKeyRef" | wc -l
      2. Assert ≥ 3 (all three use configMapKeyRef)
    Expected Result: All K8s env vars use configMapKeyRef
    Failure Indicators: Any still using inline value:
    Evidence: .sisyphus/evidence/task-13-configmap-refs.txt

  Scenario: Kustomize builds succeed
    Tool: Bash
    Steps:
      1. ./kustomize build openshift/overlays/dev > /dev/null 2>&1 && echo "DEV: PASS" || echo "DEV: FAIL"
      2. ./kustomize build openshift/overlays/prod > /dev/null 2>&1 && echo "PROD: PASS" || echo "PROD: FAIL"
    Expected Result: Both show PASS
    Failure Indicators: Either shows FAIL
    Evidence: .sisyphus/evidence/task-13-kustomize-build.txt

  Scenario: Ports NOT parameterized (guardrail check)
    Tool: Bash
    Steps:
      1. grep -n "8000\|8080" openshift/base/03-backend.yaml openshift/base/04-frontend.yaml | head -10
      2. Verify ports are still hardcoded (intentional — architectural constants)
    Expected Result: Ports 8000/8080 still present as literal values
    Evidence: .sisyphus/evidence/task-13-ports-preserved.txt
  ```

  **Evidence to Capture:**
  - [x] .sisyphus/evidence/task-13-allowed-origins.txt
  - [x] .sisyphus/evidence/task-13-configmap-refs.txt
  - [x] .sisyphus/evidence/task-13-kustomize-build.txt
  - [x] .sisyphus/evidence/task-13-ports-preserved.txt

  **Commit**: YES
  - Message: `refactor(kustomize): parameterize env vars and move ALLOWED_ORIGINS to overlays`
  - Files: `openshift/base/02-config.yaml`, `openshift/base/03-backend.yaml`, `openshift/overlays/dev/kustomization.yaml`, `openshift/overlays/prod/kustomization.yaml`
  - Pre-commit: `./kustomize build openshift/overlays/dev > /dev/null && ./kustomize build openshift/overlays/prod > /dev/null`

---

- [x] 14. Kustomize: Resolve SECRET_KEY and Parameterize VLLM_ENDPOINT

  **What to do**:
  - **SECRET_KEY resolution**:
    - The current `SECRET_KEY: "CHANGE_ME_IN_PRODUCTION"` in `02-config.yaml` is a security concern
    - Add a comment above it: `# WARNING: Change this value in production. Create a proper K8s Secret with: oc create secret generic vllm-optimizer-secret --from-literal=SECRET_KEY=<your-secure-key> -n <namespace>`
    - Keep the value as-is for dev environment (changing deployment workflow is out of scope)
    - Document the production secret creation in a comment within the YAML
  - **VLLM_ENDPOINT parameterization**:
    - Move `VLLM_ENDPOINT` from base ConfigMap to overlay-specific patches
    - Dev: `http://llm-ov-predictor.vllm.svc.cluster.local:8080`
    - Prod: placeholder `http://vllm-predictor.vllm.svc.cluster.local:8080` (or actual prod value)
  - After each change, verify kustomize builds

  **Must NOT do**:
  - Change deployment workflow (G12)
  - Introduce external secret managers (Vault, external-secrets)
  - Remove SECRET_KEY from YAML entirely (would break dev deployment)
  - Introduce Helm

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Small, focused YAML changes — add comments + move one value to overlays
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with T1, T2, T3, T7, T8, T13)
  - **Blocks**: None
  - **Blocked By**: T0

  **References**:
  **Pattern References**:
  - `openshift/base/02-config.yaml` — SECRET_KEY and VLLM_ENDPOINT locations
  - `openshift/overlays/dev/kustomization.yaml` — Add VLLM_ENDPOINT patch
  - `openshift/overlays/prod/kustomization.yaml` — Add VLLM_ENDPOINT patch

  **WHY Each Reference Matters**:
  - 02-config.yaml has both values to handle
  - Overlay kustomizations are the target for environment-specific VLLM_ENDPOINT

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: SECRET_KEY has security warning comment
    Tool: Bash
    Steps:
      1. grep -B2 "SECRET_KEY" openshift/base/02-config.yaml | grep -i "WARNING\|change\|production\|oc create secret"
      2. Assert ≥ 1 match (warning comment exists)
    Expected Result: Warning comment present above SECRET_KEY
    Failure Indicators: No warning comment found
    Evidence: .sisyphus/evidence/task-14-secret-warning.txt

  Scenario: VLLM_ENDPOINT moved to overlays
    Tool: Bash
    Steps:
      1. grep "VLLM_ENDPOINT" openshift/base/02-config.yaml | wc -l
      2. Assert 0 (removed from base) OR has a default placeholder
      3. grep "VLLM_ENDPOINT" openshift/overlays/dev/kustomization.yaml | wc -l
      4. Assert ≥ 1 (present in dev overlay)
    Expected Result: VLLM_ENDPOINT in overlays with environment-specific values
    Evidence: .sisyphus/evidence/task-14-vllm-endpoint.txt

  Scenario: Kustomize builds succeed
    Tool: Bash
    Steps:
      1. ./kustomize build openshift/overlays/dev > /dev/null 2>&1 && echo "DEV: PASS" || echo "DEV: FAIL"
      2. ./kustomize build openshift/overlays/prod > /dev/null 2>&1 && echo "PROD: PASS" || echo "PROD: FAIL"
    Expected Result: Both show PASS
    Evidence: .sisyphus/evidence/task-14-kustomize-build.txt

  Scenario: No SECRET_KEY value change (behavior preservation)
    Tool: Bash
    Steps:
      1. ./kustomize build openshift/overlays/dev | grep "CHANGE_ME_IN_PRODUCTION"
      2. Assert ≥ 1 match (value still flows through for dev)
    Expected Result: Dev overlay still has the dev SECRET_KEY value
    Evidence: .sisyphus/evidence/task-14-secret-preserved.txt
  ```

  **Evidence to Capture:**
  - [x] .sisyphus/evidence/task-14-secret-warning.txt
  - [x] .sisyphus/evidence/task-14-vllm-endpoint.txt
  - [x] .sisyphus/evidence/task-14-kustomize-build.txt
  - [x] .sisyphus/evidence/task-14-secret-preserved.txt

  **Commit**: YES
  - Message: `refactor(kustomize): resolve SECRET_KEY warning and parameterize VLLM_ENDPOINT`
  - Files: `openshift/base/02-config.yaml`, `openshift/overlays/dev/kustomization.yaml`, `openshift/overlays/prod/kustomization.yaml`
  - Pre-commit: `./kustomize build openshift/overlays/dev > /dev/null && ./kustomize build openshift/overlays/prod > /dev/null`

---

## Final Verification Wave

> 4 review agents run in PARALLEL. ALL must APPROVE. Present consolidated results to user and get explicit "okay" before completing.

- [x] F1. **Plan Compliance Audit** — `oracle`
  Read the plan end-to-end. For each "Must Have": verify implementation exists (read file, run command). For each "Must NOT Have": search codebase for forbidden patterns — reject with file:line if found. Check evidence files exist in .sisyphus/evidence/. Compare deliverables against plan.
  Output: `Must Have [N/N] | Must NOT Have [N/N] | Tasks [N/N] | VERDICT: APPROVE/REJECT`

- [x] F2. **Code Quality Review** — `unspecified-high`
  Run `cd backend && python3 -m pytest tests/ -x -q -m "not integration"` + `cd frontend && npx vitest run`. Review all changed files for: broad exceptions remaining, inline styles remaining, missing type annotations, console.log in prod, unused imports. Check AI slop: excessive comments, over-abstraction, generic names.
  Output: `Backend Tests [PASS/FAIL] | Frontend Tests [PASS/FAIL] | Files [N clean/N issues] | VERDICT`

- [x] F3. **Real Manual QA** — `unspecified-high`
  Start from clean state. Verify all QA scenarios from every task — follow exact steps, capture evidence. Test cross-task integration (decomposed components rendering correctly, CSS classes applying correctly, ARIA attributes present on correct elements). Save to `.sisyphus/evidence/final-qa/`.
  Output: `Scenarios [N/N pass] | Integration [N/N] | Edge Cases [N tested] | VERDICT`

- [x] F4. **Scope Fidelity Check** — `deep`
  For each task: read "What to do", read actual diff (git log/diff). Verify 1:1 — everything in spec was built (no missing), nothing beyond spec was built (no creep). Check "Must NOT do" compliance for all 14 guardrails. Detect cross-task contamination. Flag unaccounted changes.
  Output: `Tasks [N/N compliant] | Guardrails [14/14 clean] | Contamination [CLEAN/N issues] | VERDICT`

---

## Commit Strategy

| Commit | Message | Files | Pre-commit |
|--------|---------|-------|-----------|
| T0 | `chore: capture test baselines` | `.sisyphus/evidence/` | — |
| T1 | `refactor(auto-tuner): decompose start() into focused private methods` | `auto_tuner.py` | `pytest tests/test_tuner.py -v` |
| T2 | `refactor(auto-tuner): decompose _evaluate() into warmup and probe phases` | `auto_tuner.py` | `pytest tests/test_tuner.py -v` |
| T3 | `refactor(load-engine): decompose run() into init, process, finalize methods` | `load_engine.py` | `pytest tests/test_load_test.py -v` |
| T4 | `refactor(auto-tuner): narrow except Exception to specific types` | `auto_tuner.py` | `pytest tests/test_tuner.py -v` |
| T5 | `refactor(backend): narrow remaining broad exception blocks` | `metrics_collector.py`, `load_test.py`, `load_engine.py`, `vllm_config.py`, `startup_metrics_shim.py`, `model_resolver.py` | `pytest tests/ -x -q -m "not integration"` |
| T6 | `refactor(backend): add return type annotations` | All backend files | `pytest tests/ -x -q -m "not integration"` |
| T7 | `refactor(frontend): decompose TunerPage into sub-components` | `TunerPage.jsx`, new components | `vitest run` |
| T8 | `refactor(frontend): decompose LoadTestPage with useLoadTestSSE hook` | `LoadTestPage.jsx`, new components, new hook | `vitest run` |
| T9 | `refactor(frontend): extract ErrorAlert component` | `ErrorAlert.jsx`, 4 page files, `index.css` | `vitest run` |
| T10 | `refactor(frontend): migrate TunerPage and LoadTestPage inline styles to CSS` | `TunerPage.jsx`, `LoadTestPage.jsx`, `index.css` | `vitest run` |
| T11 | `refactor(frontend): migrate remaining inline styles to CSS classes` | `App.jsx`, `MonitorPage.jsx`, `BenchmarkPage.jsx`, `Chart.jsx`, `MetricCard.jsx`, `MockDataSwitch.jsx`, `ErrorBoundary.jsx`, `index.css` | `vitest run` |
| T12 | `feat(a11y): add ARIA labels and live regions across all components` | All frontend component files | `vitest run` |
| T13 | `refactor(kustomize): parameterize env vars and move ALLOWED_ORIGINS to overlays` | `02-config.yaml`, `03-backend.yaml`, overlay kustomizations | `kustomize build` |
| T14 | `refactor(kustomize): resolve SECRET_KEY and parameterize VLLM_ENDPOINT` | `02-config.yaml`, overlay kustomizations | `kustomize build` |

---

## Success Criteria

### Verification Commands
```bash
# Backend tests (same pass count as baseline)
cd backend && python3 -m pytest tests/ -x -q -m "not integration"

# Frontend tests (same pass count as baseline)  
cd frontend && npx vitest run

# Kustomize builds
./kustomize build openshift/overlays/dev > /dev/null && echo PASS
./kustomize build openshift/overlays/prod > /dev/null && echo PASS

# No broad exceptions remaining (production code only)
grep -rn "except Exception" backend/routers/ backend/services/ --include="*.py" | grep -v test | grep -v "# intentional"
# Expected: 0 matches

# No monster functions remaining
awk '/^    (async )?def /{name=$0; count=0} {count++} count==61{print FILENAME":"NR": "name" exceeds 60 lines"}' backend/services/auto_tuner.py backend/services/load_engine.py
# Expected: 0 output

# No inline styles remaining
grep -rn 'style={{' frontend/src/ --include="*.jsx" --include="*.js" | grep -v node_modules | grep -v test
# Expected: 0 matches

# ARIA coverage
grep -rn 'aria-label\|aria-live\|aria-labelledby' frontend/src/ --include="*.jsx" | wc -l
# Expected: ≥15 (from baseline of 1)
```

### Final Checklist
- [x] All "Must Have" items present and verified
- [x] All 14 "Must NOT Have" guardrails confirmed clean
- [x] All tests pass with same count as baseline
- [x] Kustomize overlays build successfully
- [x] No inline styles in frontend
- [x] No broad exceptions in production backend
- [x] No monster functions (>60 lines) in backend services
- [x] ARIA attributes on all interactive elements
