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

### 프로젝트 포지셔닝과 차별점

vLLM Optimizer는 Red Hat GuideLLM 같은 **벤치마크 도구와 경쟁하지 않는다**. 오히려 보완 관계이다.

| 관점 | GuideLLM (벤치마크) | vLLM Optimizer (운영 최적화) |
|------|-------------------|--------------------------|
| 핵심 질문 | "이 모델이 얼마나 빠른가?" | "이 모델을 어떻게 더 빠르게 만드는가?" |
| 사용 시점 | 배포 전 성능 측정 | 배포 후 지속적 운영 최적화 |
| 실행 방식 | CLI / K8s Job (일회성) | 상주 서비스 (FastAPI + React) |
| 출력 | JSON/HTML 리포트 (정적) | 실시간 대시보드 + 자동 튜닝 |

**핵심 차별점 — 클로즈드 루프 최적화:**
- 측정(부하 테스트) → 분석(벤치마크 비교 + SLA 판정) → 최적화(Optuna 자동 튜닝) → 적용(KServe IS 패치) → 재측정
- GuideLLM은 "측정"만 담당. vLLM Optimizer는 **전체 루프를 하나의 플랫폼에서 제공**.

**컴팩트 아키텍처의 장점:**
- Backend(FastAPI) + Frontend(React) 2-Pod 구성으로 배포 단순성 유지
- 외부 DB 없이 **SQLite + PVC**로 데이터 영구 저장 (운영 복잡도 최소화)
- OpenShift Monitoring Stack 재사용 — 별도 Prometheus 설치 불필요
- 단일 `deploy.sh`로 dev/prod 완전 배포 가능

**설계 시 지켜야 할 방향:**
- 컴팩트 구조를 유지한다. 기능 추가 시 별도 마이크로서비스로 분리하지 않는다.
- 기존 OpenShift 인프라(Monitoring Stack, KServe, RBAC)를 최대한 활용한다.
- 벤치마크 도구와의 차별점(자동 튜닝, 실시간 모니터링, KServe 통합)을 강화하는 방향으로 발전한다.
- 벤치마크 도구(GuideLLM 등)의 결과를 임포트하여 통합 분석할 수 있는 확장점을 고려한다.

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
│   │   ├── tuner.py            # Bayesian Optimization 튜너 API
│   │   ├── sla.py              # SLA 프로필 CRUD + 판정 API
│   │   └── vllm_config.py      # IS tuning args + resources GET/PATCH
│   ├── services/
│   │   ├── __init__.py
│   │   ├── shared.py           # 싱글톤 인스턴스 (MetricsCollector, load_engine)
│   │   ├── load_engine.py      # 비동기 부하 생성 엔진
│   │   ├── metrics_collector.py # Prometheus + K8s API 수집기
│   │   └── auto_tuner.py       # Optuna + InferenceService args 업데이트
│   ├── models/
│   │   ├── __init__.py
│   │   ├── load_test.py        # Pydantic 요청/응답 모델
│   │   └── sla.py              # SLA Pydantic 모델
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
│       ├── test_sla.py
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
│       ├── App.jsx             # React 대시보드 (5개 탭)
│       ├── constants.js        # 상수 정의
│       ├── mockData.js         # 목업 데이터
│       ├── mocks/
│       │   └── handlers.js        # MSW mock 핸들러 (테스트용)
│       ├── contexts/
│       │   └── ClusterConfigContext.tsx  # IS endpoint/namespace 전역 상태
│       ├── pages/
│       │   ├── MonitorPage.jsx    # 메트릭 모니터링 탭
│       │   ├── LoadTestPage.jsx   # 부하 테스트 탭
│       │   ├── BenchmarkPage.jsx  # 벤치마크 비교 탭
│       │   ├── TunerPage.jsx      # Auto Tuner 탭 (vllm-config 현재값 + 편집)
│       │   └── SlaPage.tsx        # SLA 대시보드 탭
│       └── components/
│           ├── Chart.jsx         # 차트 컴포넌트
│           ├── MetricCard.jsx    # 메트릭 카드 컴포넌트
│           ├── ClusterConfigBar.tsx  # 클러스터 설정 바 (IS endpoint/namespace 편집)
│           └── TunerConfigForm.tsx   # 튜너 파라미터 + CPU/Memory/GPU 리소스 편집 폼
│
└── openshift/
    ├── base/
    │   ├── 01-namespace-rbac.yaml  # Namespace + ServiceAccount + ClusterRole + SCC
    │   ├── 02-config.yaml          # ConfigMap + Secret
    │   ├── 03-backend.yaml        # Deployment + Service + HPA
    │   ├── 04-frontend.yaml      # Deployment + Service + Route
    │   ├── 05-monitoring.yaml    # ServiceMonitor + PrometheusRule + PDB + NetworkPolicy
    │   └── kustomization.yaml
    ├── vllm-dependency/             # vLLM 의존성 Kustomize 오버레이 (base, dev, prod)
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
| `VLLM_NAMESPACE` | LLM 추론 서비스 네임스페이스 | `llm-d-demo` (dev), `llm-d-prod` (prod) |
| `VLLM_CR_TYPE` | LLM 리소스 타입 (KServe 또는 LLMIS) | `llminferenceservice` (기본) |
| `PROMETHEUS_URL` | Thanos Querier URL | `https://thanos-querier.openshift-monitoring.svc.cluster.local:9091` |
| `K8S_NAMESPACE` | K8s Pod 조회 대상 네임스페이스 | `llm-d-demo` (dev), `llm-d-prod` (prod) |
| `K8S_DEPLOYMENT_NAME` | LLM Deployment 이름 (LLMIS: `{llmis}-kserve`). **MetricsCollector의 pod listing 및 auto-tuner의 Deployment rollout restart에 사용.** | `small-llm-d-kserve` |
| `VLLM_DEPLOYMENT_NAME` | LLMInferenceService 이름. **auto-tuner의 리소스 이름 참조에 사용.** `K8S_DEPLOYMENT_NAME`과 혼동 금지. | `small-llm-d` |
| `VLLM_ENDPOINT` | LLM 추론 엔드포인트 (테스트용). Gateway 내부 또는 외부 주소. | `http://openshift-ai-inference-openshift-default.openshift-ingress.svc/llm-d-demo/small-llm-d` |
| `VLLM_MODEL` | LLM 모델명 | `qwen2-5-7b-instruct` |

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
export VLLM_NAMESPACE="llm-d-demo"  # Dev: llm-d-demo, Prod: llm-d-prod

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
- 5개 탭 구성: **부하 테스트 / 메트릭 모니터링 / 벤치마크 비교 / Auto Tuner / SLA**
- `ClusterConfigContext`로 IS endpoint/namespace 전역 관리 — `useClusterConfig()` hook 사용
- `TunerPage`의 vllm-config fetch useEffect deps에 `namespace`, `inferenceservice` 포함 필수 (IS 변경 시 re-fetch)
- 리소스 편집 키 형식: `resources.{tier}.{key}` (예: `resources.limits.cpu`) — `editedValues`에서 `resources.` 접두사로 tuning args와 분리

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

현재 Dev 환경의 vLLM은 **LLMInferenceService (LLMIS) + Gateway** 아키텍처로 배포됩니다.

### 주 배포 모델: LLMInferenceService (LLMIS)

- **LLMInferenceService**: `small-llm-d` (namespace: `llm-d-demo`)
- **Deployment**: `small-llm-d-kserve` (자동 생성)
- **Pod label**: `app.kubernetes.io/name=small-llm-d`
- **모델**: `qwen2-5-7b-instruct`
- **Gateway 패턴**: HTTP 트래픽 → Gateway → HTTPRoute → InferencePool
- **Gateway 내부 엔드포인트**: `http://openshift-ai-inference-openshift-default.openshift-ingress.svc/llm-d-demo/small-llm-d`
- **Gateway 외부 엔드포인트**: `http://ai-gateway.apps.compact.jooan.local/llm-d-demo/small-llm-d`
- **API**: `/v1/completions`, `/v1/models` (OpenAI 호환)

### LLMIS 이름 규칙
| 리소스 | 이름 패턴 | 예시 |
|--------|-----------|------|
| LLMInferenceService | `{name}` | `small-llm-d` |
| Deployment | `{name}-kserve` | `small-llm-d-kserve` |
| Pod label | `app.kubernetes.io/name={name}` | `app.kubernetes.io/name=small-llm-d` |
| Gateway endpoint | `{gateway}/{namespace}/{name}/v1/...` | `.../llm-d-demo/small-llm-d/v1/models` |

`K8S_DEPLOYMENT_NAME` 환경변수는 반드시 LLMIS가 생성한 Deployment 이름(`{name}-kserve`)으로 설정해야 합니다.

### 네임스페이스 분리 원칙 (중요)

| CR 타입 | 네임스페이스 | 비고 |
|---------|------------|------|
| `LLMInferenceService` (llmisvc) | `llm-d-demo` | llm-d 플랫폼이 관리. **직접 생성 금지** |
| `InferenceService` (isvc) | `vllm-lab-dev` / `vllm-lab-prod` | KServe. vllm-dependency Kustomize가 관리 |

- `llm-d-demo`에는 RBAC + NetworkPolicy만 배포 (`openshift/vllm-dependency/llmis-rbac/`)
- `vllm-dependency/dev` Kustomize 오버레이는 반드시 `namespace: vllm-lab-dev`로 유지
- `deploy.sh dev`는 두 단계: ① `vllm-dependency/dev` → `vllm-lab-dev`, ② `llmis-rbac/` → `llm-d-demo`

### 레거시/대안: KServe InferenceService

이전 환경에서 사용되던 KServe InferenceService의 구조는 다음과 같습니다 (참고용):

- **InferenceService**: `llm-ov` (namespace: `vllm-lab-dev`)
- **KServe가 생성하는 Deployment**: `llm-ov-predictor`
- **Pod label**: `app=isvc.llm-ov-predictor`
- **추론 엔드포인트**: `http://llm-ov-predictor.vllm-lab-dev.svc.cluster.local:8080`

#### KServe 이름 규칙 (레거시)
| 리소스 | 이름 패턴 | 예시 |
|--------|-----------|------|
| InferenceService | `{name}` | `llm-ov` |
| Deployment | `{name}-predictor` | `llm-ov-predictor` |
| Pod label | `app=isvc.{name}-predictor` | `app=isvc.llm-ov-predictor` |
| Service | `{name}-predictor` | `llm-ov-predictor` |

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
  VLLM_ENDPOINT=http://openshift-ai-inference-openshift-default.openshift-ingress.svc/llm-d-demo/small-llm-d \
  VLLM_MODEL=qwen2-5-7b-instruct \
  VLLM_NAMESPACE=llm-d-demo \
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

# LLM 파드 상태 확인 (LLMIS)
oc get pods -n llm-d-demo -l app.kubernetes.io/name=small-llm-d
```

---

## E2E 클러스터 검증 필수 규칙

auto_tuner, 부하 테스트, RBAC, ConfigMap 관련 코드/YAML 변경 시 반드시 수행:

1. `./deploy.sh dev`로 OpenShift 클러스터에 배포
2. 실제 클러스터에서 `oc` 명령으로 기능 정상 동작 직접 확인
3. 파드 재기동이 필요한 변경: `oc get pods -n vllm-lab-dev`으로 파드 교체 확인
4. 결과를 사용자에게 물어보지 말고, 에이전트가 직접 확인 후 보고

**위반 사례**: RBAC 403 에러는 단위 테스트만으로는 발견되지 않음. 클러스터 배포 없이 코드만 수정하고 완료 처리했다가 실제로는 파드 재기동이 전혀 이루어지지 않았음.

```bash
# 기본 E2E 검증 절차
NS=vllm-optimizer-dev
BACKEND_POD=$(oc get pod -n $NS -l app=vllm-optimizer-backend -o name | head -1)

# 1. 배포
./deploy.sh dev

# 2. 튜닝 실행 전 파드 UID 기록
BEFORE_UID=$(oc get pods -n llm-d-demo -l app.kubernetes.io/name=small-llm-d -o jsonpath='{.items[*].metadata.uid}')

# 3. LLMIS annotation 확인 (재기동 트리거 방식)
oc get llminferenceservice small-llm-d -n llm-d-demo -o jsonpath='{.spec.predictor.annotations}'

# 4. 튜닝 완료 후 파드 UID 변경 확인
AFTER_UID=$(oc get pods -n llm-d-demo -l app.kubernetes.io/name=small-llm-d -o jsonpath='{.items[*].metadata.uid}')
[ "$BEFORE_UID" != "$AFTER_UID" ] && echo "PASS: pod restarted" || echo "FAIL: pod NOT restarted"

# 5. 로그에 403 없음 확인
oc logs -l app=vllm-optimizer-backend -n $NS --tail=50 | grep -i "403\|forbidden"
```

## 자주 발생하는 문제 (에이전트 참고)

### SCC 오류 발생 시

vLLM Optimizer는 OpenShift 기본 SCC인 `restricted-v2`를 사용합니다.
별도 SCC 바인딩이 필요하지 않습니다. Pod가 SCC 문제로 실패하면:

```bash
# 현재 적용된 SCC 확인
oc describe pod -l app=vllm-optimizer-backend -n vllm-optimizer-dev | grep -i scc
# 예상 결과: openshift.io/scc: restricted-v2
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
- `pods=0`이면 `K8S_DEPLOYMENT_NAME`이 실제 Deployment 이름과 불일치 → LLMIS/KServe 패턴 확인

### auto_tuner 실행 후 다른 테스트 skip
- auto_tuner가 vLLM에 추론 요청 → p99 latency 상승 → `skip_if_overloaded` 트리거
- `skip_if_overloaded`는 최대 120초 대기 후 skip (Thanos 1분 rate window 롤오버 대기)
- 지속 skip 시: vLLM pod 상태 확인 (`oc get pods -n llm-d-demo`)

### auto_tuner vLLM 파드 재기동 안 됨
- auto_tuner는 `K8S_DEPLOYMENT_NAME`(예: `small-llm-d-kserve`) Deployment를 직접 rollout restart
- 파드가 재기동되지 않으면: 백엔드 로그에서 `Deployment 재시작 실패` 오류 확인
- `K8S_DEPLOYMENT_NAME`이 실제 Deployment 이름과 일치하는지 확인: `oc get deployment -n llm-d-demo`
- 수동 확인: `oc rollout restart deployment/small-llm-d-kserve -n llm-d-demo`
- **주의**: LLMIS 이름(`small-llm-d`, `VLLM_DEPLOYMENT_NAME`)과 Deployment 이름(`small-llm-d-kserve`, `K8S_DEPLOYMENT_NAME`)은 다름. 파드 재기동에는 Deployment 이름 사용.

### IS args 아키텍처
- auto_tuner와 vllm_config API 모두 IS `spec.predictor.model.args`를 직접 패치합니다.
- **vllm_config PATCH**: dict-merge 방식 — 기존 args를 보존하고 변경된 키만 덮어씀. 부분 업데이트 안전.
- **auto_tuner._apply_params**: 전체 교체 방식 (의도된 설계) — 수정 금지.
- boolean `false` 전송 시 해당 flag 제거 (e.g. `{"enable_chunked_prefill": "false"}` → args에서 `--enable-chunked-prefill` 제거)

### IS resources 아키텍처
- IS resources 경로: `spec.predictor.model.resources.{requests,limits}`
- `ALLOWED_RESOURCE_KEYS = {"cpu", "memory", "nvidia.com/gpu"}` — 허용된 리소스 키 (backend 검증)
- GPU는 `limits`에만 설정 (K8s가 `requests`로 자동 복사)
- 빈 문자열 값 전송 시 해당 키 제거 (K8s 스케줄링에 영향 방지)
- `vllm_config.py` PATCH 요청: `data`(tuning args)와 `resources`는 독립 필드로 각각 처리

### auto_tuner model="auto" 사용 금지
- `/v1/models` 엔드포인트에서 동적 해석 필수
- `model_resolver.py`의 `resolve_model_name()` 함수 사용 (이미 auto_tuner에 통합됨)

### SLA 프로필 생성 422
- `SlaThresholds`에 `at_least_one_threshold` model_validator 존재 — 모든 threshold가 null이면 422
- 프론트엔드에서 최소 1개 threshold 입력 필수 validation이 이미 적용되어 있음
- 백엔드 `SlaProfile`/`SlaThresholds` 모델 수정 금지 (검증 로직 정상)
- 422 에러 시 응답 body의 `detail` 필드에 Pydantic 검증 메시지 포함

---

## Playwright 사용 가이드 — 토큰 절약 규칙

AI 에이전트가 Playwright로 브라우저를 조작할 때 불필요한 snapshot 요청이 토큰을 과도하게 소모합니다. 다음 규칙을 반드시 준수하십시오.

### 필수 규칙: snapshot 호출 최소화

Playwright skill이 매 상호작용 후 자동으로 `browser_snapshot`을 호출하는 것은 **巨大的** 토큰 낭비입니다. 매 페이지 상태를 텍스트로 변환하면 수천 토큰이 소비됩니다.

**올바른 사용법:**
```typescript
// ✅ GOOD: 명시적 도구만 사용 — snapshot 호출 안 함
await playwright_browser_click({ element: "theme toggle switch", ref: "e14" });
// 상태가 바뀌었는지 직접 특정 요소로 확인
const isLight = await playwright_browser_evaluate({ 
  function: "() => document.documentElement.getAttribute('data-theme')" 
});

// ❌ BAD: click 직후 snapshot (불필요하게 전체 DOM 캡처)
await playwright_browser_click({ ... });
await playwright_browser_snapshot(); // ← 토큰 폭발, 금지!
```

**금지 패턴:**
- `playwright_browser_click` → 직후 `playwright_browser_snapshot` **금지**
- `playwright_browser_type` → 직후 `playwright_browser_snapshot` **금지**
- 매 단계마다 snapshot **금지**
- 변경 확인용 snapshot 대신 `playwright_browser_evaluate` 사용

**허용 패턴:**
- 첫 페이지 로드 시 1회 snapshot (초기 상태 확인용)
- 디버깅 시 명시적 snapshot (문제가 있을 때만)
- `playwright_browser_evaluate`로 특정 값 확인 (DOM 요소 직접 쿼리)
- `playwright_browser_console_messages`로 에러 확인

### 토큰 절약 체크리스트

에이전트가 Playwright를 사용하기 전 반드시 확인:

1. **snapshot이 필요한가?** → 아니오. `evaluate`, `click`, `type`으로 충분
2. **console_messages 대신 snapshot을 쓰고 있는가?** → `console_messages`가 에러 확인에 더 효율적
3. **screenshot이 필요한가?** → 시각적 검증이 필요한 경우만. 대부분 `evaluate`로 대체 가능
4. **navigate 후 바로 snapshot?** → 필수 아님. 핵심 요소만 evaluate로 확인

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
