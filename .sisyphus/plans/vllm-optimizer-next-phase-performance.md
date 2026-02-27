# vLLM Optimizer Next Phase: Performance & Scalability Enhancement

## 1. Executive Summary
This plan focuses on enhancing the performance and scalability of the `vllm-optimizer` by addressing key bottlenecks identified in the core functionality analysis. We will optimize Prometheus metrics collection, improve the efficiency of the load test engine, and refine the auto-tuner's operational pauses.

## 2. Scope Boundaries
- **IN SCOPE**:
  - Parallelizing Prometheus queries in `metrics_collector.py`.
  - Optimizing `LoadTestEngine`'s request processing to reduce context switching.
  - Transitioning real-time frontend communication from polling to Server-Sent Events (SSE) or WebSockets.
  - Refining `AutoTuner`'s fixed 30-second wait into a dynamic, readiness-probe-based delay.
- **OUT OF SCOPE**:
  - Implementing new functional features (e.g., multi-cluster support, advanced analytics).
  - Deep architectural changes to the vLLM integration itself.
  - Comprehensive unit/integration test suite refactoring (will be a separate plan).
  - Advanced monitoring dashboard development (will be a separate plan).

## 3. Technical Approach
- **Prometheus Query Parallelization**: Modify `metrics_collector.py` to use `asyncio.gather()` for concurrent execution of Prometheus queries, reducing overall collection time.
- **LoadTestEngine Optimization**: Investigate and implement batch processing or a more efficient concurrency control mechanism in `load_engine.py` to minimize frequent context switches during high-volume load testing.
- **Real-time Communication (Polling to SSE/WebSocket)**: Analyze existing polling mechanisms in the frontend (`MonitorPage`, `LoadTestPage`) and replace them with a more efficient real-time communication protocol like SSE (Server-Sent Events) or WebSockets for better scalability and lower latency. Given the current SSE implementation for load testing, extending SSE might be simpler.
- **AutoTuner Dynamic Wait**: Change the fixed `asyncio.sleep(30)` in `auto_tuner.py` to a mechanism that periodically checks the vLLM deployment's readiness probes, dynamically waiting until the vLLM service is fully available.

## 4. Execution Tasks

- [x] **Task 1: Parallelize Prometheus Queries**
  - **What**: Modify `backend/services/metrics_collector.py` to execute multiple Prometheus queries concurrently using `asyncio.gather()` instead of sequential execution.
  - **QA**: Ensure all 11 metrics are still collected correctly and the collection time is reduced. Implement a test to verify parallel execution.

- [x] **Task 2: Optimize LoadTestEngine Request Processing**
  - **What**: Refactor `backend/services/load_engine.py` to reduce excessive context switching. This might involve adjusting the semaphore usage or introducing a batching mechanism for sending requests to vLLM.
  - **QA**: Run load tests with high concurrency and verify that the CPU utilization of the optimizer backend is more efficient and overall throughput improves.

- [x] **Task 3: Implement Dynamic Wait for AutoTuner**
  - **What**: Replace the fixed `asyncio.sleep(30)` in `backend/services/auto_tuner.py` with a loop that periodically checks the readiness of the vLLM deployment (via Kubernetes API) before proceeding with the next tuning trial.
  - **QA**: Verify that the auto-tuner correctly waits for vLLM deployment readiness and does not proceed prematurely or excessively delay.

## 5. Final Verification Wave
- Verify that the overall system performance metrics (collected by the optimizer itself) show improvement in areas targeted by these optimizations (e.g., lower metrics collection latency, higher load test throughput).
- Ensure no new regressions or functional issues are introduced.
- Review logs for any errors or warnings related to the changes.