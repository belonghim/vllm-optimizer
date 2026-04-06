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
| 22 | `POST` | `/api/load_test/start` | Load Test | Start load test |
| 23 | `POST` | `/api/load_test/stop` | Load Test | Stop load test |
| 24 | `GET` | `/api/load_test/status` | Load Test | Get load test status |
| 25 | `POST` | `/api/load_test/sweep` | Load Test | Start parameter sweep |
| 26 | `GET` | `/api/load_test/stream` | Load Test | SSE result stream |
| 27 | `GET` | `/api/load_test/history` | Load Test | Load test history |
| 28 | `POST` | `/api/load_test/sweep/save` | Load Test | Save sweep result |
| 29 | `GET` | `/api/load_test/sweep/history` | Load Test | List saved sweeps |
| 30 | `GET` | `/api/load_test/sweep/history/{sweep_id}` | Load Test | Get single sweep |
| 31 | `DELETE` | `/api/load_test/sweep/history/{sweep_id}` | Load Test | Delete sweep |
| 32 | `GET` | `/api/vllm-config` | vLLM Config | Get vLLM config from K8s |
| 33 | `PATCH` | `/api/vllm-config` | vLLM Config | Update vLLM config in K8s |
| 34 | `GET` | `/api/benchmark/list` | Benchmark | List saved benchmarks |
| 35 | `POST` | `/api/benchmark/save` | Benchmark | Save benchmark result |
| 36 | `GET` | `/api/benchmark/by-model` | Benchmark | Benchmarks by model |
| 37 | `POST` | `/api/benchmark/import` | Benchmark | Import from GuideLLM |
| 38 | `GET` | `/api/benchmark/{benchmark_id}` | Benchmark | Get single benchmark |
| 39 | `DELETE` | `/api/benchmark/{benchmark_id}` | Benchmark | Delete benchmark |
| 40 | `PATCH` | `/api/benchmark/{benchmark_id}/metadata` | Benchmark | Update benchmark metadata |
| 41 | `GET` | `/api/sla/profiles` | SLA | List SLA profiles |
| 42 | `POST` | `/api/sla/profiles` | SLA | Create SLA profile |
| 43 | `GET` | `/api/sla/profiles/{profile_id}` | SLA | Get SLA profile |
| 44 | `PUT` | `/api/sla/profiles/{profile_id}` | SLA | Update SLA profile |
| 45 | `DELETE` | `/api/sla/profiles/{profile_id}` | SLA | Delete SLA profile |
| 46 | `POST` | `/api/sla/evaluate` | SLA | Evaluate against SLA |
| 47 | `GET` | `/api/alerts/sla-violations` | Alerts | Get SLA violations |
| 48 | `GET` | `/api/status/interrupted` | Status | Get interrupted runs |
| 49 | `GET` | `/health` | System | Health check |
| 50 | `GET` | `/` | System | Root endpoint |
| 51 | `GET` | `/docs` | System | Swagger UI |
| 52 | `GET` | `/redoc` | System | ReDoc documentation |
| 53 | `GET` | `/openapi.json` | System | OpenAPI spec JSON |

---

## Common Types

### Rate Limit Levels

| Level | Requests | Window | Applies To |
|-------|----------|--------|------------|
| Exempt | Unlimited | N/A | Health, SSE streams, Prometheus |
| Low | 3-5 | per minute | Tuner start, vLLM config writes |
| Medium | 30 | per minute | vLLM config reads |
| Standard | 60 | per minute | Config, Benchmark, SLA, Alerts |
| High | 120 | per minute | Metrics endpoints |

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

**Rate Limit:** 60 requests/minute

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

**Rate Limit:** 60 requests/minute

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

**Rate Limit:** 60 requests/minute

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

**Rate Limit:** 60 requests/minute

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

Get the latest metrics snapshot for the default target or a specified target service.

**Rate Limit:** 120 requests/minute

**Query Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `namespace` | string | No | Kubernetes namespace (uses default if omitted) |
| `is_name` | string | No | InferenceService name (uses default if omitted) |
| `cr_type` | string | No | Custom resource type override |

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
| 409 | Maximum targets reached |
| 500 | Internal server error fetching metrics |

---

### POST /api/metrics/batch

Get batch metrics for multiple target services in a single request.

**Rate Limit:** 120 requests/minute

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

**Rate Limit:** 120 requests/minute

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

**Rate Limit:** 120 requests/minute

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

**Rate Limit:** 120 requests/minute

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

**Rate Limit:** Exempt

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

**Rate Limit:** 3 requests/minute

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
  "sweep_config": "object (optional)"
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

### GET /api/tuner/status

Get the current status of the tuner, including running state, trial progress, and best results found so far.

**Rate Limit:** 60 requests/minute (default)

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

**Rate Limit:** 60 requests/minute (default)

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
    "pruned": "boolean"
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
| `status` | string | Trial status (complete, running, failed) |
| `is_pareto_optimal` | boolean | Whether this trial is on the Pareto front |
| `pruned` | boolean | Whether this trial was pruned early |

**Error Responses:**

| Status | Condition |
|--------|-----------|
| 400 | Invalid pagination parameters |
| 500 | Internal server error |

---

### POST /api/tuner/stop

Stop the currently running auto-tuning job. Gracefully terminates the optimization process.

**Rate Limit:** 60 requests/minute (default)

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

**Rate Limit:** Exempt

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

**Rate Limit:** 60 requests/minute (default)

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

**Rate Limit:** 60 requests/minute (default)

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

**Rate Limit:** 60 requests/minute (default)

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

**Rate Limit:** 60 requests/minute (default)

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

**Rate Limit:** 60 requests/minute (default)

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

**Rate Limit:** 60 requests/minute (default)

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

**Rate Limit:** 5 requests/minute

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

**Rate Limit:** 5 requests/minute (default)

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

**Rate Limit:** 60 requests/minute (default)

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

**Rate Limit:** 5 requests/minute

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

**Rate Limit:** Exempt

**Query Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `test_id` | string | No | Specific test to stream (current if omitted) |

**Request Body:** None

**Response (200 OK):**

```
event: test_start
data: {"test_id": "abc123", "config": {...}}

event: progress
data: {"elapsed": 30, "requests_completed": 150, "current_tps": 45.2}

event: test_complete
data: {"test_id": "abc123", "result": {...}}
```

**Content-Type:** `text/event-stream`

---

### GET /api/load_test/history

Get load test history with pagination.

**Rate Limit:** 60 requests/minute (default)

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

**Rate Limit:** 60 requests/minute (default)

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

**Rate Limit:** 60 requests/minute (default)

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

**Rate Limit:** 60 requests/minute (default)

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

**Rate Limit:** 60 requests/minute (default)

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

**Rate Limit:** 30 requests/minute

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

**Rate Limit:** 30 requests/minute

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

**Rate Limit:** 60 requests/minute

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

**Rate Limit:** 60 requests/minute

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

**Rate Limit:** 60 requests/minute

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

**Rate Limit:** 60 requests/minute

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

**Rate Limit:** 60 requests/minute

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

**Rate Limit:** 60 requests/minute

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

**Rate Limit:** 60 requests/minute

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

**Rate Limit:** 60 requests/minute

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
      "availability_min": "number",
      "p95_latency_max_ms": "number",
      "error_rate_max_pct": "number",
      "min_tps": "number"
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

**Rate Limit:** 60 requests/minute

**Request Body (SlaProfile):**

```json
{
  "name": "string",
  "thresholds": {
    "availability_min": "number",
    "p95_latency_max_ms": "number",
    "error_rate_max_pct": "number",
    "min_tps": "number"
  }
}
```

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

**Rate Limit:** 60 requests/minute

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

**Rate Limit:** 60 requests/minute

**Path Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `profile_id` | string | Yes | SLA profile identifier |

**Request Body (SlaProfile):**

```json
{
  "name": "string",
  "thresholds": {
    "availability_min": "number",
    "p95_latency_max_ms": "number",
    "error_rate_max_pct": "number",
    "min_tps": "number"
  }
}
```

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

**Rate Limit:** 60 requests/minute

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

**Rate Limit:** 60 requests/minute

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

**Rate Limit:** 60 requests/minute

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

**Rate Limit:** 60 requests/minute

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

**Rate Limit:** Exempt

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

**Rate Limit:** Exempt

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

**Rate Limit:** Exempt

**Response:** HTML page with Swagger UI interface.

---

### GET /redoc

ReDoc documentation. Auto-generated alternative API documentation.

**Rate Limit:** Exempt

**Response:** HTML page with ReDoc interface.

---

### GET /openapi.json

OpenAPI specification in JSON format. Machine-readable API definition.

**Rate Limit:** Exempt

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

Server-Sent Events endpoints maintain persistent connections with periodic keepalive messages. Clients should implement reconnection logic with exponential backoff.

### Rate Limiting

Rate limiting is implemented via slowapi with the `@limiter` decorator. When the rate limit is exceeded, the server returns HTTP 429 Too Many Requests.

### Error Handling

All endpoints return structured error responses. Validation errors return HTTP 422 with a `detail` field containing a list of validation issues. Application-level errors return appropriate status codes with descriptive messages.
