"""
Deterministic model analysis from HF config.json.

Derives the KV cache footprint and serving capacity of the target model with plain arithmetic —
no LLM involved. Handles nested ``text_config`` (multimodal), explicit ``head_dim``, hybrid
``layer_types`` (full / sliding / linear attention), KV-shared layers, MLA and MoE metadata.

Capacity numbers are theoretical upper bounds: activation, CUDA graph and runtime overhead are not
subtracted, so the real limit is lower.
"""

import math
from dataclasses import asdict, dataclass, field
from typing import Any

GIB = 1024**3

_DTYPE_BYTES = {
    "float32": 4,
    "fp32": 4,
    "float": 4,
    "float16": 2,
    "fp16": 2,
    "half": 2,
    "bfloat16": 2,
    "bf16": 2,
    "fp8": 1,
    "fp8_e4m3": 1,
    "fp8_e5m2": 1,
    "fp8_inc": 1,
    "float8": 1,
    "int8": 1,
}

CAPACITY_CONTEXT_LENS = (1024, 2048, 4096, 8192, 16384, 32768, 65536, 131072, 262144)


def _pos_int(d: dict[str, Any], key: str) -> int | None:
    val = d.get(key)
    return val if isinstance(val, int) and not isinstance(val, bool) and val > 0 else None


def _dtype_bytes(dtype: Any, default: int = 2) -> int:
    if isinstance(dtype, str):
        return _DTYPE_BYTES.get(dtype.lower().removeprefix("torch."), default)
    return default


@dataclass
class ModelAnalysis:
    architecture: str | None = None
    model_type: str | None = None
    multimodal: bool = False
    num_hidden_layers: int | None = None
    full_attention_layers: int = 0
    sliding_attention_layers: int = 0
    linear_attention_layers: int = 0
    kv_shared_layers: int = 0
    num_attention_heads: int | None = None
    num_key_value_heads: int | None = None
    head_dim: int | None = None
    full_attention_head_dim: int | None = None
    mla: bool = False
    sliding_window: int | None = None
    max_position_embeddings: int | None = None
    num_experts: int | None = None
    num_experts_per_tok: int | None = None
    weight_dtype: str | None = None
    quantization: str | None = None
    kv_cache_dtype: str = "auto"
    kv_dtype_bytes: int = 2
    # Bytes per token that grow with context length (full-attention / MLA layers owning KV).
    kv_bytes_per_token: int | None = None
    # Bytes per token for sliding-window layers — capped at sliding_window tokens per sequence.
    sliding_kv_bytes_per_token: int = 0
    # Fixed recurrent + conv state per sequence for linear-attention (GDN/Mamba-style) layers.
    linear_state_bytes_per_seq: int = 0
    model_weight_gib: float | None = None
    openvino: bool = False
    # Runtime facts from the serving endpoint (/v1/models), not from config.json.
    served_model_name: str | None = None
    served_max_model_len: int | None = None
    warnings: list[str] = field(default_factory=list)

    def kv_bytes_per_seq(self, context_len: int) -> int | None:
        if self.kv_bytes_per_token is None:
            return None
        window_tokens = min(context_len, self.sliding_window) if self.sliding_window else context_len
        return (
            self.kv_bytes_per_token * context_len
            + self.sliding_kv_bytes_per_token * window_tokens
            + self.linear_state_bytes_per_seq
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _layer_types(text: dict[str, Any], num_layers: int, analysis: ModelAnalysis) -> list[str]:
    raw = text.get("layer_types")
    if isinstance(raw, list) and len(raw) == num_layers and all(isinstance(t, str) for t in raw):
        return raw
    interval = _pos_int(text, "full_attention_interval")
    if interval:
        return ["full_attention" if (i + 1) % interval == 0 else "linear_attention" for i in range(num_layers)]
    if _pos_int(text, "sliding_window") and text.get("use_sliding_window") is not False:
        analysis.warnings.append("layer_types 없음 — sliding_window가 있으나 전 레이어 full attention으로 가정")
    return ["full_attention"] * num_layers


def _linear_state_bytes_per_layer(text: dict[str, Any], act_bytes: int) -> int | None:
    nk = _pos_int(text, "linear_num_key_heads")
    nv = _pos_int(text, "linear_num_value_heads")
    dk = _pos_int(text, "linear_key_head_dim")
    dv = _pos_int(text, "linear_value_head_dim")
    kernel = _pos_int(text, "linear_conv_kernel_dim")
    if not (nk and nv and dk and dv and kernel):
        return None
    ssm_bytes = _dtype_bytes(text.get("mamba_ssm_dtype"), act_bytes)
    recurrent = nv * dk * dv * ssm_bytes
    conv = (2 * nk * dk + nv * dv) * (kernel - 1) * act_bytes
    return recurrent + conv


def _quantization(cfg: dict[str, Any], text: dict[str, Any], openvino_cfg: dict[str, Any] | None) -> str | None:
    if openvino_cfg:
        ov_dtype = openvino_cfg.get("dtype")
        return f"openvino-{ov_dtype}" if isinstance(ov_dtype, str) else "openvino"
    for src in (cfg, text):
        qc = src.get("quantization_config")
        if isinstance(qc, dict):
            method = qc.get("quant_method")
            fmt = qc.get("format")
            if isinstance(method, str) and isinstance(fmt, str):
                return f"{method}/{fmt}"
            if isinstance(method, str):
                return method
    return None


def analyze_config(
    cfg: dict[str, Any],
    kv_cache_dtype: str | None = None,
    openvino_cfg: dict[str, Any] | None = None,
) -> ModelAnalysis:
    """Analyze an HF config.json dict. ``kv_cache_dtype`` is the vLLM --kv-cache-dtype value (None/"auto")."""
    text_cfg = cfg.get("text_config")
    text: dict[str, Any] = text_cfg if isinstance(text_cfg, dict) else cfg
    a = ModelAnalysis()

    archs = cfg.get("architectures")
    a.architecture = archs[0] if isinstance(archs, list) and archs and isinstance(archs[0], str) else None
    a.model_type = cfg.get("model_type") if isinstance(cfg.get("model_type"), str) else None
    a.multimodal = any(isinstance(cfg.get(k), dict) for k in ("vision_config", "audio_config"))

    weight_dtype = text.get("dtype") or text.get("torch_dtype") or cfg.get("dtype") or cfg.get("torch_dtype")
    a.weight_dtype = weight_dtype if isinstance(weight_dtype, str) else None
    act_bytes = _dtype_bytes(a.weight_dtype)
    a.quantization = _quantization(cfg, text, openvino_cfg)

    a.openvino = openvino_cfg is not None
    a.kv_cache_dtype = kv_cache_dtype or "auto"
    a.kv_dtype_bytes = act_bytes if a.kv_cache_dtype == "auto" else _dtype_bytes(a.kv_cache_dtype, act_bytes)
    if a.openvino and a.kv_cache_dtype == "auto":
        # The OpenVINO CPU plugin picks u8 KV when VLLM_OPENVINO_KV_CACHE_PRECISION is unset.
        a.kv_cache_dtype = "auto (openvino u8)"
        a.kv_dtype_bytes = 1

    a.max_position_embeddings = _pos_int(text, "max_position_embeddings")
    a.num_experts = (
        _pos_int(text, "num_experts") or _pos_int(text, "n_routed_experts") or _pos_int(text, "num_local_experts")
    )
    a.num_experts_per_tok = _pos_int(text, "num_experts_per_tok") or _pos_int(text, "top_k_experts")

    num_layers = _pos_int(text, "num_hidden_layers")
    heads = _pos_int(text, "num_attention_heads")
    hidden = _pos_int(text, "hidden_size")
    a.num_hidden_layers = num_layers
    a.num_attention_heads = heads
    a.num_key_value_heads = _pos_int(text, "num_key_value_heads") or heads
    a.head_dim = _pos_int(text, "head_dim") or (hidden // heads if hidden and heads else None)
    a.full_attention_head_dim = _pos_int(text, "global_head_dim") or a.head_dim
    a.sliding_window = _pos_int(text, "sliding_window")

    if not num_layers:
        a.warnings.append("num_hidden_layers 없음 — KV 산정 불가")
        return a

    types = _layer_types(text, num_layers, a)
    a.kv_shared_layers = min(_pos_int(text, "num_kv_shared_layers") or 0, num_layers)
    owning = types[: num_layers - a.kv_shared_layers]
    full = sum(1 for t in owning if t == "full_attention")
    sliding = sum(1 for t in owning if t == "sliding_attention")
    linear = sum(1 for t in owning if t not in ("full_attention", "sliding_attention"))
    a.full_attention_layers, a.sliding_attention_layers, a.linear_attention_layers = full, sliding, linear
    if sliding and not a.sliding_window:
        a.warnings.append("sliding_attention 레이어가 있으나 sliding_window 없음 — 전체 컨텍스트로 산정")

    kv_lora_rank = _pos_int(text, "kv_lora_rank")
    if kv_lora_rank:
        # MLA caches one compressed latent + decoupled RoPE key per token per layer.
        a.mla = True
        rope_dim = _pos_int(text, "qk_rope_head_dim") or 0
        a.kv_bytes_per_token = full * (kv_lora_rank + rope_dim) * a.kv_dtype_bytes
    else:
        if not (a.num_key_value_heads and a.head_dim):
            a.warnings.append("num_key_value_heads/head_dim 없음 — KV 산정 불가")
            return a
        kv_factor = 1 if text.get("attention_k_eq_v") is True else 2
        full_kv_heads = _pos_int(text, "num_global_key_value_heads") or a.num_key_value_heads
        full_head_dim = a.full_attention_head_dim or a.head_dim
        a.kv_bytes_per_token = full * kv_factor * full_kv_heads * full_head_dim * a.kv_dtype_bytes
        a.sliding_kv_bytes_per_token = sliding * kv_factor * a.num_key_value_heads * a.head_dim * a.kv_dtype_bytes

    if linear:
        per_layer = _linear_state_bytes_per_layer(text, act_bytes)
        if per_layer is None:
            a.warnings.append("linear attention 상태 크기 필드 없음 — 고정 상태 메모리 미산정")
        else:
            a.linear_state_bytes_per_seq = linear * per_layer
    return a


OPENVINO_DEFAULT_KV_SPACE_GIB = 4.0


@dataclass
class MemoryBudget:
    gib: float | None
    source: str
    gpu_count: int = 0
    # True when the budget is a dedicated KV pool (OpenVINO VLLM_OPENVINO_KVCACHE_SPACE): no utilization
    # factor and no weight subtraction apply.
    dedicated_kv: bool = False

    def kv_bytes(self, utilization: float, weight_gib: float | None) -> float:
        if self.gib is None:
            return 0.0
        if self.dedicated_kv:
            return self.gib * GIB
        return self.gib * utilization * GIB - (weight_gib or 0.0) * GIB


def memory_budget(
    resources: dict[str, Any],
    accelerator_memory_gib: float | None,
    parse_memory_gib: Any,
    openvino: bool = False,
) -> MemoryBudget:
    """GPU targets need the per-device memory from the user (not discoverable from the CR).
    OpenVINO CPU targets use a dedicated KV pool (VLLM_OPENVINO_KVCACHE_SPACE, default 4 GiB).
    Other CPU targets fall back to the pod memory limit/request.
    """
    limits = resources.get("limits") or {}
    requests = resources.get("requests") or {}
    gpu_raw = limits.get("nvidia.com/gpu") or requests.get("nvidia.com/gpu")
    try:
        gpu_count = int(str(gpu_raw)) if gpu_raw not in (None, "") else 0
    except ValueError:
        gpu_count = 0
    if gpu_count > 0:
        if accelerator_memory_gib and accelerator_memory_gib > 0:
            return MemoryBudget(accelerator_memory_gib * gpu_count, "accelerator", gpu_count)
        return MemoryBudget(None, "unknown_accelerator_memory", gpu_count)
    if openvino:
        return MemoryBudget(OPENVINO_DEFAULT_KV_SPACE_GIB, "openvino_kvcache_space", 0, dedicated_kv=True)
    mem = limits.get("memory") or requests.get("memory")
    if mem:
        gib = parse_memory_gib(str(mem))
        if gib:
            return MemoryBudget(gib, "pod_memory")
    return MemoryBudget(None, "unknown")


def capacity_table(
    analysis: ModelAnalysis,
    budget: MemoryBudget,
    utilization: float,
    max_context: int | None,
) -> list[dict[str, Any]]:
    kv_budget = budget.kv_bytes(utilization, analysis.model_weight_gib)
    rows: list[dict[str, Any]] = []
    for ctx in CAPACITY_CONTEXT_LENS:
        if max_context and ctx > max_context:
            break
        per_seq = analysis.kv_bytes_per_seq(ctx)
        if not per_seq:
            break
        rows.append(
            {
                "context_len": ctx,
                "kv_bytes_per_seq": per_seq,
                "max_concurrent_seqs": max(0, math.floor(kv_budget / per_seq)),
            }
        )
    return rows


TYPICAL_REQUEST_TOKENS = 2048


def suggest_search_space(capacity: list[dict[str, Any]], served_max_model_len: int | None) -> dict[str, int] | None:
    """Tuner ranges consistent with the KV budget.

    max_model_len: never above what is served today (the tuner should not widen the context),
    lowered to the longest context that still fits one sequence. max_num_seqs: ceiling from the
    capacity at a typical request length (prompt + output ≈ TYPICAL_REQUEST_TOKENS); beyond it
    vLLM only preempts, so it is a useful upper bound rather than a hard limit.
    """
    fitting = [
        r
        for r in capacity
        if r["max_concurrent_seqs"] >= 1 and (not served_max_model_len or r["context_len"] <= served_max_model_len)
    ]
    if not fitting:
        return None
    max_len_max = fitting[-1]["context_len"]
    max_len_min = min(TYPICAL_REQUEST_TOKENS, max_len_max // 2)
    by_len = {r["context_len"]: r["max_concurrent_seqs"] for r in capacity}
    typical_cap = by_len.get(TYPICAL_REQUEST_TOKENS, fitting[0]["max_concurrent_seqs"])
    seqs_max = max(64, min(1024, (typical_cap // 32) * 32))
    seqs_min = max(32, (seqs_max // 4 // 32) * 32)
    return {
        "max_num_seqs_min": seqs_min,
        "max_num_seqs_max": seqs_max,
        "max_model_len_min": max_len_min,
        "max_model_len_max": max_len_max,
    }
