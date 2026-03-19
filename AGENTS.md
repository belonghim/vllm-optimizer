# AGENTS.md — vLLM Optimizer (OpenShift 배포)

이 파일은 AI 코딩 에이전트(opencode.ai)가 본 프로젝트를 이해하고 올바르게 작업하기 위한 지침서입니다.

---

## Global AGENTS.md 상속

~/.config/opencode/AGENTS.md 를 먼저 참조합니다.

---

## 프로젝트 개요

**vLLM Optimizer**는 vLLM 서비스의 부하 테스트, 실시간 모니터링, 벤치마크 비교, 자동 파라미터 튜닝을 제공하는 컨테이너 애플리케이션입니다. OpenShift 4.x에 완전 호환되도록 설계되었습니다.

- **Backend**: FastAPI (Python), 포트 `8000`
- **Frontend**: React + nginx, 포트 `8080`
- **배포 플랫폼**: OpenShift 4.x (Kubernetes 기반)
- **CI/CD**: Tekton Pipelines (Buildah 빌드 → Quay.io 푸시 → Kustomize 배포)
- **모니터링**: OpenShift Monitoring Stack (Thanos Querier)

---

## 디렉토리 구조

```
vllm-optimizer/
├── AGENTS.md
├── CHANGELOG.md
├── deploy.sh                    # OpenShift 배포 스크립트
├── nginx.conf                   # 루트 레벨 nginx 설정 (프론트엔드용)
├── baseline.dev.json            # 성능 테스트 기준값
├── pyproject.toml               # pytest 설정 (markers, asyncio)
│
├── scripts/
│   ├── run_performance_tests.sh # 통합 테스트 실행 스크립트
│   └── collect_baseline.sh      # 기준값 수집 스크립트
│
├── backend/
│   ├── __init__.py
│   ├── Dockerfile              # UBI9 Python 기반, non-root, arbitrary UID
│   ├── main.py                 # FastAPI 엔트리포인트
│   ├── requirements.txt
│   ├── startup_metrics_shim.py # MetricsCollector 백그라운드 시작
│   ├── routers/
│   │   ├── __init__.py
│   │   ├── load_test.py        # 부하 테스트 API + SSE 스트림
│   │   ├── metrics.py          # Thanos Querier 메트릭 조회
│   │   ├── benchmark.py        # 벤치마크 저장/비교
│   │   └── tuner.py            # Bayesian Optimization 튜너 API
│   ├── services/
│   │   ├── __init__.py
│   │   ├── shared.py           # 싱글톤 인스턴스 (MetricsCollector, load_engine)
│   │   ├── load_engine.py      # 비동기 부하 생성 엔진
│   │   ├── metrics_collector.py # Prometheus + K8s API 수집기
│   │   └── auto_tuner.py       # Optuna + K8s ConfigMap 업데이트
│   ├── models/
│   │   ├── __init__.py
│   │   └── load_test.py        # Pydantic 요청/응답 모델
│   ├── metrics/
│   │   ├── __init__.py
│   │   └── prometheus_metrics.py # Prometheus 메트릭 정의
│   └── tests/
│       ├── __init__.py
│       ├── conftest.py          # 단위 테스트 픽스처
│       ├── test_load_test.py
│       ├── test_benchmark.py
│       ├── test_tuner.py
│       ├── test_metrics.py
│       ├── test_metrics_collector.py
│       ├── test_prometheus_metrics.py
│       └── integration/
│           └── performance/     # OpenShift 클러스터 통합 테스트
│               ├── conftest.py  # 클러스터 연결 픽스처
│               ├── test_cluster_health.py
│               ├── test_load_test_throughput.py
│               ├── test_sse_streaming.py
│               ├── test_metrics_collection.py
│               ├── test_auto_tuner.py
│               └── utils/
│                   └── baseline.py
│
├── frontend/
│   ├── Dockerfile              # UBI9 nginx-124, 8080 포트, non-root
│   ├── nginx.conf              # SPA 라우팅, /api/* 프록시 설정
│   ├── package.json
│   ├── vite.config.js          # Vite 빌드 설정
│   ├── index.html              # HTML 엔트리포인트
│   └── src/
│       ├── main.jsx            # React 엔트리포인트
│       ├── index.css           # 글로벌 스타일
│       ├── App.jsx             # React 대시보드 (4개 탭)
│       ├── constants.js        # 상수 정의
│       ├── mockData.js         # 목업 데이터
│       ├── pages/
│       │   ├── MonitorPage.jsx    # 메트릭 모니터링 탭
│       │   ├── LoadTestPage.jsx   # 부하 테스트 탭
│       │   ├── BenchmarkPage.jsx  # 벤치마크 비교 탭
│       │   └── TunerPage.jsx      # Auto Tuner 탭
│       └── components/
│           ├── Chart.jsx         # 차트 컴포넌트
│           └── MetricCard.jsx    # 메트릭 카드 컴포넌트
│
└── openshift/
    ├── base/
    │   ├── 01-namespace-rbac.yaml  # Namespace + ServiceAccount + ClusterRole + SCC
    │   ├── 02-config.yaml          # ConfigMap + Secret
    │   ├── 03-backend.yaml        # Deployment + Service + HPA
    │   ├── 04-frontend.yaml      # Deployment + Service + Route
    │   ├── 05-monitoring.yaml    # ServiceMonitor + PrometheusRule + PDB + NetworkPolicy
    │   └── kustomization.yaml
    ├── dev-only/                    # vllm-optimizer 통합 검증용 vLLM 자원
    │   ├── 06-vllm-monitoring.yaml
    │   ├── kustomization.yaml
    │   ├── vllm-inferenceservice.yaml
    │   ├── vllm-networkpolicy.yaml
    │   ├── vllm-rbac.yaml
    │   └── vllm-runtime.yaml
    ├── overlays/
    │   ├── dev/kustomization.yaml   # Dev: 리소스 축소, 1 레플리카
    │   └── prod/kustomization.yaml  # Prod: 3 레플리카, 리소스 확대
    └── tekton/
        ├── pipeline.yaml           # CI/CD Pipeline + EventListener
        └── performance-pipeline.yaml # 성능 테스트 전용 파이프라인
```

---

## 핵심 설계 원칙 (OpenShift 필수 준수 사항)

에이전트는 코드 작성 및 수정 시 아래 원칙을 **반드시** 따라야 합니다.

### 1. 컨테이너 이미지
- 베이스 이미지는 반드시 **Red Hat UBI9** 사용 (`registry.access.redhat.com/ubi9/...`)
- DockerHub 이미지 직접 참조 금지. 프로덕션 이미지는 **Quay.io**에 호스팅

### 2. 포트 규칙
- Backend: **8000** (non-root 포트)
- Frontend/nginx: **8080** (non-root 포트)
- 80, 443 등 권한 포트 사용 금지

### 3. 사용자 권한 (SCC)
- 컨테이너는 **non-root** 실행 필수
- OpenShift는 임의 UID를 할당함
- OpenShift는 기본적으로 root group 으로 할당함

```dockerfile
# 올바른 예시
RUN chgrp -R 0 . && chmod -R g+rwX .
USER 1001
```

### 4. Ingress → OpenShift Route
- **OpenShift Route** 사용 (Edge TLS 종료)

```yaml
# 올바른 예시
apiVersion: route.openshift.io/v1
kind: Route
spec:
  tls:
    termination: edge
```

### 5. 이미지 레지스트리
- 이미지는 반드시 **Quay.io** 또는 내부 레지스트리 사용

### 6. 모니터링
- Prometheus 직접 설치 금지
- **OpenShift Monitoring Stack (Thanos Querier)** 활용
- Thanos Querier 서비스 엔드포인트(내부용): `https://thanos-querier.openshift-monitoring.svc.cluster.local:9091`
- Thanos Querier 라우트 엔드포인트(외부용): `https://thanos-querier-openshift-monitoring.apps.compact.jooan.local` (socks5 proxy 필요)
- 메트릭 노출은 `/metrics` 엔드포인트 사용

### 7. 네트워크 정책
- **NetworkPolicy**로 최소 권한 원칙 적용
- 불필요한 Pod 간 통신 차단

---

## 환경변수

| 변수명 | 설명 | 예시 |
|--------|------|------|
| `REGISTRY` | 컨테이너 레지스트리 | `quay.io/joopark` |
| `IMAGE_TAG` | 이미지 태그 | `1.0.0` |
| `VLLM_NAMESPACE` | vLLM 서비스 네임스페이스 | `vllm` |
| `PROMETHEUS_URL` | Thanos Querier URL | `https://thanos-querier.openshift-monitoring.svc.cluster.local:9091` |
| `K8S_NAMESPACE` | K8s Pod 조회 대상 네임스페이스 | `vllm` |
| `K8S_DEPLOYMENT_NAME` | vLLM Deployment 이름 (KServe: `{isvc}-predictor`). **MetricsCollector의 pod listing 및 auto-tuner의 Deployment rollout restart에 사용.** | `llm-ov-predictor` |
| `VLLM_DEPLOYMENT_NAME` | KServe InferenceService 이름. **auto-tuner의 IS 이름 참조에 사용.** `K8S_DEPLOYMENT_NAME`과 혼동 금지. | `llm-ov` |

| `VLLM_ENDPOINT` | vLLM 추론 엔드포인트 (테스트용) | `http://llm-ov-predictor.vllm.svc.cluster.local:8080` |
| `VLLM_MODEL` | vLLM 모델명. `/api/config`의 `vllm_model_name` 반환에 사용. | `Qwen2.5-Coder-3B-Instruct-int4-ov` |

---

## 빌드 및 배포

### 로컬 빌드 (Podman 권장, Docker 가능)
```bash
# Backend
podman build -t vllm-optimizer-backend:dev ./backend

# Frontend
podman build -t vllm-optimizer-frontend:dev ./frontend
```

### OpenShift 배포 (Air-gapped)
```bash
# 환경변수 설정 후
export REGISTRY="quay.io/joopark"
export IMAGE_TAG="1.0.0"
export VLLM_NAMESPACE="vllm"

# Dev 배포 (빌드 + 푸시 + 배포)
./deploy.sh dev

# 드라이런 (변경사항 미리 확인)
./deploy.sh dev --dry-run

# 빌드 없이 배포만
./deploy.sh dev --skip-build

# Prod 배포
IMAGE_TAG="1.0.0" ./deploy.sh prod
```

### Kustomize 직접 배포
```bash
# Dev
oc apply -k openshift/overlays/dev

# Prod
oc apply -k openshift/overlays/prod
```

### Kustomize 검증 (로컬 kustomize 바이너리 사용 금지)
로컬 `./kustomize` 바이너리는 사용하지 않는다. kustomization 변경사항 검증은 반드시 `oc` 명령어로 한다.
```bash
# Dry-run으로 YAML 렌더링 검증 (클러스터 연결 필요 없음)
oc apply -k openshift/overlays/dev --dry-run=client
oc apply -k openshift/overlays/prod --dry-run=client

# 또는 렌더링 결과만 확인
oc kustomize openshift/overlays/dev
oc kustomize openshift/overlays/prod
```

---

## 코드 작성 가이드라인

### Backend (Python / FastAPI)

- **비동기 우선**: 모든 I/O 작업은 `async/await` 사용
- **Pydantic 모델**: 모든 요청/응답에 `models/` 하위 Pydantic 모델 정의
- **SSE 스트림**: 부하 테스트 실시간 결과는 Server-Sent Events로 전달
- **K8s API 호출**: `kubernetes` Python 클라이언트 사용, ServiceAccount 토큰 인증
- **Prometheus 쿼리**: Bearer 토큰으로 Thanos Querier API 호출
- **MetricsCollector 싱글톤**: 반드시 `from services.shared import metrics_collector` 사용. 직접 인스턴스 생성 금지
- **Import 규칙**: `backend.` 접두사 없이 bare import 사용 (`from services.xxx`, `from models.xxx`)
- **K8s API (async)**: 동기 K8s 클라이언트를 async 코드에서 사용 시 반드시 `asyncio.to_thread()` 래핑
- **Thanos TLS**: self-signed 인증서 사용 → `httpx.AsyncClient(verify=False)` 필수
- **auto_tuner 모델명**: `model="auto"` 사용 금지. `/v1/models` 엔드포인트에서 동적 해석 필수

```python
# Thanos Querier 호출 예시
import httpx

async def query_thanos(query: str, token: str) -> dict:
    async with httpx.AsyncClient(verify=False) as client:
        resp = await client.get(
            f"{THANOS_URL}/api/v1/query",
            headers={"Authorization": f"Bearer {token}"},
            params={"query": query},
        )
        resp.raise_for_status()
        return resp.json()
```

- **ConfigMap 업데이트** (Auto Tuner): `kubernetes` 클라이언트로 vLLM 네임스페이스의 ConfigMap 패치

```python
from kubernetes import client, config

config.load_incluster_config()  # Pod 내부에서 실행 시
v1 = client.CoreV1Api()
v1.patch_namespaced_config_map(name="vllm-config", namespace=VLLM_NAMESPACE, body=patch)
```

### Frontend (React)

- `/api/*` 요청은 nginx가 Backend로 프록시 (절대경로 사용)
- SSE 수신: `EventSource` API 사용
- 4개 탭 구성: **부하 테스트 / 메트릭 모니터링 / 벤치마크 비교 / Auto Tuner**

### OpenShift YAML

- `apiVersion`은 OpenShift 전용 리소스 사용 (`route.openshift.io/v1`, `security.openshift.io/v1` 등)
- 모든 Deployment에 `resources.requests` / `resources.limits` 명시
- `livenessProbe` / `readinessProbe` 필수 설정
- `securityContext`에 `runAsNonRoot: true`, `allowPrivilegeEscalation: false` 명시

```yaml
securityContext:
  runAsNonRoot: true
  allowPrivilegeEscalation: false
  capabilities:
    drop: ["ALL"]
  seccompProfile:
    type: RuntimeDefault
```

---

## vLLM 클러스터 아키텍처 (Dev 환경)

현재 Dev 환경의 vLLM은 **KServe InferenceService**로 배포됩니다.

- **InferenceService**: `llm-ov` (namespace: `vllm`)
- **KServe가 생성하는 Deployment**: `llm-ov-predictor`
- **Pod label**: `app=isvc.llm-ov-predictor` (KServe 자동 생성 패턴)
- **모델**: `Qwen2.5-Coder-3B-Instruct-int4-ov` (CPU/OpenVINO)
- **추론 엔드포인트**: `http://llm-ov-predictor.vllm.svc.cluster.local:8080`
- **API**: `/v1/completions`, `/v1/models` (OpenAI 호환)

### KServe 이름 규칙
| 리소스 | 이름 패턴 | 예시 |
|--------|-----------|------|
| InferenceService | `{name}` | `llm-ov` |
| Deployment | `{name}-predictor` | `llm-ov-predictor` |
| Pod label | `app=isvc.{name}-predictor` | `app=isvc.llm-ov-predictor` |
| Service | `{name}-predictor` | `llm-ov-predictor` |

`K8S_DEPLOYMENT_NAME` 환경변수는 반드시 KServe가 생성한 Deployment 이름(`{name}-predictor`)으로 설정해야 합니다.

---

## 통합 테스트 (Integration Tests)

실제 OpenShift 클러스터에서 실행하는 8개 통합 테스트가 있습니다.

### 테스트 목록
| 테스트 | 설명 |
|--------|------|
| `test_backend_health_deep` | Backend /health 엔드포인트 (deep check 포함) |
| `test_metrics_endpoint_accessible` | /api/metrics/latest 응답 확인 |
| `test_prometheus_metrics_plaintext` | Prometheus 텍스트 포맷 검증 |
| `test_metrics_response_time` | 메트릭 수집 응답 시간 |
| `test_prometheus_scrape_format_valid` | Prometheus scrape 형식 유효성 |
| `test_load_test_completes_successfully` | 부하 테스트 실행 + 결과 검증 |
| `test_load_test_sse_events` | SSE 스트리밍 이벤트 수신 확인 |
| `test_auto_tuner_completes_with_results` | Auto Tuner 2-trial 실행 + 결과 검증 |

### 클러스터에서 실행
```bash
NS=vllm-optimizer-dev
BACKEND_POD=$(oc get pod -n $NS -l app=vllm-optimizer-backend -o name | head -1)
oc exec -n $NS $BACKEND_POD -- env \
  PERF_TEST_BACKEND_URL=http://localhost:8000 \
  VLLM_ENDPOINT=http://llm-ov-predictor.vllm.svc.cluster.local:8080 \
  VLLM_MODEL=Qwen2.5-Coder-3B-Instruct-int4-ov \
  VLLM_NAMESPACE=vllm \
  OPTIMIZER_NAMESPACE=vllm-optimizer-dev \
  python3 -m pytest /app/tests/integration/performance/ -v --tb=short -m "integration"
```

### 단위 테스트 (로컬)
```bash
cd backend && python3 -m pytest tests/ -x -q -m "not integration"
```

---

## Tekton CI/CD 파이프라인

파이프라인 단계: `Git Clone → Test → Buildah 빌드 → Quay.io 푸시 → Kustomize 배포`

- **Buildah** 사용 (Docker 빌드 금지 — OpenShift 표준)
- Webhook Secret: `github-webhook-secret`
- Push Secret: `quay-push-secret`

```bash
# Pipeline 리소스 배포
oc apply -f openshift/tekton/pipeline.yaml -n vllm-optimizer

# 수동 실행
tkn pipeline start vllm-optimizer-pipeline -n vllm-optimizer

# 로그 확인
tkn pipelinerun logs -f -n vllm-optimizer
```

---

## 디버깅 및 검증

에이전트가 배포 후 검증이 필요할 때 사용하는 명령어입니다.

```bash
NS=vllm-optimizer-dev

# Pod 상태 확인
oc get pods -n $NS

# Route URL 확인
oc get route vllm-optimizer -n $NS

# Backend 로그 스트리밍
oc logs -l app=vllm-optimizer-backend -n $NS -f

# SCC 적용 확인
oc describe pod -l app=vllm-optimizer-backend -n $NS | grep -i scc

# 이벤트 확인 (문제 진단)
oc get events -n $NS --sort-by=.lastTimestamp | tail -20

# Prometheus 메트릭 엔드포인트 확인
oc exec -it $(oc get pod -l app=vllm-optimizer-backend -n $NS -o name | head -1) \
  -n $NS -- curl localhost:8000/metrics

# Thanos Querier 직접 쿼리 테스트
TOKEN=$(oc create token vllm-optimizer-backend -n vllm-optimizer-dev)
curl --socks5-hostname 127.0.0.1:8882 -H "Authorization: Bearer $TOKEN" \
  https://thanos-querier-openshift-monitoring.apps.compact.jooan.local/api/v1/query \
  --data-urlencode 'query=vllm:num_requests_running' -k
```

---

## E2E 클러스터 검증 필수 규칙

auto_tuner, 부하 테스트, RBAC, ConfigMap 관련 코드/YAML 변경 시 반드시 수행:

1. `./deploy.sh dev`로 OpenShift 클러스터에 배포
2. 실제 클러스터에서 `oc` 명령으로 기능 정상 동작 직접 확인
3. 파드 재기동이 필요한 변경: `oc get pods -n vllm`으로 파드 교체 확인
4. 결과를 사용자에게 물어보지 말고, 에이전트가 직접 확인 후 보고

**위반 사례**: RBAC 403 에러는 단위 테스트만으로는 발견되지 않음. 클러스터 배포 없이 코드만 수정하고 완료 처리했다가 실제로는 파드 재기동이 전혀 이루어지지 않았음.

```bash
# 기본 E2E 검증 절차
NS=vllm-optimizer-dev
BACKEND_POD=$(oc get pod -n $NS -l app=vllm-optimizer-backend -o name | head -1)

# 1. 배포
./deploy.sh dev

# 2. 튜닝 실행 전 파드 UID 기록
BEFORE_UID=$(oc get pods -n vllm -l app=isvc.llm-ov-predictor -o jsonpath='{.items[*].metadata.uid}')

# 3. IS annotation 확인 (재기동 트리거 방식)
oc get inferenceservice llm-ov -n vllm -o jsonpath='{.spec.predictor.annotations}'

# 4. 튜닝 완료 후 파드 UID 변경 확인
AFTER_UID=$(oc get pods -n vllm -l app=isvc.llm-ov-predictor -o jsonpath='{.items[*].metadata.uid}')
[ "$BEFORE_UID" != "$AFTER_UID" ] && echo "PASS: pod restarted" || echo "FAIL: pod NOT restarted"

# 5. 로그에 403 없음 확인
oc logs -l app=vllm-optimizer-backend -n $NS --tail=50 | grep -i "403\|forbidden"
```

## 자주 발생하는 문제 (에이전트 참고)

### SCC 오류 발생 시
```bash
oc adm policy add-scc-to-user vllm-optimizer-scc \
  -z vllm-optimizer-backend -n vllm-optimizer-dev
```

### 이미지 Pull 실패 시
```bash
oc import-image vllm-optimizer-backend:latest \
  --from=quay.io/joopark/vllm-optimizer-backend:latest \
  --confirm -n vllm-optimizer-dev
```

### Thanos 접근 불가 시
- ServiceAccount에 `cluster-monitoring-view` ClusterRole 바인딩 확인
- `05-monitoring.yaml`의 ClusterRoleBinding 재적용

### MetricsCollector 올-제로 메트릭
- `curl -X POST localhost:8000/startup_metrics`로 수집기 상태 확인
- `collector_version`이 `unknown`이면 Thanos 연결 실패 → 토큰/URL 확인
- `pods=0`이면 `K8S_DEPLOYMENT_NAME`이 실제 Deployment 이름과 불일치 → KServe 패턴 확인

### auto_tuner 실행 후 다른 테스트 skip
- auto_tuner가 vLLM에 추론 요청 → p99 latency 상승 → `skip_if_overloaded` 트리거
- `skip_if_overloaded`는 최대 120초 대기 후 skip (Thanos 1분 rate window 롤오버 대기)
- 지속 skip 시: vLLM pod 상태 확인 (`oc get pods -n vllm`)

### auto_tuner vLLM 파드 재기동 안 됨
- auto_tuner는 `K8S_DEPLOYMENT_NAME`(예: `llm-ov-predictor`) Deployment를 직접 rollout restart
- 파드가 재기동되지 않으면: 백엔드 로그에서 `Deployment 재시작 실패` 오류 확인
- `K8S_DEPLOYMENT_NAME`이 실제 Deployment 이름과 일치하는지 확인: `oc get deployment -n vllm`
- 수동 확인: `oc rollout restart deployment/llm-ov-predictor -n vllm`
- **주의**: KServe InferenceService 이름(`llm-ov`, `VLLM_DEPLOYMENT_NAME`)과 Deployment 이름(`llm-ov-predictor`, `K8S_DEPLOYMENT_NAME`)은 다름. 파드 재기동에는 Deployment 이름 사용.

### auto_tuner ConfigMap 수정 후 vLLM 설정 미반영
- `envFrom`으로 마운트된 ConfigMap은 Pod 재기동 없이는 환경변수가 갱신되지 않음
- auto_tuner의 trial 실행 중 rollout restart 성공 여부를 백엔드 로그로 확인
- 수동 적용: `oc rollout restart deployment/llm-ov-predictor -n vllm`
- 현재 Pod 환경변수 확인: `oc exec <pod> -n vllm -- env | grep MAX_NUM_SEQS`

### auto_tuner model="auto" 사용 금지
- `/v1/models` 엔드포인트에서 동적 해석 필수
- `model_resolver.py`의 `resolve_model_name()` 함수 사용 (이미 auto_tuner에 통합됨)

### IS args 아키텍처
- auto_tuner와 vllm_config API는 InferenceService spec.predictor.model.args를 직접 패치합니다.

---

## 금지 사항

에이전트는 다음 작업을 수행해서는 안 됩니다.

- `root` 사용자로 컨테이너 실행
- `80` 또는 `443` 포트 직접 바인딩
- Kubernetes `Ingress` 객체 생성 (OpenShift Route 사용)
- DockerHub 이미지 직접 참조
- `docker` 사용 (이 프로젝트는 `podman` 기준)
- `kubectl` 사용 (이 프로젝트는 `oc` 기준)
- 일시적인 문제를 명확한 증명 없이 Blocked 로 남기거나, Blocked 가 있는채로 계획을 완료

---

## 참고 문서

- [OpenShift 4.x 공식 문서](https://docs.openshift.com)
- [Tekton Pipelines 문서](https://tekton.dev/docs/)
- [vLLM 공식 문서](https://docs.vllm.ai)
- [Optuna 공식 문서](https://optuna.readthedocs.io)
- [Kustomize 문서](https://kubectl.docs.kubernetes.io/guides/introduction/kustomize/)
