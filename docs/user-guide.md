---
title: "vLLM Optimizer 대시보드 사용자 가이드"
date: 2026-03-08
updated: 2026-03-15
tags: [user-guide, dashboard, vllm, korean]
status: published
---

# vLLM Optimizer 대시보드 사용자 가이드

## 1. 개요

vLLM Optimizer 대시보드는 vLLM 서비스의 실시간 성능 모니터링, 부하 테스트, 벤치마크 비교, 자동 파라미터 튜닝을 제공하는 웹 애플리케이션입니다. 이 가이드는 대시보드의 각 기능과 사용 방법을 설명합니다.

대시보드는 OpenShift Route URL을 통해 접근할 수 있습니다. OpenShift 클러스터에서 다음 명령어를 사용하여 URL을 확인하십시오:
```bash
oc get route vllm-optimizer -n vllm-optimizer-dev
```

대시보드는 다음 4개의 주요 탭으로 구성되어 있습니다:
- **실시간 모니터링**: vLLM 서비스의 현재 성능 지표를 실시간으로 확인합니다.
- **부하 테스트**: vLLM 서비스에 부하를 주어 성능을 측정하고 분석합니다.
- **벤치마크 비교**: 저장된 부하 테스트 결과를 비교하여 성능 변화를 분석합니다.
- **자동 파라미터 튜닝**: Bayesian Optimization을 사용하여 vLLM 서비스의 최적 파라미터를 자동으로 탐색합니다.

## 2. Mock 모드

대시보드 헤더의 우측 상단에는 `MOCK` 토글 스위치가 있습니다.

- **기본값: ON** — 대시보드에 처음 접속하면 Mock 데이터(가상 데이터)가 표시됩니다. 이는 실제 vLLM 서비스가 없거나 연결되지 않은 상태에서도 대시보드 기능을 미리 살펴볼 수 있도록 돕습니다.
- 실제 클러스터 데이터를 보려면 `MOCK` 토글을 클릭하여 비활성화하십시오.
- `MOCK` 설정은 브라우저의 localStorage에 저장되므로, 페이지를 새로고침하거나 다시 접속해도 설정이 유지됩니다.
- 헤더에 표시되는 초록색 점과 "CONNECTED" 문구는 대시보드의 디자인 요소이며, 실제 백엔드 연결 상태를 반영하지 않습니다.

## 3. 실시간 모니터링 탭

이 탭은 vLLM 서비스의 핵심 성능 지표를 실시간으로 모니터링합니다. 데이터는 2초마다 자동으로 갱신됩니다.

### 메트릭 카드 (상단 2행)

| 카드 | 설명 | 단위 |
|:-----|:-----|:-----|
| Tokens / sec | vLLM 서비스가 초당 처리하는 토큰 수 (처리량) | TPS |
| TTFT Mean | 첫 번째 토큰이 생성되기까지 걸리는 평균 시간 | ms |
| P99 Latency | 전체 요청의 99번째 백분위수 응답 시간 (가장 느린 1%를 제외한 응답 시간) | ms |
| KV Cache | KV 캐시 사용률 | % |
| Running Reqs | 현재 vLLM 서비스에서 처리 중인 요청 수 | requests |
| Waiting Reqs | vLLM 서비스의 큐에서 대기 중인 요청 수 | queue |
| GPU Memory | GPU 메모리 사용량 / 전체 GPU 메모리 (CPU 환경에서는 0으로 표시됩니다) | GB |
| Pods Ready | 정상 동작 중인 Kubernetes Pod 수 / 전체 vLLM Pod 수 | k8s pods |

### 차트 (4개)

- **Throughput (TPS)**: 시간에 따른 초당 토큰 처리량(TPS)의 변화를 보여줍니다.
- **Latency (ms)**: TTFT Mean과 P99 Latency의 시간에 따른 추이를 시각화합니다.
- **KV Cache Usage (%)**: KV 캐시 사용률의 시간에 따른 변화를 보여줍니다.
- **Request Queue**: Running Reqs(처리 중인 요청)와 Waiting Reqs(대기 중인 요청)의 시간에 따른 변화를 보여줍니다.

### KPI 해석 가이드

- **KV Cache > 90%**: KV 캐시 사용률이 90%를 초과하면 vLLM 서비스의 처리 용량이 포화 상태에 도달했음을 의미합니다. 이 경우, 요청 수를 줄이거나 vLLM Pod를 스케일아웃(확장)해야 합니다.
- **Waiting Reqs 지속 증가**: 대기 중인 요청 수가 지속적으로 증가한다면, 동시 요청 수가 vLLM 서비스의 처리 한계를 초과했음을 나타냅니다.
- **TTFT 급등**: 첫 번째 토큰까지의 시간이 급격히 증가하는 것은 모델 로딩 지연이나 GPU/CPU 메모리 부족의 신호일 수 있습니다.
- **Pods Ready < Pods**: 정상 동작 중인 Pod 수가 전체 Pod 수보다 적다면, vLLM Pod가 재시작 중이거나 문제가 발생했을 수 있습니다. OpenShift 이벤트 로그를 확인하여 원인을 파악하십시오 (`oc get events -n vllm-optimizer-dev`).

## 4. 부하 테스트 탭

이 탭에서는 vLLM 서비스에 대한 부하 테스트를 실행하고 그 결과를 분석합니다.

### 설정 항목

| 필드 | 설명 | 기본값 |
|:-----|:-----|:--------|
| vLLM Endpoint | 부하 테스트를 수행할 vLLM 추론 엔드포인트 URL입니다. 이 값은 자동으로 채워집니다. | — |
| Model Name | 테스트에 사용할 모델의 이름입니다. 대시보드 로드 시 vLLM 서비스에서 실제 모델명을 자동으로 감지하여 설정됩니다. | (자동 감지) |
| Total Requests | vLLM 서비스로 전송할 총 요청 수입니다. | 200 |
| Concurrency | 동시에 처리할 요청 수입니다. | 20 |
| RPS | 초당 전송할 요청 수입니다. `0`으로 설정하면 제한 없이 요청을 전송합니다. | 10 |
| Max Tokens | vLLM 응답의 최대 토큰 수입니다. | 256 |
| Streaming Mode | 체크 시 스트리밍 모드로 부하 테스트를 수행하며, TTFT(Time To First Token) 측정이 활성화됩니다. | ON |
| 프롬프트 템플릿 | vLLM에 전송할 프롬프트 텍스트입니다. 여러 줄 입력 가능합니다. | Hello, how are you? |
| Temperature | 생성 다양성을 제어합니다. 0에 가까울수록 결정적, 높을수록 무작위적입니다. (0~2 범위) | 0.7 |

### 실행

1. 필요한 설정 값을 입력합니다. `vLLM Endpoint`는 대부분 자동으로 채워집니다.
2. **▶ Run Load Test** 버튼을 클릭하여 부하 테스트를 시작합니다.
3. 진행률 표시줄과 실시간 차트를 통해 테스트 진행 상황을 실시간으로 확인할 수 있습니다.
4. 테스트가 완료되면 결과가 화면에 표시됩니다.
5. 테스트 도중 **■ Stop** 버튼을 클릭하여 언제든지 중도 중단할 수 있습니다.

### 결과 확인

**MetricCard (4개):**
- **Mean TPS**: 테스트 기간 동안의 평균 처리량 (초당 토큰 수)
- **TTFT Mean**: 첫 번째 토큰까지의 평균 시간
- **P99 Latency**: 99번째 백분위수 응답 시간
- **Success Rate**: 성공적으로 처리된 요청의 비율 (%)

**Latency Distribution 테이블:**
- **Total Requests**: 총 전송된 요청 수
- **Success**: 성공한 요청 수
- **Failed**: 실패한 요청 수
- **Actual RPS**: 실제 초당 요청 수
- **Mean Latency**: 평균 응답 시간 (ms)
- **P50 Latency**: 50번째 백분위수 응답 시간 (중앙값) (ms)
- **P95 Latency**: 95번째 백분위수 응답 시간 (ms)
- **P99 Latency**: 99번째 백분위수 응답 시간 (ms)
- **TTFT Mean**: 첫 번째 토큰까지의 평균 시간 (ms)
- **TTFT P95**: 첫 번째 토큰까지의 95번째 백분위수 시간 (ms)
- **Total TPS**: 총 처리량 (초당 토큰 수)

**실시간 차트:**
- 테스트가 진행되는 동안 레이턴시(ms)와 TPS(초당 토큰 수)의 변화를 실시간으로 확인할 수 있습니다.

> ⚠️ **오류 발생 시**: 부하 테스트 중 문제가 발생하면 화면 상단에 빨간색 경고 메시지가 표시됩니다.

## 5. 벤치마크 비교 탭

이 탭은 이전에 실행하여 저장된 부하 테스트 결과를 비교하는 전용 화면입니다.

### 테이블 열

- **(체크박스)**: 비교하고자 하는 벤치마크를 선택하는 체크박스입니다.
- **Name**: 벤치마크 테스트의 이름입니다.
- **Date**: 벤치마크 결과가 저장된 날짜입니다.
- **TPS**: 해당 벤치마크의 평균 처리량 (초당 토큰 수)입니다.
- **P99 ms**: 해당 벤치마크의 99번째 백분위수 레이턴시 (밀리초)입니다.
- **RPS**: 해당 벤치마크의 실제 초당 요청 수입니다.

### 비교 차트

- 2개 이상의 벤치마크를 체크박스로 선택하면 화면 하단에 비교 차트가 자동으로 나타납니다.
- **TPS 비교**: 선택된 벤치마크들의 TPS를 막대 차트로 비교합니다.
- **P99 Latency 비교 (ms)**: 선택된 벤치마크들의 P99 Latency를 막대 차트로 비교합니다.

> ℹ️ **참고**: 테이블이 비어 있다면, `부하 테스트` 탭에서 부하 테스트를 먼저 실행하여 결과를 생성하십시오. 비교 차트는 **2개 이상의 벤치마크를 선택**했을 때만 표시됩니다.

## 6. 자동 파라미터 튜닝 탭

이 탭은 Bayesian Optimization(Optuna) 기술을 활용하여 vLLM 서비스의 최적 파라미터를 자동으로 탐색합니다. 이를 통해 사용자는 수동으로 파라미터를 조정하는 번거로움 없이 최적의 성능을 찾을 수 있습니다.

### 설정 항목

**기본 설정:**

| 필드 | 설명 | 기본값 |
|:-----|:-----|:-----|
| 최적화 목표 | 튜닝의 목표를 선택합니다. | 균형 (TPS / Latency) |
| Trial 수 | Optuna가 탐색할 파라미터 조합의 총 개수입니다. | 10 |
| max_num_seqs 범위 | vLLM의 `max_num_seqs` 파라미터(동시 처리 시퀀스 수)를 탐색할 최소/최대 범위입니다. | 32 ~ 256 |
| GPU Memory Util 범위 | vLLM의 `gpu_memory_utilization` 파라미터(GPU 메모리 사용률)를 탐색할 최소/최대 범위입니다. | 0.8 ~ 0.95 |

**고급 설정** (▼ 버튼으로 펼치기):

| 필드 | 설명 |
|:-----|:-----|
| max_model_len 범위 | 최대 컨텍스트 길이 탐색 범위 (Min / Max) |
| max_num_batched_tokens 범위 | 배치당 최대 토큰 수 탐색 범위 (Min / Max) |
| block_size 옵션 | KV 캐시 블록 크기 선택 (체크박스: 8 / 16 / 32) |
| swap_space 포함 | CPU 스왑 메모리 사용 여부 및 크기 범위 (GB) |
| 평가 요청 수 / 동시 요청 / RPS | 각 trial의 성능 측정에 사용할 부하 테스트 설정 |

**현재 vLLM 설정**: 고급 설정 섹션 상단에 현재 InferenceService args 값이 읽기 전용으로 표시됩니다.

### 실행

1. `최적화 목표`와 각 파라미터의 `탐색 범위`를 지정합니다. 더 많은 파라미터를 탐색하려면 "고급 설정 ▼"을 펼치십시오.
2. **▶ Start Tuning** 버튼을 클릭하여 자동 튜닝을 시작합니다.
3. `N / M trials` 형식으로 Trial 진행 상황이 표시되며, 각 trial의 현재 단계(args 업데이트 → 파드 재기동 → 메트릭 안정화 → 평가)가 실시간으로 표시됩니다.
4. 튜닝이 진행되면서 최적의 파라미터 조합이 발견되면 **최적 파라미터 발견** 섹션이 화면에 나타납니다.
5. **■ Stop** 버튼을 클릭하여 언제든지 튜닝을 중도 중단할 수 있습니다.

> ℹ️ **참고**: 각 trial은 vLLM 파드를 재기동(`kubectl rollout restart` 동일)하므로 **파드당 수십 초~수 분**이 소요됩니다. 또한 파드 준비 완료 후 메트릭 안정화를 위해 30초의 쿨다운이 추가됩니다. 10 trial 기준 총 소요 시간은 환경에 따라 30분~1시간 이상일 수 있습니다.

### 결과 화면

- **Best TPS / P99 Latency MetricCard**: 현재까지 발견된 최적의 TPS와 P99 Latency를 보여줍니다.
- **최적 파라미터 테이블**: 발견된 최적 파라미터의 이름과 해당 최적 값을 표시합니다.
- **Trial 분포 차트 (Scatter: TPS vs P99 Latency)**: 각 Trial의 TPS와 P99 Latency 결과를 산점도 형태로 시각화하여 전체적인 튜닝 분포를 파악할 수 있습니다.
- **파라미터 중요도 (FAnova)**: 각 파라미터가 vLLM 서비스 성능에 미치는 영향도를 백분율(%)로 표시합니다. 이를 통해 어떤 파라미터가 성능에 가장 큰 영향을 주는지 알 수 있습니다.

### 최적 파라미터 적용

> ⚠️ **주의**: **✓ Apply Best Params** 버튼은 자동 튜닝을 통해 발견된 최적 파라미터를 InferenceService args에 직접 적용하고, vLLM 파드를 재기동합니다. 이 작업은 즉시 vLLM 설정에 반영되며, **되돌리기 기능이 없습니다**. 적용 전에 현재 InferenceService args를 별도로 기록해 두는 것을 강력히 권장합니다.
> ```bash
> oc get inferenceservice llm-ov -n vllm-lab-dev -o jsonpath='{.spec.predictor.model.args}'
> ```

### vllm-config 직접 편집

대시보드의 고급 설정 섹션에서 현재 InferenceService args 값을 확인하고, `/api/vllm-config` API를 통해 직접 수정할 수도 있습니다 (튜닝 없이 값만 변경).
```bash
# InferenceService 현재 값 조회 (API)
curl http://<backend>/api/vllm-config

# 특정 값 수정 (허용 키만 가능)
curl -X PATCH http://<backend>/api/vllm-config \
  -H 'Content-Type: application/json' \
  -d '{"data": {"max_num_seqs": "128"}}'
```
> ℹ️ **참고**: API를 통해 값만 수정하면 vLLM 파드가 자동으로 재기동되지 않습니다. 새 값을 적용하려면 파드를 수동으로 재기동하거나 자동 튜닝을 통해 적용하십시오.

## 7. 자주 묻는 질문 (FAQ)

**Q1. Mock 모드를 끄면 메트릭이 모두 "—"(대시)로 표시됩니다.**
- A: MetricsCollector가 vLLM Pod를 찾지 못했거나 Thanos 연결에 실패한 상태입니다.
  1. `K8S_DEPLOYMENT_NAME` 환경변수가 KServe Deployment 이름(`llm-ov-predictor`)으로 올바르게 설정되었는지 확인하십시오.
  2. 보다 자세한 진단 및 해결 방법은 `docs/troubleshooting.md` 문서를 참조하십시오.

**Q2. 부하 테스트가 시작되지 않습니다.**
- A: `vLLM Endpoint`가 올바르게 설정되었는지 확인하십시오.
  - 내부 클러스터 URL 형식은 `http://llm-ov-predictor.vllm-lab-dev.svc.cluster.local:8080`과 같습니다.
  - 브라우저에서 직접 접근하는 경우, 클러스터 내부 URL은 사용할 수 없습니다. OpenShift Route URL을 사용해야 합니다.

**Q3. 벤치마크 테이블이 비어 있습니다.**
- A: `부하 테스트` 탭에서 부하 테스트를 먼저 실행하십시오. 테스트가 완료되면 그 결과가 자동으로 저장되어 이 탭에 표시됩니다.

**Q4. ✓ Apply Best Params를 클릭했는데 되돌리고 싶습니다.**
- A: InferenceService args를 수동으로 복원해야 합니다. 다음 명령어를 사용하여 이전에 저장해 둔 args를 재적용하십시오:
  ```bash
  oc patch inferenceservice llm-ov -n vllm-lab-dev --type='json' -p='[{"op": "replace", "path": "/spec/predictor/model/args", "value": ["이전", "args", "값"]}]'
  ```

**Q5. 자동 파라미터 튜닝 후 다른 기능이 느려졌습니다.**
- A: 튜닝 과정에서 vLLM 서비스에 실제 추론 요청이 전송되므로, 일시적으로 레이턴시가 높아지거나 서비스가 느려질 수 있습니다. 일반적으로 약 2분 후 정상화됩니다. vLLM Pod의 상태를 확인하려면 다음 명령어를 사용하십시오:
  ```bash
  oc get pods -n vllm
  ```

---

**참고 문서:**
- `docs/deployment.md` — OpenShift 배포 가이드
- `docs/troubleshooting.md` — 상세 트러블슈팅 가이드
- `docs/monitoring_runbook.md` — 모니터링 운영 절차서
- `docs/architecture.md` — 시스템 아키텍처