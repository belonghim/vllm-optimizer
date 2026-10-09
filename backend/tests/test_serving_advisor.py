import copy
from dataclasses import replace
from typing import Any

from ..services.model_analysis import (
    MemoryBudget,
    ModelArtifacts,
    analyze_chat_template,
    analyze_config,
    capacity_table,
    gpu_overhead_gib,
)
from ..services.model_config_reader import parse_read_artifacts
from ..services.serving_advisor import recommend_serving_args
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
