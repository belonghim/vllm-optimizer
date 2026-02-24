# vLLM Optimizer — OpenShift 배포 가이드

vLLM 서비스의 부하 테스트, 실시간 모니터링, 벤치마크 비교, 자동 파라미터 튜닝을 제공하는  
**컨테이너 애플리케이션** — OpenShift 4.x 완전 호환 설계.

---

## 아키텍처

```
┌─────────────────────────────────────────────────────────────────┐
│                    OpenShift Cluster                            │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  Namespace: vllm-optimizer                              │   │
│  │                                                         │   │
│  │  ┌──────────┐   Route(TLS)   ┌──────────┐              │   │
│  │  │ Frontend │◄──────────────►│  Router  │◄── 사용자    │   │
│  │  │  nginx   │                │ (HAProxy)│              │   │
│  │  │  :8080   │                └──────────┘              │   │
│  │  └────┬─────┘                                          │   │
│  │       │ /api/* (ClusterIP)                             │   │
│  │  ┌────▼─────┐    ┌─────────────────────────────────┐  │   │
│  │  │ Backend  │    │ openshift-monitoring             │  │   │
│  │  │ FastAPI  ├───►│ Thanos Querier :9091             │  │   │
│  │  │  :8000   │    │ (Prometheus 메트릭)              │  │   │
│  │  └────┬─────┘    └─────────────────────────────────┘  │   │
│  │       │                                                │   │
│  └───────┼────────────────────────────────────────────────┘   │
│          │                                                     │
│  ┌───────▼──────────────────────────────────────────────────┐  │
│  │  Namespace: vllm                                         │  │
│  │  vLLM Pods (GPU) + ConfigMap (Auto Tuner 파라미터 주입)  │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                 │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │  OpenShift Pipelines (Tekton)                              │ │
│  │  Git Clone → Test → Buildah → Quay.io → Kustomize Deploy  │ │
│  └────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

---

## OpenShift 주요 설계 결정

| 항목 | 일반 K8s | OpenShift 대응 |
|------|----------|----------------|
| 컨테이너 이미지 | 임의 베이스 | **UBI9** (Red Hat Universal Base Image) |
| 포트 | 80, 443 가능 | **8080, 8000** (non-root 포트) |
| 사용자 | root 가능 | **non-root + arbitrary UID** (SCC) |
| Ingress | Ingress 객체 | **OpenShift Route** (Edge TLS) |
| CI/CD | 자유 선택 | **Tekton Pipeline** (Buildah 빌드) |
| 모니터링 | 직접 설치 | **OpenShift Monitoring Stack** (Thanos) |
| 네트워크 정책 | 선택 | **NetworkPolicy** (최소 권한) |

---

## 빠른 시작

### 1. 사전 요구사항

```bash
# oc CLI 설치 확인
oc version

# OpenShift 로그인
oc login https://api.your-cluster.example.com:6443 \
  --username=your-user --password=your-pass
# 또는 토큰으로:
oc login --token=<token> --server=https://api.your-cluster.example.com:6443
```

### 2. 환경변수 설정

```bash
export REGISTRY="quay.io/your-org"
export IMAGE_TAG="1.0.0"
export CLUSTER_DOMAIN="apps.your-cluster.example.com"
export VLLM_NAMESPACE="vllm"
```

### 3. 배포 (Dev)

```bash
# 전체 자동 배포 (빌드 + 푸시 + 배포)
./scripts/deploy.sh dev

# 드라이런 (변경사항 미리 확인)
./scripts/deploy.sh dev --dry-run

# 빌드 건너뛰고 배포만 (이미지 이미 있는 경우)
./scripts/deploy.sh dev --skip-build
```

### 4. 배포 (Prod)

```bash
IMAGE_TAG="1.0.0" ./scripts/deploy.sh prod
```

---

## 프로젝트 구조

```
vllm-optimizer/
├── backend/
│   ├── Dockerfile              # UBI9 Python, non-root, arbitrary UID
│   ├── main.py                 # FastAPI 앱
│   ├── requirements.txt
│   ├── routers/
│   │   ├── load_test.py        # 부하 테스트 API + SSE 스트림
│   │   ├── metrics.py          # Thanos Querier 연동 메트릭
│   │   ├── benchmark.py        # 벤치마크 저장/비교
│   │   └── tuner.py            # Bayesian Optimization 튜너
│   ├── services/
│   │   ├── load_engine.py      # 비동기 부하 생성 엔진
│   │   ├── metrics_collector.py # Prometheus + K8s API 수집
│   │   └── auto_tuner.py       # Optuna + K8s ConfigMap 업데이트
│   └── models/
│       └── load_test.py        # Pydantic 모델
│
├── frontend/
│   ├── Dockerfile              # UBI9 nginx, 8080 포트, non-root
│   ├── nginx.conf              # SPA 라우팅, /api/* 프록시
│   ├── src/App.jsx             # React 대시보드 (4개 탭)
│   └── package.json
│
└── openshift/
    ├── base/
    │   ├── 01-namespace-rbac.yaml   # NS + SA + ClusterRole + SCC
    │   ├── 02-config.yaml           # ConfigMap + Secret
    │   ├── 03-backend.yaml          # Deployment + Service + HPA
    │   ├── 04-frontend.yaml         # Deployment + Service + Route
    │   ├── 05-monitoring.yaml       # ServiceMonitor + PrometheusRule + PDB + NetworkPolicy
    │   └── kustomization.yaml
    ├── overlays/
    │   ├── dev/kustomization.yaml   # Dev: 리소스 축소, 1 레플리카
    │   └── prod/kustomization.yaml  # Prod: 3 레플리카, 리소스 확대
    └── tekton/
        └── pipeline.yaml           # CI/CD Pipeline + EventListener
```

---

## OpenShift 배포 후 확인

```bash
NS=vllm-optimizer

# Pod 상태
oc get pods -n $NS

# Route URL 확인
oc get route vllm-optimizer -n $NS

# 로그 확인
oc logs -l app=vllm-optimizer-backend -n $NS -f

# SCC 확인
oc describe pod -l app=vllm-optimizer-backend -n $NS | grep -i scc

# 이벤트 확인 (문제 진단)
oc get events -n $NS --sort-by=.lastTimestamp | tail -20

# Prometheus 메트릭 확인
oc exec -it $(oc get pod -l app=vllm-optimizer-backend -n $NS -o name | head -1) \
  -n $NS -- curl localhost:8000/metrics
```

---

## Tekton Pipeline 설정

```bash
# Pipeline 리소스 배포
oc apply -f openshift/tekton/pipeline.yaml -n vllm-optimizer

# GitHub Webhook Secret 생성
oc create secret generic github-webhook-secret \
  --from-literal=token=$(openssl rand -hex 20) \
  -n vllm-optimizer

# Quay.io Push Secret 생성
oc create secret docker-registry quay-push-secret \
  --docker-server=quay.io \
  --docker-username=your-user \
  --docker-password=your-token \
  -n vllm-optimizer

# Pipeline 수동 실행
oc create -f openshift/tekton/pipeline.yaml  # PipelineRun 생성

# Pipeline 로그 확인
tkn pipelinerun logs -f -n vllm-optimizer
```

---

## 문제 해결

### SCC 관련 오류
```bash
# 현재 SCC 확인
oc get pod <pod-name> -n vllm-optimizer -o yaml | grep scc

# SCC 재적용 (cluster-admin 필요)
oc adm policy add-scc-to-user vllm-optimizer-scc \
  -z vllm-optimizer-backend -n vllm-optimizer
```

### 이미지 Pull 실패
```bash
# Pull Secret 확인
oc get secret quay-pull-secret -n vllm-optimizer -o yaml

oc import-image vllm-optimizer-backend:latest \
  --from=quay.io/your-org/vllm-optimizer-backend:latest \
  --confirm -n vllm-optimizer
```

### Prometheus 접근 불가 (Thanos Querier)
```bash
# ServiceAccount 토큰으로 Thanos 쿼리 테스트
TOKEN=$(oc serviceaccounts get-token vllm-optimizer-backend -n vllm-optimizer)
curl -H "Authorization: Bearer $TOKEN" \
  https://thanos-querier.openshift-monitoring.svc.cluster.local:9091/api/v1/query \
  --data-urlencode 'query=vllm:num_requests_running' -k
```
