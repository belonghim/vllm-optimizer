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
      echo "  VLLM_NAMESPACE (default) => llm-d-demo (dev) | vllm-lab-prod (prod)"
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

# LLMIS RBAC 배포용 기본값 (llm-d-demo 네임스페이스에 RBAC 리소스 배포)
# 백엔드 ConfigMap의 VLLM_NAMESPACE(vllm-lab-dev)와는 별개
# Set VLLM_NAMESPACE based on environment
if [[ "$ENV" == "dev" ]]; then
  VLLM_NAMESPACE="${VLLM_NAMESPACE:-llm-d-demo}"
elif [[ "$ENV" == "prod" ]]; then
  VLLM_NAMESPACE="${VLLM_NAMESPACE:-vllm-lab-prod}"
else
  VLLM_NAMESPACE="${VLLM_NAMESPACE:-llm-d-demo}"
fi

VLLM_DEPLOYMENT_NAME="${VLLM_DEPLOYMENT_NAME:-small-llm-d}"
LLMIS_NAMESPACE="${LLMIS_NAMESPACE:-llm-d-demo}"
: "${REGISTRY:?ERROR: REGISTRY env var is required (e.g., quay.io/joopark)}"

log() { echo "[$(date +%H:%M:%S)] $*"; }
ok()  { echo "[OK] $*"; }
warn() { echo "[WARN] $*"; }
err() { echo "[ERROR] $*" >&2; }

validate_prerequisites() {
  log "Validating prerequisites..."
  
  # Check REGISTRY
  if [ -z "$REGISTRY" ]; then
    err "REGISTRY environment variable is not set"
    exit 1
  fi
  
  # Check IMAGE_TAG
  if [ -z "$IMAGE_TAG" ]; then
    err "IMAGE_TAG environment variable is not set"
    exit 1
  fi
  
  # Check oc availability
  if ! command -v oc >/dev/null 2>&1; then
    err "OpenShift CLI 'oc' not found in PATH"
    exit 1
  fi
  
  # Skip cluster checks in dry-run mode
  if [[ "$DRY_RUN" == "true" ]]; then
    log "Skipping cluster connectivity checks (dry-run mode)"
    return 0
  fi
  
  # Check oc whoami (cluster login)
  if ! oc whoami >/dev/null 2>&1; then
    err "Failed to authenticate with OpenShift cluster. Please run 'oc login'"
    exit 1
  fi
  
  # Check target namespace exists
  if ! oc get namespace "$NAMESPACE" >/dev/null 2>&1; then
    err "Namespace '$NAMESPACE' does not exist or is not accessible"
    exit 1
  fi
  
  log "Prerequisites validation passed"
}

get_image_digest() {
  local image_ref="$1"
  if [ -z "$image_ref" ]; then
    echo "" 2>/dev/null
    return 0
  fi
  local digest
  digest=$(oc image info "$image_ref" --filter-by-os=linux/amd64 -o json 2>/dev/null | jq -r '.digest // empty' || true)
  if [ -n "$digest" ]; then
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

   # Check if deployment exists (e.g., first-time deploy before kustomize apply)
   if ! oc get deployment "$deployment_name" -n "$_namespace" &>/dev/null; then
     log "[INFO] Deployment $deployment_name not found in $_namespace; skipping rollout (will be created by kustomize)"
     return 0
   fi

   # get new digest from provided image reference
   local new_digest
   new_digest=$(get_image_digest "$new_image_ref" 2>/dev/null || true)

   local current_imageID current_digest
   current_imageID=$(oc get pod -l app="$deployment_name" -n "$_namespace" -o jsonpath='{.items[0].status.containerStatuses[0].imageID}' 2>/dev/null || true)
   if [ -n "$current_imageID" ]; then
     current_digest=$(echo "$current_imageID" | grep -oE '[0-9a-f]{64}' | head -1 || true)
   else
     current_digest=""
   fi

   if [ -z "$new_digest" ]; then
     log "[WARN] Could not extract new digest for $deployment_name; skipping rollout"
     return 0
   fi

   if [ -z "$current_digest" ]; then
     log "[INFO] Current digest not found for $deployment_name; triggering rollout"
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

patch_monitoring_labels() {
  local target_namespace="$1"
  if [ -z "$target_namespace" ]; then
    warn "patch_monitoring_labels called without namespace; skipping"
    return 0
  fi

  if [[ "$DRY_RUN" == "true" ]]; then
    log "[DRY-RUN] Would patch monitoring labels in namespace '$target_namespace'"
    return 0
  fi

  local podmonitors
  podmonitors=$(oc get podmonitor -n "$target_namespace" --no-headers 2>/dev/null | awk '{print $1}' || true)
  if [ -n "$podmonitors" ]; then
    while IFS= read -r pm_name; do
      if [ -n "$pm_name" ]; then
        log "Patching PodMonitor '$pm_name' in namespace '$target_namespace' with monitoring label..."
        oc label podmonitor "$pm_name" -n "$target_namespace" openshift.io/cluster-monitoring=true --overwrite 2>/dev/null || true
        ok "PodMonitor '$pm_name' labeled"
      fi
    done <<< "$podmonitors"
  fi

  local servicemonitors
  servicemonitors=$(oc get servicemonitor -n "$target_namespace" --no-headers 2>/dev/null | awk '{print $1}' || true)
  if [ -n "$servicemonitors" ]; then
    while IFS= read -r sm_name; do
      if [ -n "$sm_name" ]; then
        log "Patching ServiceMonitor '$sm_name' in namespace '$target_namespace' with monitoring label..."
        oc label servicemonitor "$sm_name" -n "$target_namespace" openshift.io/cluster-monitoring=true --overwrite 2>/dev/null || true
        ok "ServiceMonitor '$sm_name' labeled"
      fi
    done <<< "$servicemonitors"
  fi

  if [ -z "$podmonitors" ] && [ -z "$servicemonitors" ]; then
    warn "No PodMonitor/ServiceMonitor found in namespace '$target_namespace' — skipping monitoring labels"
  fi
}

rollback_deployment() {
  local namespace=$1
  local deployment=$2
  local revision_count
  revision_count=$(oc rollout history deployment/$deployment -n $namespace 2>/dev/null | grep -c "^[0-9]" || echo 0)
  if [ "$revision_count" -ge 2 ]; then
    echo "Rolling back $deployment in $namespace..."
    oc rollout undo deployment/$deployment -n $namespace
  else
    echo "WARNING: Cannot rollback $deployment — no previous revision available (first deploy)"
  fi
}

health_check_deployment() {
  local namespace=$1
  local label=$2
  local port=$3
  local max_attempts=5
  local wait_seconds=10
  for i in $(seq 1 $max_attempts); do
    echo "Health check attempt $i/$max_attempts..."
    local pod
    pod=$(oc get pod -n "$namespace" -l "$label" --field-selector=status.phase=Running -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
    if [ -n "$pod" ] && oc exec -n "$namespace" "$pod" -- curl -sf "http://localhost:${port}/health" > /dev/null 2>&1; then
      echo "Health check passed."
      return 0
    fi
    sleep $wait_seconds
  done
  echo "ERROR: Health check failed after $max_attempts attempts"
  return 1
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

# Validate prerequisites (fatal if missing)
validate_prerequisites

if [[ "$SKIP_BUILD" != "true" && "$DRY_RUN" != "true" ]]; then
  log "Starting container image build (backend) -> ${REGISTRY}/vllm-optimizer-backend:${IMAGE_TAG}"
  podman build --layers \
    --platform linux/amd64 \
    -t "${REGISTRY}/vllm-optimizer-backend:${IMAGE_TAG}" \
    "${PROJECT_ROOT}/backend"
  ok "Backend image built: ${REGISTRY}/vllm-optimizer-backend:${IMAGE_TAG}"

  log "Starting container image build (frontend) -> ${REGISTRY}/vllm-optimizer-frontend:${IMAGE_TAG}"
  podman build --layers \
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
  podman login "${REGISTRY}" || echo "WARNING: podman login failed (may already be authenticated)"

  log "Pushing backend image..."
  podman push "${REGISTRY}/vllm-optimizer-backend:${IMAGE_TAG}"

  log "Pushing frontend image..."
  podman push "${REGISTRY}/vllm-optimizer-frontend:${IMAGE_TAG}"
  ok "Images pushed to ${REGISTRY}"
  
  # Wait a moment for registry to index the new blobs
  sleep 2
  
  # After push: perform digest-based rollout checks
  compare_and_rollout "vllm-optimizer-backend" "${REGISTRY}/vllm-optimizer-backend:${IMAGE_TAG}" "${NAMESPACE}"
  compare_and_rollout "vllm-optimizer-frontend" "${REGISTRY}/vllm-optimizer-frontend:${IMAGE_TAG}" "${NAMESPACE}"
else
  warn "[DRY-RUN] Skipping image push"
fi

if [[ "$DRY_RUN" != "true" ]]; then
  log "Copying oauth-proxy ImageStream tag..."
  oc tag openshift/oauth-proxy:v4.4 "${NAMESPACE}/oauth-proxy:v4.4" --reference-policy=source 2>/dev/null || echo "WARNING: Failed to tag oauth-proxy ImageStream (may already exist or cluster lacks access)"
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

log "Performing health check for vllm-optimizer-backend..."
if ! health_check_deployment "${NAMESPACE}" "app=vllm-optimizer-backend" "8000"; then
  warn "Health check failed; rolling back vllm-optimizer-backend..."
  rollback_deployment "${NAMESPACE}" "vllm-optimizer-backend"
  exit 1
fi
ok "Backend deployment healthy"

log "Waiting for vllm-optimizer-frontend deployment to be ready..."
oc rollout status deployment/vllm-optimizer-frontend -n "${NAMESPACE}" --timeout=5m

VLLM_DEP_PATH="${SCRIPT_DIR}/openshift/vllm-dependency/${ENV}"
VLLM_DEP_NAMESPACE="vllm-lab-${ENV}"
if [[ -d "$VLLM_DEP_PATH" ]]; then
  log "Applying vllm-dependency overlays (environment: ${ENV}) to namespace ${VLLM_DEP_NAMESPACE}..."
  if [[ "$DRY_RUN" == "true" ]]; then
    if command -v kustomize >/dev/null 2>&1; then
      kustomize build "${VLLM_DEP_PATH}" | oc apply --dry-run=client -f -
    else
      oc kustomize "${VLLM_DEP_PATH}" | oc apply --dry-run=client -f -
    fi
  else
    if command -v kustomize >/dev/null 2>&1; then
      kustomize build "${VLLM_DEP_PATH}" | oc apply -f -
    else
      oc kustomize "${VLLM_DEP_PATH}" | oc apply -f -
    fi
  fi
  ok "vllm-dependency applied: ${ENV} -> namespace ${VLLM_DEP_NAMESPACE}"
else
  warn "vllm-dependency path not found: ${VLLM_DEP_PATH}; skipping"
fi

# subst_env: portable envsubst replacement using sed (envsubst may not be installed)
subst_env() {
  sed \
    -e "s|\${VLLM_NAMESPACE}|${VLLM_NAMESPACE}|g" \
    -e "s|\${VLLM_DEPLOYMENT_NAME}|${VLLM_DEPLOYMENT_NAME}|g" \
    -e "s|\${NAMESPACE}|${NAMESPACE}|g"
}

if [[ "${ENV}" == "dev" ]]; then
  LLMIS_RBAC_PATH="${SCRIPT_DIR}/openshift/vllm-dependency/llmis-rbac"
  if [[ -d "$LLMIS_RBAC_PATH" ]]; then
    # Use nullglob so the loop is skipped when no *.yaml files exist
    shopt -s nullglob
    yaml_files=("${LLMIS_RBAC_PATH}"/*.yaml)
    shopt -u nullglob
    if [[ ${#yaml_files[@]} -eq 0 ]]; then
      warn "No YAML files found in ${LLMIS_RBAC_PATH}; skipping LLMIS RBAC apply"
    else
      log "Applying LLMIS monitoring RBAC to namespace ${VLLM_NAMESPACE}..."
      for f in "${yaml_files[@]}"; do
        if [[ "$DRY_RUN" == "true" ]]; then
          subst_env < "$f" | oc apply --dry-run=client -f -
        else
          subst_env < "$f" | oc apply -f - || { warn "Failed to apply $(basename "$f") to ${VLLM_NAMESPACE}"; exit 1; }
        fi
      done
      ok "LLMIS monitoring RBAC applied: ${VLLM_NAMESPACE}"
    fi
  fi
fi

log "Patching LLMIS monitoring labels in namespace ${VLLM_NAMESPACE}..."
patch_monitoring_labels "$VLLM_NAMESPACE"

log "Deployment complete (dev/prod overlay applied)."
