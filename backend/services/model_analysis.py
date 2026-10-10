"""
Deterministic model analysis from HF config.json.

Derives the KV cache footprint and serving capacity of the target model with plain arithmetic —
no LLM involved. Handles nested ``text_config`` (multimodal), explicit ``head_dim``, hybrid
``layer_types`` (full / sliding / linear attention), KV-shared layers, MLA and MoE metadata.

Capacity numbers are estimates: GPU budgets subtract a conservative TP-based overhead, but the real
limit is whatever vLLM measured at startup (see ``observed_capacity``).
"""

import math
import re
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

# Fallback --gpu-memory-utilization when the target sets none (conservative vs vLLM v0.24.0's 0.92).
DEFAULT_UTILIZATION = 0.9

# vLLM v1 default on H100/H200-class GPUs; sliding-window layers reserve window - 1 + this many tokens.
DEFAULT_MAX_NUM_BATCHED_TOKENS = 8192

_CONTEXT_KEYS = (
    "max_position_embeddings",
    "n_positions",
    "max_seq_len",
    "seq_length",
    "model_max_length",
    "max_sequence_length",
)
_NO_FACTOR_ROPE_TYPES = frozenset({"llama3", "longrope", "su", "default"})


def _pos_int(d: dict[str, Any], key: str) -> int | None:
    val = d.get(key)
    return val if isinstance(val, int) and not isinstance(val, bool) and val > 0 else None


def _dtype_bytes(dtype: Any, default: int = 2) -> int:
    if isinstance(dtype, str):
        return _DTYPE_BYTES.get(dtype.lower().removeprefix("torch."), default)
    return default


@dataclass
class ModelArtifacts:
    """Auxiliary model files read next to config.json (all optional)."""

    generation_config: dict[str, Any] | None = None
    tokenizer_config: dict[str, Any] | None = None
    chat_template: str | None = None
    custom_code_files: list[str] = field(default_factory=list)


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
    # Context ceiling vLLM derives from config/tokenizer/rope when --max-model-len is unset.
    context_limit: int | None = None
    rope_type: str | None = None
    mtp_layers: int = 0
    auto_map: bool = False
    # auto_map points at another Hub repo ("org/repo--module.Class") — unreachable offline.
    auto_map_remote: bool = False
    custom_code_files: list[str] = field(default_factory=list)
    # False when only config.json was readable (artifacts below are then unknown, not absent).
    artifacts_read: bool = False
    chat_template_source: str | None = None
    template_signatures: list[str] = field(default_factory=list)
    thinking_default: str | None = None
    generation_defaults: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def kv_bytes_per_seq(self, context_len: int, max_num_batched_tokens: int | None = None) -> int | None:
        """KV bytes one sequence of ``context_len`` tokens occupies.

        With ``max_num_batched_tokens`` sliding-window layers reserve ``window - 1 + max_num_batched_tokens``
        tokens (vLLM admits a request against that, not the bare window).
        """
        if self.kv_bytes_per_token is None:
            return None
        window_tokens = context_len
        if self.sliding_window:
            reserved = (
                self.sliding_window - 1 + max_num_batched_tokens if max_num_batched_tokens else self.sliding_window
            )
            window_tokens = min(context_len, reserved)
        return (
            self.kv_bytes_per_token * context_len
            + self.sliding_kv_bytes_per_token * window_tokens
            + self.linear_state_bytes_per_seq
        )

    @property
    def boot_state_bytes_per_seq(self) -> int:
        """Bytes one ``max_num_seqs`` slot must find free at boot for the linear-attention state.

        The CUDA backend pools state in blocks shared by layer groups of ``min(full, linear)`` layers, so a slot
        costs ``group`` layers of state rather than all of them (measured on Qwen3.5-0.8B: 6.7 MB, not 19.5 MB).
        The OpenVINO backend reserves the full per-sequence state.
        """
        if not self.linear_attention_layers or not self.linear_state_bytes_per_seq or self.openvino:
            return self.linear_state_bytes_per_seq
        group = min(self.full_attention_layers, self.linear_attention_layers) or self.linear_attention_layers
        return self.linear_state_bytes_per_seq * group // self.linear_attention_layers

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


def _derive_context_limit(
    cfg: dict[str, Any], text: dict[str, Any], tokenizer_cfg: dict[str, Any] | None
) -> tuple[int | None, str | None]:
    """vLLM's max-model-len ceiling (config keys, tokenizer model_max_length, rope scaling) and the rope type."""
    candidates = [v for k in _CONTEXT_KEYS if (v := _pos_int(text, k) or _pos_int(cfg, k))]
    if tokenizer_cfg:
        tok_len = tokenizer_cfg.get("model_max_length")
        if isinstance(tok_len, (int, float)) and not isinstance(tok_len, bool) and 0 < tok_len < 10**15:
            candidates.append(int(tok_len))
    derived = min(candidates) if candidates else None
    rope = text.get("rope_scaling") or text.get("rope_parameters") or cfg.get("rope_scaling")
    if not isinstance(rope, dict):
        return derived, None
    rope_type = rope.get("rope_type") or rope.get("type")
    rope_type = rope_type if isinstance(rope_type, str) else None
    factor = rope.get("factor")
    if rope_type and isinstance(factor, (int, float)) and not isinstance(factor, bool) and factor > 0:
        if rope_type == "yarn":
            original = _pos_int(rope, "original_max_position_embeddings") or derived
            derived = int(original * factor) if original else derived
        elif rope_type not in _NO_FACTOR_ROPE_TYPES and derived:
            derived = int(derived * factor)
    return derived, rope_type


_TEMPLATE_SIGNATURES = (
    ("tool_xml", lambda t: "<function=" in t),
    ("tool_json", lambda t: "<tool_call>" in t and "<function=" not in t),
    ("harmony", lambda t: "<|channel|>" in t),
    ("gemma4_tool", lambda t: "<|tool_call>" in t),
    ("enable_thinking", lambda t: "enable_thinking" in t),
    ("think", lambda t: "<think>" in t),
    ("reasoning_effort", lambda t: "reasoning_effort" in t),
)


def analyze_chat_template(template: str) -> tuple[list[str], str | None]:
    """Template signatures (tool-call / reasoning dialect) and whether thinking is on by default."""
    signatures = [name for name, test in _TEMPLATE_SIGNATURES if test(template)]
    thinking_default: str | None = None
    if re.search(r"enable_thinking is defined and enable_thinking is false", template):
        thinking_default = "enabled"
    elif re.search(r"enable_thinking is defined and enable_thinking|enable_thinking\s*\|\s*default\(false\)", template):
        thinking_default = "disabled"
    return signatures, thinking_default


def _resolve_chat_template(artifacts: ModelArtifacts) -> tuple[str, str | None]:
    if artifacts.chat_template and artifacts.chat_template.strip():
        return artifacts.chat_template, "chat_template.jinja"
    tpl = (artifacts.tokenizer_config or {}).get("chat_template")
    if isinstance(tpl, list):
        tpl = " ".join(t.get("template", "") for t in tpl if isinstance(t, dict))
    if isinstance(tpl, str) and tpl.strip():
        return tpl, "tokenizer_config.json"
    return "", None


_SAMPLING_KEYS = ("temperature", "top_p", "top_k", "min_p", "repetition_penalty", "max_new_tokens")


def _apply_artifacts(a: ModelAnalysis, artifacts: ModelArtifacts) -> None:
    a.artifacts_read = True
    a.custom_code_files = list(artifacts.custom_code_files)
    template, a.chat_template_source = _resolve_chat_template(artifacts)
    if template:
        a.template_signatures, a.thinking_default = analyze_chat_template(template)
    gen = artifacts.generation_config or {}
    a.generation_defaults = {k: gen[k] for k in _SAMPLING_KEYS if k in gen}


def analyze_config(
    cfg: dict[str, Any],
    kv_cache_dtype: str | None = None,
    openvino_cfg: dict[str, Any] | None = None,
    artifacts: ModelArtifacts | None = None,
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
    a.context_limit, a.rope_type = _derive_context_limit(cfg, text, artifacts.tokenizer_config if artifacts else None)
    a.mtp_layers = _pos_int(text, "mtp_num_hidden_layers") or _pos_int(text, "num_nextn_predict_layers") or 0
    auto_map = cfg.get("auto_map")
    if isinstance(auto_map, dict) and auto_map:
        a.auto_map = True
        values = [v for val in auto_map.values() for v in (val if isinstance(val, list) else [val])]
        a.auto_map_remote = any(isinstance(v, str) and "--" in v for v in values)
    if artifacts is not None:
        _apply_artifacts(a, artifacts)
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
    # CUDA graph / activation / NCCL reserve across all devices (see gpu_overhead_gib).
    overhead_gib: float = 0.0

    def kv_bytes(self, utilization: float, weight_gib: float | None) -> float:
        if self.gib is None:
            return 0.0
        if self.dedicated_kv:
            return self.gib * GIB
        return self.gib * utilization * GIB - ((weight_gib or 0.0) + self.overhead_gib) * GIB


_OVERHEAD_GIB_PER_GPU_BY_TP = ((1, 6.0), (2, 10.0), (4, 16.0), (8, 24.0))


def gpu_overhead_gib(device_count: int) -> float:
    """Conservative non-KV, non-weight GPU reserve (CUDA graph, activations, NCCL) before a first boot measurement."""
    if device_count <= 0:
        return 0.0
    per_gpu = next((gib for tp, gib in _OVERHEAD_GIB_PER_GPU_BY_TP if device_count <= tp), 24.0)
    return per_gpu * device_count


def calibrated_overhead_gib(
    analysis: ModelAnalysis,
    budget: MemoryBudget,
    running_utilization: float,
    kv_cache_size_tokens: int | None,
    available_kv_gib: float | None = None,
) -> float | None:
    """Back-solve the non-weight, non-KV GPU reserve from the KV memory vLLM actually allocated.

    ``overhead = budget * util - weights - KV memory`` at the utilization the pod runs with. The KV memory is
    vLLM's logged ``Available KV cache memory`` (per GPU; valid for every architecture, including hybrid and
    sliding-window models) or, without it, ``pool_tokens * kv_bytes_per_token`` (pure full-attention models only,
    since the pool token count of other models is not a plain multiple of one per-token size).
    Only trusted when the result is non-negative.
    """
    if budget.dedicated_kv or not budget.gib or running_utilization <= 0 or analysis.model_weight_gib is None:
        return None
    if available_kv_gib:
        kv_gib = available_kv_gib * max(budget.gpu_count, 1)
    elif (
        kv_cache_size_tokens
        and analysis.kv_bytes_per_token
        and not (analysis.sliding_kv_bytes_per_token or analysis.linear_state_bytes_per_seq)
    ):
        kv_gib = kv_cache_size_tokens * analysis.kv_bytes_per_token / GIB
    else:
        return None
    overhead = budget.gib * running_utilization - analysis.model_weight_gib - kv_gib
    return round(overhead, 2) if overhead >= 0 else None


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
    max_num_batched_tokens: int | None = None,
) -> list[dict[str, Any]]:
    kv_budget = budget.kv_bytes(utilization, analysis.model_weight_gib)
    rows: list[dict[str, Any]] = []
    for ctx in CAPACITY_CONTEXT_LENS:
        if max_context and ctx > max_context:
            break
        per_seq = analysis.kv_bytes_per_seq(ctx, max_num_batched_tokens)
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


def observed_capacity(
    capacity: list[dict[str, Any]],
    kv_cache_size_tokens: int,
    served_max_model_len: int | None,
    analysis: ModelAnalysis | None = None,
    max_num_batched_tokens: int | None = None,
) -> list[dict[str, Any]]:
    """Add vLLM's measured capacity (``observed_max_seqs``) to the estimated rows.

    vLLM reports its allocated KV pool in tokens; at context length L it fits pool // L sequences
    (the same figure it logs as "Maximum concurrency"). Rows are only measured up to the served
    max_model_len — longer contexts are rejected by the running server. Rows missing from the
    estimate (no memory budget known) are added with ``max_concurrent_seqs`` = None.
    """
    rows = {r["context_len"]: dict(r) for r in capacity}
    for ctx in CAPACITY_CONTEXT_LENS:
        if served_max_model_len and ctx > served_max_model_len:
            break
        row = rows.setdefault(
            ctx,
            {
                "context_len": ctx,
                "kv_bytes_per_seq": analysis.kv_bytes_per_seq(ctx, max_num_batched_tokens) if analysis else None,
                "max_concurrent_seqs": None,
            },
        )
        row["observed_max_seqs"] = kv_cache_size_tokens // ctx
    return [rows[k] for k in sorted(rows)]


TYPICAL_REQUEST_TOKENS = 2048


def suggest_search_space(
    capacity: list[dict[str, Any]],
    served_max_model_len: int | None,
    key: str = "max_concurrent_seqs",
) -> dict[str, int] | None:
    """max_num_seqs range consistent with the KV budget.

    The ceiling is the capacity at a typical request length (prompt + output ≈ TYPICAL_REQUEST_TOKENS);
    beyond it vLLM only preempts, so it is a useful upper bound rather than a hard limit. ``key`` selects
    the estimated (``max_concurrent_seqs``) or measured (``observed_max_seqs``) capacity.
    """
    fitting = [
        r
        for r in capacity
        if (r.get(key) or 0) >= 1 and (not served_max_model_len or r["context_len"] <= served_max_model_len)
    ]
    if not fitting:
        return None
    by_len = {r["context_len"]: r.get(key) for r in fitting}
    typical_cap = by_len.get(TYPICAL_REQUEST_TOKENS) or fitting[0][key]
    seqs_max = max(64, min(1024, (typical_cap // 32) * 32))
    seqs_min = max(32, (seqs_max // 4 // 32) * 32)
    return {"max_num_seqs_min": seqs_min, "max_num_seqs_max": seqs_max}


def mamba_seq_cap(analysis: ModelAnalysis, observed: dict[str, Any] | None) -> int | None:
    """Hard ``--max-num-seqs`` ceiling for hybrid (GDN/Mamba) models, from vLLM's allocated block count.

    Every decode sequence needs one Mamba cache block, and with full CUDA graphs vLLM refuses to start when
    ``max_num_seqs > kv_cache_config.num_blocks``. ``num_gpu_blocks`` is only exposed by some vLLM releases.
    """
    if not analysis.linear_attention_layers or not observed:
        return None
    blocks = observed.get("num_gpu_blocks")
    return blocks if isinstance(blocks, int) and blocks > 0 else None


def clamp_search_space_to_cap(space: dict[str, int] | None, cap: int | None) -> dict[str, int] | None:
    if not space or not cap or space["max_num_seqs_max"] <= cap:
        return space
    seqs_max = cap
    return {**space, "max_num_seqs_max": seqs_max, "max_num_seqs_min": min(space["max_num_seqs_min"], seqs_max)}
