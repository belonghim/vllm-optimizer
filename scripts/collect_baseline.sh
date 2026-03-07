#!/bin/bash
set -euo pipefail

ENV="${1:-dev}"
BACKEND_URL="${PERF_TEST_BACKEND_URL:-http://vllm-optimizer-backend.vllm-optimizer-${ENV}.svc.cluster.local:8000}"

echo "Collecting baseline from $BACKEND_URL..."

METRICS=$(curl -s "$BACKEND_URL/api/metrics/latest")

python3 -c "
import json, sys
m = json.loads('$METRICS')
baseline = {
    'throughput_rps': m.get('rps', 0),
    'avg_latency_ms': m.get('latency_mean', 0),
    'p95_latency_ms': m.get('latency_p99', 0),
    'tokens_per_sec': m.get('tps', 0),
    'gpu_utilization_avg': m.get('gpu_util', 0),
    'metrics_collection_duration_seconds': 0,
}
with open('baseline.${ENV}.json', 'w') as f:
    json.dump(baseline, f, indent=2)
print('Baseline saved to baseline.${ENV}.json')
"