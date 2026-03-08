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

get_image_digest() {
  local image_ref="$1"
  if [ -z "$image_ref" ]; then
    echo "" 2>/dev/null
    return 0
  fi
  local digest
  # Use registry-confirmed digest from oc image info (works with remote registries)
  digest=$(oc image info "$image_ref" --filter-by-os=linux/amd64 -o jsonpath='{.config.digest}' 2>/dev/null)
  if [ -n "$digest" ]; then
    # strip sha256: prefix if present
    echo "${digest#sha256:}"
    return 0
  fi
  echo "" 2>/dev/null
  return 0
}

get_deployment_image_id() {
  local deployment_name="$1"
  if [ -z "$deployment_name" ]; then
    echo "" 2>/dev/null
    return 0
  fi
  local image
  image=$(oc get deployment "$deployment_name" -o jsonpath='{.spec.template.spec.containers[0].image}' 2>/dev/null || true)
  if [ -n "$image" ]; then
    echo "$image"
    return 0
  fi
  echo "" 2>/dev/null
  return 0
}

compare_and_rollout() {
  local deployment_name="$1"
  local new_image_ref="$2"
  local _namespace="$3"
  if [ -z "$deployment_name" ] || [ -z "$new_image_ref" ]; then
    log "[WARN] compare_and_rollout called with missing arguments"; return 0
  fi

  # get new digest from provided image reference
  local new_digest
  new_digest=$(get_image_digest "$new_image_ref" 2>/dev/null || true)

  
  local current_imageID current_digest
  current_imageID=$(oc get pod -l app="$deployment_name" -n "$_namespace" -o jsonpath='{.items[0].status.containerStatuses[0].imageID}' 2>/dev/null || true)
  if [ -n "$current_imageID" ]; then
  
    local tmp
    tmp=${current_imageID#docker://}
    current_digest=${tmp#sha256:}
  else
    current_digest=""
  fi

  if [ -z "$new_digest" ]; then
    log "[WARN] Could not extract new digest for $deployment_name; skipping rollout";
    return 0
  fi

  if [ -z "$current_digest" ]; then
    log "[INFO] Current digest not found for $deployment_name; triggering rollout";
    oc rollout restart deployment/$deployment_name -n "$_namespace" || true
    oc rollout status deployment/$deployment_name -n "$_namespace" --timeout=5m
    return 0
  fi

  if [ "$new_digest" != "$current_digest" ]; then
    log "[INFO] Image changed for $deployment_name: ${current_digest} -> ${new_digest}; triggering rollout"
    oc rollout restart deployment/$deployment_name -n "$_namespace" || true
    oc rollout status deployment/$deployment_name -n "$_namespace" --timeout=5m
  else
    log "[INFO] Image unchanged for $deployment_name, skipping rollout"
  fi
}

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

if [[ "$SKIP_BUILD" != "true" && "$DRY_RUN" != "true" ]]; then
  log "Starting container image build (backend) -> ${REGISTRY}/vllm-optimizer-backend:${IMAGE_TAG}"
  podman build \
    --platform linux/amd64 \
    -t "${REGISTRY}/vllm-optimizer-backend:${IMAGE_TAG}" \
    "${PROJECT_ROOT}/backend"
  ok "Backend image built: ${REGISTRY}/vllm-optimizer-backend:${IMAGE_TAG}"

  log "Starting container image build (frontend) -> ${REGISTRY}/vllm-optimizer-frontend:${IMAGE_TAG}"
  podman build \
    --platform linux/amd64 \
    -t "${REGISTRY}/vllm-optimizer-frontend:${IMAGE_TAG}" \
    "${PROJECT_ROOT}/frontend"
  ok "Frontend image built: ${REGISTRY}/vllm-optimizer-frontend:${IMAGE_TAG}"
else
  warn "Skipping container image build (--skip-build or --dry-run)"
fi

    
    

## Push phase (non-dry-run)
if [[ "$DRY_RUN" != "true" && "$SKIP_BUILD" != "true" ]]; then
  log "Logging in to registry..."
  podman login "${REGISTRY}" || true

  log "Pushing backend image..."
  podman push "${REGISTRY}/vllm-optimizer-backend:${IMAGE_TAG}"

  log "Pushing frontend image..."
  podman push "${REGISTRY}/vllm-optimizer-frontend:${IMAGE_TAG}"
  ok "Images pushed to ${REGISTRY}"
  # After push: perform digest-based rollout checks
  compare_and_rollout "vllm-optimizer-backend" "${REGISTRY}/vllm-optimizer-backend:${IMAGE_TAG}" "${NAMESPACE}"
  compare_and_rollout "vllm-optimizer-frontend" "${REGISTRY}/vllm-optimizer-frontend:${IMAGE_TAG}" "${NAMESPACE}"
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
    log "Waiting for vllm-optimizer-backend deployment to be ready..."
    oc rollout status deployment/vllm-optimizer-backend -n "${NAMESPACE}" --timeout=5m
    log "Waiting for vllm-optimizer-frontend deployment to be ready..."
    oc rollout status deployment/vllm-optimizer-frontend -n "${NAMESPACE}" --timeout=5m



if [[ "$ENV" == "dev" ]]; then
  log "Applying OpenShift overlays for vLLM resources (environment: ${ENV}) to namespace ${VLLM_NAMESPACE}..."
  OVERLAY_PATH="${SCRIPT_DIR}/openshift/dev-only"
  if [[ "$DRY_RUN" == "true" ]]; then
    if command -v kustomize >/dev/null 2>&1; then
      kustomize build "${OVERLAY_PATH}" | oc apply --dry-run=client -f -
    else
      oc kustomize "${OVERLAY_PATH}" | oc apply --dry-run=client -f -
    fi
  else
    if command -v kustomize >/dev/null 2>&1; then
      kustomize build "${OVERLAY_PATH}" | oc apply -n "${VLLM_NAMESPACE}" -f -
    else
      oc kustomize "${OVERLAY_PATH}" | oc apply -n "${VLLM_NAMESPACE}" -f -
    fi
  fi
    log "Waiting for vllm-optimizer-backend deployment to be ready..."
    oc rollout status deployment/vllm-optimizer-backend -n "${NAMESPACE}" --timeout=5m
    log "Waiting for vllm-optimizer-frontend deployment to be ready..."
    oc rollout status deployment/vllm-optimizer-frontend -n "${NAMESPACE}" --timeout=5m

 

  
  ok "vLLM Overlay applied: ${ENV} -> namespace ${VLLM_NAMESPACE}"
fi

# Post-deployment: assign SCC to backend/frontend service accounts
oc adm policy add-scc-to-user vllm-optimizer-scc -z vllm-optimizer-backend -n "${NAMESPACE}" || warn "SCC assignment failed. Backend"
oc adm policy add-scc-to-user vllm-optimizer-scc -z vllm-optimizer-frontend -n "${NAMESPACE}" || warn "SCC assignment failed. Frontend"
if [[ "$ENV" == "dev" ]]; then
  oc adm policy add-scc-to-user vllm-optimizer-scc -z vllm-optimizer-backend -n "${VLLM_NAMESPACE}" || warn "SCC assignment failed for vLLM namespace. Backend"
fi
log "Deployment complete (dev/prod overlay applied)."
