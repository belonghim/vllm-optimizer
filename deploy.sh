#!/usr/bin/env bash
set -euo pipefail

# Simple, auditable OpenShift deploy script aligned with image registry overlays

# Root directory of repo (where Dockerfiles live)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$SCRIPT_DIR"

# Environment and run options
ENV="${1:-dev}"
DRY_RUN=false
SKIP_BUILD=false

for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=true ;;
    --skip-build) SKIP_BUILD=true ;;
  esac
done

# Registry and namespace defaults (overrideable via env)
REGISTRY="${REGISTRY:-quay.io/joopark}"

# Image tagging policy per environment (overlay-driven)
if [[ "$ENV" == "dev" ]]; then
  NAMESPACE="vllm-optimizer-dev"
  IMAGE_TAG="dev"
elif [[ "$ENV" == "prod" ]]; then
  NAMESPACE="vllm-optimizer"
  IMAGE_TAG="1.0.0"
else
  NAMESPACE="vllm-optimizer-dev"
  IMAGE_TAG="dev"
fi

log() { echo "["$(date +%H:%M:%S)"] $*"; }
ok()  { echo "[OK] $*"; }
warn() { echo "[WARN] $*"; }

## Pre-flight checks (non-fatal in dry-run)
log "Checking prerequisites..."
command -v oc >/dev/null 2>&1 || { warn "OpenShift CLI 'oc' not found; proceeding with dry-run only"; }
command -v podman >/dev/null 2>&1 || { warn "Podman not found; deploy steps requiring build will fail"; }

## Build phase
if [[ "$SKIP_BUILD" != "true" ]]; then
  log "Starting container image build (backend) -> ${REGISTRY}/vllm-optimizer-backend:${IMAGE_TAG}"
  podman build \
    --platform linux/amd64 \
    -t "${REGISTRY}/vllm-optimizer-backend:${IMAGE_TAG}" \
    -f "${PROJECT_ROOT}/backend/Dockerfile" \
    "${PROJECT_ROOT}/backend"
  ok "Backend image built: ${REGISTRY}/vllm-optimizer-backend:${IMAGE_TAG}"

  log "Starting container image build (frontend) -> ${REGISTRY}/vllm-optimizer-frontend:${IMAGE_TAG}"
  podman build \
    --platform linux/amd64 \
    -t "${REGISTRY}/vllm-optimizer-frontend:${IMAGE_TAG}" \
    -f "${PROJECT_ROOT}/frontend/Dockerfile" \
    "${PROJECT_ROOT}/frontend"
  ok "Frontend image built: ${REGISTRY}/vllm-optimizer-frontend:${IMAGE_TAG}"
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
if command -v kustomize >/dev/null 2>&1; then
  kustomize build "${OVERLAY_PATH}" | oc apply -n "${NAMESPACE}" -f -
else
  oc kustomize "${OVERLAY_PATH}" | oc apply -n "${NAMESPACE}" -f -
fi
ok "Overlay applied: ${ENV} -> namespace ${NAMESPACE}"

log "Deployment complete (dev/prod overlay applied)."
