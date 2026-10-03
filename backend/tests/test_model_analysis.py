from typing import Any
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from ..models.load_test import TuningConfig
from ..services.cr_adapter import extract_arg_value, get_cr_adapter
from ..services.model_analysis import (
    MemoryBudget,
    analyze_config,
    capacity_table,
    memory_budget,
    observed_capacity,
    suggest_search_space,
)
from ..services.model_config_reader import parse_cache_config_info, parse_read_output
from ..services.tuner_logic import kv_cache_oom_risk
from .conftest import get_route_handler_globals

# Trimmed from the real modelcar config.json files served on the dev cluster.
QWEN35_08B = {
    "architectures": ["Qwen3_5ForConditionalGeneration"],
    "model_type": "qwen3_5",
    "dtype": "bfloat16",
    "text_config": {
        "dtype": "bfloat16",
        "full_attention_interval": 4,
        "head_dim": 256,
        "hidden_size": 1024,
        "layer_types": ["linear_attention"] * 3 + ["full_attention"],
        "linear_conv_kernel_dim": 4,
        "linear_key_head_dim": 128,
        "linear_num_key_heads": 16,
        "linear_num_value_heads": 16,
        "linear_value_head_dim": 128,
        "mamba_ssm_dtype": "float32",
        "max_position_embeddings": 262144,
        "num_attention_heads": 8,
        "num_hidden_layers": 4,
        "num_key_value_heads": 2,
    },
    "vision_config": {"depth": 12, "hidden_size": 768},
}
QWEN35_08B["text_config"]["layer_types"] = QWEN35_08B["text_config"]["layer_types"] * 6
QWEN35_08B["text_config"]["num_hidden_layers"] = 24

GEMMA4_E2B = {
    "architectures": ["Gemma4ForConditionalGeneration"],
    "model_type": "gemma4",
    "dtype": "bfloat16",
    "text_config": {
        "attention_k_eq_v": False,
        "dtype": "bfloat16",
        "global_head_dim": 512,
        "head_dim": 256,
        "hidden_size": 1536,
        "layer_types": (["sliding_attention"] * 4 + ["full_attention"]) * 7,
        "max_position_embeddings": 131072,
        "num_attention_heads": 8,
        "num_global_key_value_heads": None,
        "num_hidden_layers": 35,
        "num_key_value_heads": 1,
        "num_kv_shared_layers": 20,
        "sliding_window": 512,
    },
    "vision_config": {"hidden_size": 768},
    "audio_config": {"hidden_size": 1024},
}

LLAMA_8B = {
    "architectures": ["LlamaForCausalLM"],
    "model_type": "llama",
    "torch_dtype": "bfloat16",
    "hidden_size": 4096,
    "num_attention_heads": 32,
    "num_key_value_heads": 8,
    "num_hidden_layers": 32,
    "max_position_embeddings": 131072,
}


def test_qwen35_hybrid_gdn_counts_only_full_attention_for_growing_kv() -> None:
    a = analyze_config(QWEN35_08B)
    assert a.multimodal is True
    assert (a.full_attention_layers, a.linear_attention_layers, a.sliding_attention_layers) == (6, 18, 0)
    assert a.head_dim == 256  # explicit head_dim, not hidden_size // heads (=128)
    assert a.kv_bytes_per_token == 6 * 2 * 2 * 256 * 2
    # GDN state: recurrent 16*128*128*fp32 + conv (2*16*128 + 16*128)*(4-1)*bf16, per linear layer
    per_layer = 16 * 128 * 128 * 4 + (2 * 16 * 128 + 16 * 128) * 3 * 2
    assert a.linear_state_bytes_per_seq == 18 * per_layer
    assert a.max_position_embeddings == 262144


def test_gemma4_excludes_kv_shared_layers_and_caps_sliding_window() -> None:
    a = analyze_config(GEMMA4_E2B)
    assert a.kv_shared_layers == 20
    # First 15 layers own KV: 3 full (global_head_dim 512) + 12 sliding (head_dim 256)
    assert (a.full_attention_layers, a.sliding_attention_layers) == (3, 12)
    assert a.kv_bytes_per_token == 3 * 2 * 1 * 512 * 2
    assert a.sliding_kv_bytes_per_token == 12 * 2 * 1 * 256 * 2
    assert a.kv_bytes_per_seq(8192) == 6144 * 8192 + 12288 * 512


def test_dense_model_and_fp8_kv_cache_dtype() -> None:
    a = analyze_config(LLAMA_8B)
    assert a.head_dim == 128
    assert a.kv_bytes_per_token == 32 * 2 * 8 * 128 * 2
    assert analyze_config(LLAMA_8B, kv_cache_dtype="fp8").kv_bytes_per_token == 32 * 2 * 8 * 128 * 1
    assert analyze_config(LLAMA_8B).warnings == []


def test_mla_and_moe_metadata() -> None:
    cfg = {
        "num_hidden_layers": 4,
        "num_attention_heads": 16,
        "hidden_size": 2048,
        "kv_lora_rank": 512,
        "qk_rope_head_dim": 64,
        "n_routed_experts": 64,
        "num_experts_per_tok": 6,
        "torch_dtype": "bfloat16",
        "quantization_config": {"quant_method": "fp8"},
    }
    a = analyze_config(cfg)
    assert a.mla is True
    assert a.kv_bytes_per_token == 4 * (512 + 64) * 2
    assert (a.num_experts, a.num_experts_per_tok, a.quantization) == (64, 6, "fp8")


def test_openvino_quantization_label_and_u8_kv() -> None:
    a = analyze_config(LLAMA_8B, openvino_cfg={"dtype": "int4"})
    assert a.quantization == "openvino-int4"
    assert (a.openvino, a.kv_dtype_bytes) == (True, 1)
    assert a.kv_bytes_per_token == 32 * 2 * 8 * 128 * 1


def test_parse_read_output_sections() -> None:
    raw = '{"num_hidden_layers": 2}\n__VLLM_OPTIMIZER_SECTION__\n\n__VLLM_OPTIMIZER_SECTION__\n907981153\ttotal\n'
    cfg, ov_cfg, weight = parse_read_output(raw)
    assert cfg == {"num_hidden_layers": 2}
    assert ov_cfg is None
    assert weight == 907981153


def test_memory_budget_gpu_needs_device_memory_cpu_uses_pod_memory() -> None:
    gpu = {"limits": {"nvidia.com/gpu": "2", "memory": "64Gi"}}
    assert memory_budget(gpu, None, lambda _: 64.0) == MemoryBudget(None, "unknown_accelerator_memory", 2)
    assert memory_budget(gpu, 141.0, lambda _: 64.0) == MemoryBudget(282.0, "accelerator", 2)
    cpu = {"limits": {"memory": "8Gi"}}
    assert memory_budget(cpu, None, lambda _: 8.0) == MemoryBudget(8.0, "pod_memory")
    ov = memory_budget(cpu, None, lambda _: 8.0, openvino=True)
    assert ov == MemoryBudget(4.0, "openvino_kvcache_space", 0, dedicated_kv=True)
    assert ov.kv_bytes(0.5, 3.0) == 4 * 1024**3


def test_capacity_table_and_suggested_search_space() -> None:
    a = analyze_config(LLAMA_8B)
    a.model_weight_gib = 16.0
    rows = capacity_table(a, MemoryBudget(80.0, "accelerator", 1), 0.9, max_context=a.max_position_embeddings)
    by_len = {r["context_len"]: r["max_concurrent_seqs"] for r in rows}
    kv_budget = 80 * 0.9 * 1024**3 - 16 * 1024**3
    assert by_len[8192] == int(kv_budget // (131072 * 8192))
    assert rows[-1]["context_len"] == 131072

    # Never widen beyond the served context; seqs ceiling from capacity at a 2K request
    space = suggest_search_space(rows, served_max_model_len=8192)
    assert space == {
        "max_num_seqs_min": 32,
        "max_num_seqs_max": min(1024, (by_len[2048] // 32) * 32),
        "max_model_len_min": 2048,
        "max_model_len_max": 8192,
    }
    # Unknown served length: bounded by what fits one sequence
    assert suggest_search_space(rows, served_max_model_len=None)["max_model_len_max"] == 131072
    # Nothing fits → no suggestion
    assert suggest_search_space([{"context_len": 1024, "kv_bytes_per_seq": 1, "max_concurrent_seqs": 0}], None) is None


def test_kv_cache_oom_risk_checks_single_max_len_sequence() -> None:
    a = analyze_config(LLAMA_8B)
    base: dict[str, Any] = {
        "model_kv_bytes_per_token": a.kv_bytes_per_token,
        "model_weight_gib": 16.0,
        "memory_budget_gib": 24.0,
    }
    cfg = TuningConfig(**base)
    # 24*0.9-16 = 5.6 GiB KV → 8192 tokens (1 GiB) fits, 65536 tokens (8 GiB) does not
    assert kv_cache_oom_risk({"max_model_len": 8192, "max_num_seqs": 1024, "gpu_memory_utilization": 0.9}, cfg) is False
    assert kv_cache_oom_risk({"max_model_len": 65536, "max_num_seqs": 1, "gpu_memory_utilization": 0.9}, cfg) is True
    assert kv_cache_oom_risk({"max_model_len": 65536}, TuningConfig()) is False


def test_kv_cache_oom_risk_reserves_linear_state_per_seq_slot() -> None:
    # Reproduces llm-ov (Qwen3.5 GDN on OpenVINO, 4 GiB KV space): 256 slots → 0 KV blocks, 32 → boots.
    a = analyze_config(QWEN35_08B, openvino_cfg={"dtype": "int4"})
    cfg = TuningConfig(
        model_kv_bytes_per_token=a.kv_bytes_per_token,
        model_linear_state_bytes_per_seq=a.linear_state_bytes_per_seq,
        memory_budget_gib=4.0,
        memory_budget_dedicated_kv=True,
        model_weight_gib=0.8,
    )
    assert kv_cache_oom_risk({"max_model_len": 8192, "max_num_seqs": 256}, cfg) is True
    assert kv_cache_oom_risk({"max_model_len": 8192, "max_num_seqs": 32}, cfg) is False


def test_extract_arg_value_forms() -> None:
    assert extract_arg_value(["--kv-cache-dtype=fp8"], "--kv-cache-dtype") == "fp8"
    assert extract_arg_value(["--tensor-parallel-size", "4"], "--tensor-parallel-size") == "4"
    assert extract_arg_value(["--enforce-eager"], "--kv-cache-dtype") is None


def test_analyst_disabled_without_endpoint(monkeypatch) -> None:
    import asyncio

    from ..services.llm_assistant import LLMAssistant

    monkeypatch.delenv("ANALYST_ENDPOINT", raising=False)
    assistant = LLMAssistant()
    assert assistant.available is False
    assert asyncio.run(assistant.explain_model_analysis({"model": {}})) is None

    monkeypatch.setenv("ANALYST_ENDPOINT", "http://llm-ov-predictor.ns.svc.cluster.local:8080/")
    assert assistant.available is True
    assert assistant.endpoint == "http://llm-ov-predictor.ns.svc.cluster.local:8080"


def test_explain_endpoint_returns_none_when_analyst_unset(monkeypatch) -> None:
    from ..main import app

    monkeypatch.delenv("ANALYST_ENDPOINT", raising=False)
    resp = TestClient(app).post(
        "/api/tuner/model-analysis/explain",
        json={"target": {"namespace": "ns", "name": "m", "cr_type": "inferenceservice"}, "available": True},
    )
    assert resp.status_code == 200
    assert resp.json() == {"markdown": None, "analyst_available": False}


class _FakeReader:
    def __init__(self, cfg: dict[str, Any], observed: dict[str, Any] | None = None) -> None:
        self.calls: list[dict[str, Any]] = []
        self.observed_calls: list[tuple[str, str, int, str]] = []
        self._cfg = cfg
        self._observed = observed

    def invalidate(self, storage_uri: str | None = None) -> None:
        pass

    async def read_observed_kv(self, namespace: str, pod_label_selector: str, port: int, scheme: str):
        self.observed_calls.append((namespace, pod_label_selector, port, scheme))
        return dict(self._observed) if self._observed else None

    async def read(self, **kwargs: Any):
        self.calls.append(kwargs)
        analysis = analyze_config(self._cfg, kv_cache_dtype=kwargs.get("kv_cache_dtype"))
        analysis.model_weight_gib = 1.0
        if self._observed:
            analysis.served_max_model_len = 8192
        return analysis


def _call_analysis(
    cr_type: str, spec: dict[str, Any], query: str, observed: dict[str, Any] | None = None
) -> tuple[dict[str, Any], _FakeReader]:
    from ..main import app

    handler_globals = get_route_handler_globals(app, "/api/tuner/model-analysis", "GET")
    assert handler_globals is not None
    reader = _FakeReader(LLAMA_8B, observed)
    auto_tuner = handler_globals["auto_tuner"]
    original_ctx = auto_tuner.get_cr_context
    original_reader = handler_globals["get_model_config_reader"]
    runtime = handler_globals["runtime_config"]
    original_cr_type = runtime.cr_type
    auto_tuner.get_cr_context = AsyncMock(return_value=(spec, get_cr_adapter(cr_type)))
    handler_globals["get_model_config_reader"] = lambda: reader
    runtime.set_cr_type(cr_type)
    try:
        resp = TestClient(app).get(f"/api/tuner/model-analysis{query}")
    finally:
        auto_tuner.get_cr_context = original_ctx
        handler_globals["get_model_config_reader"] = original_reader
        runtime.set_cr_type(original_cr_type)
    assert resp.status_code == 200
    return resp.json(), reader


def test_model_analysis_endpoint_inferenceservice_gpu() -> None:
    spec = {
        "predictor": {
            "model": {
                "storageUri": "oci://example/llama",
                "args": ["--kv-cache-dtype=fp8", "--tensor-parallel-size=2"],
                "resources": {"limits": {"nvidia.com/gpu": "2"}},
            }
        }
    }
    data, reader = _call_analysis("inferenceservice", spec, "?accelerator_memory_gib=80")
    assert data["available"] is True
    assert reader.calls[0]["container"] == "kserve-container"
    assert reader.calls[0]["kv_cache_dtype"] == "fp8"
    assert data["runtime"]["gpu_count"] == 2
    assert data["runtime"]["tensor_parallel_size"] == 2
    assert data["memory_budget"]["gib"] == 160.0
    assert data["capacity"] and data["suggested_search_space"] is not None
    assert data["model"]["kv_bytes_per_token"] == 32 * 2 * 8 * 128 * 1


def test_model_analysis_endpoint_llminferenceservice_requires_gpu_memory() -> None:
    spec = {
        "model": {"uri": "oci://example/llama", "name": "llama"},
        "template": {
            "containers": [
                {
                    "name": "main",
                    "env": [{"name": "VLLM_ADDITIONAL_ARGS", "value": "--max-model-len=8192"}],
                    "resources": {"limits": {"nvidia.com/gpu": "1"}},
                }
            ]
        },
    }
    data, reader = _call_analysis("llminferenceservice", spec, "")
    assert data["available"] is True
    assert reader.calls[0]["container"] == "main"
    assert reader.calls[0]["storage_uri"] == "oci://example/llama"
    assert data["memory_budget"]["source"] == "unknown_accelerator_memory"
    assert data["capacity"] == []
    assert any("GPU 장당 메모리" in w for w in data["warnings"])


def test_model_analysis_endpoint_explicit_target_reads_that_cr() -> None:
    from unittest.mock import MagicMock

    from ..main import app

    handler_globals = get_route_handler_globals(app, "/api/tuner/model-analysis", "GET")
    assert handler_globals is not None
    reader = _FakeReader(QWEN35_08B)
    auto_tuner = handler_globals["auto_tuner"]
    custom = MagicMock()
    custom.get_namespaced_custom_object.return_value = {
        "spec": {
            "model": {"uri": "oci://quay.io/x/qwen", "name": "qwen"},
            "template": {"containers": [{"name": "main", "resources": {"limits": {"memory": "8Gi"}}}]},
        }
    }
    original_custom = auto_tuner._k8s_custom
    original_reader = handler_globals["get_model_config_reader"]
    auto_tuner._k8s_custom = custom
    handler_globals["get_model_config_reader"] = lambda: reader
    try:
        resp = TestClient(app).get(
            "/api/tuner/model-analysis?namespace=serving1&is_name=qwen&cr_type=llminferenceservice"
            "&endpoint=https://gw/serving1/qwen"
        )
    finally:
        auto_tuner._k8s_custom = original_custom
        handler_globals["get_model_config_reader"] = original_reader
    assert resp.status_code == 200
    data = resp.json()
    kwargs = custom.get_namespaced_custom_object.call_args.kwargs
    assert (kwargs["namespace"], kwargs["name"], kwargs["plural"]) == ("serving1", "qwen", "llminferenceservices")
    assert data["target"] == {"namespace": "serving1", "name": "qwen", "cr_type": "llminferenceservice"}
    assert reader.calls[0]["pod_label_selector"] == "app.kubernetes.io/name=qwen,kserve.io/component=workload"
    assert reader.calls[0]["vllm_endpoint"] == "https://gw/serving1/qwen"
    assert data["memory_budget"]["source"] == "pod_memory"
    assert data["model"]["linear_attention_layers"] == 18


def test_analyst_facts_are_preformatted_with_units() -> None:
    from ..services.llm_assistant import format_analysis_facts

    a = analyze_config(QWEN35_08B, openvino_cfg={"dtype": "int4"})
    text = format_analysis_facts(
        {
            "model": a.to_dict(),
            "memory_budget": {"gib": 4.0, "source": "openvino_kvcache_space"},
            "capacity": [{"context_len": 8192, "kv_bytes_per_seq": 1, "max_concurrent_seqs": 61}],
            "suggested_search_space": None,
            "warnings": ["분석 LLM(ANALYST_ENDPOINT)이 튜닝 대상과 같음", "OpenVINO KV 공간 가정"],
        }
    )
    assert "토큰당 6.0 KiB" in text
    assert "시퀀스 슬롯(max_num_seqs)당 18.6 MiB" in text
    assert "8192 토큰 → 61" in text
    assert "OpenVINO KV 공간 가정" in text
    assert "ANALYST_ENDPOINT" not in text
    assert "19537920" not in text


# Verbatim line from llm-ov (vLLM 0.30.0, OpenVINO) on the dev cluster, trimmed of unrelated labels.
CACHE_CONFIG_LINE = (
    'vllm:cache_config_info{_block_size_resolved="True",block_size="32",cache_dtype="auto",'
    'enable_prefix_caching="True",engine="0",gpu_memory_utilization="0.9",kv_cache_dtype_skip_layers="[]",'
    'kv_cache_max_concurrency="69.62109375",kv_cache_memory_bytes="None",kv_cache_size_tokens="570336",'
    'mamba_cache_mode="align"} 1.0'
)


def test_parse_cache_config_info_new_and_legacy_formats() -> None:
    text = "# HELP vllm:cache_config_info x\n# TYPE vllm:cache_config_info gauge\n" + CACHE_CONFIG_LINE
    observed = parse_cache_config_info(text)
    assert observed == {
        "kv_cache_size_tokens": 570336,
        "max_concurrency": 69.62109375,
        "block_size": 32,
        "gpu_memory_utilization": 0.9,
        "prefix_caching": True,
        "cache_dtype": "auto",
    }
    legacy = parse_cache_config_info(
        'kserve_vllm:cache_config_info{block_size="16",num_gpu_blocks="2000",gpu_memory_utilization="0.85"} 1.0'
    )
    assert legacy is not None
    assert legacy["kv_cache_size_tokens"] == 32000
    assert legacy["max_concurrency"] is None
    assert parse_cache_config_info('vllm:num_requests_running{engine="0"} 0.0') is None
    assert parse_cache_config_info('vllm:cache_config_info{block_size="16",num_gpu_blocks="None"} 1.0') is None


def test_observed_capacity_merges_and_stops_at_served_len() -> None:
    estimated = [
        {"context_len": 4096, "kv_bytes_per_seq": 1, "max_concurrent_seqs": 90},
        {"context_len": 8192, "kv_bytes_per_seq": 2, "max_concurrent_seqs": 61},
        {"context_len": 16384, "kv_bytes_per_seq": 3, "max_concurrent_seqs": 30},
    ]
    rows = observed_capacity(estimated, 570336, 8192)
    by_len = {r["context_len"]: r for r in rows}
    assert by_len[8192]["observed_max_seqs"] == 69
    assert by_len[8192]["max_concurrent_seqs"] == 61
    assert by_len[1024] == {
        "context_len": 1024,
        "kv_bytes_per_seq": None,
        "max_concurrent_seqs": None,
        "observed_max_seqs": 556,
    }
    assert "observed_max_seqs" not in by_len[16384]
    space = suggest_search_space(rows, 8192, key="observed_max_seqs")
    assert space == {
        "max_num_seqs_min": 64,
        "max_num_seqs_max": 256,
        "max_model_len_min": 2048,
        "max_model_len_max": 8192,
    }


OBSERVED = {"kv_cache_size_tokens": 570336, "max_concurrency": 69.62109375, "block_size": 32, "pod": "p-0"}


def test_model_analysis_endpoint_isvc_observed_compares_estimate() -> None:
    spec = {
        "predictor": {"model": {"storageUri": "oci://example/llama", "resources": {"limits": {"nvidia.com/gpu": "1"}}}}
    }
    data, reader = _call_analysis("inferenceservice", spec, "?accelerator_memory_gib=12", observed=OBSERVED)
    assert reader.observed_calls[0][2:] == (8080, "http")
    estimated_8k = next(r["max_concurrent_seqs"] for r in data["capacity"] if r["context_len"] == 8192)
    assert data["observed"]["estimate_ratio"] == round(estimated_8k / 69.62109375, 3)
    assert next(r for r in data["capacity"] if r["context_len"] == 8192)["observed_max_seqs"] == 69
    assert data["suggested_search_space"]["max_model_len_max"] == 8192


def test_model_analysis_endpoint_llmis_observed_without_gpu_memory() -> None:
    spec = {
        "model": {"uri": "oci://example/llama", "name": "llama"},
        "template": {"containers": [{"name": "main", "resources": {"limits": {"nvidia.com/gpu": "1"}}}]},
    }
    data, reader = _call_analysis("llminferenceservice", spec, "", observed=OBSERVED)
    assert reader.observed_calls[0][2:] == (8000, "https")
    assert data["memory_budget"]["source"] == "unknown_accelerator_memory"
    assert not any("GPU 장당 메모리" in w for w in data["warnings"])
    assert data["observed"]["estimate_ratio"] is None
    assert all(r["max_concurrent_seqs"] is None for r in data["capacity"])
    assert data["suggested_search_space"] is not None
