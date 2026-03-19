# Learnings — cpu-integration-tests

## [2026-03-07] 세션 시작 — Phase 1에서 승계된 지식

### 프로젝트 환경
- Backend: FastAPI (Python), port 8000
- Frontend: React + nginx, port 8080
- `oc` CLI: /home/user/bin/oc
- Working worktree: /home/user/project/vllm-optimizer-perf-tests (enhanced-perf-tests-v2 branch)
- Main worktree: /home/user/project/vllm-optimizer (main branch)

### 핵심 임포트 규칙
- NO `backend.` prefix (bare `from services.xxx` 사용)
- 단위 테스트 실행: `python3 -m pytest backend/tests/ -x -q -m "not integration"`

### MetricsCollector 아키텍처 (Phase 1에서 확정)
- 싱글톤: `backend/services/shared.py`
- startup_metrics_shim.py → `start_collection(interval=2.0)`
- routers/metrics.py, routers/tuner.py → shared 싱글톤 사용
- conftest.py → `services.shared` stub

### 클러스터 Facts (2026-03-07 검증)
- vLLM 버전: 0.13.0 (CPU/OpenVINO)
- 모델명: `Qwen2.5-Coder-3B-Instruct-int4-ov`
- vLLM 엔드포인트: `http://llm-ov-predictor.vllm.svc.cluster.local:8080`
- API: `/v1/completions` 지원 (vllm.entrypoints.openai.api_server)
- Thanos: verify=False (self-signed), Bearer token auth
- MetricsCollector 버전 감지: `0.13.x-cpu`

### Rebase 충돌 해결 원칙
- main 우선: metrics_collector.py, tuner.py, startup_metrics_shim.py, conftest.py
- branch 수용: integration/ 디렉토리, load_engine.py 확장, models 확장
- rebase에서 --ours = branch(현재), --theirs = main(upstream)

### asyncio.to_thread 패턴
```python
result = await asyncio.to_thread(
    self._k8s_core.read_namespaced_config_map,
    name=K8S_CONFIGMAP, namespace=K8S_NAMESPACE,
)
```
- Python 3.9+ 내장, K8s client는 thread-safe

## [2026-03-07] Task 1: Rebase 완료
- 충돌 해결한 파일: backend/services/metrics_collector.py (main 버전 유지 · GPU/CPU 감지 + TLS verify=False), backend/routers/tuner.py (shared 싱글톤 중심으로 wait_metrics 필드 및 추가 엔드포인트 병합)
- 각 파일 전략: metrics_collector는 main의 GPU metric 우선 검사 + Prometheus TLS 검증 비활성화, tuner는 shared import 유지하며 wait_metrics/상태 필드 확장; branch-only integration 폴더는 그대로 포함
- 단위 테스트: `python3 -m pytest backend/tests/ -x -q -m "not integration"` → 40 passed, 8 deselected

## [2026-03-07] Task 2+3: auto_tuner asyncio.to_thread 수정
- 4곳 수정 완료: _wait_for_ready (1), _apply_params (3)
- 단위 테스트 결과: 40 passed

## [2026-03-08] Fix test_load_test_throughput.py — redeploy + test run
- Commit: 544d466646fbd483099bf4c30501d355de193e88
- Build + push: success
- Full test results:
  PASSED tests/integration/performance/test_auto_tuner.py::TestAutoTuner::test_auto_tuner_completes_with_results
  PASSED tests/integration/performance/test_cluster_health.py::TestClusterHealth::test_backend_health_deep
  PASSED tests/integration/performance/test_cluster_health.py::TestClusterHealth::test_metrics_endpoint_accessible
  PASSED tests/integration/performance/test_cluster_health.py::TestClusterHealth::test_prometheus_metrics_plaintext
  SKIPPED tests/integration/performance/test_load_test_throughput.py::TestLoadTestThroughput::test_load_test_completes_successfully
  PASSED tests/integration/performance/test_metrics_collection.py::TestMetricsCollection::test_metrics_response_time
  PASSED tests/integration/performance/test_metrics_collection.py::TestMetricsCollection::test_prometheus_scrape_format_valid
  SKIPPED tests/integration/performance/test_sse_streaming.py::TestSSEStreaming::test_load_test_sse_events
