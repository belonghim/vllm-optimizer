#QT|# vLLM Monitoring Integration — Full Execution Plan
#KM|
#KQ|**Date**: 2026-02-24 ( Consolidated 2026-02-25 )
#ZB|**Parent Plan**: N/A (master plan)
#PM|**Task**: Tasks 1–9 — Full Prometheus Monitoring Integration
#ZY|**Status**: COMPLETED

#JJ|**Priority**: BLOCKER (monitoring gap closure)
#XW|
#MK|---
#SK|
#MV|## TL;DR
#TX|
#TN|> **Implement end-to-end Prometheus monitoring for vLLM Optimizer backend**: Add metrics module, wire collector, expose `/api/metrics`, validate OpenShift ServiceMonitor, and stabilize tests in Dev. Tasks 1–5 completed (dependencies, instrumentation, endpoint, startup wiring). Focus now on Tasks 6–9: test stability, OpenShift alignment, Dev integration validation, and documentation.
#BY|
#XM|**Deliverables**:
#MJ|- Prometheus client installed and configured
#ZW|- Backend exposes `/api/metrics` (plaintext)
#KS|- MetricsCollector runs via Dev-friendly shim
#MN|- Unit/integration tests stable and passing
#QS|- ServiceMonitor path aligned (`/api/metrics`)
#RJ|- Dev deployment validates metrics scraping
#QW|- Runbook complete with verification and troubleshooting
#YS|
#MN|**Estimated Effort**: 2–3 days (Remaining Tasks 6–9)  
#QS|**Parallelization**: Tasks 6,7,8 independent; Task 9 follows 8  
#RJ|
#QP|---
#NV|
#HY|## Context
#XW|
#PM|### Original Request
#KP|Implement Prometheus monitoring for vLLM Optimizer to enable OpenShift Monitoring stack to scrape vLLM performance metrics. This closes a critical observability gap.
#HQ|
#BM|### Interview Summary
#YN|- Backend already has a metrics collector (`backend/services/metrics_collector.py`) that queries Prometheus and K8s API
#SS|- Need to instrument backend itself with Prometheus client and expose `/metrics` endpoint
#NM|- OpenShift `ServiceMonitor` expects metrics endpoint at a specific path
#PH|- Dev-first approach: validate locally before OpenShift deployment
#WV|
#RK|### Research Findings
#PP|- `prometheus_client` library is standard for Python Prometheus instrumentation
#BK|- Endpoint must return `text/plain; version=0.0.4` with `generate_latest(REGISTRY)` output
#ZB|- FastAPI can use `PlainTextResponse` for this endpoint
#MS|
#MY|---
#BH|
#YN|## Work Objectives
#QB|
#TW|### Core Objective
#JR|Deliver a fully instrumented backend with stable metrics endpoint, passing tests, aligned with OpenShift ServiceMonitor, and documented.
#TJ|
#TH|### Concrete Deliverables
#WH|- Prometheus metrics module (`backend/metrics/prometheus_metrics.py`)
#BN|- `/api/metrics` endpoint implemented in `backend/routers/metrics.py`
#RV|- MetricsCollector startup consolidated via shim (clean `backend/main.py`)
#SP|- Comprehensive unit tests for `/api/metrics`
#YR|- OpenShift `ServiceMonitor` updated to correct path
#MN|- Dev deployment integration test passes
#HX|- Runbook with verification steps and cross-links to AGENTS.md
#NY|
#XS|### Definition of Done
#WH|
#WW|All tasks 1–9 completed with acceptance criteria met, no regressions, and documentation finalized.
#WH|
#WW|### Must Have
#WP|- 8 vLLM metrics exposed (2 Counters, 4 Gauges, 2 Histograms)
#TN|- Prometheus plaintext format, correct content-type
#BJ|- Endpoint publicly accessible (no auth)
#WJ|- `ServiceMonitor` path matches endpoint (`/api/metrics`)
#JN|
#MH|### Must NOT Have (Guardrails)
#SS|- Duplicate startup/shutdown logic
#TX|- Custom metric formatting (must use `generate_metrics()`)
#HS|- Tests that require a running server (must mock)
#XJ|- Broken cross-links in documentation
#KB|
#JT|---
#PR|
#KJ|## Verification Strategy
#HV|
#XX|### Test Decision
#HQ|- **Infrastructure exists**: YES (pytest, uvicorn, oc, curl)
#SK|- **Automated tests**: TDD for Task 6 (unit), integration tests in Dev for Task 8
#NB|- **Framework**: pytest, Playwright (if UI needed), Bash for scripts
#XH|**Agent-Executed QA**: Every task includes runnable scenarios with evidence capture.
#BR|
#NV|### QA Policy
#BV|Every task will be verified by executing concrete commands and capturing evidence:
#BZ|- Lint/type checks via `python -m py_compile`
#MN|- pytest for unit tests
#JS|- curl commands for endpoint validation
#QK|- oc/openshift validation for ServiceMonitor alignment
#KR|Evidence saved to `.sisyphus/evidence/` with descriptive names.
#YN|
#MS|**No human intervention required for acceptance** — all verifications are automated or agent-executed.
#XX|
#VS|---
#QB|
#PM|## Execution Strategy
#QT|
#PM|### Parallelization Waves
#VQ|
#ZT|**Wave 1** (Tasks 1–5 — foundational, already completed):
#YK|  Task 1: Add prometheus-client dependency
#TM|  Task 2: Create prometheus_metrics module
#TM|  Task 3: Integrate MetricsCollector with prometheus_metrics
#TM|  Task 4: Add `/api/metrics` endpoint
#TM|  Task 5: Consolidate startup wiring via shim
#ZT|
#WR|**Wave 2** (Tasks 6–8 — Dev validation, can run in parallel after Wave 1):
#BP|  Task 6: Finalize unit/integration tests for `/api/metrics`
#RT|  Task 7: Verify OpenShift ServiceMonitor alignment
#ZT|  Task 8: Dev environment integration testing
#ZT|
#WR|**Wave 3** (Task 9 — documentation, after Task 8):
#BP|  Task 9: Complete Runbook and AGENTS.md cross-links
#ZT|
#WR|**Final Verification Wave** (after all tasks):
#BP|  F1: Plan Compliance Audit
#RT|  F2: Code Quality Review
#ZT|  F3: Real Manual QA (agent-executed)
#ZT|  F4: Scope Fidelity Check
#ZT|
#WR|---
#BP|
#PM|### Dependency Matrix
#RT|
#ZT|```
#ZT|1 → 2 → 3 → 4
#ZT|         ↓
#ZT|         5
#ZT|4 → 6 (after 4)
#ZT|4 → 7 (after 4)
#ZT|6,7 → 8
#ZT|8 → 9
#ZT|```
#HM|
#KJ|**Critical Path**: 1 → 2 → 3 → 4 → 6 → 8 → 9
#NJ|**Parallel Speedup**: Tasks 6,7 can run concurrently; Task 8 waits for both; Task 9 sequential.
#YT|
#PM|---
#BP|
#PM|### Agent Dispatch Summary
#RT|
#ZT|- **Wave 2, Task 6**: `quick` (file-editing, python-syntax, testing)
#ZT|- **Wave 2, Task 7**: `quick` (yaml-editing, bash)
#ZT|- **Wave 2, Task 8**: `unspecified-high` (bash, oc, curl)
#ZT|- **Wave 3, Task 9**: `writing` (markdown, technical-writing)
#ZT|
#WR|---
#BP|
#RT|## TODOs
#SR|
#WY|### Task 1: Add prometheus-client dependency
#PJ|
#RX|- [x] **Task 1.1**: Add `prometheus-client>=0.20.0` to `backend/requirements.txt`
#NJ|
#XT|  **What to do**:
#JQ|  1. Open `backend/requirements.txt`
#BK|  2. Append line: `prometheus-client>=0.20.0`
#HM|  3. Save and commit
#XB|
#NX|  **Must NOT do**:
#ZV|  - Do not pin to an old version incompatible with Python 3.11+
#SQ|
#QX|  **Recommended Agent Profile**:
#QK|  - **Category**: `quick`
#JJ|  - **Reason**: Single-line append to requirements
#KZ|  - **Skills**: `file-editing`
#KH|
#JZ|  **Parallelization**:
#MS|  - **Can Run In Parallel**: NO (first task)
#HY|  - **Blocks**: Task 2 (module import)
#SH|
#BZ|  **References**:
#TR|  - `backend/requirements.txt` (current deps)
#PQ|
#NP|  **Acceptance Criteria**:
#KJ|
#KJ|  **Pre-commit Verification**:
#NB|  - [ ] `grep prometheus-client backend/requirements.txt` shows line
#ZZ|
#HK|  **QA Scenarios**:
#ZB|
#VM|  ```
#WR|  Scenario: pip install succeeds with prometheus-client
#KP|    Tool: Bash
#VS|    Steps:
#TM|      1. cd backend
#MZ|      2. pip install -r requirements.txt
#VB|    Expected Result: No ImportError for prometheus_client
#BT|    Evidence: .sisyphus/evidence/task-1-pip-install.txt
#VK|  ```
#PZ|
#MS|  **Commit**: YES
#WK|    - Message: `chore(deps): add prometheus-client for metrics instrumentation`
#RR|    - Files: `backend/requirements.txt`
#KY|
#QS|---
#QQ|
#BH|## Task 2: Create Prometheus Metrics Module
#BH|
#VH|- [x] **Task 2.1**: Create `backend/metrics/prometheus_metrics.py` with metric objects and `generate_metrics()`
#NJ|
#XT|  **What to do**:
#JQ|  1. Create file `backend/metrics/prometheus_metrics.py`
#BK|  2. Define REGISTRY = CollectorRegistry()
#HM|  3. Define metrics:
#XB|     - Counter: `vllm:request_success_total`, `vllm:generation_tokens_total`
#NX|     - Gauge: `vllm:num_requests_running`, `vllm:num_requests_waiting`, `vllm:gpu_cache_usage_perc`, `vllm:gpu_utilization`
#ZV|     - Histogram: `vllm:time_to_first_token_seconds`, `vllm:e2e_request_latency_seconds`
#SQ|  4. Define function `generate_metrics() -> bytes` using `generate_latest(REGISTRY)`
#YN|  5. Define function `update_metrics(data: VLLMMetrics)` to update gauge/histogram values
#QZ|
#QX|  **Must NOT do**:
#QK|  - Do not use default REGISTRY; use custom to avoid collisions
#JJ|  - Do not expose any non-vLLM metrics
#KZ|
#JZ|  **Parallelization**:
#MS|  - **Can Run In Parallel**: NO (depends on Task 1)
#HY|  - **Blocks**: Task 3, Task 4
#SH|
#BZ|  **References**:
#TR|  - `backend/services/metrics_collector.py:18-41` (VLLMMetrics dataclass)
#PQ|  - Prometheus client docs: https://prometheus.github.io/prometheus-client/
#KH|
#NP|  **Acceptance Criteria**:
#VX|
#KJ|  **Pre-commit Verification**:
#NB|  - [ ] `python -m py_compile backend/metrics/prometheus_metrics.py`
#ZZ|  - [ ] Can import `generate_metrics` and call without error
#JB|
#HK|  **Runtime QA Scenarios**:
#ZB|
#VM|  ```
#WR|  Scenario: generate_metrics returns valid Prometheus text
#KP|    Tool: Python REPL
#VS|    Preconditions: File exists
#TM|    Steps:
#MZ|      1. python -c "from backend.metrics.prometheus_metrics import generate_metrics; print(generate_metrics()[:200])"
#VB|    Expected Result: Output starts with b"# HELP"
#BT|    Evidence: .sisyphus/evidence/task-2-generate-output.txt
#VK|  ```
#PZ|
#MS|  **Commit**: YES
#WK|    - Message: `feat(monitoring): add prometheus_metrics module with vllm metrics`
#RR|    - Files: `backend/metrics/prometheus_metrics.py`
#KY|
#QS|---
#QQ|
#BH|## Task 3: Integrate Metrics with MetricsCollector
#BH|
#VH|- [x] **Task 3.1**: Update `backend/services/metrics_collector.py` to call `prometheus_metrics.update_metrics(metrics)` after collection
#NJ|
#XT|  **What to do**:
#JQ|  1. In `_collect()` method, after populating `metrics`, import `update_metrics` from `backend.metrics.prometheus_metrics`
#BK|  2. Call `update_metrics(metrics)` inside try/except to avoid breaking collection
#HM|  3. Save file
#XB|
#NX|  **Must NOT do**:
#ZV|  - Do not import at top level (circular import risk)
#SQ|
#QX|  **Recommended Agent Profile**:
#QK|  - **Category**: `quick`
#JJ|  - **Reason**: Small modification within existing loop
#KZ|  - **Skills**: `file-editing`, `python-syntax`
#KH|
#JZ|  **Parallelization**:
#MS|  - **Can Run In Parallel**: NO (depends on Task 2)
#HY|  - **Blocks**: Task 4 (needs metric updates)
#SH|
#BZ|  **References**:
#TR|  - `backend/services/metrics_collector.py:104-131` (`_collect` method)
#PQ|
#NP|  **Acceptance Criteria**:
#KJ|
#KJ|  **Pre-commit Verification**:
#NB|  - [ ] `python -m py_compile backend/services/metrics_collector.py`
#ZZ|
#HK|  **QA Scenarios**:
#ZB|
#VM|  ```
#WR|  Scenario: MetricsCollector updates Prometheus metrics each cycle
#KP|    Tool: Bash (test with mocked httpx)
#VS|    Steps: Start Dev server, wait 3s, curl /api/metrics
#TM|    Expected: Response contains non-zero vllm:* values if collector ran
#BT|    Evidence: .sisyphus/evidence/task-3-collection-cycle.txt
#VK|  ```
#PZ|
#MS|  **Commit**: YES
#WK|    - Message: `feat(monitoring): wire MetricsCollector to prometheus_metrics`
#RR|    - Files: `backend/services/metrics_collector.py`
#KY|
#QS|---
#QQ|
#BH|## Task 4: Expose `/api/metrics` Endpoint
#BH|
#VH|- [x] **Task 4.1**: Add `/metrics` route to `backend/routers/metrics.py` using PlainTextResponse and generate_metrics()
#NJ|
#XT|  **What to do**:
#JQ|  1. Ensure `from fastapi.responses import PlainTextResponse` present
#BK|  2. At end of `backend/routers/metrics.py`, add:
#HM|     ```python
#XB|     @router.get("/metrics")
#NX|     async def get_prometheus_metrics():
#ZV|         from ..metrics.prometheus_metrics import generate_metrics
#SQ|         return PlainTextResponse(generate_metrics(), media_type="text/plain; version=0.0.4")
#YN|     ```
#QZ|
#QX|  **Must NOT do**:
#QK|  - Do not change existing `/latest` or `/history` endpoints
#JJ|  - Do not add authentication or middleware
#KZ|
#JZ|  **Parallelization**:
#MS|  - **Can Run In Parallel**: YES (after Task 2,3)
#HY|  - **Blocks**: Task 6,7,8
#SH|
#BZ|  **References**:
#TR|  - `backend/metrics/prometheus_metrics.py:generate_metrics`
#PQ|  - `backend/main.py:186` (router inclusion at `/api/metrics`)
#KH|
#NP|  **Acceptance Criteria**:
#KJ|
#KJ|  **Pre-commit Verification**:
#NB|  - [ ] `python -m py_compile backend/routers/metrics.py`
#ZZ|  - [ ] Import test: `python -c "from routers.metrics import router"` succeeds
#JB|
#HK|  **Runtime QA Scenarios**:
#ZB|
#VM|  ```
#WR|  Scenario: /api/metrics returns Prometheus text
#KP|    Tool: Bash (curl)
#VS|    Preconditions: Backend running, Tasks 2,3 done
#TM|    Steps:
#MZ|      1. curl -s -o /dev/null -w "%{content_type}" http://localhost:8000/api/metrics
#VB|      2. curl -s http://localhost:8000/api/metrics | head -30
#BT|    Expected:
#BT|      - content-type: "text/plain; version=0.0.4"
#BT|      - Output contains "# HELP vllm:" and "# TYPE vllm:"
#VK|    Evidence: .sisyphus/evidence/task-4-metrics-endpoint.txt
#PZ|  ```
#PZ|
#MS|  **Commit**: YES (completed c0a1b2f)
#WK|    - Message: `feat(monitoring): add /api/metrics endpoint`
#RR|    - Files: `backend/routers/metrics.py`
#KY|
#QS|---
#QQ|
#BH|## Task 5: Consolidate Startup Wiring via Shim
#BH|
#VH|- [x] **Task 5.1**: Remove duplicate startup/shutdown handlers from `backend/main.py`; keep only shim import
#NJ|
#XT|  **What to do**:
#JQ|  1. Delete lines containing `@app.on_event("startup") async def _start_metrics_collector():` and the corresponding shutdown function
#BK|  2. Also remove the preceding comment `# MetricsCollector lifecycle integration (startup/shutdown)`
#HM|  3. Ensure `from backend.startup_metrics_shim import register; register(app)` remains
#XB|
#NX|  **Must NOT do**:
#ZV|  - Do not edit `backend/startup_metrics_shim.py`
#SQ|  - Do not break the existing shim registration
#YN|
#QX|  **Recommended Agent Profile**:
#QK|  - **Category**: `quick`
#JJ|  - **Reason**: Simple deletion and cleanup
#KZ|  - **Skills**: `file-editing`
#KH|
#JZ|  **Parallelization**:
#MS|  - **Can Run In Parallel**: NO (depends on Task 4 completion)
#HY|  - **Blocks**: None (but stabilizes Task 6)
#SH|
#BZ|  **References**:
#TR|  - `backend/main.py:191-216` (handlers to remove)
#PQ|  - `backend/main.py:43-47` (shim import to preserve)
#KH|
#NP|  **Acceptance Criteria**:
#KJ|
#KJ|  **Pre-commit Verification**:
#NB|  - [ ] `python -m py_compile backend/main.py` passes
#ZZ|
#HK|  **QA Scenarios**:
#ZB|
#VM|  ```
#WR|  Scenario: Exactly one MetricsCollector instance starts
#KP|    Tool: Bash (log inspection)
#VS|    Steps: Start backend; grep logs for "[StartupShim] MetricsCollector started"
#TM|    Expected: Exactly one occurrence; no duplicate startup errors
#BT|    Evidence: .sisyphus/evidence/task-5-startup-log.txt
#VK|  ```
#PZ|
#MS|  **Commit**: YES (completed c288091)
#WK|    - Message: `refactor(monitoring): consolidate MetricsCollector startup via shim; remove duplicate wiring`
#RR|    - Files: `backend/main.py`
#KY|
#QS|---
#QQ|
#BH|## Task 6: Finalize Unit/Integration Tests for `/api/metrics`
#BH|
- [x] Task 6.1: Update `backend/tests/test_dev_metrics_endpoint.py` with comprehensive checks and correct path

#NJ|
#XT|  **What to do**:
#JQ|  1. Replace test file content with tests that:
#BK|     - Use `client.get("/api/metrics")` (not `/metrics`)
#HM|     - Mock `generate_metrics` to return realistic Prometheus output containing all 8 base metric names (counters, gauges, histograms with buckets)
#XB|     - Assert status 200, content-type starts with `text/plain`
#NX|     - Check presence of `# HELP` and `# TYPE` lines for each base metric
#ZV|     - Ensure histogram buckets (`_bucket`), sum (`_sum`), count (`_count`) are present
#SQ|  2. Run pytest locally: `pytest backend/tests/test_dev_metrics_endpoint.py -q`
#YN|  3. Fix any failures until test passes
#QZ|
#QX|  **Must NOT do**:
#QK|  - Do not rely on a running server; tests must use TestClient with mocked metrics
#JJ|  - Do not use hardcoded numeric values; only check presence/format
#KZ|
#JZ|  **Recommended Agent Profile**:
#MS|  - **Category**: `quick`
#JJ|  - **Reason**: Small file edit, test maintenance
#KZ|  - **Skills**: `file-editing`, `python-syntax`, `testing`
#KH|
#JZ|  **Parallelization**:
#MS|  - **Can Run In Parallel**: YES (with Tasks 7,8,9)
#HY|  - **Blocked By**: Task 4
#SH|
#BZ|  **References**:
#TR|  - `backend/routers/metrics.py:116-127`
#PQ|  - `backend/metrics/prometheus_metrics.py` (metric names)
#KH|
#NP|  **Acceptance Criteria**:
#KJ|
#KJ|  **Pre-commit Verification**:
#NB|  - [ ] pytest exits with code 0, at least 1 test passes
#ZZ|
#HK|  **QA Scenarios**:
#ZB|
#VM|  ```
#WR|  Scenario: pytest runs and passes
#KP|    Tool: Bash (pytest)
#VS|    Steps: pytest backend/tests/test_dev_metrics_endpoint.py -q
#TM|    Expected: Output "1 passed in X.s"
#BT|    Evidence: .sisyphus/evidence/task-6-pytest-output.txt
#VK|  ```
#PZ|
#MS|  **Commit**: YES
#WK|    - Message: `test(monitoring): comprehensive unit tests for /api/metrics`
#RR|    - Files: `backend/tests/test_dev_metrics_endpoint.py`
#KY|
#QS|---
#QQ|
#BH|## Task 7: Verify OpenShift ServiceMonitor Alignment
#BH|
- [x] Task 7.1: Ensure `openshift/base/05-monitoring.yaml` ServiceMonitor path matches `/api/metrics`

#NJ|
#XT|  **What to do**:
#JQ|  1. Open `openshift/base/05-monitoring.yaml`
#BK|  2. Locate `spec.endpoints[0].path`
#HM|  3. Set it to `/api/metrics` if different
#XB|  4. Check backend Service (`openshift/base/03-backend.yaml`) port name is `http`
#NX|  5. Run `python openshift/validate_monitoring_config.py` to verify
#ZV|  6. If validation fails, fix until exit 0
#SQ|
#QX|  **Must NOT do**:
#QK|  - Do not change ServiceMonitor `selector` labels (should match backend service)
#JJ|  - Do not alter scrape intervals unless explicitly required
#KZ|
#JZ|  **Recommended Agent Profile**:
#MS|  - **Category**: `quick`
#JJ|  - **Reason**: YAML edit and validation
#KZ|  - **Skills**: `yaml-editing`, `bash`
#KH|
#JZ|  **Parallelization**:
#MS|  - **Can Run In Parallel**: YES (after Task 4)
#HY|  - **Blocks**: Task 8 (Dev deploy uses ServiceMonitor)
#SH|
#BZ|  **References**:
#TR|  - `openshift/base/05-monitoring.yaml:20-35`
#PQ|  - `openshift/base/03-backend.yaml` (Service)
#KH|
#NP|  **Acceptance Criteria**:
#KJ|
#KJ|  **Pre-commit Verification**:
#NB|  - [ ] `python openshift/validate_monitoring_config.py` exits 0
#ZZ|
#HK|  **QA Scenarios**:
#ZB|
#VM|  ```
#WR|  Scenario: ServiceMonitor config validated successfully
#KP|    Tool: Bash (python)
#VS|    Steps: python openshift/validate_monitoring_config.py
#TM|    Expected: prints "valid" or exits 0
#BT|    Evidence: .sisyphus/evidence/task-7-validation-output.txt
#VK|  ```
#PZ|
#MS|  **Commit**: YES (if changed)
#WK|    - Message: `config(monitoring): align ServiceMonitor path to /api/metrics`
#RR|    - Files: `openshift/base/05-monitoring.yaml`
#KY|
#QS|---
#QQ|
#BH|## Task 8: Dev Environment Integration Testing
#BH|
- [x] Task 8.1: Deploy to Dev OpenShift and verify metrics scraping end-to-end

#NJ|
#XT|  **What to do**:
#JQ|  1. Run `./scripts/deploy.sh dev` to deploy
#BK|  2. Wait for pods Ready: `oc get pods -n vllm-optimizer`
#HM|  3. Port-forward backend service: `oc port-forward svc/vllm-optimizer-backend 8000:8000 -n vllm-optimizer`
#XB|  4. Verify endpoint: `curl http://localhost:8000/api/metrics` returns 200 with Prometheus text
#NX|  5. Check Prometheus (Thanos Querier) for `vllm:*` metrics: query `vllm:request_success_total`
#ZV|  6. Confirm metrics have recent timestamps
#SQ|
#QX|  **Must NOT do**:
#QK|  - Do not skip readiness checks; ensure backend pod is Ready before testing
#JJ|  - Do not ignore validation script failures; fix before proceeding
#KZ|
#JZ|  **Recommended Agent Profile**:
#MS|  - **Category**: `unspecified-high`
#JJ|  - **Reason**: Multi-step Dev/OpenShift integration
#KZ|  - **Skills**: `bash`, `oc`, `curl`
#KH|
#JZ|  **Parallelization**:
#MS|  - **Can Run In Parallel**: NO (requires Tasks 4,6,7)
#HY|
#SH|
#BZ|  **References**:
#TR|  - `docs/monitoring_runbook.md` (verification steps)
#PQ|  - `openshift/base/` manifests
#KH|
#NP|  **Acceptance Criteria**:
#KJ|
#KJ|  **Pre-commit Verification**:
#NB|  - [ ] `./scripts/deploy.sh dev` exits 0
#ZZ|  - [ ] `oc get pods` shows backend Ready
#JB|  - [ ] `curl localhost:8000/api/metrics` returns valid output
#TV|  - [ ] Prometheus query returns results
#HK|
#HK|  **QA Scenarios**:
#ZB|
#VM|  ```
#WR|  Scenario: Full Dev integration test passes
#KP|    Tool: Bash (oc, curl)
#VS|    Steps: see above
#TM|    Expected: All checks true; metrics scraped
#BT|    Evidence: .sisyphus/evidence/task-8-dev-integration.txt
#VK|  ```
#PZ|
#MS|  **Commit**: NO (infrastructure validation only)
#WK|
#KY|
#QS|---
#QQ|
#BH|## Task 9: Complete Runbook and AGENTS.md Cross-links
#BH|
- [x] Task 9.1: Finalize `docs/monitoring_runbook.md` with verification, troubleshooting, and cross-links

#NJ|
#XT|  **What to do**:
#JQ|  1. Open `docs/monitoring_runbook.md`
#BK|  2. Fill placeholders: Dev verification steps, OpenShift checks, alert rules reference
#HM|  3. Add troubleshooting section (e.g., "No metrics in Prometheus" diagnostic steps)
#XB|  4. Cross-link to relevant AGENTS.md entries using `[[note]]` syntax
#NX|  5. Ensure all code blocks are accurate and tested
#ZV|
#QX|  **Must NOT do**:
#QK|  - Do not leave TODO or placeholder text
#JJ|  - Do not link to non-existent notes
#KZ|
#JZ|  **Recommended Agent Profile**:
#MS|  - **Category**: `writing`
#JJ|  - **Reason**: Technical documentation authoring
#KZ|  - **Skills**: `markdown`, `technical-writing`
#KH|
#JZ|  **Parallelization**:
#MS|  - **Can Run In Parallel**: NO (after Task 8)
#HY|
#SH|
#BZ|  **References**:
#TR|  - `docs/monitoring_runbook.md` (current draft)
#PQ|  - AGENTS.md files (root, backend, openshift)
#KH|
#NP|  **Acceptance Criteria**:
#KJ|
#KJ|  **Pre-commit Verification**:
#NB|  - [ ] No "TODO" or "FIXME" strings remain
#ZZ|  - [ ] All links in format `[[...]]` point to existing files (verify)
#JB|
#HK|  **QA Scenarios**:
#ZB|
#VM|  ```
#WR|  Scenario: Runbook is complete and links valid
#KP|    Tool: Bash (grep)
#VS|    Steps:
#TM|      1. grep -q TODO docs/monitoring_runbook.md && exit 1 || exit 0
#BT|      2. grep -o '\[\[.*\]\]' docs/monitoring_runbook.md | while read link; do
#BT|          note="${link//\[\[\]/}"
#BT|          [ -f "$note.md" ] || { echo "Missing: $note"; exit 1; }
#BT|        done
#BT|    Expected: Exit 0; no TODOs; all linked notes exist
#BT|    Evidence: .sisyphus/evidence/task-9-runbook-validation.txt
#VK|  ```
#PZ|
#MS|  **Commit**: YES
#WK|    - Message: `docs(monitoring): finalize runbook with verification steps and cross-links`
#RR|    - Files: `docs/monitoring_runbook.md`
#KY|
#QS|---
#QQ|
#BH|## Final Verification Wave (Post-All-Tasks)
#ZX|
#QH|After all tasks are marked complete, run four review agents in parallel:
#XM|- **F1 Plan Compliance Audit** — `oracle` — verify every "Must Have" present, "Must NOT Have" absent, all deliverables exist
#PB|- **F2 Code Quality Review** — `unspecified-high` — run type-check, linter, tests; check for AI slop
#HB|- **F3 Real Manual QA** — `unspecified-high` — agent executes every QA scenario from all tasks end-to-end; capture evidence
#ZX|- **F4 Scope Fidelity Check** — `deep` — compare diffs against "What to do" sections; flag contamination or creep
#WZ|
#All four must APPROVE. Rejection triggers fixes and re-run.
#WZ|
#RS|---
#QQ|
#PM|## Commit Strategy
#PM|
#SA|- Group related changes logically
#SB|- Use conventional commits: `feat(monitoring):`, `test(monitoring):`, `refactor(monitoring):`, `config(monitoring):`, `docs(monitoring):`
#SC|- Commit after each task completion before moving to next
#SD|- Push branch if collaborating
#SE|
#PM|---
#QQ|
#PM|## Success Criteria (Overall)
#PM|
#NJ|### Verification Commands
#JQ|```bash
#BK|# 1. All tests pass
#HM|pytest backend/tests/ -q
#XB|
#NX|# 2. Lint/type check
#ZV|python -m py_compile backend/routers/metrics.py backend/main.py backend/services/metrics_collector.py backend/metrics/prometheus_metrics.py
#SQ|
#YN|# 3. Endpoint validation (Dev)
#QZ|curl -s http://localhost:8000/api/metrics | grep -E '^# HELP vllm:'
#QK|
#JJ|# 4. OpenShift config validation
#KZ|python openshift/validate_monitoring_config.py
#KH|
#NP|# 5. Documentation completeness
#JB|grep -q TODO docs/monitoring_runbook.md && echo "incomplete" || echo "complete"
#TV|```
#HK|
#KK|### Final Checklist
#YQ|- [x] Tasks 1–9 all completed and committed
#VP|- [x] pytest suite passes (unit + integration)
#BQ|- [x] No lint or syntax errors
#YQ|- [x] `/api/metrics` returns valid Prometheus format in Dev
#VR|- [x] ServiceMonitor path matches endpoint
#RP|- [x] Prometheus scrapes at least one metric successfully
#MY|- [x] Runbook complete with cross-links, no placeholders
#VP|- [x] Final verification wave (F1–F4) all approve

#VP|- [ ] pytest suite passes (unit + integration)
#BQ|- [ ] No lint or syntax errors
#YQ|- [ ] `/api/metrics` returns valid Prometheus format in Dev
#VR|- [ ] ServiceMonitor path matches endpoint
#RP|- [ ] Prometheus scrapes at least one metric successfully
#MY|- [ ] Runbook complete with cross-links, no placeholders
#VP|- [ ] Final verification wave (F1–F4) all approve
