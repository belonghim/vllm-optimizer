# vLLM Metrics Collector 버그 수정 계획

## TL;DR

> **문제 1**: Backend가 Thanos에서 vLLM 메트릭을 조회할 수 없음 (메트릭 이름 형식 불일치)
> - Thanos 실제 형식: `vllm:` (콜론)
> - Backend 검색 형식: `vllm_` (밑줄)
>
> **문제 2**: Backend ServiceMonitor가 Backend 메트릭을 스크래핑할 수 없음 (경로 불일치)
> - ServiceMonitor 경로: `/metrics`
> - 실제 Backend 경로: `/api/metrics`

> **문제 3**: Thanos URL이 클러스터 외부에서 접근 불가 (기본값이 내부용)
> - 현재 기본값: `https://thanos-querier.openshift-monitoring.svc.cluster.local:9091` (내부 only)
> - 올바른 외부용: `https://thanos-querier-openshift-monitoring.apps.compact.jooan.local`

> **수정**: 위 3개 파일에서 경로/이름/URL 修正

---

## Context

### 문제 1: VLLM 메트릭 이름 불일치
- Thanos Prometheus의 vLLM 메트릭 형식: `vllm:num_requests_running` (콜론)
- Backend 코드 검색 형식: `vllm_num_requests_running` (밑줄)
- 결과: 메트릭 조회 실패 → 항상 0값 반환 → Auto-tuner 작동 불가

### 문제 2: Backend ServiceMonitor 경로 불일치
- ServiceMonitor가 스크래핑하는 경로: `/metrics` (openshift/base/03-backend.yaml)
- Backend가 메트릭을 제공하는 경로: `/api/metrics` (backend/main.py)
- 결과: Prometheus가 Backend 메트릭을 수집하지 못함

### 문제 3: Thanos URL 클러스터 외부 접근 불가
- **Backend 코드**: 클러스터 내부에서 실행되므로 내부용 URL 유지 (수정 불필요)
  - 기본값: `https://thanos-querier.openshift-monitoring.svc.cluster.local:9091`
- **테스트/검증 시**: 클러스터 외부에서 curl 호출하므로 외부용 URL + socks5 프록시 필요

---

## Work Objectives

### Core Objective
1. Thanos Prometheus에서 vLLM 메트릭을 정상 조회할 수 있도록 `metrics_collector.py`의 쿼리 형식 수정
2. Backend ServiceMonitor가 Backend 메트릭을 정상 스크래핑할 수 있도록 경로 수정

### Deliverables
- `backend/services/metrics_collector.py` 수정 (VLLM_QUERIES 딕셔너리 + Thanos URL)
- `openshift/base/03-backend.yaml` 수정 (prometheus.io/path)

### Definition of Done
- [ ] VLLM_QUERIES 딕셔너리의 모든 키를 콜론 형식으로 변경
- [ ] Backend ServiceMonitor 경로를 /api/metrics로 변경
- [ ] 테스트 시 socks5 프록시로 Thanos 쿼리 가능한지 확인
- [ ] 수정 후 `/api/metrics/latest`가 실제 메트릭 반환 확인
- [ ] Auto-tuner가 ConfigMap 패치 가능한지 확인

---

## Execution

### Tasks

- [x] 1. `backend/services/metrics_collector.py` 파일의 `VLLM_QUERIES` 딕셔너리 (lines ~47-59) 수정

  **현재 (잘못)**:
  ```python
  VLLM_QUERIES = {
      "tokens_per_second": 'rate(vllm_generation_tokens_total[1m])',
      "requests_per_second": 'rate(vllm_request_success_total[1m])',
      "mean_ttft_ms": 'histogram_quantile(0.5, rate(vllm_time_to_first_token_seconds_bucket[1m])) * 1000',
      "p99_ttft_ms": 'histogram_quantile(0.99, rate(vllm_time_to_first_token_seconds_bucket[1m])) * 1000',
      "mean_e2e_latency_ms": 'histogram_quantile(0.5, rate(vllm_e2e_request_latency_seconds_bucket[1m])) * 1000',
      "p99_e2e_latency_ms": 'histogram_quantile(0.99, rate(vllm_e2e_request_latency_seconds_bucket[1m])) * 1000',
      "kv_cache_usage_pct": 'vllm_gpu_cache_usage_perc * 100',
      "kv_cache_hit_rate": 'vllm_cache_config_info',
      "running_requests": 'vllm_num_requests_running',
      "waiting_requests": 'vllm_num_requests_waiting',
      "gpu_memory_used_gb": 'vllm_gpu_cache_usage_perc * vllm_gpu_memory_total_bytes / 1024^3',
  }
  ```

  **수정 (올림 - 콜론 형식)**:
  ```python
  VLLM_QUERIES = {
      "tokens_per_second": 'rate(vllm:generation_tokens_total[1m])',
      "requests_per_second": 'rate(vllm:request_success_total[1m])',
      "mean_ttft_ms": 'histogram_quantile(0.5, rate(vllm:time_to_first_token_seconds_bucket[1m])) * 1000',
      "p99_ttft_ms": 'histogram_quantile(0.99, rate(vllm:time_to_first_token_seconds_bucket[1m])) * 1000',
      "mean_e2e_latency_ms": 'histogram_quantile(0.5, rate(vllm:e2e_request_latency_seconds_bucket[1m])) * 1000',
      "p99_e2e_latency_ms": 'histogram_quantile(0.99, rate(vllm:e2e_request_latency_seconds_bucket[1m])) * 1000',
      "kv_cache_usage_pct": 'vllm:gpu_cache_usage_perc * 100',
      "kv_cache_hit_rate": 'vllm:cache_config_info',
      "running_requests": 'vllm:num_requests_running',
      "waiting_requests": 'vllm:num_requests_waiting',
      "gpu_memory_used_gb": 'vllm:gpu_cache_usage_perc * vllm:gpu_memory_total_bytes / 1024^3',
      "gpu_utilization_pct": 'vllm:gpu_utilization',
  }
  ```

  **References**:
  - Thanos 실제 메트릭: `vllm:num_requests_running`, `vllm:num_requests_waiting`, `vllm:gpu_cache_usage_perc`, `vllm:gpu_utilization`

- [x] 2. `openshift/base/03-backend.yaml` 파일의 ServiceMonitor 경로 수정

  **현재 (잘못)**:
  ```yaml
  annotations:
    prometheus.io/scrape: "true"
    prometheus.io/port: "8000"
    prometheus.io/path: "/metrics"    # ← 잘못됨
  ```

  **수정 (올림)**:
  ```yaml
  annotations:
    prometheus.io/scrape: "true"
    prometheus.io/port: "8000"
    prometheus.io/path: "/api/metrics"  # ← 올림
  ```

  **References**:
  - Backend main.py line 245: `@app.get("/api/metrics", ...)`

- [ ] (Backend 코드 불필요) — 클러스터 내부에서 실행되므로 내부용 URL 유지

- [ ] 3. 테스트/검증 시에만 외부용 URL + socks5 프록시 사용

  **테스트 명령어 (내가 bash로 실행할 때만)**:
  ```bash
  # socks5 프록시로 Thanos 쿼리
  curl --socks5-hostname 127.0.0.1:8882 -k -s \
    -H "Authorization: Bearer $(oc create token vllm-optimizer-backend -n vllm-optimizer-dev)" \
    "https://thanos-querier-openshift-monitoring.apps.compact.jooan.local/api/v1/query?query=vllm:num_requests_running"
  ```

  ** 참고 **:
  - Backend 코드 (`metrics_collector.py`)의 PROMETHEUS_URL 기본값은 **변경하지 않음** — 클러스터 내부에서 실행되므로
  - 환경변수 `PROMETHEUS_URL`을 통해 필요시 외부용 URL로_override 가능

- [x] 3. Backend 재빌드 및 배포
  - 이미지 빌드 및 푸시
  - `vllm-optimizer-backend` 디플로이먼트 롤아웃

- [x] 4. 메트릭 조회 테스트
   ```bash
   oc port-forward svc/vllm-optimizer-backend 8000:8000 -n vllm-optimizer-dev &
   curl -s http://localhost:8000/api/metrics/latest | jq .
   ```
   - `running`, `waiting`, `gpu_util` 등이 0이 아닌 값 반환 확인 (노트: 부하가 없으면 0 반환은 정상, Auto-tuner 테스트 시 non-zero 확인 가능)

- [ ] 5. Auto-tuner 엔드투엔드 테스트
  ```bash
  curl -X POST http://localhost:8000/api/tuner/start \
    -H "Content-Type: application/json" \
    -d '{"n_trials":1, "objective":"tps", "max_num_seqs_range":[64,128]}'
  ```
  - ConfigMap 패치 확인
  ```bash
  oc get cm vllm-config -n vllm -o jsonpath='{.data.MAX_NUM_SEQS}'
  ```

---

## Verification

### Success Criteria Commands
```bash
# 1. 메트릭 조회
curl -s http://localhost:8000/api/metrics/latest | jq '.running, .waiting, .gpu_util'

# 2. Prometheus에서 Backend 메트릭 확인 (ServiceMonitor가 작동하는지)
TOKEN=$(oc create token vllm-optimizer-backend -n vllm-optimizer-dev)
curl -k -H "Authorization: Bearer $TOKEN" \
  "https://thanos-querier.openshift-monitoring.svc.cluster.local:9091/api/v1/query?query=up{app='vllm-optimizer-backend'}"

# 3. Auto-tuner
curl -X POST http://localhost:8000/api/tuner/start -d '{"n_trials":1}' && \
oc get cm vllm-config -n vllm -o jsonpath='{.data.MAX_NUM_SEQS}'
```

### Final Checklist
- [ ] VLLM_QUERIES 콜론 형식으로 변경됨
- [ ] Backend ServiceMonitor 경로 /api/metrics로 변경됨
- [ ] Backend 재빌드/재배포 완료
- [ ] 메트릭 조회 시 0 아닌 실제 값 반환
- [ ] Prometheus/Thanos에서 Backend 메트릭 확인 가능
- [ ] Auto-tuner가 ConfigMap 패치 성공
