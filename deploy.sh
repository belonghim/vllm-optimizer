#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════════
# deploy.sh — vLLM Optimizer OpenShift 배포 스크립트
#
# 사용법:
#   ./scripts/deploy.sh [dev|prod] [--dry-run] [--skip-build]
#
# 사전 요구사항:
#   - oc CLI (OpenShift Client) 설치 및 로그인
#   - podman 설치 (이미지 빌드)
#   - quay.io 계정 및 레포지터리
# ═══════════════════════════════════════════════════════════════════════════════
set -euo pipefail

# ── 설정 변수 ──────────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

ENV="${1:-dev}"
DRY_RUN=false
SKIP_BUILD=false

# 옵션 파싱
for arg in "$@"; do
  case $arg in
    --dry-run) DRY_RUN=true ;;
    --skip-build) SKIP_BUILD=true ;;
  esac
done

# ── 커스터마이즈 가능한 변수 ───────────────────────────────────────────────────
REGISTRY="${REGISTRY:-quay.io/your-org}"
IMAGE_TAG="${IMAGE_TAG:-latest}"
NAMESPACE="${NAMESPACE:-vllm-optimizer}"
CLUSTER_DOMAIN="${CLUSTER_DOMAIN:-apps.your-cluster.example.com}"
VLLM_NAMESPACE="${VLLM_NAMESPACE:-vllm}"

if [[ "$ENV" == "dev" ]]; then
  NAMESPACE="vllm-optimizer-dev"
  IMAGE_TAG="${IMAGE_TAG:-dev}"
fi

# ── 색상 출력 ──────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; CYAN='\033[0;36m'; NC='\033[0m'

log()  { echo -e "${BLUE}[$(date +%H:%M:%S)]${NC} $*"; }
ok()   { echo -e "${GREEN}✓${NC} $*"; }
warn() { echo -e "${YELLOW}⚠${NC} $*"; }
err()  { echo -e "${RED}✗${NC} $*" >&2; exit 1; }
step() { echo -e "\n${CYAN}═══ $* ═══${NC}"; }

# ── 사전 검사 ──────────────────────────────────────────────────────────────────
step "사전 요구사항 확인"

command -v oc &>/dev/null || err "oc CLI가 필요합니다: https://console.redhat.com/openshift/downloads"
command -v podman &>/dev/null || err "podman이 필요합니다: dnf install podman"
command -v kustomize &>/dev/null || warn "kustomize 없음 — oc kustomize 사용"

# OpenShift 로그인 확인
oc whoami &>/dev/null || err "OpenShift에 로그인하세요: oc login https://api.your-cluster.example.com:6443"
CURRENT_USER=$(oc whoami)
CURRENT_SERVER=$(oc whoami --show-server)
ok "로그인됨: ${CURRENT_USER} @ ${CURRENT_SERVER}"

# ── 이미지 빌드 & 푸시 ─────────────────────────────────────────────────────────
if [[ "$SKIP_BUILD" == "false" ]]; then
  step "컨테이너 이미지 빌드 (Podman)"

  # Backend
  log "Backend 이미지 빌드..."
  podman build \
    --platform linux/amd64 \
    -t "${REGISTRY}/vllm-optimizer-backend:${IMAGE_TAG}" \
    -f "${PROJECT_ROOT}/backend/Dockerfile" \
    "${PROJECT_ROOT}/backend"
  ok "Backend 이미지 빌드 완료"

  # Frontend
  log "Frontend 이미지 빌드..."
  podman build \
    --platform linux/amd64 \
    -t "${REGISTRY}/vllm-optimizer-frontend:${IMAGE_TAG}" \
    -f "${PROJECT_ROOT}/frontend/Dockerfile" \
    "${PROJECT_ROOT}/frontend"
  ok "Frontend 이미지 빌드 완료"

  if [[ "$DRY_RUN" == "false" ]]; then
    log "Quay.io 로그인..."
    podman login quay.io

    log "이미지 푸시..."
    podman push "${REGISTRY}/vllm-optimizer-backend:${IMAGE_TAG}"
    podman push "${REGISTRY}/vllm-optimizer-frontend:${IMAGE_TAG}"
    ok "이미지 푸시 완료"
  else
    warn "[DRY-RUN] 이미지 푸시 건너뜀"
  fi
fi

# ── OpenShift 배포 ─────────────────────────────────────────────────────────────
step "OpenShift 배포 (환경: ${ENV})"

OC_CMD="oc"
[[ "$DRY_RUN" == "true" ]] && OC_CMD="oc --dry-run=client"

# 1. Namespace 생성 (없으면)
log "Namespace 확인/생성: ${NAMESPACE}"
if ! oc get namespace "${NAMESPACE}" &>/dev/null; then
  $OC_CMD new-project "${NAMESPACE}" \
    --description="vLLM Optimizer - ${ENV} 환경" \
    --display-name="vLLM Optimizer (${ENV})" \
    2>/dev/null || oc create namespace "${NAMESPACE}"
  ok "Namespace 생성: ${NAMESPACE}"
else
  ok "Namespace 존재: ${NAMESPACE}"
fi

# 2. Namespace 레이블 설정 (OpenShift Monitoring 활성화)
oc label namespace "${NAMESPACE}" \
  openshift.io/cluster-monitoring=true \
  --overwrite 2>/dev/null || true

# 3. Quay.io Pull Secret 생성
log "이미지 Pull Secret 설정..."
if ! oc get secret quay-pull-secret -n "${NAMESPACE}" &>/dev/null; then
  warn "quay-pull-secret이 없습니다. 생성 중..."
  echo "Quay.io 사용자명을 입력하세요:"
  read -r QUAY_USER
  echo "Quay.io 패스워드/토큰을 입력하세요:"
  read -rs QUAY_PASS

  $OC_CMD create secret docker-registry quay-pull-secret \
    --docker-server=quay.io \
    --docker-username="${QUAY_USER}" \
    --docker-password="${QUAY_PASS}" \
    -n "${NAMESPACE}"
  ok "Pull Secret 생성 완료"

  # ServiceAccount에 연결
  $OC_CMD secrets link default quay-pull-secret \
    --for=pull -n "${NAMESPACE}" || true
else
  ok "Pull Secret 존재: quay-pull-secret"
fi

# 4. SCC 바인딩 (cluster-admin 권한 필요)
log "SCC 바인딩 설정..."
if oc auth can-i create securitycontextconstraints &>/dev/null; then
  oc apply -f "${PROJECT_ROOT}/openshift/base/01-namespace-rbac.yaml" \
    2>/dev/null || warn "SCC 적용 실패 (cluster-admin 권한 확인 필요)"

  # ServiceAccount에 SCC 연결
  oc adm policy add-scc-to-user vllm-optimizer-scc \
    -z vllm-optimizer-backend -n "${NAMESPACE}" 2>/dev/null || true
  oc adm policy add-scc-to-user vllm-optimizer-scc \
    -z vllm-optimizer-frontend -n "${NAMESPACE}" 2>/dev/null || true
  ok "SCC 바인딩 완료"
else
  warn "cluster-admin 권한 없음 — SCC는 관리자에게 요청하세요"
  warn "  oc adm policy add-scc-to-user vllm-optimizer-scc \\"
  warn "    -z vllm-optimizer-backend -n ${NAMESPACE}"
fi

# 5. Kustomize로 배포
log "Kustomize 배포 적용..."
OVERLAY_PATH="${PROJECT_ROOT}/openshift/overlays/${ENV}"

if command -v kustomize &>/dev/null; then
  kustomize build "${OVERLAY_PATH}" | $OC_CMD apply -n "${NAMESPACE}" -f -
else
  oc kustomize "${OVERLAY_PATH}" | $OC_CMD apply -n "${NAMESPACE}" -f -
fi
ok "Kustomize 리소스 적용 완료"

if [[ "$DRY_RUN" == "true" ]]; then
  warn "[DRY-RUN] 실제 배포 없이 완료"
  exit 0
fi

# 6. 배포 완료 대기
step "배포 완료 대기"

log "Backend 롤아웃 대기..."
oc rollout status deployment/vllm-optimizer-backend \
  -n "${NAMESPACE}" --timeout=5m
ok "Backend 준비 완료"

log "Frontend 롤아웃 대기..."
oc rollout status deployment/vllm-optimizer-frontend \
  -n "${NAMESPACE}" --timeout=5m
ok "Frontend 준비 완료"

# 7. 배포 검증
step "배포 검증"

ROUTE=$(oc get route vllm-optimizer -n "${NAMESPACE}" \
  -o jsonpath='{.spec.host}' 2>/dev/null || echo "")

if [[ -n "$ROUTE" ]]; then
  log "Route URL: https://${ROUTE}"
  log "헬스체크..."
  sleep 5
  if curl -sf --max-time 10 "https://${ROUTE}/health" &>/dev/null; then
    ok "헬스체크 통과"
  else
    warn "헬스체크 실패 — Pod 로그 확인 필요"
    oc logs -l app=vllm-optimizer-backend -n "${NAMESPACE}" --tail=20
  fi
fi

# ── 최종 요약 ──────────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}═══════════════════════════════════════${NC}"
echo -e "${GREEN}  vLLM Optimizer 배포 완료!${NC}"
echo -e "${GREEN}═══════════════════════════════════════${NC}"
echo ""
echo -e "  환경: ${CYAN}${ENV}${NC}"
echo -e "  Namespace: ${CYAN}${NAMESPACE}${NC}"
[[ -n "$ROUTE" ]] && echo -e "  URL: ${CYAN}https://${ROUTE}${NC}"
echo ""
echo "  유용한 명령어:"
echo "    oc get pods -n ${NAMESPACE}"
echo "    oc logs -l app=vllm-optimizer-backend -n ${NAMESPACE} -f"
echo "    oc get events -n ${NAMESPACE} --sort-by=.lastTimestamp"
echo ""
