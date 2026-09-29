#!/bin/bash
set -euo pipefail

ENV="${1:-dev}"
BACKEND_URL="${PERF_TEST_BACKEND_URL:-http://vllm-optimizer-backend.vllm-optimizer-${ENV}.svc.cluster.local:8000}"
NAMESPACE="${VLLM_NAMESPACE:-vllm-lab-dev}"
IS_NAME="${VLLM_DEPLOYMENT_NAME:-llm-ov}"
CR_TYPE="${VLLM_CR_TYPE:-inferenceservice}"

echo "Collecting baseline from $BACKEND_URL (${NAMESPACE}/${IS_NAME}, ${CR_TYPE})..."

METRICS=$(curl -sf --get "$BACKEND_URL/api/metrics/latest" \
  --data-urlencode "namespace=${NAMESPACE}" \
  --data-urlencode "is_name=${IS_NAME}" \
  --data-urlencode "cr_type=${CR_TYPE}")

METRICS="$METRICS" python3 -c "
import json, os

payload = json.loads(os.environ['METRICS'])
if payload.get('status') != 'ready' or not payload.get('data'):
    raise SystemExit(f'Metrics not ready yet (status={payload.get(\"status\")}); retry shortly.')

m = payload['data']
baseline = {
    'throughput_rps': m.get('rps', 0),
    'avg_latency_ms': m.get('latency_mean', 0),
    'p95_latency_ms': m.get('latency_p99', 0),
    'tokens_per_sec': m.get('tps', 0),
    'gpu_utilization_avg': m.get('gpu_util', 0),
}
with open('baseline.${ENV}.json', 'w') as f:
    json.dump(baseline, f, indent=2)
print('Baseline saved to baseline.${ENV}.json')
"
