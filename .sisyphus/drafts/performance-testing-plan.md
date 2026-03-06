# Enhanced Integration Testing for Performance Validation
## Work Plan Preparation Draft

**Status**: Draft - Awaiting User Clarification  
**Created**: 2025-03-06  
**Objective**: Implement comprehensive integration tests that validate actual performance optimizations (throughput gains, latency improvements, tuning effectiveness) beyond basic deployment smoke tests.

---

## 📊 Current State Assessment

### Existing Test Infrastructure

**Test Framework**: Pytest with FastAPI TestClient
- Location: `backend/tests/`
- Configuration: `conftest.py` with minimal fixtures
- Coverage: Unit/integration tests with extensive mocking for Kubernetes interactions

**Test Files Currently Present**:
- `test_integration_metrics_e2e.py` - Basic Prometheus format check
- `test_load_test.py` - API endpoint unit tests (start/status/history)
- `test_tuner.py` - AutoTuner logic with mocked K8s and load engine
- `test_benchmark.py` - Benchmark API tests
- `test_metrics.py` - Metrics endpoint tests
- `test_prometheus_metrics.py` - Metric generation tests
- `test_service_monitor_config.py` - OpenShift ServiceMonitor validation
- `test_dev_integration.py` - Dev environment endpoint checks

**CI/CD Pipeline** (`openshift/tekton/pipeline.yaml`):
```
1. git-clone
2. test-backend (pytest) ← Tests run BEFORE build
3. build-backend (Buildah) [parallel with build-frontend]
4. build-frontend (Buildah)
5. deploy (kustomize apply)
6. verify-deployment (rollout status + /health curl)
```

**Post-Deployment Verification**:
- `deploy.sh`: Performs `oc rollout status` checks, SCC assignments
- Tekton `verify-deployment` task: Checks rollout status + `/health` endpoint
- No performance regression testing after deployment

**Key Services Available for Testing**:
- **LoadTestEngine** (`backend/services/load_engine.py`): Concurrent load generation, RPS control, SSE streaming of real-time results
- **AutoTuner** (`backend/services/auto_tuner.py`): Optuna-based parameter optimization with K8s ConfigMap updates and InferenceService restarts
- **MetricsCollector** (inferred): Gathers metrics from Prometheus + K8s API
- **Metrics API** (`backend/routers/metrics.py`): `/api/metrics` (Prometheus format), `/api/metrics/raw` (latest snapshot), `/api/metrics/history`

**Critical Gap Identified**: 
- Current tests use mocks extensively and don't validate actual performance improvements
- No integration tests run load tests against deployed system to measure throughput/latency
- No before/after comparison framework for optimization validation
- No tests that verify AutoTuner's actual tuning effectiveness on real vLLM
- No performance benchmarking integrated into CI/CD

---

## 🎯 Proposed Enhanced Integration Test Structure

Based on user requirements, proposed test scenarios:

### 1. Deployment & Health Baseline (Enhanced)
- Standard rollout status checks (existing)
- **ADD**: Backend `/health` deep check with configurable timeout
- **ADD**: Frontend `/` route accessible
- **ADD**: vLLM connectivity check (if `/api/vllm/status` exists)

### 2. Metrics Collection Performance Validation
**Goal**: Verify that metrics collection overhead meets target (< 5% impact on LLM performance)
- Baseline measurement: Time `MetricsCollector.collect_all_metrics()` with 11 Prometheus queries
- Target: Parallelization reduces collection time by 40-70% (e.g., 8s → <3s)
- Metrics: Collection duration, number of queries, concurrent vs sequential timing

### 3. LoadTestEngine Throughput & Efficiency Test
**Most Critical**: Validate that optimization actually improves throughput/latency
```
Fixed Parameters:
- Model: meta-llama/Meta-Llama-3-8B-Instruct (or smaller for speed)
- Concurrency: 32 (adjustable)
- Duration: 180 seconds
- RPS: 0 (unlimited, let engine drive based on concurrency)
- Prompt template: simple-chat (minimal token generation)

Procedure:
1) Run baseline load test, capture metrics
2) Apply optimization (e.g., vLLM batching, semaphore tuning)
3) Restart backend or apply config changes
4) Run identical load test, capture metrics
5) Compare:
   - Throughput (requests/s, tokens/s): Target ≥ 1.15× baseline
   - Backend CPU usage: Same or lower while throughput increases
   - p95/p99 latency: Not degraded (>1.05× acceptable for throughput gains)
   - Memory usage: Stable or reduced
```

### 4. AutoTuner Effectiveness Validation
**Most Challenging**: Prove tuning produces meaningful improvements
```
Procedure:
1) Start with conservative vLLM config (low max_num_seqs, high safety margins)
2) Run short tuning session (3-5 trials) with objective="throughput"
3) Capture best trial's metrics vs baseline
4) Apply best config and re-run load test
5) Validate improvement thresholds:
   - Throughput ≥ 1.12× baseline
   - p95 latency ≤ 1.05× baseline (no significant regression)
   - GPU utilization improved or stable
```

### 5. Dynamic Wait / Readiness Probe Validation
**Goal**: Ensure AutoTuner doesn't start trials before vLLM ready
- Deploy vLLM with slow start (initContainer sleep 60s)
- Trigger AutoTuner
- Verify logs show polling loop (not fixed 30s sleep) until InferenceService ready
- Confirm tuning trials only start after vLLM ready
- Time tracking: total wait time, number of polls

### 6. SSE Real-time Streaming Validation
**Smoke Test**: Verify SSE events deliver during load tests
- Connect to `/api/load_test/events` endpoint
- Verify at least 3-5 events received within 25 seconds
- Event types: progress updates, intermediate metrics, completion
- Connection stability: no premature disconnects

---

## 🤔 Clarifying Questions for User

Before finalizing plan, need answers on:

### A. Test Execution Context
1. **Where should these enhanced integration tests run?**
   - Option 1: As part of CI/CD (Tekton) AFTER deployment (separate pipeline stage)
   - Option 2: As standalone script/tool run manually by SRE/DevOps after deployment
   - Option 3: Both: Fast smoke in CI, comprehensive benchmark run on-demand
   - *Recommended*: Option 3 - keep CI fast (<5min), comprehensive tests run manually with `./scripts/run_performance_tests.sh`

2. **What environment should be used for performance tests?**
   - Dev cluster (small vLLM instance, quick but less accurate)
   - Dedicated performance cluster (larger, consistent hardware)
   - Staging environment that mirrors production
   - *Constraint*: Need sustained load generation for 3-5 minutes per test → requires isolated environment

3. **What constitutes acceptable performance thresholds?**
   - Throughput improvement: 10%? 15%? 20%?
   - Latency regression tolerance: 5%? 10%?
   - Metrics collection time: <3s? <5s?
   - *Need concrete numbers to make tests deterministic*

### B. Test Infrastructure Requirements
4. **How to handle vLLM dependency for load tests?**
   - Assume vLLM already deployed in namespace `vllm` (existing setup)
   - Tests should verify vLLM is ready before running load tests
   - Model availability: Should tests pre-download model, or assume it's present?
   - If model missing, should tests skip with warning or fail?

5. **Test execution permissions in OpenShift:**
   - Need ServiceAccount with permission to:
     - Read pods from `vllm-optimizer-dev` namespace
     - Read custom resources (InferenceService) from `vllm` namespace
     - Execute into backend pod to run metrics collection commands?
   - Should we create dedicated `performance-test` ServiceAccount?

6. **How to handle test flakiness from shared cluster resources?**
   - Performance tests on shared clusters can vary due to noise
   - Options:
     - Run each test 3 times, take median
     - Require minimum difference (statistical significance)
     - Provide mode to "compare against stored baseline" rather than absolute thresholds
   - *Recommended*: Allow both absolute thresholds and baseline comparison with tolerance bands

### C. Integration with AutoTuner
7. **AutoTuner test duration vs practicality:**
   - Full tuning with 10+ trials could take 30+ minutes
   - Proposed: 3-5 trials for tests (5-10 minutes)
   - Is this sufficient to demonstrate tuning effectiveness?
   - Should we pre-seed Optuna with known good parameters to speed convergence?

8. **How to reset vLLM configuration between test runs?**
   - AutoTuner can apply best params, but how to revert to baseline?
   - Need mechanism to store/restore ConfigMap `vllm-config` before test suite
   - Should tests be responsible for cleanup, or should test harness handle?

### D. Reporting & Artifacts
9. **What test output format is needed?**
   - Simple pass/fail (JUnit XML for CI)
   - Detailed performance report (JSON with all metrics, before/after comparisons)
   - Human-readable summary (markdown/HTML)
   - Grafana dashboard link with metrics visualization?

10. **Where to store baseline metrics for comparison?**
    - Local file in repo (baseline.json) that gets updated when performance improves
    - External storage (S3, ConfigMap) with environment-specific baselines
    - Use Tekton TaskResults to pass baseline between pipeline runs?
    - *Recommendation*: Baseline stored in `baseline.dev.json`, `baseline.prod.json` with PR requirement to update baseline when performance improves

---

## 🏗️ Implementation Structure (Anticipated)

```
backend/tests/integration/performance/
├── __init__.py
├── conftest.py                      # Fixtures for performance tests
├── test_deployment_health.py        # Enhanced health checks
├── test_metrics_collection.py       # Metrics collection timing
├── test_load_test_engine.py         # Throughput/latency comparisons
├── test_auto_tuner_effectiveness.py # Before/after tuning validation
├── test_dynamic_wait.py             # Readiness polling logic
├── test_sse_streaming.py           # Real-time event delivery
└── fixtures/
    ├── baseline_metrics.json       # Known-good performance baselines
    └── vllm_test_config.yaml       # Test-specific vLLM configuration

scripts/
├── run_performance_tests.sh         # Orchestrate full test suite
├── collect_baseline.sh              # Capture and store new baseline
└── compare_performance.py           # Before/after analysis tool

openshift/
├── performance-test/
│   ├── serviceaccount.yaml         # SA with metrics/validation permissions
│   ├── role.yaml
│   └── rolebinding.yaml
└── tekton/
    └── performance-task.yaml       # Optional: Tekton task for perf tests
```

---

## ⚠️ Risk Assessment & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| **Flaky tests due to cluster noise** | Medium | Run each test 3x, take median; require statistical significance; allow baseline comparison with tolerance bands |
| **Tests interfere with production vLLM** | High | Tests run in isolated dev namespace; use dedicated vLLM instance; implement circuit breaker to abort if vLLM already overloaded |
| **Test duration too long for CI** | Medium | Split into fast smoke (2min) and full benchmark (15min); run full suite on-demand; use smaller models for CI |
| **Baseline drift unmanaged** | Medium | Baseline files versioned; require PR to update baseline with performance improvement evidence |
| **AutoTuner tests non-deterministic** | High | Use Optuna with fixed seed; limit to 3-5 trials; mock vLLM restart time; skip if vLLM not ready within timeout |

---

## 📋 Decision-Completeness Check

Items requiring user decisions before plan finalization:

- [ ] Test execution context (CI vs manual, environment)
- [ ] Concrete performance thresholds (throughput %, latency tolerance, metrics time)
- [ ] vLLM dependency handling (model availability, readiness checks)
- [ ] Test flakiness mitigation strategy
- [ ] AutoTuner duration and convergence expectations
- [ ] Baseline storage and update policy
- [ ] Reporting format requirements

**Next Step**: Get user answers → Finalize scope → Generate decision-complete work plan with Metis review → Present plan with "Start Work" vs "High Accuracy Review" choice

---

## 🔍 Initial Thoughts Based on Exploration

1. **Leverage existing infrastructure**: The current LoadTestEngine and AutoTuner are perfect - they already expose APIs we can call from integration tests. We don't need to build new load generation tools.

2. **Test execution approach**: Should we create a `PerformanceTestOrchestrator` service that coordinates before/after measurements? Or keep tests as pure client-side scripts that call APIs? 
   - **Recommendation**: Keep tests as pure client-side (no server-side test runner) to maintain separation of concerns. Tests live in `backend/tests/integration/performance/` and use `httpx` or `TestClient` to drive APIs.

3. **Metrics collection**: The `MetricsCollector` is internal service method, not API. Options:
   - Call `/api/metrics/raw` endpoint repeatedly to measure collection "from the outside"
   - Add new `/api/admin/metrics-collection-time` endpoint for testing (instrument collection duration)
   - Execute Python code inside backend pod via `oc rsh` (messy, not decoupled)
   - **Recommendation**: Add optional timing instrumentation to existing metrics endpoint to expose collection duration for testing.

4. **CI/CD integration**: The Tekton pipeline currently runs tests before build. Performance tests should run AFTER deployment to a test environment. We need either:
   - New `performance-test` Tekton task that runs after `verify-deployment`
   - Separate PipelineRun for performance validation triggered manually
   - External CI job (GitHub Actions) that targets OpenShift dev cluster

5. **Baseline management**: Storing baseline in repo as JSON is simplest, but:
   - Different environments (dev/staging/prod) have different capacities → need environment-specific baselines
   - Model size affects performance → baseline per model?
   - **Recommendation**: Baselines stored as `baseline.{env}.{model}.json`; tests load appropriate baseline based on environment vars.

6. **AutoTuner validation challenge**: Proving tuning effectiveness requires controlled experiments:
   - Need to reset vLLM config to known suboptimal state before each tuning run
   - ConfigMap backup/restore mechanism
   - May need to skip AutoTuner test if vLLM not in suboptimal state (detect via metrics)
   - **Simplification**: Mock the tuning effectiveness test with predetermined param sets if real tuning takes too long

7. **Readiness/wait validation**: The `AutoTuner._wait_for_ready()` already implements polling. Should we add a test endpoint to expose wait duration for verification? Or test via log scraping?
   - **Option A**: Add `/api/tuner/wait-stats` endpoint that returns recent wait metrics
   - **Option B**: Parse pod logs in test to find "Waiting for vLLM ready" entries
   - **Recommendation**: Option A - cleaner for integration tests

---

**Draft Status**: Ready for user interview phase. All preliminary exploration done. Need user preferences to finalize scope and approach.
