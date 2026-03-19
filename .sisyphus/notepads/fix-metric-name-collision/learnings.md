# Learnings — fix-metric-name-collision

## 2026-03-15 Session Start
- Root cause confirmed: prometheus_metrics.py re-exports 8 metrics with same vLLM names
- Thanos returns 2 series for `vllm:num_requests_running` — optimizer (value:0) and vLLM (value:20)
- result[0] always picks optimizer's self-shadowed value
- Pre-flight confirmed: `{namespace="vllm"}` filter correctly returns ONLY vLLM pod metrics
- K8S_NAMESPACE="vllm" is set in 03-backend.yaml env section
- Naming convention: `vllm_optimizer_` (underscore) — NOT colon, per Prometheus convention
- _detect_version() is SAFE (uses non-colliding metrics: gpu_memory_usage_bytes, kv_cache_usage_perc)
- PrometheusRule alerts reference vLLM original names — do NOT change them

## Guardrails
- DO NOT touch _detect_version()
- DO NOT fix counter.inc(rate) semantic bug
- DO NOT change vllm_optimizer:metrics_collection_duration_seconds colon
- DO NOT touch PrometheusRule alert expressions
- DO NOT touch frontend code
