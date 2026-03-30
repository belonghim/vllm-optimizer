---
title: "vLLM Optimizer 통합 테스트 가이드"
date: 2026-03-08
updated: 2026-03-15
tags: [integration-test, performance, vllm, korean]
status: published
---

# vLLM Optimizer 통합 테스트 가이드

이 문서는 vLLM Optimizer 프로젝트의 통합 테스트 실행 및 관리에 대한 가이드입니다. 통합 테스트는 실제 OpenShift 클러스터 환경에서 vLLM Optimizer의 기능과 성능을 검증하는 데 중점을 둡니다.

## 1. 단위 테스트 (Unit Tests)

단위 테스트는 로컬 환경에서 실행되며, 각 컴포넌트의 개별 기능을 검증합니다. 통합 테스트와 달리 클러스터 환경이 필요하지 않습니다.

```bash
cd backend && python3 -m pytest tests/ -x -q -m "not integration"
```

## 2. 성능 통합 테스트 (Performance Integration Tests)

성능 통합 테스트는 OpenShift 클러스터에 배포된 vLLM Optimizer와 vLLM 서비스 간의 상호작용을 검증합니다. `backend/tests/integration/performance/` 디렉토리에 위치하며, 다음 시나리오를 포함합니다:

- `test_cluster_health.py`: 클러스터 상태 및 기본 연결 확인
- `test_load_test_throughput.py`: 부하 테스트 기능의 처리량 검증
- `test_metrics_collection.py`: 메트릭 수집 기능 검증
- `test_auto_tuner.py`: 자동 튜너 기능 검증
- `test_sse_streaming.py`: SSE 스트리밍 기능 검증
- `test_pod_restart.py`: **자동 튜닝 시 vLLM 파드 재기동 E2E 검증** — 튜닝 실행 전/후 파드 UID 비교로 실제 재기동 확인. `/api/vllm-config` PATCH API 기능도 검증.

## 3. 환경변수

성능 통합 테스트 실행 시 필요한 환경변수는 다음과 같습니다. 이 변수들은 테스트 대상 vLLM 서비스 및 Optimizer의 위치를 지정합니다.

| 변수 | 설명 | 기본값 |
|:-----|:-----|:--------|
| `PERF_TEST_BACKEND_URL` | Backend URL | `http://vllm-optimizer-backend.vllm-optimizer-dev.svc.cluster.local:8000` |
| `VLLM_ENDPOINT` | vLLM completions endpoint | `http://llm-ov-predictor.vllm-lab-dev.svc.cluster.local:8080` |
| `VLLM_MODEL` | vLLM 모델명 | `Qwen2.5-Coder-3B-Instruct-int4-ov` |
| `VLLM_NAMESPACE` | vLLM 네임스페이스 | `vllm-lab-dev` |
| `OPTIMIZER_NAMESPACE` | Optimizer 네임스페이스 | `vllm-optimizer-dev` |
| `PERF_BASELINE_FILE` | Baseline JSON 경로 | `baseline.dev.json` |
| `VLLM_POD_LABEL` | vLLM 파드 식별 레이블 (`test_pod_restart.py`) | `app=isvc.llm-ov-predictor` |
| `POD_RESTART_TIMEOUT` | 파드 재기동 대기 최대 시간(초) (`test_pod_restart.py`) | `300` |

## 4. Baseline 관리

`scripts/collect_baseline.sh` 스크립트를 사용하여 성능 테스트의 기준값(baseline)을 수집하고 관리할 수 있습니다. 이 기준값은 `baseline.dev.json` 파일에 저장되며, 향후 테스트 결과와 비교하는 데 사용됩니다.

```bash
./scripts/collect_baseline.sh
```

## 5. 클러스터에서 직접 실행 (Pod exec)

OpenShift 클러스터 내에서 vLLM Optimizer 백엔드 Pod에 직접 접속하여 통합 테스트를 실행할 수 있습니다. 이는 CI/CD 파이프라인 외부에서 디버깅하거나 특정 테스트를 수동으로 실행할 때 유용합니다.

```bash
NS=vllm-optimizer-dev
BACKEND_POD=$(oc get pod -n $NS -l app=vllm-optimizer-backend -o name | head -1)
oc exec -n $NS $BACKEND_POD -- env \
  PERF_TEST_BACKEND_URL=http://localhost:8000 \
  VLLM_ENDPOINT=http://llm-ov-predictor.vllm-lab-dev.svc.cluster.local:8080 \
  VLLM_MODEL=Qwen2.5-Coder-3B-Instruct-int4-ov \
  VLLM_NAMESPACE=vllm-lab-dev \
  OPTIMIZER_NAMESPACE=vllm-optimizer-dev \
  python3 -m pytest /app/tests/integration/performance/ -v --tb=short -m "integration"
```

## 6. pytest 마커 설명

`pyproject.toml` 파일에 정의된 pytest 마커를 사용하여 특정 테스트 그룹을 선택적으로 실행할 수 있습니다.

- `integration`: 통합 테스트를 나타냅니다.
- `performance`: 성능 관련 테스트를 나타냅니다.
- `slow`: 실행 시간이 오래 걸리는 테스트를 나타냅니다.

예시:
```bash
# 모든 통합 테스트 실행
pytest -m "integration"

# 성능 테스트만 실행
pytest -m "performance"

# 느린 테스트를 제외한 모든 테스트 실행
pytest -m "not slow"
```

## 7. 문제 해결

통합 테스트 실행 중 문제가 발생하면 다음 사항을 확인하십시오.

- **환경변수**: 모든 필수 환경변수가 올바르게 설정되었는지 확인하십시오. 특히 `VLLM_ENDPOINT`와 `VLLM_NAMESPACE`가 중요합니다.
- **Pod 상태**: vLLM Optimizer 백엔드 Pod 및 vLLM 서비스 Pod가 모두 정상적으로 실행 중인지 확인하십시오.
  ```bash
  oc get pods -n vllm-optimizer-dev
  oc get pods -n vllm
  ```
- **로그 확인**: 백엔드 Pod의 로그를 확인하여 오류 메시지를 분석하십시오.
  ```bash
  oc logs -l app=vllm-optimizer-backend -n vllm-optimizer-dev -f
  ```
- **네트워크 연결**: vLLM Optimizer 백엔드 Pod에서 vLLM 서비스 엔드포인트로의 네트워크 연결이 가능한지 확인하십시오.
  ```bash
  oc exec -it <backend-pod-name> -n vllm-optimizer-dev -- curl -v http://llm-ov-predictor.vllm-lab-dev.svc.cluster.local:8080/v1/models
  ```