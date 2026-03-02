#!/bin/bash
set -euo pipefail
# Simple, auditable OpenShift deploy script aligned with image registry overlays

# Root directory of repo (where Dockerfiles live)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$SCRIPT_DIR"

# Environment and run options (defaults)
ENV="${1:-dev}"
DRY_RUN=false
SKIP_BUILD=false
VLLM_NAMESPACE="${VLLM_NAMESPACE:-vllm}" # Default vLLM namespace

# Parse flags
for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=true ;;
    --skip-build) SKIP_BUILD=true ;;
    -h|--help)
      echo "Usage: $0 [ENV] [--dry-run] [--skip-build]"
      echo ""
      echo "Environment:"
      echo "  dev    - Deploy to vllm-optimizer-dev namespace"
      echo "  prod   - Deploy to vllm-optimizer-prod namespace"
      echo ""
      echo "Registry and tags (overrideable via environment variables):"
      echo "  REGISTRY=${REGISTRY:-quay.io/joopark}"
      echo "  IMAGE_TAG (dev) => dev  |  (prod) => 1.0.0"
      echo "  NAMESPACE (dev) => vllm-optimizer-dev | (prod) => vllm-optimizer-prod"
      echo "  VLLM_NAMESPACE (default) => vllm"
      echo ""
      echo "Examples:"
      echo "  $0 dev --dry-run         # Preview dev deployment"
      echo "  $0 prod                  # Deploy to production"
      echo "  REGISTRY=myreg.io $0 dev  # Use custom registry"
      exit 0
      ;;
  esac
done

# Registry and namespace defaults (overrideable via env)
REGISTRY="${REGISTRY:-quay.io/joopark}"

# Image tagging policy per environment (overlay-driven)
if [[ "$ENV" == "dev" ]]; then
  NAMESPACE="vllm-optimizer-dev"
  IMAGE_TAG="dev"
elif [[ "$ENV" == "prod" ]]; then
  NAMESPACE="vllm-optimizer-prod"
  IMAGE_TAG="1.0.0"
else
  NAMESPACE="vllm-optimizer-dev"
  IMAGE_TAG="dev"
fi

log() { echo "[$(date +%H:%M:%S)] $*"; }
ok()  { echo "[OK] $*"; }
warn() { echo "[WARN] $*"; }

info_dry_run() {
  if [[ "$DRY_RUN" == "true" ]]; then
    echo ""
    echo "==== DRY-RUN CONFIGURATION ===="
    echo "Environment:   $ENV"
    echo "Namespace:     $NAMESPACE"
    echo "Registry:      $REGISTRY"
    echo "Image Tags:    Backend => ${REGISTRY}/vllm-optimizer-backend:${IMAGE_TAG}"
    echo "               Frontend => ${REGISTRY}/vllm-optimizer-frontend:${IMAGE_TAG}"
    echo "Build:         $([[ "$SKIP_BUILD" == "true" ]] && echo 'SKIPPED' || echo 'ENABLED')"
    echo "Push:          $([[ "$DRY_RUN" == "true" ]] && echo 'SKIPPED (dry-run)' || echo 'ENABLED')"
    echo "================================"
    echo ""
  fi
}

## Pre-flight checks (non-fatal in dry-run)
log "Checking prerequisites..."
command -v oc >/dev/null 2>&1 || { warn "OpenShift CLI 'oc' not found; proceeding with dry-run only"; }
command -v podman >/dev/null 2>&1 || { warn "Podman not found; deploy steps requiring build will fail"; }

## Show dry-run info before any actions
info_dry_run

## Build phase
if [[ "$SKIP_BUILD" != "true" ]]; then
  log "Starting container image build (backend) -> ${REGISTRY}/vllm-optimizer-backend:${IMAGE_TAG}"
  podman build \
    --platform linux/amd64 \
    -t "${REGISTRY}/vllm-optimizer-backend:${IMAGE_TAG}" \
    -f "${PROJECT_ROOT}/backend/Dockerfile" \
    "${PROJECT_ROOT}"
  ok "Backend image built: ${REGISTRY}/vllm-optimizer-backend:${IMAGE_TAG}"

  log "Starting container image build (frontend) -> ${REGISTRY}/vllm-optimizer-frontend:${IMAGE_TAG}"
  podman build \
    --platform linux/amd64 \
    -t "${REGISTRY}/vllm-optimizer-frontend:${IMAGE_TAG}" \
    -f "${PROJECT_ROOT}/frontend/Dockerfile" \
    "${PROJECT_ROOT}"
  ok "Frontend image built: ${REGISTRY}/vllm-optimizer-frontend:${IMAGE_TAG}"
else
  log "Build skipped (--skip-build flag)"
fi

## Push phase (non-dry-run)
if [[ "$DRY_RUN" != "true" ]]; then
  log "Logging in to registry..."
  podman login "${REGISTRY}" || true

  log "Pushing backend image..."
  podman push "${REGISTRY}/vllm-optimizer-backend:${IMAGE_TAG}"

  log "Pushing frontend image..."
  podman push "${REGISTRY}/vllm-optimizer-frontend:${IMAGE_TAG}"
  ok "Images pushed to ${REGISTRY}"
else
  warn "[DRY-RUN] Skipping image push"
fi

## Deploy phase (overlay-based via kustomize)
log "Applying OpenShift overlays (environment: ${ENV})..."
OVERLAY_PATH="${SCRIPT_DIR}/openshift/overlays/${ENV}"
if [[ "$DRY_RUN" == "true" ]]; then
  if command -v kustomize >/dev/null 2>&1; then
    kustomize build "${OVERLAY_PATH}" | oc apply --dry-run=client -n "${NAMESPACE}" -f -
  else
    oc kustomize "${OVERLAY_PATH}" | oc apply --dry-run=client -n "${NAMESPACE}" -f -
  fi
else
  if command -v kustomize >/dev/null 2>&1; then
    kustomize build "${OVERLAY_PATH}" | oc apply -n "${NAMESPACE}" -f -
  else
    oc kustomize "${OVERLAY_PATH}" | oc apply -n "${NAMESPACE}" -f -
  fi
fi
ok "Overlay applied: ${ENV} -> namespace ${NAMESPACE}"

## Deploy phase for vLLM resources (overlay-based via kustomize)
log "Applying OpenShift overlays for vLLM resources (environment: ${ENV}) to namespace ${VLLM_NAMESPACE}..."
OVERLAY_PATH="${SCRIPT_DIR}/openshift/overlays/${ENV}"
if [[ "$DRY_RUN" == "true" ]]; then
  if command -v kustomize >/dev/null 2>&1; then
    kustomize build "${OVERLAY_PATH}" | oc apply --dry-run=client -n "${VLLM_NAMESPACE}" -f -
  else
    oc kustomize "${OVERLAY_PATH}" | oc apply --dry-run=client -n "${VLLM_NAMESPACE}" -f -
  fi
else
  if command -v kustomize >/dev/null 2>&1; then
    kustomize build "${OVERLAY_PATH}" | oc apply -n "${VLLM_NAMESPACE}" -f -
  else
    oc kustomize "${OVERLAY_PATH}" | oc apply -n "${VLLM_NAMESPACE}" -f -
  fi
fi
ok "vLLM Overlay applied: ${ENV} -> namespace ${VLLM_NAMESPACE}"

# Post-deployment: assign SCC to backend/frontend service accounts
oc adm policy add-scc-to-user vllm-optimizer-scc -z vllm-optimizer-backend -n "${NAMESPACE}" || warn "SCC assignment failed. Backend"
oc adm policy add-scc-to-user vllm-optimizer-scc -z vllm-optimizer-frontend -n "${NAMESPACE}" || warn "SCC assignment failed. Frontend"
oc adm policy add-scc-to-user vllm-optimizer-scc -z vllm-optimizer-backend -n "${VLLM_NAMESPACE}" || warn "SCC assignment failed for vLLM namespace. Backend"
log "Deployment complete (dev/prod overlay applied)."
