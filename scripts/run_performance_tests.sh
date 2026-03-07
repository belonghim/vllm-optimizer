#!/bin/bash
set -euo pipefail

ENV="${1:-dev}"
REPORT_DIR="reports/$(date +%Y-%m-%dT%H-%M-%S)"
mkdir -p "$REPORT_DIR"

echo "=== Performance Tests: env=$ENV ==="

export PERF_TEST_BACKEND_URL="${PERF_TEST_BACKEND_URL:-http://vllm-optimizer-backend.vllm-optimizer-${ENV}.svc.cluster.local:8000}"
export PERF_BASELINE_FILE="baseline.${ENV}.json"

python3 -m pytest backend/tests/integration/performance/ \
    -v --tb=short \
    -m "integration and performance" \
    --junitxml="$REPORT_DIR/results.xml" \
    2>&1 | tee "$REPORT_DIR/output.log"

echo "=== Results saved to $REPORT_DIR ==="