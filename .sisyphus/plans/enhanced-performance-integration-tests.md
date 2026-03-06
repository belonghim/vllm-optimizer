# Work Plan: Enhanced Performance Integration Testing

**Plan ID**: perf-test-enhancement-2025-03-06  
**Created**: 2025-03-06  
**Status**: Draft → Ready for Review  
**Priority**: High (Performance & Scalability Enhancement phase)  
**Estimates**: ~4-6 days implementation  
**Review Required**: Yes (Momus verification recommended)

---

## Executive Summary

This plan implements comprehensive performance integration tests that validate actual optimization effectiveness for the vLLM optimizer. Moving beyond basic deployment smoke tests, the plan introduces:

- 6 new integration test scenarios measuring throughput, latency, metrics overhead, AutoTuner effectiveness, readiness waits, and SSE streaming
- Before/after comparison framework with environment-specific baselines
- Separate Tekton pipeline for performance validation (not blocking PR merges)
- Safety guardrails to prevent disruption of shared dev environments
- Standardized reporting: JUnit XML (CI) + detailed JSON metrics

---

## Problem Statement

Current integration tests (`backend/tests/`) primarily use mocks and validate API endpoints in isolation. They do not:
- Measure actual performance improvements from vLLM optimizations
- Compare before/after states quantitatively
- Validate that AutoTuner produces meaningful tuning results
- Assess metrics collection overhead
- Test real load generation against deployed vLLM instances

This gap prevents confident deployment of performance enhancements and makes regression detection manual and ad-hoc.

---

## Objectives & Success Criteria

**Primary Objective**: Establish automated performance regression testing that validates optimization effectiveness.

**Success Criteria** (Measurable):
- [ ] All 6 test scenarios implemented and passing on dev cluster
- [ ] Performance baseline captured for development environment (`baseline.dev.json`)
- [ ] Separate Tekton pipeline created and validated
- [ ] Test suite executes completely in ≤20 minutes (manual run)
- [ ] Fast smoke subset (<2min) integrated into CI (optional)
- [ ] No test disrupts shared vLLM instances (guardrail validation)
- [ ] Detailed performance report auto-generated after each run

---

## Scope

### IN SCOPE

1. **New Test Scenarios** (6 total):
   - `test_deployment_health.py`: Enhanced health checks with vLLM connectivity
   - `test_metrics_collection.py`: Measure metrics collection overhead
   - `test_load_test_throughput.py`: Before/after throughput comparison (15% improvement threshold)
   - `test_auto_tuner_effectiveness.py`: Validate tuning produces ≥15% throughput gain with ≤5% latency regression (3 trials)
   - `test_dynamic_wait.py`: Verify vLLM readiness polling (vs fixed sleep)
   - `test_sse_streaming.py`: Real-time event delivery validation

2. **Test Infrastructure**:
   - New `backend/tests/integration/performance/` directory
   - Shared fixtures for OpenShift access, baseline loading, vLLM reset
   - Performance test orchestrator (script) for running full suite
   - Baseline storage format (JSON) and comparison logic
   - Median-of-3 runs strategy for flakiness mitigation

3. **Metrics Collection**:
   - Extend `/api/metrics/raw` to include `metrics_collection_duration_seconds` field
   - OR: Create new `/api/admin/metrics-collection-time` endpoint for test-only access
   - Capture throughput, latency, GPU utilization from LoadTestEngine results
   - Store pre/post metrics in structured JSON report

4. **CI/CD**:
   - New `openshift/tekton/performance-pipeline.yaml` (separate from main pipeline)
   - Performance pipeline triggered manually via `tkn` or scheduled
   - Pipeline executes: baseline load → optimization → compare → generate report
   - Publish report as Tekton TaskResult and/or S3/GitHub artifact

5. **Baseline Management**:
   - `baseline.dev.json` and `baseline.prod.json` stored in repo (or ConfigMap for dynamic updates)
   - Baselines contain: throughput_rps, avg_latency_ms, p95_latency_ms, tokens_per_sec, gpu_utilization_avg
   - Tolerance bands: throughput ±5%, latency ±5% (to account for environment noise)

6. **Safety & Guardrails**:
   - Pre-test check: Ensure vLLM model is ready (skip if not)
   - Pre-test backup: Save current vLLM ConfigMap to restore after tests
   - Post-test restoration: Revert vLLM config to pre-test state
   - Circuit breaker: Abort if vLLM already overloaded (high latency/p99 > 2s)
   - Configurable load intensity: Start with conservative concurrency (16) not 64+

7. **Documentation**:
   - `docs/performance-testing.md`: Guide for running tests, interpreting reports, updating baselines
   - `scripts/run_performance_tests.sh`: Main entrypoint for manual execution
   - `scripts/collect_baseline.sh`: Capture and store new performance baseline
   - `scripts/compare_performance.py`: Before/after analysis tool

### OUT OF SCOPE

- Performance testing in production (staging/prod shadow environments)
- Advanced statistical analysis beyond median-of-3 runs
- Dynamic baseline adjustment based on model size/hardware
- Load testing against vLLM directly (bypassing backend) - should use backend API
- Performance tuning recommendations (AutoTuner already exists, tests only validate)
- Integration with external performance monitoring systems (Grafana, etc.) - reports sufficient
- Testing with multiple concurrent vLLM models simultaneously

---

## Work Breakdown Structure (WBS)

### Phase 1: Foundation (Day 1-2)

#### Task 1.1: Create Performance Test Directory Structure
- **File**: `backend/tests/integration/performance/__init__.py`
- **File**: `backend/tests/integration/performance/conftest.py`
  - Fixture: `openshift_client` (authenticated oc client)
  - Fixture: `performance_baseline` (load baseline.json based on env var)
  - Fixture: `vllm_namespace_config` (ConfigMap data for vLLM)
  - Fixture: `safe_test_environment` (check vLLM ready, not overloaded)
  - Fixture: `metrics_snapshot` (call /api/metrics/raw and return dict)

#### Task 1.2: Extend Metrics Endpoint for Timing
- **File**: `backend/metrics/prometheus_metrics.py`
  - Add `metrics_collection_duration_seconds` histogram metric
- **File**: `backend/services/metrics_collector.py` (if exists) or `backend/routers/metrics.py`
  - Wrap `collect_all_metrics()` with timing instrumentation
  - Expose duration in `/api/metrics/raw` response as `meta.collection_duration_seconds`
- **Test**: `backend/tests/integration/performance/test_metrics_collection.py`
  - Verify duration field present and reasonable (<5s target)

#### Task 1.3: Create Baseline Storage & Comparison Utility
- **File**: `backend/tests/integration/performance/utils/baseline.py`
  - `load_baseline(env: str) -> dict`
  - `save_baseline(env: str, metrics: dict)`
  - `compare_metrics(baseline: dict, current: dict) -> dict` (compute % changes)
- **File**: `baseline.dev.json` (initial placeholder with sample structure)
- **File**: `baseline.prod.json` (if different scale, or symlink to dev)

### Phase 2: Core Test Implementation (Day 3-5)

#### Task 2.1: Deployment Health Enhanced Test
- **File**: `backend/tests/integration/performance/test_deployment_health.py`
- **Test**: `test_backend_health_deep()`
  - GET `/health` → 200 OK
  - Response includes Prometheus and K8s connectivity status
  - Time response < 2s
- **Test**: `test_frontend_route_accessible()`
  - GET frontend route (`/`) → 200 OK, contains HTML
- **Test**: `test_vllm_connectivity()`
  - If `/api/vllm/status` exists, GET → 200 OK, status "ready"

#### Task 2.2: LoadTestEngine Throughput Validation (Most Critical)
- **File**: `backend/tests/integration/performance/test_load_test_throughput.py`
- **Test**: `test_throughput_improvement_after_optimization()`
  - **Setup**:
    - Backup current vLLM ConfigMap to restore later
    - Load known suboptimal baseline config (or use current if suboptimal)
    - Run load test via POST `/api/load_test/start` with fixed config (concurrency=16, duration=180s)
    - Wait for completion (poll `/api/load_test/status` or stream SSE)
  - **Capture Baseline Metrics**:
    - GET `/api/metrics/raw` after load test completes
    - Extract: `throughput_rps`, `avg_latency_ms`, `p95_latency_ms`, `tokens_per_sec`, `backend_cpu_avg`, `gpu_utilization_avg`
  - **Apply Optimization**:
    - Wait for user to manually apply optimization OR read optimized ConfigMap from `optimized-config.yaml`
    - Trigger backend rollout: `oc rollout restart deployment/vllm-optimizer-backend`
    - Wait for rollout complete and readiness
  - **Run Post-Optimization Load Test**:
    - Same load test config exactly
    - Capture same metrics
  - **Assertion** (comparison):
    - `post_throughput >= pre_throughput * 1.15` (15% improvement)
    - `post_p95_latency <= pre_p95_latency * 1.05` (≤5% regression)
    - `post_backend_cpu_avg <= pre_backend_cpu_avg * 1.10` (CPU not increase >10%)
    - `post_gpu_utilization_avg >= pre_gpu_utilization_avg * 0.95` (GPU utilization stable or better)
  - **Cleanup**: Restore backed-up vLLM ConfigMap, restart backend
  - **Report**: Write JSON report with pre/post metrics and pass/fail status

#### Task 2.3: AutoTuner Effectiveness Validation
- **File**: `backend/tests/integration/performance/test_auto_tuner_effectiveness.py`
- **Test**: `test_auto_tuner_produces_meaningful_improvement()`
  - **Setup**:
    - Backup current vLLM ConfigMap
    - Apply suboptimal baseline config (if not already)
    - Ensure vLLM ready
  - **Start Tuning**:
    - POST `/api/tuner/start` with config:
      ```json
      {
        "n_trials": 3,
        "eval_requests": 20,
        "objective": "throughput",
        "constraints": {"max_latency_p95_ms": 2000}
      }
      ```
    - Poll `/api/tuner/status` until "completed"
    - Wait for vLLM restart after best params applied (check InferenceService ready)
  - **Capture Post-Tuning Load Test**:
    - Run 60s load test (shorter for speed) with same config as baseline
    - Capture metrics
  - **Assertion**:
    - Same throughput/latency criteria as Task 2.2
  - **Cleanup**: Restore original vLLM ConfigMap, restart backend
  - **Note**: If tuning fails or no improvement, test FAILS (must demonstrate effectiveness)

#### Task 2.4: Dynamic Wait / Readiness Validation
- **File**: `backend/tests/integration/performance/test_dynamic_wait.py`
- **Test**: `test_autotuner_waits_for_vllm_ready_before_trials()`
  - **Setup**:
    - Patch vLLM InferenceService to add initContainer delay (via K8s client)
    - Apply patch, wait for rollout start
    - Record start time
  - **Trigger Tuning**:
    - Start AutoTuner with 2 trials
    - Monitor logs: `oc logs -f deployment/vllm-optimizer-backend --since=...`
    - Or add new endpoint `/api/tuner/wait-metrics` that returns:
      ```json
      {"total_wait_seconds": 45, "poll_count": 9, "first_ready_at_elapsed": 42}
      ```
    - Poll this endpoint after tuning completes
  - **Assertion**:
    - `wait_seconds >= 30` (vLLM was delayed)
    - `wait_seconds < 90` (didn't wait excessively longer than needed)
    - Logs show "Waiting for vLLM ready..." messages, not immediate trial start
  - **Cleanup**: Remove initContainer delay, restore vLLM config

#### Task 2.5: SSE Streaming Validation
- **File**: `backend/tests/integration/performance/test_sse_streaming.py`
- **Test**: `test_load_test_events_streaming()`
  - Connect to `/api/load_test/events` using `httpx` or `sseclient`
  - Start a load test via API (short duration: 30s)
  - Collect SSE events for 40s
  - **Assertion**:
    - At least 3 events received within 25s of connection
    - Event types present: "test_started", "progress" (multiple), "test_completed"
    - Each event has valid JSON data with timestamp
  - **Test**: `test_sse_connection_stable_during_load()`
    - Keep SSE connection open for full 180s load test
    - Verify no connection drops, reconnects not needed
    - Events arrive at regular intervals (not bursty)

#### Task 2.6: Metrics Collection Performance
- **File**: `backend/tests/integration/performance/test_metrics_collection.py`
- **Test**: `test_metrics_collection_time_reasonable()`
  - Call `/api/metrics/raw` repeatedly (5 times)
  - Measure response time for each call
  - Assert: median response time < 5 seconds (measure only, no hard fail if exceeded; log warning)
  - Additionally compare to baseline if available: current / baseline < 1.20 (no >20% regression)
  - **Test**: `test_parallel_collection_improvement()`
    - If metrics collector supports parallel mode via config flag:
      - Toggle config, measure collection time
      - Assert parallel mode is ≥40% faster OR enables larger scale
    - Otherwise: SKIP with message "Parallel metrics collection not implemented"

### Phase 3: Orchestration & CI/CD (Day 6)

#### Task 3.1: Create Performance Test Runner Script
- **File**: `scripts/run_performance_tests.sh`
  - Accept arguments: `--env dev|prod`, `--baseline baseline.dev.json`, `--skip-restore`, `--only <test-name>`
  - Logic:
    1. Set env vars: `TEST_ENV`, `BASELINE_FILE`, `NAMESPACE=vllm-optimizer-dev`
    2. Create timestamped results directory: `reports/2025-03-06T12-34-56/`
    3. Run each test sequentially (or parallel if independent):
       - `pytest backend/tests/integration/performance/test_deployment_health.py -v`
       - `pytest .../test_metrics_collection.py -v`
       - ...
    4. Capture stdout, JUnit XML, JSON results
    5. Consolidate results into `reports/YYYY-MM-DDTHH-MM-SS/summary.json`
    6. Exit with non-zero if any test fails
  - Generate human-readable `SUMMARY.md` with pass/fail, metrics tables
- **File**: `scripts/collect_baseline.sh`
  - Run full load test with current known-good config
  - Extract metrics from `/api/metrics/raw` after load
  - Save to specified baseline file (`baseline.dev.json`)
  - Backup previous baseline to `baseline.dev.json.bak`
- **File**: `scripts/compare_performance.py`
  - CLI tool: `python compare_performance.py --before baseline.dev.json --after results/current/metrics.json`
  - Output: table of % changes, pass/fail per threshold

#### Task 3.2: Create Separate Tekton Performance Pipeline
- **File**: `openshift/tekton/performance-pipeline.yaml`
  - Pipeline: `vllm-optimizer-performance-pipeline`
  - Tasks:
    1. `check-prerequisites` (ensure dev cluster accessible, model ready)
    2. `backup-current-config` (save ConfigMap to temporary file)
    3. `run-performance-tests` (script task running `./scripts/run_performance_tests.sh`)
    4. `restore-config` (restore backed-up ConfigMap)
    5. `publish-report` (upload results as PipelineRun results, optionally to S3)
  - Workspace: `performance-results` (persistent volume for reports)
  - Parameters: `ENVIRONMENT`, `BASELINE_FILE`, `SKIP_RESTORE`
- **PipelineRun** template for manual trigger
- **Trigger**: Not auto-enabled; manual `tkn pipeline start` or schedule

#### Task 3.3: Add Smoke Tests to Main CI (Optional but Recommended)
- **File**: `openshift/tekton/pipeline.yaml` (modify existing)
- Add new task `fast-performance-smoke` after `verify-deployment`
- Runs only 2 quick tests: deployment health + SSE streaming smoke
- Duration < 2 minutes
- Fails pipeline if smoke fails
- Controlled by parameter `RUN_PERF_SMOKE` (default false for PRs)

### Phase 4: Safety & Guardrails (Concurrent with Phases 2-3)

#### Task 4.1: Safe Test Environment Fixtures
- **File**: `backend/tests/integration/performance/conftest.py` (add)
- Fixture: `safe_to_run()`
  - Check cluster load: GET `/api/metrics/raw` → if `vllm:request_pending_count` > 50, SKIP test with reason "high load"
  - Check test namespace pod count: if >10 pods (other tests running), SKIP
- Fixture: `backup_restore_vllm_config()`
  - `yield` before test runs
  - `finally` after test: restore ConfigMap from backup, restart backend
- Fixture: `vllm_readiness_check()`
  - Poll `/api/vllm/status` (if exists) or INFERENCE SERVICE READY condition
  - Timeout 30s, skip if not ready

#### Task 4.2: Post-Test Cleanup Enforcement
- All test functions must use `backup_restore_vllm_config` fixture (autouse=True)
- Ensure no leftover load test running: `requests.post("/api/load_test/stop")` in finalizer
- Verify no AutoTuner running: POST `/api/tuner/stop` if status "running"

### Phase 5: Documentation & Runbooks (Day 6-7)

#### Task 5.1: Performance Testing Guide
- **File**: `docs/performance-testing.md`
  - Purpose and scope of performance tests
  - Prerequisites: oc CLI logged in, vLLM model ready, dev cluster accessible
  - Running tests: `./scripts/run_performance_tests.sh --env dev`
  - Understanding reports: `reports/latest/SUMMARY.md`
  - Updating baselines: `./scripts/collect_baseline.sh --env dev`
  - Troubleshooting:
    - Test fails due to high cluster noise: rerun with `--runs 3` (median already handled)
    - vLLM not ready: check model download status, wait or skip
    - AutoTuner fails to improve: verify baseline is truly suboptimal, or vLLM already optimized
  - CI/CD integration: How to trigger performance pipeline

#### Task 5.2: Baseline Management Policy
- Define when to update baseline:
  - After verified performance improvement (code change + manual validation)
  - Must include PR with code change + performance evidence
  - Baseline files require review from architecture team
- Version baseline files with timestamp: `baseline.dev.2025-03-06.json`
- Keep 3 most recent baselines, archive old ones to `baselines/archive/`

---

## Detailed Task Descriptions

### Task 2.2 Detail: LoadTestEngine Throughput Validation

**Dependencies**: Task 1.2 (metrics timing), Task 1.3 (baseline utils), Task 4.1 (safety fixtures)

**Implementation Steps**:
1. Create test file with pytest markers: `@pytest.mark.integration`, `@pytest.mark.slow`
2. Use `backup_restore_vllm_config` autouse fixture
3. Use `performance_baseline` fixture to load `baseline.dev.json`
4. In test function:
   - Ensure vLLM ready (`vllm_readiness_check` fixture)
   - Start load test: `client.post("/api/load_test/start", json={concurrency: 16, duration_sec: 180, ...})`
   - Poll status every 10s, timeout after 200s
   - On completion: `result = client.get("/api/load_test/results/latest").json()`
   - Extract metrics: `throughput_rps`, `avg_latency_ms`, `p95_latency_ms`, `backend_cpu_avg` (need to add these fields to LoadTestEngine results! - **GAP IDENTIFIED**)
   - Store as `pre_metrics`
5. **Apply optimization**:
   - User must manually apply optimization before running this test? Or read from fixed `optimized-config.yaml` in repo?
   - **Decision**: Read optimized config from `test/fixtures/optimized-config.yaml` (committed to repo)
   - Compare `pre_metrics` vs `optimized_config` expected improvement? No, test must verify actual improvement after rollout.
   - Wait for rollout: `oc rollout status deployment/vllm-optimizer-backend`
6. Run post-optimization load test (same parameters)
7. Extract `post_metrics`
8. Assert thresholds:
   ```python
   assert post_metrics['throughput_rps'] >= pre_metrics['throughput_rps'] * 1.15
   assert post_metrics['p95_latency_ms'] <= pre_metrics['p95_latency_ms'] * 1.05
   assert post_metrics['backend_cpu_avg'] <= pre_metrics['backend_cpu_avg'] * 1.10
   ```
9. Write `reports/throughput-test-{timestamp}.json` with full metrics
10. Cleanup automatically via fixture

**Critical Gap Identified**: LoadTestEngine must expose backend CPU usage and GPU utilization in its results. Currently does not (from code inspection). Need to add these fields to `LoadTestResult` model and populate from metrics collector during test.

**Required code changes outside tests**:
- `backend/services/load_engine.py`: Track backend CPU (query Prometheus during test?) or estimate from request handling time
- `backend/models/load_test.py`: Add fields `backend_cpu_avg`, `gpu_utilization_avg`, `tokens_per_sec`
- `backend/routers/load_test.py`: Include these fields in `/api/load_test/results` response

**Alternative**: Instead of LoadTestEngine providing CPU/GPU, test could query `/api/metrics/raw` before/after load test and compute averages. But that captures overall system, not load-test-specific. Need clarification: The load test should measure resource usage **during** the load period.

**Recommendation**: Modify LoadTestEngine to sample metrics every 30s during load test and average. This is part of test infrastructure, not core optimization, so in scope.

### Task 2.4 Detail: Dynamic Wait Validation

**Implementation challenge**: How to verify AutoTuner waited for vLLM ready without relying on logs?

**Option A (preferred)**: Enhance AutoTuner to expose wait metrics:
- Add to `/api/tuner/status` response:
  ```json
  {
    "status": "completed",
    "current_trial": 3,
    "best_params": {...},
    "wait_metrics": {
      "total_wait_seconds": 45,
      "poll_count": 9,
      "vllm_ready_after_seconds": 42
    }
  }
  ```
- Test polls this endpoint after tuning completes, asserts `wait_seconds > 30`

**Option B**: Scrape pod logs in test using `oc logs`:
- Start tuning, wait for completion
- `logs = subprocess.check_output(["oc", "logs", "deployment/vllm-optimizer-backend", "--since=..."])`
- Count occurrences of "Waiting for vLLM ready"
- Assert at least 5 logs found

**Decision**: Option A cleaner, more testable. Requires code change to AutoTuner. Should be included in scope as minor enhancement.

**Required code changes**:
- `backend/services/auto_tuner.py`: Track `_wait_start_time`, `_wait_durations` list, expose via property
- `backend/routers/tuner.py`: Include wait_metrics in status response JSON

---

## Quality Gates

**Before plan approval, ensure**:
1. All test scenarios have explicit pass/fail assertions with thresholds
2. Baseline comparison method verified (median, tolerance bands)
3. Required code modifications to LoadTestEngine and AutoTuner identified and scoped
4. Safety guardrails (backup/restore, skip conditions) implemented
5. Tekton performance pipeline structure validated with cluster admin (permissions, resource quotas)
6. Baseline files created and reviewed for being realistic (not too aggressive)

---

## Risk Register

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| LoadTestEngine lacks backend CPU/GPU metrics → test cannot evaluate efficiency | High | High | **Mitigation**: Add metrics tracking to LoadTestEngine as part of this work (Task 2.2 detail) |
| vLLM model download takes >10min, breaking test timing | Medium | Medium | Assume pre-downloaded (user confirmation); test skips if model not ready |
| Shared dev cluster too noisy → tests flaky despite median-of-3 | High | Medium | Increase runs to 5? Or require baseline comparison with wider tolerance; document as known limitation |
| AutoTuner fails to improve suboptimal baseline (already near optimal) | Medium | Medium | Use deliberately suboptimal baseline config committed to repo; ensure it's clearly worse (e.g., max_num_seqs=8) |
| Tests interfere with other developers' work on shared vLLM | High | High | Guardrails: skip if vLLM already overloaded; restore config; run in isolated namespace |
| Performance pipeline prohibits cluster resources (quota) | Medium | High | Resource requests for performance test pod; run during off-hours; schedule only |
| Baseline drift: environment changes (hardware upgrade) invalidate baseline | Medium | Medium | Version baseline files with dates; keep archive; require manual review before applying new baseline |
| Developer forgets to run performance tests before merge | High | Medium | Integrate fast smoke into main CI (Task 3.3) as reminder |

---

## Dependencies

**External Dependencies**:
- OpenShift cluster with `vllm-optimizer-dev` namespace accessible
- vLLM model pre-downloaded to `vllm` namespace (ModelCache or PersistentVolume)
- oc CLI available in test runner pod
- ServiceAccount with permission to read pods, configmaps, inferenceservices in both `vllm-optimizer-dev` and `vllm` namespaces
- Baseline file committed to repo or stored in ConfigMap

**Internal Dependencies**:
- LoadTestEngine must expose `backend_cpu_avg`, `gpu_utilization_avg`, `tokens_per_sec` (enhancement required)
- AutoTuner must expose wait metrics in `/api/tuner/status` (enhancement required)
- MetricsCollector timing instrumentation (Task 1.2)
- `/api/metrics/raw` endpoint must include collection duration (Task 1.2)

---

## Estimates

| Phase | Tasks | Estimate (person-days) |
|-------|-------|----------------------|
| Phase 1: Foundation | 3 tasks | 2 |
| Phase 2: Core Tests | 6 tasks | 2 |
| Phase 3: Orchestration | 3 tasks | 1 |
| Phase 4: Guardrails | 2 tasks | 0.5 |
| Phase 5: Documentation | 2 tasks | 0.5 |
| **Buffer & Review** | - | 1 |
| **Total** | - | **~6 days** |

Note: Includes minor code enhancements to LoadTestEngine and AutoTuner.

---

## Post-Plan Actions (After Approval)

1. **Register todos** for each task in this plan (detailed subtasks within tasks)
2. **Create parent task** linking all subtasks
3. **Start first task**: Implement foundation (Task 1.1-1.3)
4. **After implementation**: Run Momus high-accuracy review before marking complete
5. **Handoff**: Guide user to run `/start-work` to begin execution

---

## Decisions Requiring User Confirmation

Although interview was comprehensive, a few minor decisions remain that could slightly alter scope:

1. **LoadTestEngine metrics tracking**: Should it sample Prometheus during load test or estimate from request timing? 
   - **Default**: Sample `/api/metrics/raw` every 30s via async client within LoadTestEngine
   - **Alternative**: Compute from request processing time (less accurate)

2. **Baseline storage location**: Should baseline JSON files be committed to repo or stored in ConfigMap for easier updates?
   - **Default**: Committed to repo as `baseline.{env}.json` (versioned, auditable)
   - **Alternative**: ConfigMap `performance-baselines` that scripts update

3. **Fast smoke test selection**: Which 2 tests for CI?
   - **Default**: Deployment health + SSE streaming (fastest, no load)
   - **Alternative**: Include metrics collection smoke (also fast)

4. **Optimization application method**: How does test know which config is "optimized"?
   - **Default**: Read from committed `test/fixtures/optimized-config.yaml` file
   - **Alternative**: Manual step where user applies config before running test, test detects change via metrics improvement

**These will be auto-resolved with defaults unless user objects before plan generation.**

---

## Final Verification Checklist

- [x] Core objective clearly defined
- [x] Scope boundaries established (IN/OUT)
- [x] No critical ambiguities remaining (from user interview)
- [x] Technical approach decided (pytest + scripts + separate pipeline)
- [x] Test strategy confirmed (6 scenarios, median-of-3, baseline compare)
- [x] All acceptance criteria specified with pass/fail thresholds
- [x] Safety guardrails identified (backup/restore, skip conditions)
- [x] Dependencies mapped (internal code changes required)
- [x] Risks registered with mitigations
- [x] Estimates provided

**Plan is decision-complete. Ready for Metis review and user finalization.**

---

## Next Steps

1. Present this plan to user with summary of key decisions
2. Ask about high accuracy mode (Momus review)
3. Incorporate any final feedback
4. Register todos and begin execution
