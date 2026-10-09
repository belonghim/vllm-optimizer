#!/usr/bin/env bash
# Live UI smoke against the deployed frontend, bypassing oauth-proxy via `oc port-forward`.
#
#   ./scripts/smoke-ui.sh [env]     env = dev (default) | prod
#
# Requires: oc login, frontend/node_modules, and a Playwright Chromium (`npx playwright install chromium`).
# Env: SMOKE_PORT (default 18080), SMOKE_PLAYWRIGHT_ARGS (extra args for `playwright test`).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_NAME="${1:-dev}"
NS="vllm-optimizer-${ENV_NAME}"
PORT="${SMOKE_PORT:-18080}"

oc get deploy/vllm-optimizer-frontend -n "$NS" >/dev/null

oc port-forward -n "$NS" deploy/vllm-optimizer-frontend "${PORT}:8080" >/tmp/smoke-ui-pf.log 2>&1 &
PF_PID=$!
trap 'kill "$PF_PID" 2>/dev/null || true' EXIT

for _ in $(seq 1 30); do
  curl -fs -o /dev/null "http://localhost:${PORT}/" && break
  kill -0 "$PF_PID" 2>/dev/null || { cat /tmp/smoke-ui-pf.log >&2; echo "port-forward died" >&2; exit 1; }
  sleep 1
done
curl -fs -o /dev/null "http://localhost:${PORT}/" || { echo "frontend not reachable on :${PORT}" >&2; exit 1; }

cd "$ROOT/frontend"
SMOKE_BASE_URL="http://localhost:${PORT}" npx playwright test -c playwright.live.config.ts ${SMOKE_PLAYWRIGHT_ARGS:-}
