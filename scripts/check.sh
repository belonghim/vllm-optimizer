#!/usr/bin/env bash
# Minimal verification gate for vLLM Optimizer.
#
#   ./scripts/check.sh            full gate: full suites incl. slow tests + lint/type/build
#   ./scripts/check.sh --smoke    fast core-functionality smoke only
#   ./scripts/check.sh --help     show this help
#
# Requires: backend deps + ruff available in $PYTHON (or .venv/bin/python, or python3),
#           and frontend/node_modules installed.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

MODE="full"
for arg in "$@"; do
  case "$arg" in
    --smoke) MODE="smoke" ;;
    -h | --help)
      sed -n '2,9p' "$0"
      exit 0
      ;;
    *)
      echo "Unknown option: $arg (use --smoke or --help)" >&2
      exit 2
      ;;
  esac
done

# Resolve Python interpreter: $PYTHON > project venv > python3
PY="${PYTHON:-}"
if [ -z "$PY" ]; then
  if [ -x "$ROOT/.venv/bin/python" ]; then
    PY="$ROOT/.venv/bin/python"
  else
    PY="python3"
  fi
fi

step() { printf '\n== %s ==\n' "$1"; }
fail() {
  printf '\nFAILED: %s\n' "$1" >&2
  exit 1
}

"$PY" -c "import pytest, ruff" 2>/dev/null ||
  fail "backend deps missing for '$PY'. Install: $PY -m pip install -r backend/requirements.txt ruff"
[ -d frontend/node_modules ] ||
  fail "frontend deps missing. Run: (cd frontend && npm ci)"

if [ "$MODE" = "smoke" ]; then
  step "backend smoke (core feature contracts)"
  "$PY" -m pytest backend/tests/test_smoke.py -q || fail "backend smoke"
  step "frontend smoke (core pages)"
  (cd frontend && npm run test:smoke) || fail "frontend smoke"
  printf '\nSMOKE OK\n'
  exit 0
fi

step "backend tests (incl. slow; integration needs a cluster)"
"$PY" -m pytest backend/tests -q -m "not integration" || fail "backend tests"

step "backend lint"
"$PY" -m ruff check backend/ || fail "ruff check"
"$PY" -m ruff format --check backend/ || fail "ruff format"

step "frontend tests"
(cd frontend && npm run test) || fail "frontend tests"

step "frontend types"
(cd frontend && npm run type-check) || fail "tsc"

step "frontend lint"
(cd frontend && npm run lint) || fail "eslint"

step "frontend format"
(cd frontend && npm run format:check) || fail "prettier"

step "frontend build"
(cd frontend && npm run build) || fail "frontend build"

printf '\nALL CHECKS PASSED\n'
