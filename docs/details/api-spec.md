---
title: vLLM Optimizer API Specification
date: 2026-04-05
tags:
  - api
  - documentation
  - backend
  - fastapi
version: "1.0"
status: draft
---

# vLLM Optimizer API Specification

> [!NOTE]
> 이 문서는 **고수준 요약**입니다. 정확한 API 스키마는 `/docs` (Swagger UI) 또는 `/openapi.json`을 참조하세요.

## Quick Reference (참고용)

| # | Method | Path | Feature | Description |
|---|--------|------|---------|-------------|
| 1 | `GET` | `/api/config` | Config | Get current optimizer configuration |
| 2 | `PATCH` | `/api/config` | Config | Update optimizer configuration |
| 3 | `GET` | `/api/config/default-targets` | Config | Get default target services |
| 4 | `PATCH` | `/api/config/default-targets` | Config | Update default targets |
| 5 | `GET` | `/api/metrics/latest` | Metrics | Get latest metrics |
| 6 | `POST` | `/api/metrics/batch` | Metrics | Batch metrics for multiple targets |
| 7 | `POST` | `/api/metrics/pods` | Metrics | Per-pod metrics breakdown |
| 8 | `POST` | `/api/metrics/pods/history` | Metrics | Per-pod historical metrics |
| 9 | `GET` | `/api/metrics/history` | Metrics | Metrics history |
| 10 | `GET` | `/api/metrics` | Metrics | Prometheus metrics endpoint |
| 11 | `POST` | `/api/tuner/start` | Tuner | Start Bayesian optimization |
| 12 | `GET` | `/api/tuner/status` | Tuner | Get tuner status |
| 13 | `GET` | `/api/tuner/trials` | Tuner | Get tuning trials |
| 14 | `POST` | `/api/tuner/stop` | Tuner | Stop auto-tuning |
| 15 | `GET` | `/api/tuner/stream` | Tuner | SSE event stream |
| 16 | `GET` | `/api/tuner/importance` | Tuner | Parameter importance |
| 17 | `GET` | `/api/tuner/all` | Tuner | Combined tuner state |
| 18 | `POST` | `/api/tuner/apply-best` | Tuner | Apply best parameters |
| 19 | `GET` | `/api/tuner/sessions` | Tuner | List tuning sessions |
| 20 | `GET` | `/api/tuner/sessions/{session_id}` | Tuner | Get session detail |
| 21 | `DELETE` | `/api/tuner/sessions/{session_id}` | Tuner | Delete tuning session |
| 22 | `GET` | `/api/tuner/model-analysis` | Tuner | Deterministic model analysis (config.json → KV, capacity, search ranges) |
| 23 | `POST` | `/api/tuner/model-analysis/explain` | Tuner | Analyst LLM narrative of an analysis |
| 24 | `GET` | `/api/tuner/boot-diagnosis` | Tuner | Why a target pod fails to boot: container status + previous/current log matched to known vLLM errors |
| 25 | `POST` | `/api/load_test/start` | Load Test | Start load test |
| 26 | `POST` | `/api/load_test/stop` | Load Test | Stop load test |
| 27 | `GET` | `/api/load_test/status` | Load Test | Get load test status |
| 28 | `POST` | `/api/load_test/sweep` | Load Test | Start parameter sweep |
| 29 | `GET` | `/api/load_test/stream` | Load Test | SSE result stream |
| 30 | `GET` | `/api/load_test/history` | Load Test | Load test history |
| 31 | `POST` | `/api/load_test/sweep/save` | Load Test | Save sweep result |
| 32 | `GET` | `/api/load_test/sweep/history` | Load Test | List saved sweeps |
| 33 | `GET` | `/api/load_test/sweep/history/{sweep_id}` | Load Test | Get single sweep |
| 34 | `DELETE` | `/api/load_test/sweep/history/{sweep_id}` | Load Test | Delete sweep |
| 35 | `GET` | `/api/vllm-config` | vLLM Config | Get vLLM config from K8s |
| 36 | `PATCH` | `/api/vllm-config` | vLLM Config | Update vLLM config in K8s |
| 37 | `GET` | `/api/benchmark/list` | Benchmark | List saved benchmarks |
| 38 | `POST` | `/api/benchmark/save` | Benchmark | Save benchmark result |
| 39 | `GET` | `/api/benchmark/by-model` | Benchmark | Benchmarks by model |
| 40 | `POST` | `/api/benchmark/import` | Benchmark | Import from GuideLLM |
| 41 | `GET` | `/api/benchmark/{benchmark_id}` | Benchmark | Get single benchmark |
| 42 | `DELETE` | `/api/benchmark/{benchmark_id}` | Benchmark | Delete benchmark |
| 43 | `PATCH` | `/api/benchmark/{benchmark_id}/metadata` | Benchmark | Update benchmark metadata |
| 44 | `GET` | `/api/sla/profiles` | SLA | List SLA profiles |
| 45 | `POST` | `/api/sla/profiles` | SLA | Create SLA profile |
| 46 | `GET` | `/api/sla/profiles/{profile_id}` | SLA | Get SLA profile |
| 47 | `PUT` | `/api/sla/profiles/{profile_id}` | SLA | Update SLA profile |
| 48 | `DELETE` | `/api/sla/profiles/{profile_id}` | SLA | Delete SLA profile |
| 49 | `POST` | `/api/sla/evaluate` | SLA | Evaluate against SLA |
| 50 | `GET` | `/api/alerts/sla-violations` | Alerts | Get SLA violations |
| 51 | `GET` | `/api/status/interrupted` | Status | Get interrupted runs |
| 52 | `GET` | `/health` | System | Health check |
| 53 | `GET` | `/` | System | Root endpoint |
| 54 | `GET` | `/docs` | System | Swagger UI |
| 55 | `GET` | `/redoc` | System | ReDoc documentation |
| 56 | `GET` | `/openapi.json` | System | OpenAPI spec JSON |

---

## Common Types

### Standard Error Response

All error responses follow this structure:

```json
{
  "detail": "Human-readable error message"
}
```

HTTP status codes used across the API:

| Code | Meaning | Typical Cause |
|------|---------|---------------|
| 400 | Bad Request | Invalid input, preflight check failed |
| 404 | Not Found | Resource does not exist |
| 409 | Conflict | Resource conflict (tuner running, already running) |
| 413 | Payload Too Large | File upload exceeds size limit |
| 422 | Unprocessable Entity | Invalid keys, parse error |
| 500 | Internal Server Error | Unexpected server error |
| 503 | Service Unavailable | External dependency unavailable |

---

## Config

Configuration management for the vLLM optimizer. Controls which vLLM endpoint and namespace the optimizer targets.

### GET /api/config

Get the current vLLM optimizer configuration.

**Query Parameters:** None

**Request Body:** None

**Response (200 OK):**

```json
{
  "vllm_endpoint": "string",
  "vllm_namespace": "string",
  "vllm_is_name": "string",
  "vllm_model_name": "string",
  "resolved_model_name": "string",
  "cr_type": "inferenceservice | llminferenceservice",
  "configmap_updated": "boolean"
}
```

**Response Fields:**

| Field | Type | Description |
|-------|------|-------------|
| `vllm_endpoint` | string | URL of the vLLM endpoint |
| `vllm_namespace` | string | Kubernetes namespace |
| `vllm_is_name` | string | InferenceService name |
| `vllm_model_name` | string | Model name from configuration |
| `resolved_model_name` | string | Resolved model name after lookup |
| `cr_type` | string | Custom resource type: `inferenceservice` or `llminferenceservice` |
| `configmap_updated` | boolean | Whether ConfigMap has been updated |

**Error Responses:**

| Status | Condition |
|--------|-----------|
| 500 | Internal server error reading configuration |

---

### PATCH /api/config

Update the optimizer configuration. Allows changing the target endpoint, namespace, inference service name, and custom resource type.

**Request Body:**

```json
{
  "vllm_endpoint": "string (optional)",
  "vllm_namespace": "string (optional)",
  "vllm_is_name": "string (optional)",
  "cr_type": "inferenceservice | llminferenceservice (optional)"
}
```

**Request Fields:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `vllm_endpoint` | string | No | New vLLM endpoint URL |
| `vllm_namespace` | string | No | New Kubernetes namespace |
| `vllm_is_name` | string | No | New InferenceService name |
| `cr_type` | string | No | Custom resource type |

**Response (200 OK):**

```json
{
  "vllm_endpoint": "string",
  "vllm_namespace": "string",
  "vllm_is_name": "string",
  "vllm_model_name": "string",
  "resolved_model_name": "string",
  "cr_type": "string",
  "configmap_updated": "boolean"
}
```

**Error Responses:**

| Status | Condition |
|--------|-----------|
| 409 | Tuner is running and request attempts to change `cr_type` |
| 400 | Invalid configuration values |
| 500 | Internal server error |

---

### GET /api/config/default-targets

Get default target services from the Kubernetes ConfigMap. Returns the configured default InferenceService and LLMInferenceService targets.

**Request Body:** None

**Response (200 OK):**

```json
{
  "isvc": {
    "name": "string",
    "namespace": "string"
  },
  "llmisvc": {
    "name": "string",
    "namespace": "string"
  }
}
```

**Response Fields:**

| Field | Type | Description |
|-------|------|-------------|
| `isvc.name` | string | Default InferenceService name |
| `isvc.namespace` | string | Default InferenceService namespace |
| `llmisvc.name` | string | Default LLMInferenceService name |
| `llmisvc.namespace` | string | Default LLMInferenceService namespace |

---

### PATCH /api/config/default-targets

Update default target services in the Kubernetes ConfigMap.

**Request Body:**

```json
{
  "isvc": {
    "name": "string (optional)",
    "namespace": "string (optional)"
  },
  "llmisvc": {
    "name": "string (optional)",
    "namespace": "string (optional)"
  }
}
```

**Response (200 OK):**

```json
{
  "isvc": {
    "name": "string",
    "namespace": "string"
  },
  "llmisvc": {
    "name": "string",
    "namespace": "string"
  }
}
```

**Error Responses:**

| Status | Condition |
|--------|-----------|
| 400 | Invalid target configuration |
| 500 | Internal server error updating ConfigMap |

---

## Metrics

Real-time and historical metrics collection from Prometheus/Thanos for vLLM inference services.

### GET /api/metrics/latest

Get the latest metrics snapshot for a specified target service.

**Query Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `namespace` | string | Yes | Kubernetes namespace |
| `is_name` | string | Yes | InferenceService name |
| `cr_type` | string | No | Custom resource type override |

Omit both `namespace` and `is_name` to receive `400` — there is no default target auto-registration.

**Request Body:** None

**Response (200 OK):**

```json
{
  "status": "ready | collecting",
  "data": {
    "timestamp": "number",
    "tps": "number",
    "rps": "number",
    "ttft_mean": "number | null",
    "ttft_p99": "number | null",
    "latency_mean": "number | null",
    "latency_p99": "number | null",
    "kv_cache": "number",
    "kv_hit_rate": "number",
    "running": "number",
    "waiting": "number",
    "gpu_mem_used": "number",
    "gpu_mem_total": "number",
    "gpu_util": "number",
    "pods": "number",
    "pods_ready": "number"
  },
  "hasMonitoringLabel": "boolean"
}
```

> **Note:** `data` is `null` when `status` is `"collecting"` (metrics not yet available).

**Response Fields:**

| Field | Type | Description |
|-------|------|-------------|
| `status` | string | `ready` if metrics available, `collecting` if still gathering |
| `data` | object \| null | MetricsSnapshot object, or `null` when status is `collecting` |
| `data.timestamp` | number | Unix timestamp of the snapshot |
| `data.tps` | number | Tokens per second |
| `data.rps` | number | Requests per second |
| `data.ttft_mean` | number \| null | Time to first token (mean) in ms |
| `data.ttft_p99` | number \| null | Time to first token (P99) in ms |
| `data.latency_mean` | number \| null | End-to-end latency (mean) in ms |
| `data.latency_p99` | number \| null | End-to-end latency (P99) in ms |
| `data.kv_cache` | number | KV cache utilization percentage |
| `data.kv_hit_rate` | number | KV cache hit rate |
| `data.running` | number | Number of currently running requests |
| `data.waiting` | number | Number of requests waiting in queue |
| `data.gpu_mem_used` | number | GPU memory used in GB |
| `data.gpu_mem_total` | number | Total GPU memory in GB |
| `data.gpu_util` | number | GPU utilization percentage |
| `data.pods` | number | Total pod count |
| `data.pods_ready` | number | Number of ready pods |
| `hasMonitoringLabel` | boolean | Whether target has monitoring labels configured |

**Error Responses:**

| Status | Condition |
|--------|-----------|
| 401 | `namespace` or `is_name` missing |
| 500 | Internal server error fetching metrics |

---

### POST /api/metrics/batch

Get batch metrics for multiple target services in a single request.

**Request Body:**

```json
{
  "targets": [
    {
      "namespace": "string",
      "inferenceService": "string",
      "cr_type": "string (optional)"
    }
  ],
  "time_range": "number (optional)",
  "history_points": "number (optional)"
}
```

**Request Fields:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `targets` | array | Yes | List of target services to query |
| `targets[].namespace` | string | Yes | Kubernetes namespace |
| `targets[].inferenceService` | string | Yes | InferenceService name |
| `targets[].cr_type` | string | No | Custom resource type |
| `time_range` | number | No | Time range in seconds for history |
| `history_points` | number | No | Number of historical data points |

**Response (200 OK):**

```json
{
  "results": {
    "{namespace}/{inferenceService}": {
      "status": "string",
      "data": {
        "tps": "number",
        "rps": "number",
        "kv_cache": "number",
        "running": "number",
        "waiting": "number",
        "gpu_util": "number",
        "pods": "number",
        "pods_ready": "number"
      },
      "hasMonitoringLabel": "boolean",
      "history": [
        {
          "timestamp": "string",
          "tps": "number",
          "rps": "number"
        }
      ]
    }
  }
}
```

**Error Responses:**

| Status | Condition |
|--------|-----------|
| 400 | Invalid target specification |
| 500 | Internal server error |

---

### POST /api/metrics/pods

Get per-pod metrics breakdown for target services. Returns aggregated metrics plus individual pod-level data.

**Request Body:**

```json
{
  "targets": [
    {
      "namespace": "string",
      "inferenceService": "string",
      "cr_type": "string (optional)"
    }
  ],
  "time_range": "number (optional)",
  "history_points": "number (optional)"
}
```

**Response (200 OK):**

```json
{
  "{namespace}/{inferenceService}": {
    "aggregated": {
      "tps": "number",
      "rps": "number",
      "kv_cache": "number",
      "running": "number",
      "waiting": "number",
      "gpu_util": "number",
      "pods": "number",
      "pods_ready": "number"
    },
    "per_pod": [
      {
        "pod_name": "string",
        "tps": "number",
        "rps": "number",
        "kv_cache": "number",
        "running": "number",
        "waiting": "number",
        "gpu_util": "number",
        "gpu_mem_used": "number"
      }
    ],
    "pod_names": ["string"],
    "timestamp": "string"
  }
}
```

**Response Fields:**

| Field | Type | Description |
|-------|------|-------------|
| `aggregated` | object | Aggregated metrics across all pods |
| `per_pod` | array | Per-pod metrics breakdown |
| `per_pod[].pod_name` | string | Pod name |
| `per_pod[].gpu_mem_used` | number | GPU memory used by this pod |
| `pod_names` | array | List of all pod names |
| `timestamp` | string | ISO 8601 timestamp of the snapshot |

**Error Responses:**

| Status | Condition |
|--------|-----------|
| 400 | Invalid target specification |
| 500 | Internal server error |

---

### POST /api/metrics/pods/history

Get per-pod historical metrics via Thanos. Returns time-series data for each pod.

**Request Body:**

```json
{
  "targets": [
    {
      "namespace": "string",
      "inferenceService": "string",
      "cr_type": "string (optional)"
    }
  ],
  "time_range": "number (optional)",
  "history_points": "number (optional)"
}
```

**Response (200 OK):**

```json
{
  "{namespace}/{inferenceService}": {
    "aggregated": {
      "tps": "number",
      "rps": "number"
    },
    "per_pod": [
      {
        "pod_name": "string",
        "history": [
          {
            "timestamp": "string",
            "tps": "number",
            "rps": "number",
            "kv_cache": "number",
            "running": "number",
            "waiting": "number",
            "gpu_util": "number",
            "gpu_mem_used": "number"
          }
        ]
      }
    ],
    "pod_names": ["string"],
    "timestamp": "string"
  }
}
```

**Error Responses:**

| Status | Condition |
|--------|-----------|
| 400 | Invalid target specification |
| 500 | Internal server error querying Thanos |

---

### GET /api/metrics/history

Get metrics history for a target service. Returns a time-series of metric snapshots.

**Query Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `last_n` | integer | No | Number of data points (default: 60, max: 10000) |
| `namespace` | string | No | Kubernetes namespace |
| `is_name` | string | No | InferenceService name |

**Request Body:** None

**Response (200 OK):**

```json
[
  {
    "timestamp": "string",
    "tps": "number",
    "rps": "number",
    "ttft_mean": "number",
    "ttft_p99": "number",
    "latency_mean": "number",
    "latency_p99": "number",
    "kv_cache": "number",
    "kv_hit_rate": "number",
    "running": "number",
    "waiting": "number",
    "gpu_mem_used": "number",
    "gpu_mem_total": "number",
    "gpu_util": "number",
    "pods": "number",
    "pods_ready": "number"
  }
]
```

**Response Fields:**

| Field | Type | Description |
|-------|------|-------------|
| `timestamp` | string | ISO 8601 timestamp |
| `tps` | number | Transactions per second |
| `rps` | number | Requests per second |
| `ttft_mean` | number | Mean time to first token (ms) |
| `ttft_p99` | number | P99 time to first token (ms) |
| `latency_mean` | number | Mean request latency (ms) |
| `latency_p99` | number | P99 request latency (ms) |
| `kv_cache` | number | KV cache utilization percentage |
| `kv_hit_rate` | number | KV cache hit rate percentage |
| `running` | number | Running requests |
| `waiting` | number | Waiting requests |
| `gpu_mem_used` | number | GPU memory used (bytes) |
| `gpu_mem_total` | number | Total GPU memory (bytes) |
| `gpu_util` | number | GPU utilization percentage |
| `pods` | number | Total pod count |
| `pods_ready` | number | Ready pod count |

**Error Responses:**

| Status | Condition |
|--------|-----------|
| 400 | Invalid query parameters |
| 500 | Internal server error |

---

### GET /api/metrics

Prometheus metrics endpoint. Returns metrics in plain text Prometheus exposition format.

**Query Parameters:** None

**Request Body:** None

**Response (200 OK):**

```
# Prometheus exposition format
# TYPE vllm_optimizer_requests_total counter
vllm_optimizer_requests_total 1234
...
```

**Content-Type:** `text/plain; version=0.0.4; charset=utf-8`

---

## Tuner

Bayesian optimization engine for automatic vLLM parameter tuning using Optuna.

### POST /api/tuner/start

Start Bayesian optimization auto-tuning. Launches an asynchronous optimization job that iteratively tests parameter configurations.

**Request Body:**

```json
{
  "objective": "string (optional)",
  "n_trials": "number (optional)",
  "eval_requests": "number (optional)",
  "vllm_endpoint": "string (optional)",
  "max_num_seqs_min": "number (optional)",
  "max_num_seqs_max": "number (optional)",
  "gpu_memory_min": "number (optional)",
  "gpu_memory_max": "number (optional)",
  "max_model_len_min": "number (optional)",
  "max_model_len_max": "number (optional)",
  "max_num_batched_tokens_min": "number (optional)",
  "max_num_batched_tokens_max": "number (optional)",
  "block_size_options": "[number] (optional)",
  "include_swap_space": "boolean (optional)",
  "swap_space_min": "number (optional)",
  "swap_space_max": "number (optional)",
  "eval_concurrency": "number (optional)",
  "eval_rps": "number (optional)",
  "auto_benchmark": "boolean (optional)",
  "evaluation_mode": "single | sweep (optional)",
  "sweep_config": "object (optional)",
  "enable_llm_assistant": "boolean (optional)",
  "accelerator_memory_gib": "number (optional)"
}
```

**Request Fields:**

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `objective` | string | `max_tps` | Optimization objective |
| `n_trials` | number | 20 | Number of optimization trials |
| `eval_requests` | number | 100 | Number of requests per evaluation |
| `vllm_endpoint` | string | current | vLLM endpoint to tune |
| `max_num_seqs_min` | number | 16 | Minimum max_num_seqs |
| `max_num_seqs_max` | number | 256 | Maximum max_num_seqs |
| `gpu_memory_min` | number | 0.5 | Minimum GPU memory utilization |
| `gpu_memory_max` | number | 0.95 | Maximum GPU memory utilization |
| `max_model_len_min` | number | 512 | Minimum max_model_len |
| `max_model_len_max` | number | 8192 | Maximum max_model_len |
| `max_num_batched_tokens_min` | number | 512 | Minimum max_num_batched_tokens |
| `max_num_batched_tokens_max` | number | 8192 | Maximum max_num_batched_tokens |
| `block_size_options` | array | [16, 32] | Block size candidates |
| `include_swap_space` | boolean | false | Whether to tune swap space |
| `swap_space_min` | number | 0 | Minimum swap space (GB) |
| `swap_space_max` | number | 8 | Maximum swap space (GB) |
| `eval_concurrency` | number | 1 | Concurrent evaluation requests |
| `eval_rps` | number | auto | Requests per second for evaluation |
| `auto_benchmark` | boolean | false | Run benchmark after tuning |
| `evaluation_mode` | string | `single` | `single` or `sweep` mode |
| `sweep_config` | object | null | Configuration for sweep mode |
| `enable_llm_assistant` | boolean | true | Use the analyst LLM (`ANALYST_ENDPOINT`) for warm-start suggestions, failure explanations and the report. No-op when unset or equal to the tuning endpoint |
| `accelerator_memory_gib` | number | null | Per-GPU memory in GiB. Enables the KV budget (GPU count × this) for the startup-OOM pre-filter and the gpu_memory_utilization floor |

**Response (200 OK):**

```json
{
  "success": true,
  "message": "string",
  "tuning_id": "string"
}
```

**Error Responses:**

| Status | Condition |
|--------|-----------|
| 400 | Preflight validation failed |
| 409 | Tuner is already running |
| 500 | Internal server error |

---

### GET /api/tuner/model-analysis

Deterministic analysis of a target model. Reads `/mnt/models/config.json`, `openvino_config.json`, `generation_config.json`, `tokenizer_config.json`, `chat_template.jinja`, the `*.py` file list and weight file sizes via pod exec (container `kserve-container` for InferenceService, `main` for LLMInferenceService), plus `/v1/models` for the served name and `max_model_len`.

**Query Parameters:**

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `namespace`, `is_name`, `cr_type` | string | runtime target | Explicit target; all of `namespace`/`is_name` required to override |
| `endpoint` | string | runtime endpoint | Endpoint for `/v1/models` |
| `accelerator_memory_gib` | number | null | Per-GPU memory. Required for GPU targets to compute capacity |
| `utilization` | number | target's `--gpu-memory-utilization`, else 0.9 | Fraction of the memory budget usable for weights + KV |
| `refresh` | boolean | false | Bypass the per-storageUri cache |

**Response (200 OK):** `target`, `available`, `model` (layer mix, `kv_bytes_per_token`, `sliding_kv_bytes_per_token`, `linear_state_bytes_per_seq`, `model_weight_gib`, quantization, MoE, context limits, `warnings`), `runtime` (`gpu_count`, `tensor_parallel_size`, `kv_cache_dtype`, `max_num_batched_tokens`, `current_args`), `memory_budget` (`gib`, `overhead_gib`, `overhead_source`: `table` | `observed` | null, `source`: `accelerator` | `pod_memory` | `unknown_accelerator_memory` | `unknown`), `capacity` (`context_len`, `kv_bytes_per_seq`, `max_concurrent_seqs` | null, `observed_max_seqs`), `observed` (vLLM's allocated pool from the pod's `/metrics` `cache_config_info`: `kv_cache_size_tokens`, `max_concurrency`, `block_size`, `gpu_memory_utilization`, `prefix_caching`, `cache_dtype`, `pod`, `estimate_ratio`), `suggested_search_space`, `advice`, `analyst_available`, `warnings`.

`model` additionally carries `context_limit` (min of config context keys, tokenizer `model_max_length`, YaRN/rope-scaled length; rope types llama3/longrope/su/default are not multiplied), `rope_type`, `mtp_layers`, `auto_map`/`auto_map_remote`/`custom_code_files`, `artifacts_read`, `chat_template_source`, `template_signatures` (`tool_xml`, `tool_json`, `harmony`, `gemma4_tool`, `enable_thinking`, `think`, `reasoning_effort`), `thinking_default` and `generation_defaults`.

`advice` (null when no CR spec is available) = `{recommendations, notes, add_args}`. Each recommendation: `flag`, `kind` (`required` | `workload` | `avoid`), `status` (`present` | `missing` | `mismatch`), `reason`, `value`, `current`, `arg` (paste-ready token or null when a value cannot be derived), `evidence`. It is evaluated against the target's current args (`static + tuning`), so it works for both InferenceService and LLMInferenceService. Rules: tool/reasoning parsers from chat-template signatures, `--chat-template` when none ships, `--kv-cache-dtype=fp8`, `--enable-prefix-caching` (hybrid), MTP `--speculative-config`, multimodal flags (`--language-model-only`, `--limit-mm-per-prompt`, `--mm-encoder-tp-mode=data`, Gemma4 `--attention-backend=TRITON_ATTN`), `--trust-remote-code` for `auto_map`, and `avoid` for `--quantization`/`--dtype` when the checkpoint carries a quantization config. `notes` flag `--max-model-len` above `context_limit`, remote/missing custom code, prefix-caching + MTP conflicts on hybrid models, Mamba block `--max-num-seqs` limits and the sliding-window reservation. `add_args` = space-joined `arg` of required + missing recommendations.

KV per sequence = `kv_bytes_per_token × len + sliding_kv_bytes_per_token × min(len, sliding_window - 1 + max_num_batched_tokens) + linear_state_bytes_per_seq`. On accelerator targets a conservative per-GPU reserve for CUDA graph / activation / vision-encoder overhead (`memory_budget.overhead_gib`: 6/10/16/24 GiB per GPU for TP 1/2/4/8+) is subtracted, so the estimate is a planning figure — measured `observed` values take precedence. When the pod is running and the model is pure full-attention (no sliding/linear layers), the reserve is back-solved from the allocated pool (`overhead = budget × running utilization − weights − pool_tokens × kv_bytes_per_token`, `overhead_source: observed`) and used for both the capacity table and the tuner's OOM prediction. `observed` needs only pod `list` (no exec); measured rows stop at the served `max_model_len` (`observed_max_seqs = kv_cache_size_tokens // context_len`) and the suggested search space prefers measured capacity when present.

`observed` also carries `num_gpu_blocks` and `mamba_cache_mode` when vLLM exposes them. For hybrid (GDN/Mamba) models with a known block count, `observed.mamba_seq_cap` equals `num_gpu_blocks` (vLLM refuses full-CUDA-graph start when `max_num_seqs` exceeds it); `suggested_search_space.max_num_seqs_max` is clamped to it and `advice.notes` warns when the current `--max-num-seqs` is above it.

---

### GET /api/tuner/boot-diagnosis

Explains why a target's vLLM pod is not booting. Reads the newest matching pod's model container status (restarts, waiting/terminated reason, last terminated reason such as `OOMKilled`) and its log — the previous container's log when it has restarted — then matches known vLLM errors deterministically. Works for both CR types (container `kserve-container` / `main`); needs pod `get`/`list` and `pods/log`.

**Query Parameters:** `namespace`, `is_name`, `cr_type` (runtime target when omitted), `tail_lines` (20–2000, default 300).

**Response (200 OK):** `target`, `available` (false when no pod found), `pod` (`pod`, `container`, `phase`, `restarts`, `state`, `last_terminated_reason`, `exit_code`, `logs_source`: `current` | `previous`), `diagnoses` (each: `code`, `title`, `cause`, `fix`, `evidence`, `fix_args`, `suggested_value`), `log_tail` (last 40 lines). Covered causes: Mamba cache blocks exceeded (suggested `--max-num-seqs` from the log), KV cache smaller than one `max_model_len` sequence (estimated max length from the log), no KV memory, GPU memory busy at startup, CUDA OOM, `max_model_len` above the derived limit, `max_num_batched_tokens` < `max_model_len`, quantization mismatch, `--trust-remote-code` required, unsupported architecture, missing chat template, tool-parser flags, TP not dividing attention heads, bf16 unsupported, container OOMKilled, CrashLoopBackOff, image pull errors.

The tuner also runs the same diagnosis on every failed trial: the `tuning_failure_explanation` SSE event gains `diagnoses`, and its `explanation` falls back to the diagnosis summary when the analyst LLM is disabled.

---

### POST /api/tuner/model-analysis/explain

Body: a `GET /api/tuner/model-analysis` response. Returns `{ "markdown": string | null, "analyst_available": bool }`. The analyst LLM (`ANALYST_ENDPOINT`) only narrates the given numbers; `markdown` is null when the analyst is not configured or fails.

---

### GET /api/tuner/status

Get the current status of the tuner, including running state, trial progress, and best results found so far.

**Request Body:** None

**Response (200 OK):**

```json
{
  "running": "boolean",
  "trials_completed": "number",
  "best": {
    "params": "object",
    "tps": "number",
    "p99_latency": "number"
  },
  "status": "string",
  "best_score_history": "[number]",
  "pareto_front_size": "number",
  "last_rollback_trial": "object (optional)"
}
```

**Response Fields:**

| Field | Type | Description |
|-------|------|-------------|
| `running` | boolean | Whether tuner is currently running |
| `trials_completed` | number | Number of completed trials |
| `best.params` | object | Best parameter configuration found |
| `best.tps` | number | TPS achieved with best params |
| `best.p99_latency` | number | P99 latency with best params |
| `status` | string | Current status string |
| `best_score_history` | array | Historical best scores over trials |
| `pareto_front_size` | number | Size of Pareto front (multi-objective) |
| `last_rollback_trial` | object | Last trial that triggered a rollback |

---

### GET /api/tuner/trials

Get tuning trials with pagination support. Returns details of each trial including parameters, scores, and status.

**Query Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `limit` | integer | No | Number of trials to return (default: 20) |
| `offset` | integer | No | Offset for pagination (default: 0) |

**Request Body:** None

**Response (200 OK):**

```json
[
  {
    "id": "number",
    "tps": "number",
    "p99_latency": "number",
    "params": {
      "max_num_seqs": "number",
      "gpu_memory_utilization": "number",
      "max_model_len": "number",
      "max_num_batched_tokens": "number",
      "block_size": "number"
    },
    "score": "number",
    "status": "string",
    "is_pareto_optimal": "boolean",
    "pruned": "boolean",
    "failure": "object | null"
  }
]
```

**Response Headers:**

| Header | Type | Description |
|--------|------|-------------|
| `X-Total-Count` | integer | Total number of trials available |

**Response Fields:**

| Field | Type | Description |
|-------|------|-------------|
| `id` | number | Trial ID |
| `tps` | number | Throughput achieved |
| `p99_latency` | number | P99 latency achieved |
| `params` | object | Parameters used in this trial |
| `score` | number | Computed score for this trial |
| `status` | string | Trial status (completed, running, failed, skipped) |
| `is_pareto_optimal` | boolean | Whether this trial is on the Pareto front |
| `pruned` | boolean | Whether this trial was pruned early |
| `failure` | object \| null | For `failed`/`skipped` trials: `{reason, diagnoses:[{code,title,fix}]}` (max 3 diagnoses). `reason` is the classified failure (`OOM_predicted`, `learned_limit`, `startup_timeout`, ...) |

Failed trials are persisted (`tuner_trials.failure_json`). A boot failure that matches `mamba_blocks_exceeded` / `kv_cache_too_small` / `max_model_len_exceeds_model` yields an upper bound (`max_num_seqs` / `max_model_len`, valid at the failing `gpu_memory_utilization` and below) that is kept for the rest of the session; later trials above it are skipped (`reason: learned_limit`) without restarting the pod.

**Error Responses:**

| Status | Condition |
|--------|-----------|
| 400 | Invalid pagination parameters |
| 500 | Internal server error |

---

### POST /api/tuner/stop

Stop the currently running auto-tuning job. Gracefully terminates the optimization process.

**Request Body:** None

**Response (200 OK):**

```json
{
  "success": true,
  "message": "string"
}
```

**Error Responses:**

| Status | Condition |
|--------|-----------|
| 400 | No tuner is currently running |
| 500 | Internal server error stopping tuner |

---

### GET /api/tuner/stream

Server-Sent Events (SSE) stream of tuner events. Provides real-time updates on trial progress, results, and status changes.

**Request Body:** None

**Response (200 OK):**

```
event: trial_start
data: {"trial_id": 1, "params": {...}}

event: trial_complete
data: {"trial_id": 1, "tps": 150.5, "p99_latency": 45.2}

event: status_update
data: {"running": true, "trials_completed": 5}
```

**Content-Type:** `text/event-stream`

**Connection:** Keep-alive with periodic keepalive messages.

---

### GET /api/tuner/importance

Get parameter importance rankings from Optuna FAnova analysis. Shows which parameters have the most impact on the optimization objective.

**Request Body:** None

**Response (200 OK):**

```json
{
  "max_num_seqs": 0.35,
  "gpu_memory_utilization": 0.28,
  "max_model_len": 0.18,
  "max_num_batched_tokens": 0.12,
  "block_size": 0.07
}
```

**Response Fields:**

| Field | Type | Description |
|-------|------|-------------|
| `{param_name}` | number | Importance value (0.0 to 1.0) |

Higher values indicate greater influence on the optimization objective. Values sum to approximately 1.0.

**Error Responses:**

| Status | Condition |
|--------|-----------|
| 400 | Insufficient trial data for analysis |
| 500 | Internal server error |

---

### GET /api/tuner/all

Get combined tuner state in a single request. Returns status, trials, and parameter importance together.

**Request Body:** None

**Response (200 OK):**

```json
{
  "status": {
    "running": "boolean",
    "trials_completed": "number",
    "best": "object",
    "status": "string"
  },
  "trials": [
    {
      "id": "number",
      "tps": "number",
      "p99_latency": "number",
      "params": "object",
      "score": "number",
      "status": "string",
      "is_pareto_optimal": "boolean",
      "pruned": "boolean"
    }
  ],
  "importance": {
    "param_name": "number"
  }
}
```

---

### POST /api/tuner/apply-best

Apply the best parameters found during tuning to the vLLM deployment. Updates the Kubernetes deployment with optimized configuration.

**Request Body:** None

**Response (200 OK):**

```json
{
  "success": true,
  "message": "string",
  "applied_parameters": {
    "max_num_seqs": "number",
    "gpu_memory_utilization": "number",
    "max_model_len": "number",
    "max_num_batched_tokens": "number",
    "block_size": "number"
  },
  "deployment_name": "string"
}
```

**Error Responses:**

| Status | Condition |
|--------|-----------|
| 400 | No completed trials available |
| 409 | Tuner is still running |
| 500 | Internal server error applying parameters |

---

### GET /api/tuner/sessions

List saved tuning sessions with pagination. Each session represents a complete tuning run.

**Query Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `limit` | integer | No | Number of sessions (default: 20) |
| `offset` | integer | No | Offset for pagination (default: 0) |

**Request Body:** None

**Response (200 OK):**

```json
[
  {
    "id": "string",
    "timestamp": "string",
    "objective": "string",
    "n_trials": "number",
    "best_tps": "number",
    "best_p99": "number",
    "best_score": "number"
  }
]
```

**Response Headers:**

| Header | Type | Description |
|--------|------|-------------|
| `X-Total-Count` | integer | Total number of sessions |

**Error Responses:**

| Status | Condition |
|--------|-----------|
| 400 | Invalid pagination parameters |
| 500 | Internal server error |

---

### GET /api/tuner/sessions/{session_id}

Get detailed information for a specific tuning session, including all trials and parameter importance data.

**Path Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `session_id` | string | Yes | Unique session identifier |

**Request Body:** None

**Response (200 OK):**

```json
{
  "id": "string",
  "timestamp": "string",
  "objective": "string",
  "n_trials": "number",
  "best_tps": "number",
  "best_p99": "number",
  "best_score": "number",
  "trials_json": "[object]",
  "importance_json": "object"
}
```

**Error Responses:**

| Status | Condition |
|--------|-----------|
| 404 | Session not found |
| 500 | Internal server error |

---

### DELETE /api/tuner/sessions/{session_id}

Delete a saved tuning session and all associated data.

**Path Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `session_id` | string | Yes | Unique session identifier |

**Request Body:** None

**Response (200 OK):**

```json
{
  "success": true,
  "id": "string"
}
```

**Error Responses:**

| Status | Condition |
|--------|-----------|
| 404 | Session not found |
| 500 | Internal server error |

---

## Load Test

Load testing engine for evaluating vLLM performance under various concurrency and request rate conditions.

### POST /api/load_test/start

Start a new load test against the configured vLLM endpoint.

**Request Body (LoadTestConfig):**

```json
{
  "endpoint": "string",
  "model": "string",
  "prompt_template": "string (optional)",
  "total_requests": "integer (optional)",
  "concurrency": "integer (optional)",
  "duration": "integer (optional)",
  "rps": "integer (optional)",
  "max_tokens": "integer (optional)",
  "temperature": "number (optional)",
  "stream": "boolean (optional)",
  "prompt_mode": "string (optional)",
  "endpoint_type": "string (optional)",
  "synthetic_config": "object (optional)"
}
```

**Request Fields:**

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `endpoint` | string | No | `""` | vLLM endpoint URL (empty = use VLLM_ENDPOINT env) |
| `model` | string | No | `"auto"` | Model name |
| `prompt_template` | string | No | `"Hello, how are you?"` | Prompt for generation |
| `total_requests` | integer | No | `100` | Total number of requests |
| `concurrency` | integer | No | `10` | Number of concurrent requests |
| `duration` | integer | No | `30` | Test duration in seconds (max 1 hour) |
| `rps` | integer | No | `0` | Requests per second (0 = unlimited) |
| `max_tokens` | integer | No | `256` | Max tokens to generate |
| `temperature` | number | No | `0.7` | Temperature for generation |
| `stream` | boolean | No | `true` | Enable streaming mode |
| `prompt_mode` | string | No | `"static"` | Prompt mode: `"static"` or `"synthetic"` |
| `endpoint_type` | string | No | `"completions"` | API endpoint type: `"completions"` or `"chat"` |
| `synthetic_config` | object | No | `null` | Synthetic prompt config (used when `prompt_mode="synthetic"`) |
| `api_key` | string | No | `null` | Bearer token for gateway-fronted endpoints (MaaS). Sent as `Authorization: Bearer …` on `/v1/models` and inference calls; excluded from every response and from persisted history/benchmarks |

**Response (200 OK):**

```json
{
  "test_id": "string",
  "status": "string",
  "message": "string",
  "config": "object"
}
```

**Error Responses:**

| Status | Condition |
|--------|-----------|
| 400 | Preflight validation failed |
| 409 | Load test is already running |
| 500 | Internal server error |

---

### POST /api/load_test/stop

Stop a running load test.

**Query Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `test_id` | string | No | Specific test to stop (stops current if omitted) |

**Request Body:** None

**Response (200 OK):**

```json
{
  "status": "string",
  "test_id": "string",
  "message": "string"
}
```

**Error Responses:**

| Status | Condition |
|--------|-----------|
| 400 | No load test is running |
| 500 | Internal server error |

---

### GET /api/load_test/status

Get the status of a load test. Returns current state, configuration, and partial results.

**Query Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `test_id` | string | No | Specific test ID (returns current if omitted) |

**Request Body:** None

**Response (200 OK):**

```json
{
  "test_id": "string (optional)",
  "running": "boolean",
  "config": "object (optional)",
  "current_result": "object (optional)",
  "elapsed": "number",
  "sweep_result": "object (optional)",
  "is_sweeping": "boolean"
}
```

**Response Fields:**

| Field | Type | Description |
|-------|------|-------------|
| `test_id` | string | Test identifier |
| `running` | boolean | Whether test is currently running |
| `config` | object | Test configuration |
| `current_result` | object | Partial results if test is running |
| `elapsed` | number | Elapsed time in seconds |
| `sweep_result` | object | Sweep results if running a sweep |
| `is_sweeping` | boolean | Whether a parameter sweep is in progress |

---

### POST /api/load_test/sweep

Start a parameter sweep that tests multiple concurrency levels sequentially.

**Request Body (SweepConfig):**

```json
{
  "endpoint": "string",
  "model": "string",
  "rps_start": "integer (optional)",
  "rps_end": "integer (optional)",
  "rps_step": "integer (optional)",
  "requests_per_step": "integer (optional)",
  "concurrency": "integer (optional)",
  "max_tokens": "integer (optional)",
  "stream": "boolean (optional)",
  "prompt": "string (optional)",
  "saturation_error_rate": "number (optional)",
  "saturation_latency_factor": "number (optional)",
  "min_stable_steps": "integer (optional)"
}
```

**Request Fields:**

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `endpoint` | string | No | `""` | vLLM endpoint URL |
| `model` | string | No | `"auto"` | Model name |
| `rps_start` | integer | No | `1` | Starting RPS |
| `rps_end` | integer | No | `50` | Ending RPS |
| `rps_step` | integer | No | `5` | RPS increment per step |
| `requests_per_step` | integer | No | `20` | Requests per step |
| `concurrency` | integer | No | `10` | Concurrent requests |
| `max_tokens` | integer | No | `128` | Max tokens per request |
| `stream` | boolean | No | `true` | Enable streaming |
| `prompt` | string | No | `"Explain quantum computing in simple terms"` | Request prompt |
| `saturation_error_rate` | number | No | `0.1` | Error rate threshold for saturation detection |
| `saturation_latency_factor` | number | No | `3.0` | P99 latency multiple vs step-1 for saturation detection |
| `min_stable_steps` | integer | No | `1` | Consecutive saturated steps required to stop sweep |
| `api_key` | string | No | `null` | Bearer token (same handling as load test `api_key`) |

The final `sweep_completed` result includes `knee_rps`: the target RPS whose step maximizes token throughput / mean latency (Kleinrock power) among steps within `saturation_error_rate`.

**Response (200 OK):**

```json
{
  "status": "string",
  "config": "object"
}
```

**Error Responses:**

| Status | Condition |
|--------|-----------|
| 409 | Load test or sweep is already running |
| 400 | Invalid sweep configuration |
| 500 | Internal server error |

---

### GET /api/load_test/stream

Server-Sent Events (SSE) stream of load test results. Provides real-time updates as the test progresses.

**Query Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `test_id` | string | No | Specific test to stream (current if omitted) |

**Request Body:** None

**Response (200 OK):**

```
data: {"type": "progress", "data": {...}}

data: {"type": "completed", "data": {...}}
```

**Content-Type:** `text/event-stream`

Each message is a JSON object `{"type": <string>, "data": <object|null>}`. Event types:
`progress`, `completed`, `stopped`, `error` (sweep runs also emit `sweep_step`, `sweep_completed`).
While idle, the server sends `: keepalive` comments every 15 seconds.

**Late subscribers:** if the last run has already finished, the stream immediately replays the
final terminal event (`completed` / `stopped` / `error` / `sweep_completed`) and closes — a
client reconnecting after completion never hangs waiting on keepalives. Starting a new run
(`POST /start`, `POST /sweep`) clears the recorded terminal event.

---

### GET /api/load_test/history

Get load test history with pagination.

**Query Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `limit` | integer | No | Number of results (default: 10) |
| `offset` | integer | No | Offset for pagination (default: 0) |

**Request Body:** None

**Response (200 OK):**

```json
[
  {
    "test_id": "string",
    "config": "object",
    "result": "object",
    "timestamp": "string"
  }
]
```

**Response Headers:**

| Header | Type | Description |
|--------|------|-------------|
| `X-Total-Count` | integer | Total number of tests in history |

**Error Responses:**

| Status | Condition |
|--------|-----------|
| 400 | Invalid pagination parameters |
| 500 | Internal server error |

---

### POST /api/load_test/sweep/save

Save a sweep result to persistent storage.

**Request Body:**

```json
{
  "config": "object",
  "results": "[object]",
  "timestamp": "string (optional)"
}
```

**Response (200 OK):**

```json
{
  "id": "string"
}
```

**Error Responses:**

| Status | Condition |
|--------|-----------|
| 500 | Internal server error saving result |

---

### GET /api/load_test/sweep/history

List saved sweep results with pagination.

**Query Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `limit` | integer | No | Number of results (default: 20) |
| `offset` | integer | No | Offset for pagination (default: 0) |

**Request Body:** None

**Response (200 OK):**

```json
[
  {
    "id": "string",
    "config": "object",
    "results": "[object]",
    "timestamp": "string"
  }
]
```

**Response Headers:**

| Header | Type | Description |
|--------|------|-------------|
| `X-Total-Count` | integer | Total number of saved sweeps |

**Error Responses:**

| Status | Condition |
|--------|-----------|
| 400 | Invalid pagination parameters |
| 500 | Internal server error |

---

### GET /api/load_test/sweep/history/{sweep_id}

Get a single saved sweep result by ID.

**Path Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `sweep_id` | string | Yes | Unique sweep result identifier |

**Request Body:** None

**Response (200 OK):**

```json
{
  "id": "string",
  "config": "object",
  "results": "[object]",
  "timestamp": "string"
}
```

**Error Responses:**

| Status | Condition |
|--------|-----------|
| 404 | Sweep result not found |
| 500 | Internal server error |

---

### DELETE /api/load_test/sweep/history/{sweep_id}

Delete a saved sweep result.

**Path Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `sweep_id` | string | Yes | Unique sweep result identifier |

**Request Body:** None

**Response (200 OK):**

```json
{
  "status": "string",
  "sweep_id": "string"
}
```

**Error Responses:**

| Status | Condition |
|--------|-----------|
| 404 | Sweep result not found |
| 500 | Internal server error |

---

## vLLM Config

Direct management of vLLM InferenceService configuration in Kubernetes. Reads and writes to the actual K8s resources.

### GET /api/vllm-config

Get the current vLLM configuration from the Kubernetes InferenceService resource.

**Query Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `namespace` | string | No | Kubernetes namespace override |
| `is_name` | string | No | InferenceService name override |
| `cr_type` | string | No | Custom resource type override |

**Request Body:** None

**Response (200 OK):**

```json
{
  "success": true,
  "data": {
    "max_num_seqs": "string",
    "gpu_memory_utilization": "string",
    "max_model_len": "string",
    "max_num_batched_tokens": "string",
    "block_size": "string",
    "swap_space": "string"
  },
  "storageUri": "string",
  "resources": {
    "requests": "object",
    "limits": "object"
  },
  "extraArgs": "[object]",
  "modelName": "string",
  "resolvedModelName": "string"
}
```

**Response Fields:**

| Field | Type | Description |
|-------|------|-------------|
| `success` | boolean | Whether the read was successful |
| `data` | object | Current vLLM configuration parameters |
| `data.max_num_seqs` | string | Maximum number of sequences |
| `data.gpu_memory_utilization` | string | GPU memory utilization fraction |
| `data.max_model_len` | string | Maximum model context length |
| `data.max_num_batched_tokens` | string | Maximum batched tokens |
| `data.block_size` | string | Paged attention block size |
| `data.swap_space` | string | CPU swap space in GB |
| `storageUri` | string | Model storage URI |
| `resources` | object | Kubernetes resource requests and limits |
| `extraArgs` | array | Additional vLLM arguments |
| `modelName` | string | Configured model name |
| `resolvedModelName` | string | Resolved model name |

**Error Responses:**

| Status | Condition |
|--------|-----------|
| 503 | Kubernetes API unavailable |
| 500 | Internal server error |

---

### PATCH /api/vllm-config

Update vLLM configuration in the Kubernetes InferenceService resource. Triggers a rolling update of the deployment.

**Request Body:**

```json
{
  "data": {
    "max_num_seqs": "string (optional)",
    "gpu_memory_utilization": "string (optional)",
    "max_model_len": "string (optional)",
    "max_num_batched_tokens": "string (optional)",
    "block_size": "string (optional)",
    "swap_space": "string (optional)",
    "enable_chunked_prefill": "string (optional)",
    "enable_enforce_eager": "string (optional)"
  },
  "storageUri": "string (optional)",
  "resources": {
    "requests": "object (optional)",
    "limits": "object (optional)"
  }
}
```

**Allowed Config Keys:**

| Key | Description |
|-----|-------------|
| `max_num_seqs` | Maximum number of sequences per batch |
| `gpu_memory_utilization` | Fraction of GPU memory to use (0.0-1.0) |
| `max_model_len` | Maximum model context length |
| `max_num_batched_tokens` | Maximum tokens per batch |
| `block_size` | Paged attention block size |
| `swap_space` | CPU swap space in GB |
| `enable_chunked_prefill` | Enable chunked prefill optimization |
| `enable_enforce_eager` | Enable eager mode enforcement |

**Response (200 OK):**

```json
{
  "success": true,
  "updated_keys": ["string"],
  "updated_storageUri": "string (optional)"
}
```

**Error Responses:**

| Status | Condition |
|--------|-----------|
| 409 | Tuner is running (config changes blocked during tuning) |
| 422 | Invalid configuration keys provided |
| 503 | Kubernetes API unavailable |
| 500 | Internal server error |

---

## Benchmark

Storage and retrieval of benchmark results for performance comparison and SLA evaluation.

### GET /api/benchmark/list

List saved benchmark results with pagination.

**Query Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `limit` | integer | No | Number of results (default: 20, max: 1000) |
| `offset` | integer | No | Offset for pagination (default: 0) |

**Request Body:** None

**Response (200 OK):**

```json
[
  {
    "id": "number",
    "name": "string",
    "timestamp": "string",
    "config": "object",
    "result": "object",
    "metadata": "object"
  }
]
```

**Response Headers:**

| Header | Type | Description |
|--------|------|-------------|
| `X-Total-Count` | integer | Total number of benchmarks |

**Error Responses:**

| Status | Condition |
|--------|-----------|
| 400 | Invalid pagination parameters |
| 500 | Internal server error |

---

### POST /api/benchmark/save

Save a benchmark result to persistent storage.

**Request Body (Benchmark):**

```json
{
  "name": "string",
  "timestamp": "string (optional)",
  "config": "object",
  "result": "object",
  "metadata": "object"
}
```

**Request Fields:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | Yes | Benchmark name/identifier |
| `timestamp` | string | No | ISO 8601 timestamp (auto-generated if omitted) |
| `config` | object | Yes | Test configuration used |
| `result` | object | Yes | Benchmark results data |
| `metadata` | object | No | Additional metadata |

**Response (200 OK):**

```json
{
  "id": "number",
  "name": "string",
  "timestamp": "string",
  "config": "object",
  "result": "object",
  "metadata": "object"
}
```

**Error Responses:**

| Status | Condition |
|--------|-----------|
| 400 | Invalid benchmark data |
| 500 | Internal server error |

---

### GET /api/benchmark/by-model

Get all benchmarks grouped by model name. Includes computed GPU efficiency metrics.

**Request Body:** None

**Response (200 OK):**

```json
{
  "models": {
    "model_name": [
      {
        "id": "number",
        "name": "string",
        "timestamp": "string",
        "config": "object",
        "result": "object",
        "metadata": "object",
        "gpu_efficiency": "number"
      }
    ]
  }
}
```

**Response Fields:**

| Field | Type | Description |
|-------|------|-------------|
| `models` | object | Map of model name to benchmark array |
| `models.{name}[]` | array | Benchmarks for this model |
| `models.{name}[].gpu_efficiency` | number | Computed GPU efficiency score |

**Error Responses:**

| Status | Condition |
|--------|-----------|
| 500 | Internal server error |

---

### POST /api/benchmark/import

Import benchmark results from a GuideLLM JSON export file.

**Request Body:** `multipart/form-data` file upload

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `file` | file | Yes | GuideLLM JSON export file (max 50MB) |

**Response (200 OK):**

```json
{
  "imported_count": "number",
  "benchmark_ids": ["number"]
}
```

**Error Responses:**

| Status | Condition |
|--------|-----------|
| 400 | Invalid JSON format |
| 413 | File too large (exceeds 50MB limit) |
| 422 | Parse error in JSON data |
| 500 | Internal server error |

---

### GET /api/benchmark/{benchmark_id}

Get a single benchmark result by ID.

**Path Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `benchmark_id` | integer | Yes | Benchmark identifier |

**Request Body:** None

**Response (200 OK):**

```json
{
  "id": "number",
  "name": "string",
  "timestamp": "string",
  "config": "object",
  "result": "object",
  "metadata": "object"
}
```

**Error Responses:**

| Status | Condition |
|--------|-----------|
| 404 | Benchmark not found |
| 500 | Internal server error |

---

### DELETE /api/benchmark/{benchmark_id}

Delete a benchmark result by ID.

**Path Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `benchmark_id` | integer | Yes | Benchmark identifier |

**Request Body:** None

**Response (200 OK):**

```json
{
  "status": "string",
  "benchmark_id": "number",
  "message": "string"
}
```

**Error Responses:**

| Status | Condition |
|--------|-----------|
| 404 | Benchmark not found |
| 500 | Internal server error |

---

### PATCH /api/benchmark/{benchmark_id}/metadata

Update the metadata of an existing benchmark.

**Path Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `benchmark_id` | integer | Yes | Benchmark identifier |

**Request Body (BenchmarkMetadata):**

```json
{
  "name": "string (optional)",
  "metadata": "object (optional)"
}
```

**Response (200 OK):**

```json
{
  "id": "number",
  "name": "string",
  "timestamp": "string",
  "config": "object",
  "result": "object",
  "metadata": "object"
}
```

**Error Responses:**

| Status | Condition |
|--------|-----------|
| 404 | Benchmark not found |
| 500 | Internal server error |

---

## SLA

Service Level Agreement management. Define SLA profiles and evaluate benchmark results against them.

### GET /api/sla/profiles

List all SLA profiles with pagination.

**Query Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `limit` | integer | No | Number of profiles (default: 50) |
| `offset` | integer | No | Offset for pagination (default: 0) |

**Request Body:** None

**Response (200 OK):**

```json
[
  {
    "id": "string",
    "name": "string",
    "thresholds": {
      "availability_min": "number | null",
      "p95_latency_max_ms": "number | null",
      "error_rate_max_pct": "number | null",
      "mean_ttft_max_ms": "number | null",
      "p95_ttft_max_ms": "number | null",
      "mean_e2e_latency_max_ms": "number | null",
      "mean_tpot_max_ms": "number | null",
      "p95_tpot_max_ms": "number | null",
      "mean_queue_time_max_ms": "number | null",
      "p95_queue_time_max_ms": "number | null"
    },
    "created_at": "string"
  }
]
```

**Response Headers:**

| Header | Type | Description |
|--------|------|-------------|
| `X-Total-Count` | integer | Total number of SLA profiles |

---

### POST /api/sla/profiles

Create a new SLA profile.

**Request Body (SlaProfile):**

```json
{
  "name": "string",
  "thresholds": {
    "availability_min": "number | null",
    "p95_latency_max_ms": "number | null",
    "error_rate_max_pct": "number | null",
    "mean_ttft_max_ms": "number | null",
    "p95_ttft_max_ms": "number | null",
    "mean_e2e_latency_max_ms": "number | null",
    "mean_tpot_max_ms": "number | null",
    "p95_tpot_max_ms": "number | null",
    "mean_queue_time_max_ms": "number | null",
    "p95_queue_time_max_ms": "number | null"
  }
}
```

> [!NOTE]
> At least one threshold field must be non-null.

**Response (201 Created):**

```json
{
  "id": "string",
  "name": "string",
  "thresholds": "object",
  "created_at": "string"
}
```

**Error Responses:**

| Status | Condition |
|--------|-----------|
| 400 | Invalid SLA profile data |
| 409 | Profile with same name already exists |
| 500 | Internal server error |

---

### GET /api/sla/profiles/{profile_id}

Get a specific SLA profile by ID.

**Path Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `profile_id` | string | Yes | SLA profile identifier |

**Request Body:** None

**Response (200 OK):**

```json
{
  "id": "string",
  "name": "string",
  "thresholds": "object",
  "created_at": "string"
}
```

**Error Responses:**

| Status | Condition |
|--------|-----------|
| 404 | SLA profile not found |
| 500 | Internal server error |

---

### PUT /api/sla/profiles/{profile_id}

Update an existing SLA profile. Full replacement of the profile data.

**Path Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `profile_id` | string | Yes | SLA profile identifier |

**Request Body (SlaProfile):**

```json
{
  "name": "string",
  "thresholds": {
    "availability_min": "number | null",
    "p95_latency_max_ms": "number | null",
    "error_rate_max_pct": "number | null",
    "mean_ttft_max_ms": "number | null",
    "p95_ttft_max_ms": "number | null",
    "mean_e2e_latency_max_ms": "number | null",
    "mean_tpot_max_ms": "number | null",
    "p95_tpot_max_ms": "number | null",
    "mean_queue_time_max_ms": "number | null",
    "p95_queue_time_max_ms": "number | null"
  }
}
```

> [!NOTE]
> At least one threshold field must be non-null.

**Response (200 OK):**

```json
{
  "id": "string",
  "name": "string",
  "thresholds": "object",
  "created_at": "string"
}
```

**Error Responses:**

| Status | Condition |
|--------|-----------|
| 404 | SLA profile not found |
| 400 | Invalid SLA profile data |
| 500 | Internal server error |

---

### DELETE /api/sla/profiles/{profile_id}

Delete an SLA profile.

**Path Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `profile_id` | string | Yes | SLA profile identifier |

**Request Body:** None

**Response (200 OK):**

```json
{
  "deleted": true
}
```

**Error Responses:**

| Status | Condition |
|--------|-----------|
| 404 | SLA profile not found |
| 500 | Internal server error |

---

### POST /api/sla/evaluate

Evaluate one or more benchmark results against an SLA profile. Returns pass/fail verdicts for each metric.

**Request Body:**

```json
{
  "profile_id": "string",
  "benchmark_ids": ["number"]
}
```

**Request Fields:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `profile_id` | string | Yes | SLA profile to evaluate against |
| `benchmark_ids` | array | Yes | List of benchmark IDs to evaluate |

**Response (200 OK):**

```json
{
  "profile": "object",
  "results": [
    {
      "benchmark_id": "number",
      "benchmark_name": "string",
      "timestamp": "string",
      "verdicts": [
        {
          "metric": "string",
          "value": "number",
          "threshold": "number",
          "pass": "boolean",
          "status": "string"
        }
      ],
      "overall_pass": "boolean"
    }
  ],
  "warnings": ["string"]
}
```

**Response Fields:**

| Field | Type | Description |
|-------|------|-------------|
| `profile` | object | The SLA profile used for evaluation |
| `results` | array | Evaluation results per benchmark |
| `results[].benchmark_id` | number | Benchmark identifier |
| `results[].benchmark_name` | string | Benchmark name |
| `results[].verdicts` | array | Per-metric verdicts |
| `results[].verdicts[].metric` | string | Metric name |
| `results[].verdicts[].value` | number | Actual metric value |
| `results[].verdicts[].threshold` | number | SLA threshold |
| `results[].verdicts[].pass` | boolean | Whether this metric passed |
| `results[].verdicts[].status` | string | Status string (pass/fail/warning) |
| `results[].overall_pass` | boolean | Whether all metrics passed |
| `warnings` | array | Warning messages |

**Error Responses:**

| Status | Condition |
|--------|-----------|
| 404 | SLA profile or benchmark not found |
| 400 | Invalid evaluation request |
| 500 | Internal server error |

---

## Alerts

Alerting and violation detection for SLA monitoring.

### GET /api/alerts/sla-violations

Get current SLA violations across all active SLA profiles.

**Request Body:** None

**Response (200 OK):**

```json
{
  "violations": [
    {
      "profile_id": "string",
      "profile_name": "string",
      "violated_metrics": [
        {
          "metric": "string",
          "threshold": "number",
          "actual": "number",
          "severity": "string"
        }
      ]
    }
  ],
  "has_violations": "boolean",
  "checked_at": "string"
}
```

**Response Fields:**

| Field | Type | Description |
|-------|------|-------------|
| `violations` | array | List of profiles with violations |
| `violations[].profile_id` | string | SLA profile identifier |
| `violations[].profile_name` | string | SLA profile name |
| `violations[].violated_metrics` | array | Metrics that violated thresholds |
| `violations[].violated_metrics[].metric` | string | Metric name |
| `violations[].violated_metrics[].threshold` | number | SLA threshold value |
| `violations[].violated_metrics[].actual` | number | Actual measured value |
| `violations[].violated_metrics[].severity` | string | Severity level (low/medium/high/critical) |
| `has_violations` | boolean | Whether any violations exist |
| `checked_at` | string | ISO 8601 timestamp of last check |

---

## Status

System status and lifecycle management endpoints.

### GET /api/status/interrupted

Get and clear interrupted runs from the previous application lifecycle. Useful for recovering state after a restart.

**Request Body:** None

**Response (200 OK):**

```json
{
  "interrupted_runs": [
    {
      "type": "string",
      "id": "string",
      "config": "object",
      "interrupted_at": "string"
    }
  ]
}
```

**Response Fields:**

| Field | Type | Description |
|-------|------|-------------|
| `interrupted_runs` | array | List of runs that were interrupted |
| `interrupted_runs[].type` | string | Run type (tuner, load_test, sweep) |
| `interrupted_runs[].id` | string | Run identifier |
| `interrupted_runs[].config` | object | Run configuration |
| `interrupted_runs[].interrupted_at` | string | Timestamp of interruption |

---

## System

Health, root, and auto-generated documentation endpoints.

### GET /health

Health check endpoint with dependency validation. Returns the health status of the application and its external dependencies.

**Query Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `deep` | integer | No | Set to `1` for full connectivity checks |

**Request Body:** None

**Response (200 OK):**

```json
{
  "status": "healthy | unhealthy",
  "cr_type": "string",
  "dependencies": {
    "prometheus": {
      "healthy": "boolean",
      "message": "string"
    },
    "kubernetes": {
      "healthy": "boolean",
      "message": "string"
    }
  },
  "timestamp": "string"
}
```

**Response Fields:**

| Field | Type | Description |
|-------|------|-------------|
| `status` | string | Overall health status |
| `cr_type` | string | Current custom resource type |
| `dependencies.prometheus` | object | Prometheus connectivity status |
| `dependencies.prometheus.healthy` | boolean | Prometheus reachable |
| `dependencies.prometheus.message` | string | Status message |
| `dependencies.kubernetes` | object | Kubernetes connectivity status |
| `dependencies.kubernetes.healthy` | boolean | Kubernetes API reachable |
| `dependencies.kubernetes.message` | string | Status message |
| `timestamp` | string | ISO 8601 timestamp |

**Error Responses:**

| Status | Condition |
|--------|-----------|
| 503 | One or more dependencies are unhealthy |

---

### GET /

Root endpoint. Returns basic service information and available API endpoints.

**Request Body:** None

**Response (200 OK):**

```json
{
  "message": "string",
  "version": "string",
  "docs": "string",
  "health": "string",
  "endpoints": ["string"]
}
```

**Response Fields:**

| Field | Type | Description |
|-------|------|-------------|
| `message` | string | Welcome message |
| `version` | string | API version |
| `docs` | string | URL to API documentation |
| `health` | string | URL to health endpoint |
| `endpoints` | array | List of available API endpoint paths |

---

### GET /docs

OpenAPI Swagger UI. Auto-generated interactive API documentation.

**Response:** HTML page with Swagger UI interface.

---

### GET /redoc

ReDoc documentation. Auto-generated alternative API documentation.

**Response:** HTML page with ReDoc interface.

---

### GET /openapi.json

OpenAPI specification in JSON format. Machine-readable API definition.

**Response (200 OK):**

```json
{
  "openapi": "3.x.x",
  "info": {
    "title": "vLLM Optimizer API",
    "version": "string"
  },
  "paths": { "...": "..." }
}
```

---

## Appendix

### Authentication

Currently the API does not enforce authentication. When deployed in production, it is recommended to place the service behind an authentication proxy or enable FastAPI middleware for token validation.

### CORS

Cross-Origin Resource Sharing is configured to allow requests from the frontend application. The CORS middleware is applied to all `/api/**` routes.

### Pagination Pattern

Endpoints that return lists support pagination via `limit` and `offset` query parameters. The total count is returned in the `X-Total-Count` response header.

### SSE Connection Handling

Server-Sent Events endpoints maintain persistent connections with periodic keepalive messages. Clients should implement reconnection logic with exponential backoff. Terminal events are recorded per engine and replayed to late subscribers (see `/api/load_test/stream`), so reconnecting after a run completes still yields the final result.

### Error Handling

All endpoints return structured error responses. Validation errors return HTTP 422 with a `detail` field containing a list of validation issues. Application-level errors return appropriate status codes with descriptive messages.
