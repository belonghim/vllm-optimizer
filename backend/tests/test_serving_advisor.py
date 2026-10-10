import copy
from dataclasses import replace
from typing import Any

from ..models.load_test import TuningConfig
from ..services.model_analysis import (
    MemoryBudget,
    ModelArtifacts,
    analyze_chat_template,
    analyze_config,
    calibrated_overhead_gib,
    capacity_table,
    clamp_search_space_to_cap,
    gpu_overhead_gib,
    mamba_seq_cap,
)
from ..services.model_config_reader import parse_available_kv_gib, parse_read_artifacts
from ..services.serving_advisor import recommend_serving_args
from ..services.tuner_logic import kv_cache_oom_risk
from .test_model_analysis import GEMMA4_E2B, LLAMA_8B, QWEN35_08B, _call_analysis

_SEC = "__VLLM_OPTIMIZER_SECTION__"
XML_TOOL_TEMPLATE = (
    "{% if tools %}<tool_call><function={{ n }}><parameter=a>{% endif %}"
    "{%- if enable_thinking is defined and enable_thinking is false %}<think>\n\n</think>{% else %}<think>{% endif %}"
)
HARMONY_TEMPLATE = "<|start|>assistant<|channel|>analysis<|message|>{{ reasoning_effort }}"


def _by_flag(result: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {r["flag"]: r for r in result["recommendations"]}


def _notes(result: dict[str, Any]) -> list[str]:
    return [n["text"] for n in result["notes"]]


def test_parse_read_artifacts_sections() -> None:
    raw = _SEC.join(
        [
            "{}\n",
            "\n",
            "1\ttotal\n",
            '{"temperature": 0.6}\n',
            '{"model_max_length": 4096}\n',
            "T\n",
            "/mnt/models/mod.py\n",
        ]
    )
    art = parse_read_artifacts(raw)
    assert art is not None
    assert art.generation_config == {"temperature": 0.6}
    assert art.tokenizer_config == {"model_max_length": 4096}
    assert art.chat_template == "T"
    assert art.custom_code_files == ["mod.py"]


def test_parse_read_artifacts_legacy_output_returns_none() -> None:
    assert parse_read_artifacts(_SEC.join(["{}", "", "1\ttotal"])) is None


def test_analyze_chat_template_signatures() -> None:
    sigs, thinking = analyze_chat_template(XML_TOOL_TEMPLATE)
    assert {"tool_xml", "think", "enable_thinking"} <= set(sigs)
    assert thinking == "enabled"
    assert "harmony" in analyze_chat_template(HARMONY_TEMPLATE)[0]


def test_context_limit_from_tokenizer_and_yarn() -> None:
    art = ModelArtifacts(None, {"model_max_length": 32768}, None, [])
    assert analyze_config(LLAMA_8B, artifacts=art).context_limit == 32768
    cfg = copy.deepcopy(LLAMA_8B)
    cfg["max_position_embeddings"] = 32768
    cfg["rope_scaling"] = {"rope_type": "yarn", "factor": 4.0, "original_max_position_embeddings": 32768}
    a = analyze_config(cfg)
    assert a.context_limit == 131072
    assert a.rope_type == "yarn"


def test_sliding_window_reservation_uses_max_num_batched_tokens() -> None:
    a = analyze_config(GEMMA4_E2B)
    assert a.kv_bytes_per_seq(131072, 8192) > a.kv_bytes_per_seq(131072)


def test_gpu_overhead_scales_with_tensor_parallel_and_reduces_budget() -> None:
    assert gpu_overhead_gib(1) < gpu_overhead_gib(2) < gpu_overhead_gib(8)
    a = analyze_config(LLAMA_8B)
    a.model_weight_gib = 16.0
    base = MemoryBudget(80.0, "accelerator", 1)
    reserved = replace(base, overhead_gib=gpu_overhead_gib(1))
    rows_a = capacity_table(a, base, 0.9, max_context=8192)
    rows_b = capacity_table(a, reserved, 0.9, max_context=8192)
    assert rows_b[-1]["max_concurrent_seqs"] < rows_a[-1]["max_concurrent_seqs"]


def test_advisor_qwen_hybrid_with_xml_tools_and_thinking() -> None:
    art = ModelArtifacts({"temperature": 0.7}, {"model_max_length": 131072}, XML_TOOL_TEMPLATE, [])
    a = analyze_config(QWEN35_08B, artifacts=art)
    result = recommend_serving_args(a, ["--max-model-len=262144"], gpu_count=1, tensor_parallel_size=1)
    recs = _by_flag(result)
    assert recs["--tool-call-parser"]["arg"] == "--tool-call-parser=qwen3_coder"
    assert recs["--reasoning-parser"]["arg"] == "--reasoning-parser=qwen3"
    assert recs["--enable-auto-tool-choice"]["kind"] == "required"
    assert recs["--enable-prefix-caching"]["kind"] == "workload"
    assert result["add_args"] == "--enable-auto-tool-choice --tool-call-parser=qwen3_coder --reasoning-parser=qwen3"
    texts = _notes(result)
    assert any("config 유도 상한" in t for t in texts)
    assert any("Mamba" in t for t in texts)
    assert any("generation_config" in t for t in texts)


def test_advisor_marks_present_flags_and_omits_them_from_add_args() -> None:
    art = ModelArtifacts(None, None, XML_TOOL_TEMPLATE, [])
    a = analyze_config(QWEN35_08B, artifacts=art)
    args = [
        "--enable-auto-tool-choice",
        "--tool-call-parser=qwen3_coder",
        "--reasoning-parser",
        "deepseek_r1",
    ]
    result = recommend_serving_args(a, args, gpu_count=1, tensor_parallel_size=1)
    recs = _by_flag(result)
    assert recs["--tool-call-parser"]["status"] == "present"
    assert recs["--reasoning-parser"]["status"] == "mismatch"
    assert result["add_args"] == ""


def test_advisor_gemma4_flags_multimodal_and_attention_backend() -> None:
    a = analyze_config(GEMMA4_E2B)
    result = recommend_serving_args(a, [], gpu_count=2, tensor_parallel_size=2)
    recs = _by_flag(result)
    assert recs["--attention-backend"]["arg"] == "--attention-backend=TRITON_ATTN"
    assert recs["--mm-encoder-tp-mode"]["arg"] == "--mm-encoder-tp-mode=data"
    assert "--language-model-only" in recs
    assert any("sliding window" in t for t in _notes(result))
    assert any("읽지 못해" in t for t in _notes(result))


def test_advisor_harmony_template_does_not_recommend_fp8_kv() -> None:
    a = analyze_config(LLAMA_8B, artifacts=ModelArtifacts(None, None, HARMONY_TEMPLATE, []))
    result = recommend_serving_args(a, [], gpu_count=1, tensor_parallel_size=1)
    assert "--kv-cache-dtype" not in _by_flag(result)


def test_advisor_flags_avoid_dtype_with_quantization_config() -> None:
    cfg = copy.deepcopy(LLAMA_8B)
    cfg["quantization_config"] = {"quant_method": "fp8"}
    result = recommend_serving_args(analyze_config(cfg), ["--dtype=bfloat16"], gpu_count=1, tensor_parallel_size=1)
    recs = _by_flag(result)
    assert recs["--dtype"]["kind"] == "avoid"
    assert recs["--dtype"]["status"] == "present"
    assert result["add_args"] == ""


def test_advisor_auto_map_requires_trust_remote_code() -> None:
    cfg = copy.deepcopy(LLAMA_8B)
    cfg["auto_map"] = {"AutoModel": "modeling_x.X"}
    art = ModelArtifacts(None, None, None, [])
    result = recommend_serving_args(analyze_config(cfg, artifacts=art), [], gpu_count=1, tensor_parallel_size=1)
    rec = _by_flag(result)["--trust-remote-code"]
    assert rec["kind"] == "required"
    assert rec["status"] == "missing"
    assert any("modeling_x" in t or ".py" in t for t in _notes(result))


def test_model_analysis_endpoint_returns_advice_for_both_cr_types() -> None:
    isvc = {
        "predictor": {
            "model": {
                "storageUri": "oci://example/llama",
                "args": ["--gpu-memory-utilization=0.5"],
                "resources": {"limits": {"nvidia.com/gpu": "1"}},
            }
        }
    }
    llmis = {
        "model": {"uri": "oci://example/llama", "name": "llama"},
        "template": {
            "containers": [
                {
                    "name": "main",
                    "env": [{"name": "VLLM_ADDITIONAL_ARGS", "value": "--gpu-memory-utilization=0.5"}],
                    "resources": {"limits": {"nvidia.com/gpu": "1"}},
                }
            ]
        },
    }
    for cr_type, spec in (("inferenceservice", isvc), ("llminferenceservice", llmis)):
        data, _ = _call_analysis(cr_type, spec, "?accelerator_memory_gib=80")
        assert data["advice"] is not None, cr_type
        assert {"recommendations", "notes", "add_args"} <= set(data["advice"])
        assert data["memory_budget"]["utilization"] == 0.5, cr_type
        assert data["memory_budget"]["overhead_gib"] > 0, cr_type


def test_advisor_skips_mtp_on_openvino() -> None:
    a = analyze_config(LLAMA_8B, openvino_cfg={"dtype": "int4"})
    a.mtp_layers = 1
    assert "--speculative-config" not in _by_flag(recommend_serving_args(a, [], gpu_count=0, tensor_parallel_size=None))


def test_tuner_oom_risk_subtracts_overhead_reserve() -> None:
    a = analyze_config(LLAMA_8B)
    base: dict[str, Any] = {
        "model_kv_bytes_per_token": a.kv_bytes_per_token,
        "model_weight_gib": 16.0,
        "memory_budget_gib": 24.0,
    }
    params = {"max_model_len": 32768, "max_num_seqs": 8, "gpu_memory_utilization": 0.9}
    # 24*0.9-16 = 5.6 GiB; 4 GiB sequence fits (<= 5.04), but not once a 6 GiB overhead is reserved.
    assert kv_cache_oom_risk(params, TuningConfig(**base)) is False
    assert kv_cache_oom_risk(params, TuningConfig(**base, memory_overhead_gib=6.0)) is True


def test_tuner_oom_risk_sliding_window_grows_with_batched_tokens() -> None:
    a = analyze_config(GEMMA4_E2B)
    small = {"max_model_len": 131072, "max_num_batched_tokens": 256, "gpu_memory_utilization": 1.0}
    big = {**small, "max_num_batched_tokens": 65536}
    need_small = a.kv_bytes_per_seq(131072, 256)
    need_big = a.kv_bytes_per_seq(131072, 65536)
    assert need_big > need_small
    # Budget sized so the 256-token reservation fits (with the 0.9 safety factor) but 65536 does not.
    budget_gib = (need_small / 0.9 * 1.01) / 1024**3
    cfg = TuningConfig(
        model_kv_bytes_per_token=a.kv_bytes_per_token,
        model_sliding_kv_bytes_per_token=a.sliding_kv_bytes_per_token,
        model_sliding_window=a.sliding_window,
        memory_budget_gib=budget_gib,
    )
    assert kv_cache_oom_risk(small, cfg) is False
    assert kv_cache_oom_risk(big, cfg) is True


def test_mamba_seq_cap_requires_hybrid_and_block_count() -> None:
    hybrid = analyze_config(QWEN35_08B)
    dense = analyze_config(LLAMA_8B)
    assert mamba_seq_cap(hybrid, {"num_gpu_blocks": 96}) == 96
    assert mamba_seq_cap(hybrid, {"num_gpu_blocks": None}) is None
    assert mamba_seq_cap(hybrid, None) is None
    assert mamba_seq_cap(dense, {"num_gpu_blocks": 96}) is None


def test_clamp_search_space_to_cap() -> None:
    space = {"max_num_seqs_min": 64, "max_num_seqs_max": 256}
    clamped = clamp_search_space_to_cap(space, 48)
    assert clamped is not None
    assert (clamped["max_num_seqs_min"], clamped["max_num_seqs_max"]) == (48, 48)
    assert clamp_search_space_to_cap(space, 512) == space
    assert clamp_search_space_to_cap(space, None) == space
    assert clamp_search_space_to_cap(None, 48) is None


def test_advisor_warns_when_max_num_seqs_exceeds_mamba_blocks() -> None:
    a = analyze_config(QWEN35_08B)
    over = recommend_serving_args(a, ["--max-num-seqs=256"], gpu_count=1, mamba_cap=96)
    assert any("96" in t and "exceeds available Mamba cache blocks" in t for t in _notes(over))
    assert any(n["level"] == "warning" and "Mamba" in n["text"] for n in over["notes"])
    ok = recommend_serving_args(a, ["--max-num-seqs=64"], gpu_count=1, mamba_cap=96)
    assert not any(n["level"] == "warning" and "Mamba" in n["text"] for n in ok["notes"])


def test_calibrated_overhead_back_solves_from_observed_pool() -> None:
    a = analyze_config(LLAMA_8B)
    a.model_weight_gib = 15.0
    budget = MemoryBudget(80.0, "accelerator", 1, overhead_gib=6.0)
    pool_tokens = int((80 * 0.9 - 15.0 - 8.0) * 2**30 / a.kv_bytes_per_token)
    assert calibrated_overhead_gib(a, budget, 0.9, pool_tokens) == 8.0
    assert calibrated_overhead_gib(a, budget, 0.9, None) is None
    assert calibrated_overhead_gib(a, budget, 0.9, 10**12) is None  # pool larger than budget → distrust
    assert calibrated_overhead_gib(a, replace(budget, dedicated_kv=True), 0.9, pool_tokens) is None
    a.sliding_kv_bytes_per_token = 1024
    assert calibrated_overhead_gib(a, budget, 0.9, pool_tokens) is None


def test_model_analysis_calibrates_overhead_from_observed_pool_for_both_cr_types() -> None:
    kv_per_token = 32 * 2 * 8 * 128 * 2
    tokens = int((80 * 0.9 - 1.0 - 8.0) * 2**30 / kv_per_token)
    observed = {"kv_cache_size_tokens": tokens, "max_concurrency": 10.0}
    isvc = {
        "predictor": {
            "model": {
                "storageUri": "oci://example/llama",
                "args": ["--gpu-memory-utilization=0.9"],
                "resources": {"limits": {"nvidia.com/gpu": "1"}},
            }
        }
    }
    llmis = {
        "model": {"uri": "oci://example/llama", "name": "llama"},
        "template": {
            "containers": [
                {
                    "name": "main",
                    "env": [{"name": "VLLM_ADDITIONAL_ARGS", "value": "--gpu-memory-utilization=0.9"}],
                    "resources": {"limits": {"nvidia.com/gpu": "1"}},
                }
            ]
        },
    }
    for cr_type, spec in (("inferenceservice", isvc), ("llminferenceservice", llmis)):
        data, _ = _call_analysis(cr_type, spec, "?accelerator_memory_gib=80", observed)
        assert data["memory_budget"]["overhead_gib"] == 8.0, cr_type
        assert data["memory_budget"]["overhead_source"] == "observed", cr_type
        table_data, _ = _call_analysis(cr_type, spec, "?accelerator_memory_gib=80")
        assert table_data["memory_budget"]["overhead_source"] == "table", cr_type


def test_calibrated_overhead_uses_logged_kv_memory_for_hybrid_models() -> None:
    a = analyze_config(QWEN35_08B)
    assert a.linear_state_bytes_per_seq  # hybrid: the token-based path refuses it
    a.model_weight_gib = 1.72
    budget = MemoryBudget(12.0, "accelerator", 1, overhead_gib=6.0)
    assert calibrated_overhead_gib(a, budget, 0.8, 407013) is None
    assert calibrated_overhead_gib(a, budget, 0.8, 407013, available_kv_gib=5.88) == 2.0
    # per-GPU log value scales with the device count
    two = MemoryBudget(24.0, "accelerator", 2, overhead_gib=10.0)
    assert calibrated_overhead_gib(a, two, 0.8, None, available_kv_gib=5.88) == 5.72
    assert calibrated_overhead_gib(a, budget, 0.8, None, available_kv_gib=50.0) is None


def test_parse_available_kv_gib_from_boot_log() -> None:
    log = (
        "(EngineCore pid=121) INFO 10-09 14:07:28 [gpu_worker.py:508] Available KV cache memory: 5.88 GiB\n"
        "(EngineCore pid=121) INFO 10-09 14:07:28 [kv_cache_utils.py:2146] GPU KV cache size: 407,013 tokens\n"
    )
    assert parse_available_kv_gib(log) == 5.88
    assert parse_available_kv_gib("INFO nothing here") is None
    assert parse_available_kv_gib(None) is None


def test_model_analysis_calibrates_hybrid_overhead_from_logged_kv_for_both_cr_types() -> None:
    observed = {"kv_cache_size_tokens": 407013, "max_concurrency": 49.68}
    isvc = {
        "predictor": {
            "model": {
                "storageUri": "oci://example/qwen",
                "args": ["--gpu-memory-utilization=0.8"],
                "resources": {"limits": {"nvidia.com/gpu": "1"}},
            }
        }
    }
    llmis = {
        "model": {"uri": "oci://example/qwen", "name": "qwen"},
        "template": {
            "containers": [
                {
                    "name": "main",
                    "env": [{"name": "VLLM_ADDITIONAL_ARGS", "value": "--gpu-memory-utilization=0.8"}],
                    "resources": {"limits": {"nvidia.com/gpu": "1"}},
                }
            ]
        },
    }
    for cr_type, spec in (("inferenceservice", isvc), ("llminferenceservice", llmis)):
        data, _ = _call_analysis(
            cr_type, spec, "?accelerator_memory_gib=12", observed, cfg=QWEN35_08B, available_kv_gib=5.88
        )
        assert data["memory_budget"]["overhead_source"] == "observed", cr_type
        assert data["memory_budget"]["overhead_gib"] == 2.72, cr_type  # fake reader reports 1.0 GiB of weights
        assert data["observed"]["available_kv_gib"] == 5.88, cr_type
        no_log, _ = _call_analysis(cr_type, spec, "?accelerator_memory_gib=12", observed, cfg=QWEN35_08B)
        assert no_log["memory_budget"]["overhead_source"] == "table", cr_type
