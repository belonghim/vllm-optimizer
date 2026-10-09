import types
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from ..services import k8s_operator
from ..services.auto_tuner import AutoTuner
from ..services.boot_diagnosis import (
    compact_failure,
    diagnose_boot,
    first_violated_limit,
    learn_limits,
    summarize_diagnoses,
)
from ..services.cr_adapter import get_cr_adapter
from .conftest import get_route_handler_globals

MAMBA_LOG = (
    "ValueError: max_num_seqs (256) exceeds available Mamba cache blocks (96). Each decode sequence requires "
    "one Mamba cache block, so CUDA graph capture cannot proceed. Please lower max_num_seqs to at most 96 or "
    "increase gpu_memory_utilization."
)
KV_LOG = (
    "ValueError: To serve at least one request with the models's max seq len (131072), (10.0 GiB KV cache is "
    "needed, which is larger than the available KV cache memory (4.0 GiB). Based on the available memory, the "
    "estimated maximum model length is 52,416. Try increasing `gpu_memory_utilization` or decreasing "
    "`max_model_len` when initializing the engine."
)


def _codes(diagnoses: list[dict[str, Any]]) -> list[str]:
    return [d["code"] for d in diagnoses]


def test_mamba_block_error_yields_numeric_cap() -> None:
    (d,) = diagnose_boot(MAMBA_LOG)
    assert d["code"] == "mamba_blocks_exceeded"
    assert d["suggested_value"] == 96
    assert "--max-num-seqs" in d["fix_args"]


def test_kv_too_small_extracts_estimated_max_len() -> None:
    (d,) = diagnose_boot(KV_LOG)
    assert d["code"] == "kv_cache_too_small"
    assert d["suggested_value"] == 52416
    assert "52,416" in d["fix"]


@pytest.mark.parametrize(
    ("log", "code"),
    [
        ("No available memory for the cache blocks. Try increasing `gpu_memory_utilization`", "no_kv_memory"),
        (
            "Free memory on device (3/80 GiB) on startup is less than desired GPU memory utilization (0.9)",
            "gpu_memory_busy",
        ),
        ("torch.OutOfMemoryError: CUDA out of memory. Tried to allocate 2 GiB", "cuda_oom"),
        (
            "User-specified max_model_len (200000) is greater than the derived max_model_len (max_position_embeddings=131072)",
            "max_model_len_exceeds_model",
        ),
        ("max_num_batched_tokens (2048) is smaller than max_model_len (8192)", "batched_tokens_below_model_len"),
        (
            "Quantization method specified in the model config (fp8) does not match the quantization method specified in the `quantization` argument (awq)",
            "quantization_mismatch",
        ),
        ("Model architectures ['FooForCausalLM'] are not supported for now.", "unsupported_architecture"),
        ("Total number of attention heads (14) must be divisible by tensor parallel size (4).", "tp_not_divisible"),
        ("invalid tool call parser: nope (chose from { hermes })", "tool_parser_unknown"),
        ("Bfloat16 is only supported on GPUs with compute capability of at least 8.0.", "bf16_unsupported"),
    ],
)
def test_known_boot_errors(log: str, code: str) -> None:
    assert code in _codes(diagnose_boot(log))


def test_derived_max_len_is_parsed() -> None:
    log = "User-specified max_model_len (200000) is greater than the derived max_model_len (max_position_embeddings=131072)"
    (d,) = diagnose_boot(log)
    assert d["suggested_value"] == 131072


def test_pod_status_diagnoses_and_unrelated_logs() -> None:
    oom = diagnose_boot(
        "loading weights", {"state": "CrashLoopBackOff", "restarts": 3, "last_terminated_reason": "OOMKilled"}
    )
    assert _codes(oom) == ["container_oom_killed", "crash_loop"]
    assert _codes(diagnose_boot(None, {"state": "ImagePullBackOff"})) == ["image_pull"]
    assert diagnose_boot("INFO all good") == []
    assert diagnose_boot(None) == []


def test_summarize_diagnoses() -> None:
    assert summarize_diagnoses([]) is None
    text = summarize_diagnoses(diagnose_boot(MAMBA_LOG))
    assert text is not None and "96" in text


def _pod(name: str, ts: int, restarts: int, waiting: str | None, last_reason: str | None) -> Any:
    state = types.SimpleNamespace(
        waiting=types.SimpleNamespace(reason=waiting) if waiting else None, terminated=None, running=None
    )
    last = types.SimpleNamespace(
        terminated=types.SimpleNamespace(reason=last_reason, exit_code=137) if last_reason else None
    )
    cs = types.SimpleNamespace(name="kserve-container", restart_count=restarts, state=state, last_state=last)
    return types.SimpleNamespace(
        metadata=types.SimpleNamespace(name=name, creation_timestamp=datetime.fromtimestamp(ts, UTC)),
        status=types.SimpleNamespace(phase="Running", container_statuses=[cs]),
    )


@pytest.mark.asyncio
async def test_read_boot_report_picks_newest_pod_and_previous_logs(monkeypatch: pytest.MonkeyPatch) -> None:
    pods = types.SimpleNamespace(
        items=[_pod("old", 100, 0, None, None), _pod("new", 200, 2, "CrashLoopBackOff", "OOMKilled")]
    )
    calls: list[dict[str, Any]] = []

    def read_log(**kw: Any) -> str:
        calls.append(kw)
        return "previous crash" if kw["previous"] else ""

    core = types.SimpleNamespace(list_namespaced_pod=lambda **kw: pods, read_namespaced_pod_log=read_log)
    monkeypatch.setattr(k8s_operator.k8s_client, "CoreV1Api", lambda: core)
    report = await k8s_operator.read_boot_report("ns", "sel", "kserve-container", 50)
    assert report is not None
    assert report["pod"] == "new"
    assert report["state"] == "CrashLoopBackOff"
    assert report["last_terminated_reason"] == "OOMKilled"
    assert report["logs"] == "previous crash" and report["logs_source"] == "previous"
    assert calls[0]["container"] == "kserve-container" and calls[0]["previous"] is True


@pytest.mark.asyncio
async def test_on_trial_failure_broadcasts_diagnosis_without_analyst() -> None:
    tuner = AutoTuner(MagicMock(), MagicMock())
    tuner._assistant_enabled = lambda: False  # type: ignore[method-assign]
    tuner._broadcast = AsyncMock()  # type: ignore[method-assign]
    tuner._save_trial_fn = lambda: AsyncMock()  # type: ignore[method-assign]
    await tuner._on_trial_failure(4, {"max_num_seqs": 256}, "crash", MAMBA_LOG)
    event = tuner._broadcast.await_args_list[-1].args[0]
    assert event["type"] == "tuning_failure_explanation"
    assert event["data"]["trial_id"] == 4
    assert event["data"]["diagnoses"][0]["code"] == "mamba_blocks_exceeded"
    assert "96" in event["data"]["explanation"]
    assert tuner._trials[0].status == "failed"


def test_learn_limits_and_violation_rules() -> None:
    params = {"max_num_seqs": 256, "gpu_memory_utilization": 0.85, "max_model_len": 8192}
    limits = learn_limits(diagnose_boot(MAMBA_LOG), params)
    assert limits == [{"param": "max_num_seqs", "max": 96, "util": 0.85, "code": "mamba_blocks_exceeded"}]
    assert first_violated_limit({"max_num_seqs": 128, "gpu_memory_utilization": 0.8}, limits) == limits[0]
    assert first_violated_limit({"max_num_seqs": 96, "gpu_memory_utilization": 0.8}, limits) is None
    assert first_violated_limit({"max_num_seqs": 128, "gpu_memory_utilization": 0.9}, limits) is None
    kv = learn_limits(diagnose_boot(KV_LOG), params)
    assert kv[0]["param"] == "max_model_len" and kv[0]["max"] == 52416
    derived = learn_limits(
        diagnose_boot(
            "User-specified max_model_len (200000) is greater than the derived max_model_len (max_position_embeddings=131072)"
        ),
        params,
    )
    assert derived[0]["util"] is None
    assert first_violated_limit({"max_model_len": 262144, "gpu_memory_utilization": 0.99}, derived) == derived[0]
    assert learn_limits(diagnose_boot("loading"), params) == []


def test_compact_failure_trims_to_three() -> None:
    diagnoses = [{"code": str(i), "title": "t", "fix": "f", "cause": "c"} for i in range(5)]
    out = compact_failure("crash", diagnoses)
    assert out["reason"] == "crash" and len(out["diagnoses"]) == 3
    assert set(out["diagnoses"][0]) == {"code", "title", "fix"}


@pytest.mark.parametrize(
    ("cr_type", "selector", "container"),
    [
        ("inferenceservice", "serving.kserve.io/inferenceservice=m", "kserve-container"),
        ("llminferenceservice", "app.kubernetes.io/name=m,kserve.io/component=workload", "main"),
    ],
)
def test_boot_diagnosis_endpoint_both_cr_types(cr_type: str, selector: str, container: str) -> None:
    from ..main import app

    assert get_cr_adapter(cr_type).pod_label_selector("m") == selector
    handler_globals = get_route_handler_globals(app, "/api/tuner/boot-diagnosis", "GET")
    assert handler_globals is not None
    fake = AsyncMock(
        return_value={"pod": "p", "container": container, "state": "Error", "restarts": 1, "logs": MAMBA_LOG}
    )
    original = handler_globals["read_boot_report"]
    handler_globals["read_boot_report"] = fake
    try:
        resp = TestClient(app).get(f"/api/tuner/boot-diagnosis?namespace=ns&is_name=m&cr_type={cr_type}")
    finally:
        handler_globals["read_boot_report"] = original
    assert resp.status_code == 200
    data = resp.json()
    assert fake.await_args.args[:3] == ("ns", selector, container)
    assert data["available"] is True
    assert data["diagnoses"][0]["code"] == "mamba_blocks_exceeded"
    assert "logs" not in data["pod"]
    assert data["log_tail"] and "Mamba" in data["log_tail"]


def _fixture(name: str) -> str:
    from pathlib import Path

    return (Path(__file__).parent / "fixtures" / name).read_text()


def test_real_vllm_030_openvino_kv_too_small_log() -> None:
    """Captured from a crash-looping dev InferenceService (--max-model-len=2000000, vLLM 0.30.0 OpenVINO)."""
    diagnoses = {d["code"]: d for d in diagnose_boot(_fixture("vllm030_openvino_kv_too_small.log"))}
    kv = diagnoses["kv_cache_too_small"]
    assert kv["suggested_value"] == 257504
    assert "larger than the available KV cache memory" in kv["evidence"]
    assert diagnoses["max_model_len_exceeds_model"]["suggested_value"] == 262144
