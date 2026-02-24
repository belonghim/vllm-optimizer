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
├── backend/
│   ├── Dockerfile              # UBI9 Python 기반, non-root, arbitrary UID
│   ├── main.py                 # FastAPI 엔트리포인트
│   ├── requirements.txt
│   ├── routers/
│   │   ├── load_test.py        # 부하 테스트 API + SSE 스트림
│   │   ├── metrics.py          # Thanos Querier 메트릭 조회
│   │   ├── benchmark.py        # 벤치마크 저장/비교
│   │   └── tuner.py            # Bayesian Optimization 튜너 API
│   ├── services/
│   │   ├── load_engine.py      # 비동기 부하 생성 엔진
│   │   ├── metrics_collector.py # Prometheus + K8s API 수집기
│   │   └── auto_tuner.py       # Optuna + K8s ConfigMap 업데이트
│   └── models/
│       └── load_test.py        # Pydantic 요청/응답 모델
│
├── frontend/
│   ├── Dockerfile              # UBI9 nginx, 8080 포트, non-root
│   ├── nginx.conf              # SPA 라우팅, /api/* 프록시 설정
│   ├── src/App.jsx             # React 대시보드 (4개 탭)
│   └── package.json
│
└── openshift/
    ├── base/
    │   ├── 01-namespace-rbac.yaml   # Namespace + ServiceAccount + ClusterRole + SCC
    │   ├── 02-config.yaml           # ConfigMap + Secret
    │   ├── 03-backend.yaml          # Deployment + Service + HPA
    │   ├── 04-frontend.yaml         # Deployment + Service + Route
    │   ├── 05-monitoring.yaml       # ServiceMonitor + PrometheusRule + PDB + NetworkPolicy
    │   ├── 06-imagestream.yaml      # ImageStream (Quay.io 자동 동기화)
    │   └── kustomization.yaml
    ├── overlays/
    │   ├── dev/kustomization.yaml   # Dev: 리소스 축소, 1 레플리카
    │   └── prod/kustomization.yaml  # Prod: 3 레플리카, 리소스 확대
    └── tekton/
        └── pipeline.yaml           # CI/CD Pipeline + EventListener
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
- **arbitrary UID** 지원 필요 (OpenShift는 임의 UID를 할당함)
- `USER 1001` 또는 `USER 65532` 등 고정 UID 사용 가능하나, arbitrary UID 호환 코드 작성

```dockerfile
# 올바른 예시
RUN chown -R 1001:0 /app && chmod -R g=u /app
USER 1001
```

### 4. Ingress → OpenShift Route
- Kubernetes `Ingress` 객체 사용 금지
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
- **ImageStream**을 통한 이미지 관리 권장

### 6. 모니터링
- Prometheus 직접 설치 금지
- **OpenShift Monitoring Stack (Thanos Querier)** 활용
- Thanos Querier 엔드포인트: `https://thanos-querier.openshift-monitoring.svc.cluster.local:9091`
- 메트릭 노출은 `/metrics` 엔드포인트 사용

### 7. 네트워크 정책
- **NetworkPolicy**로 최소 권한 원칙 적용
- 불필요한 Pod 간 통신 차단

---

## 환경변수

| 변수명 | 설명 | 예시 |
|--------|------|------|
| `REGISTRY` | 컨테이너 레지스트리 | `quay.io/your-org` |
| `IMAGE_TAG` | 이미지 태그 | `1.0.0` |
| `CLUSTER_DOMAIN` | OpenShift 클러스터 도메인 | `apps.your-cluster.example.com` |
| `VLLM_NAMESPACE` | vLLM 서비스 네임스페이스 | `vllm` |
| `THANOS_URL` | Thanos Querier URL | `https://thanos-querier.openshift-monitoring.svc.cluster.local:9091` |

---

## 빌드 및 배포

### 로컬 빌드 (Podman 권장, Docker 가능)
```bash
# Backend
podman build -t vllm-optimizer-backend:dev ./backend

# Frontend
podman build -t vllm-optimizer-frontend:dev ./frontend
```

### OpenShift 배포
```bash
# 환경변수 설정 후
export REGISTRY="quay.io/your-org"
export IMAGE_TAG="1.0.0"
export CLUSTER_DOMAIN="apps.your-cluster.example.com"
export VLLM_NAMESPACE="vllm"

# Dev 배포 (빌드 + 푸시 + 배포)
./scripts/deploy.sh dev

# 드라이런 (변경사항 미리 확인)
./scripts/deploy.sh dev --dry-run

# 빌드 없이 배포만
./scripts/deploy.sh dev --skip-build

# Prod 배포
IMAGE_TAG="1.0.0" ./scripts/deploy.sh prod
```

### Kustomize 직접 배포
```bash
# Dev
oc apply -k openshift/overlays/dev

# Prod
oc apply -k openshift/overlays/prod
```

---

## 코드 작성 가이드라인

### Backend (Python / FastAPI)

- **비동기 우선**: 모든 I/O 작업은 `async/await` 사용
- **Pydantic 모델**: 모든 요청/응답에 `models/` 하위 Pydantic 모델 정의
- **SSE 스트림**: 부하 테스트 실시간 결과는 Server-Sent Events로 전달
- **K8s API 호출**: `kubernetes` Python 클라이언트 사용, ServiceAccount 토큰 인증
- **Prometheus 쿼리**: Bearer 토큰으로 Thanos Querier API 호출

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
NS=vllm-optimizer

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
TOKEN=$(oc serviceaccounts get-token vllm-optimizer-backend -n vllm-optimizer)
curl -H "Authorization: Bearer $TOKEN" \
  https://thanos-querier.openshift-monitoring.svc.cluster.local:9091/api/v1/query \
  --data-urlencode 'query=vllm:num_requests_running' -k
```

---

## 자주 발생하는 문제 (에이전트 참고)

### SCC 오류 발생 시
```bash
oc adm policy add-scc-to-user vllm-optimizer-scc \
  -z vllm-optimizer-backend -n vllm-optimizer
```

### 이미지 Pull 실패 시
```bash
# ImageStream 수동 동기화
oc import-image vllm-optimizer-backend:latest \
  --from=quay.io/your-org/vllm-optimizer-backend:latest \
  --confirm -n vllm-optimizer
```

### Thanos 접근 불가 시
- ServiceAccount에 `cluster-monitoring-view` ClusterRole 바인딩 확인
- `05-monitoring.yaml`의 ClusterRoleBinding 재적용

---

## 금지 사항

에이전트는 다음 작업을 수행해서는 안 됩니다.

- `root` 사용자로 컨테이너 실행
- `80` 또는 `443` 포트 직접 바인딩
- Kubernetes `Ingress` 객체 생성 (OpenShift Route 사용)
- DockerHub 이미지 직접 참조
- `cluster-admin` 권한에 의존하는 로직 작성
- `kubectl` 대신 `oc` 사용 금지 위반 (이 프로젝트는 `oc` 기준)

---

## 참고 문서

- [OpenShift 4.x 공식 문서](https://docs.openshift.com)
- [Tekton Pipelines 문서](https://tekton.dev/docs/)
- [vLLM 공식 문서](https://docs.vllm.ai)
- [Optuna 공식 문서](https://optuna.readthedocs.io)
- [Kustomize 문서](https://kubectl.docs.kubernetes.io/guides/introduction/kustomize/)
