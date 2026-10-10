"""
Auto Tuner Router
Provides endpoints for viewing tuning status, trials, and applying best parameters.
"""

import asyncio
import json
import logging
import time
import uuid
from dataclasses import replace
from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query, Request, Response
from fastapi.responses import StreamingResponse
from kubernetes.client.exceptions import ApiException
from models.load_test import (
    TUNING_DEFAULTS,
    ErrorResponse,
    TuningConfig,
    TuningSessionDetail,
    TuningSessionSummary,
)
from pydantic import BaseModel, Field
from services.auto_tuner import AutoTuner
from services.boot_diagnosis import LEARNED_LIMIT_TTL_S, diagnose_boot
from services.cr_adapter import CRAdapter, config_dict_to_args_list, extract_arg_value, get_cr_adapter
from services.k8s_operator import read_boot_report
from services.llm_assistant import get_llm_assistant
from services.model_analysis import (
    DEFAULT_MAX_NUM_BATCHED_TOKENS,
    DEFAULT_UTILIZATION,
    ModelAnalysis,
    calibrated_overhead_gib,
    capacity_table,
    clamp_search_space_to_cap,
    gpu_overhead_gib,
    mamba_seq_cap,
    memory_budget,
    observed_capacity,
    suggest_search_space,
)
from services.model_config_reader import get_model_config_reader
from services.serving_advisor import recommend_serving_args
from services.shared import load_engine, multi_target_collector, runtime_config, storage

logger = logging.getLogger(__name__)
router = APIRouter()

auto_tuner = AutoTuner(metrics_collector=multi_target_collector, load_engine=load_engine)


class TunerStatusResponse(BaseModel):
    """Response for tuner status"""

    status: str = "idle"  # "idle", "running", "completed", "error"
    current_trial: int | None = None
    total_trials: int | None = None
    best_metric: float | None = None
    elapsed_seconds: float | None = None
    message: str | None = None
    wait_metrics: dict[str, Any] | None = None


class TrialInfo(BaseModel):
    """Information about a single tuning trial"""

    trial_number: int
    parameters: dict[str, Any]
    metrics: dict[str, float]
    status: str  # "running", "completed", "failed"
    timestamp: datetime | None = None


class ApplyBestResponse(BaseModel):
    """Response when applying best parameters"""

    success: bool
    message: str
    applied_parameters: dict[str, Any] | None = None
    deployment_name: str | None = None


class TuningStartRequest(BaseModel):
    """Max TPS for `eval_concurrency` users with p99 latency ≤ `p99_latency_sla_ms` (flat schema matching frontend)"""

    n_trials: int = Field(default=TUNING_DEFAULTS["n_trials"], ge=1, le=100)
    eval_requests: int = Field(default=TUNING_DEFAULTS["eval_requests"], ge=1, le=1000)
    eval_concurrency: int = Field(default=TUNING_DEFAULTS["eval_concurrency"], ge=1, le=512)
    p99_latency_sla_ms: int = Field(default=TUNING_DEFAULTS["p99_latency_sla_ms"], ge=100, le=600000)
    max_tokens: int = Field(default=TUNING_DEFAULTS["max_tokens"], ge=1, le=8192)
    max_model_len: int = Field(default=TUNING_DEFAULTS["max_model_len"], ge=256)
    vllm_endpoint: str = ""
    max_num_seqs_min: int = TUNING_DEFAULTS["max_num_seqs_min"]
    max_num_seqs_max: int = TUNING_DEFAULTS["max_num_seqs_max"]
    gpu_memory_min: float = TUNING_DEFAULTS["gpu_memory_min"]
    gpu_memory_max: float = TUNING_DEFAULTS["gpu_memory_max"]
    max_num_batched_tokens_min: int = TUNING_DEFAULTS["max_num_batched_tokens_min"]
    max_num_batched_tokens_max: int = TUNING_DEFAULTS["max_num_batched_tokens_max"]
    auto_benchmark: bool = False
    enable_llm_assistant: bool = TUNING_DEFAULTS["enable_llm_assistant"]
    accelerator_memory_gib: float | None = Field(default=None, gt=0, le=1024)
    vllm_namespace: str | None = None
    vllm_is_name: str | None = None
    vllm_cr_type: Literal["inferenceservice", "llminferenceservice"] | None = None


class TuningStartResponse(BaseModel):
    """Response when starting auto-tuning"""

    success: bool
    message: str
    tuning_id: str | None = None


class BestTrialInfo(BaseModel):
    """Best trial info for frontend"""

    params: dict[str, Any]
    tps: float
    p99_latency: float
    sla_met: bool = True


class TunerStatusFrontendResponse(BaseModel):
    """Frontend-compatible tuner status response"""

    running: bool
    trials_completed: int = 0
    best: BestTrialInfo | None = None
    status: str | None = None
    best_score_history: list[float] = []
    last_rollback_trial: int | None = None


class TrialFrontendInfo(BaseModel):
    """Frontend-compatible trial info"""

    id: int
    tps: float
    p99_latency: float  # milliseconds
    params: dict[str, Any]
    score: float
    status: str
    sla_met: bool | None = None
    pruned: bool = False
    failure: dict[str, Any] | None = None


class TunerAllResponse(BaseModel):
    """Combined response for status, trials, and importance"""

    status: TunerStatusFrontendResponse
    trials: list[TrialFrontendInfo]
    importance: dict[str, Any]


async def _auto_save_tuning_session() -> None:
    try:
        existing_trials = await storage.get_trials()
        if existing_trials:
            best = auto_tuner.best
            session_data = {
                "timestamp": time.time(),
                "objective": auto_tuner._config.objective_label if auto_tuner._config else "",
                "n_trials": len(existing_trials),
                "best_tps": best.tps if best else None,
                "best_p99": best.p99_latency * 1000 if best else None,
                "best_score": auto_tuner._best_trial.score if auto_tuner._best_trial else None,
                "trials_json": json.dumps([t.model_dump() for t in existing_trials], default=str),
                "importance_json": json.dumps(await auto_tuner.get_importance()),
            }
            await storage.save_tuning_session(session_data)
    except (
        OSError,
        ValueError,
        RuntimeError,
    ) as e:  # intentional: fail-open, session auto-save must not block new tuning run
        logger.warning("[Tuner] Failed to auto-save tuning session before new run: %s", e)


def _parse_memory_gib(value: str) -> float | None:
    v = value.strip()
    try:
        if v.endswith("Gi"):
            return float(v[:-2])
        if v.endswith("Mi"):
            return float(v[:-2]) / 1024
        if v.endswith("Ki"):
            return float(v[:-2]) / (1024**2)
        if v.endswith("G"):
            return float(v[:-1]) * 1e9 / (1024**3)
        if v.endswith("M"):
            return float(v[:-1]) * 1e6 / (1024**3)
        return float(v) / (1024**3)
    except ValueError:
        return None


class ModelAnalysisResponse(BaseModel):
    """Deterministic analysis of the current tuning target (config.json + CR + memory budget)."""

    target: dict[str, str]
    available: bool = False
    model: dict[str, Any] | None = None
    runtime: dict[str, Any] = Field(default_factory=dict)
    memory_budget: dict[str, Any] = Field(default_factory=dict)
    capacity: list[dict[str, Any]] = Field(default_factory=list)
    observed: dict[str, Any] | None = None
    suggested_search_space: dict[str, int] | None = None
    max_model_len_limit: int | None = None
    advice: dict[str, Any] | None = None
    analyst_available: bool = False
    warnings: list[str] = Field(default_factory=list)


def _positive_number(value: Any, cast: type[int] | type[float]) -> float | int | None:
    try:
        number = cast(float(value)) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None
    return number if number and number > 0 else None


class ModelAnalysisExplainResponse(BaseModel):
    markdown: str | None = None
    analyst_available: bool = False


async def _read_target_spec(namespace: str, is_name: str, adapter: CRAdapter) -> dict[str, Any] | None:
    custom = auto_tuner._k8s_custom
    if custom is None:
        return None
    try:
        obj = await asyncio.to_thread(
            custom.get_namespaced_custom_object,
            group=adapter.api_group(),
            version=adapter.api_version(),
            namespace=namespace,
            plural=adapter.api_plural(),
            name=is_name,
        )
    except ApiException as e:
        logger.warning("[Tuner] Failed to read %s/%s for model analysis: %s", namespace, is_name, e.reason)
        return None
    return obj.get("spec", {}) if isinstance(obj, dict) else None


async def _analyze_target(
    vllm_endpoint: str,
    accelerator_memory_gib: float | None,
    utilization: float | None,
    refresh: bool = False,
    target: tuple[str, str, str] | None = None,
) -> tuple[ModelAnalysisResponse, ModelAnalysis | None, dict[str, Any] | None, CRAdapter]:
    """Analyze ``target`` (namespace, name, cr_type) or, when None, the runtime-config target.

    ``utilization`` None → the target's own ``--gpu-memory-utilization``, else DEFAULT_UTILIZATION.
    """
    if target is not None:
        namespace, is_name, cr_type = target
        adapter = get_cr_adapter(cr_type)
        cr_spec = await _read_target_spec(namespace, is_name, adapter)
    else:
        namespace, is_name, cr_type = auto_tuner.target
        cr_spec, adapter = await auto_tuner.get_cr_context()

    assistant = get_llm_assistant()
    resp = ModelAnalysisResponse(
        target={"namespace": namespace, "name": is_name, "cr_type": cr_type},
        analyst_available=assistant.available,
    )
    if assistant.available and assistant.endpoint == vllm_endpoint.rstrip("/"):
        resp.warnings.append("분석 LLM(ANALYST_ENDPOINT)이 튜닝 대상과 같음 — 튜닝 중 분석 LLM 호출은 생략됩니다")

    storage_uri: str | None = None
    pod_selector: str | None = None
    container: str | None = None
    resources: dict[str, Any] = {}
    static_args: list[str] = []
    if cr_spec is None:
        resp.warnings.append("대상 CR을 읽지 못함 — 대상 설정과 RBAC를 확인하세요")
    else:
        storage_uri = adapter.read_model_uri(cr_spec)
        pod_selector = adapter.pod_label_selector(is_name)
        container = adapter.model_container_name()
        resources = adapter.read_resources(cr_spec)
        static_args = adapter.read_extra_args(cr_spec)

    reader = get_model_config_reader()
    if refresh:
        reader.invalidate(storage_uri)
    if pod_selector:
        resp.observed = await reader.read_observed_kv(
            namespace, pod_selector, adapter.metrics_port(), adapter.metrics_scheme()
        )
    analysis = await reader.read(
        vllm_endpoint=vllm_endpoint,
        storage_uri=storage_uri,
        namespace=namespace if pod_selector else None,
        pod_label_selector=pod_selector,
        container=container,
        kv_cache_dtype=extract_arg_value(static_args, "--kv-cache-dtype"),
    )
    if analysis is None:
        resp.warnings.append("모델 정보를 읽지 못함 — 엔드포인트 응답과 pods/exec 권한을 확인하세요")
        return resp, None, cr_spec, adapter

    resp.available = True
    resp.model = analysis.to_dict()
    resp.warnings.extend(analysis.warnings)

    budget = memory_budget(resources, accelerator_memory_gib, _parse_memory_gib, openvino=analysis.openvino)
    if budget.source == "accelerator":
        budget = replace(budget, overhead_gib=gpu_overhead_gib(budget.gpu_count))
    tp = extract_arg_value(static_args, "--tensor-parallel-size") or extract_arg_value(static_args, "-tp")
    tp_size = int(tp) if tp and tp.isdigit() else None
    current_args = adapter.read_args(cr_spec) if cr_spec is not None else {}
    utilization = (
        utilization or _positive_number(current_args.get("gpu_memory_utilization"), float) or DEFAULT_UTILIZATION
    )
    batched = _positive_number(current_args.get("max_num_batched_tokens"), int) or (
        DEFAULT_MAX_NUM_BATCHED_TOKENS if budget.gpu_count > 0 else None
    )
    resp.runtime = {
        "gpu_count": budget.gpu_count,
        "tensor_parallel_size": tp_size,
        "kv_cache_dtype": analysis.kv_cache_dtype,
        "max_num_batched_tokens": batched,
        "current_args": current_args,
    }
    resp.memory_budget = {
        "gib": budget.gib,
        "source": budget.source,
        "utilization": None if budget.dedicated_kv else utilization,
        "dedicated_kv": budget.dedicated_kv,
        "overhead_gib": budget.overhead_gib,
        "overhead_source": "table" if budget.source == "accelerator" else None,
    }
    if cr_spec is not None:
        resp.advice = recommend_serving_args(
            analysis,
            static_args + config_dict_to_args_list(current_args),
            budget.gpu_count,
            tp_size,
            mamba_seq_cap(analysis, resp.observed),
        )
    observed = resp.observed
    if budget.source == "unknown_accelerator_memory" and observed is None:
        resp.warnings.append("GPU 장당 메모리(GiB)를 입력하면 동시 시퀀스 상한과 탐색 범위를 계산합니다")
    if budget.source == "openvino_kvcache_space" and observed is None:
        resp.warnings.append(
            "OpenVINO KV 공간을 VLLM_OPENVINO_KVCACHE_SPACE 기본값(4 GiB)·u8로 가정 — 런타임 env로 바꿨다면 다를 수 있습니다"
        )
    served_len = analysis.served_max_model_len
    resp.max_model_len_limit = analysis.context_limit or analysis.max_position_embeddings
    if budget.gib:
        max_context = analysis.context_limit or analysis.max_position_embeddings or served_len
        resp.capacity = capacity_table(analysis, budget, utilization, max_context, batched)
        resp.suggested_search_space = suggest_search_space(resp.capacity, served_len)
    if observed is not None:
        available_kv_gib = None
        if budget.source == "accelerator" and pod_selector:
            available_kv_gib = await reader.read_available_kv_gib(namespace, pod_selector, container)
            if available_kv_gib is not None:
                observed["available_kv_gib"] = available_kv_gib
        calibrated = calibrated_overhead_gib(
            analysis,
            budget,
            _positive_number(current_args.get("gpu_memory_utilization"), float) or DEFAULT_UTILIZATION,
            observed["kv_cache_size_tokens"],
            available_kv_gib,
        )
        if calibrated is not None and budget.source == "accelerator":
            budget = replace(budget, overhead_gib=calibrated)
            resp.memory_budget.update({"overhead_gib": calibrated, "overhead_source": "observed"})
            resp.capacity = capacity_table(analysis, budget, utilization, max_context, batched)
            resp.suggested_search_space = suggest_search_space(resp.capacity, served_len)
        estimated = next(
            (r["max_concurrent_seqs"] for r in resp.capacity if served_len and r["context_len"] == served_len), None
        )
        reported = observed.get("max_concurrency")
        observed["estimate_ratio"] = round(estimated / reported, 3) if estimated and reported else None
        resp.capacity = observed_capacity(
            resp.capacity, observed["kv_cache_size_tokens"], served_len, analysis, batched
        )
        resp.suggested_search_space = (
            suggest_search_space(resp.capacity, served_len, key="observed_max_seqs") or resp.suggested_search_space
        )
        seq_cap = mamba_seq_cap(analysis, observed)
        if seq_cap is not None:
            observed["mamba_seq_cap"] = seq_cap
            resp.suggested_search_space = clamp_search_space_to_cap(resp.suggested_search_space, seq_cap)
    return resp, analysis, cr_spec, adapter


@router.get("/model-analysis", response_model=ModelAnalysisResponse)
async def get_model_analysis(
    accelerator_memory_gib: float | None = Query(default=None, gt=0, le=1024),
    utilization: float | None = Query(default=None, gt=0, le=1.0),
    refresh: bool = False,
    namespace: str | None = Query(default=None),
    is_name: str | None = Query(default=None),
    cr_type: Literal["inferenceservice", "llminferenceservice"] | None = Query(default=None),
    endpoint: str | None = Query(default=None),
) -> ModelAnalysisResponse:
    """Analyze a target model from its config.json — KV per token, capacity, search ranges, serving-arg advice.

    Without namespace/is_name the runtime-config target is used.
    """
    target = (namespace, is_name, cr_type or runtime_config.cr_type) if namespace and is_name else None
    resp, *_ = await _analyze_target(
        endpoint or runtime_config.vllm_endpoint, accelerator_memory_gib, utilization, refresh=refresh, target=target
    )
    return resp


class BootDiagnosisResponse(BaseModel):
    target: dict[str, str]
    available: bool = False
    pod: dict[str, Any] | None = None
    diagnoses: list[dict[str, Any]] = Field(default_factory=list)
    log_tail: str | None = None


@router.get("/boot-diagnosis", response_model=BootDiagnosisResponse)
async def get_boot_diagnosis(
    namespace: str | None = Query(default=None),
    is_name: str | None = Query(default=None),
    cr_type: Literal["inferenceservice", "llminferenceservice"] | None = Query(default=None),
    tail_lines: int = Query(default=300, ge=20, le=2000),
) -> BootDiagnosisResponse:
    """Why a target's vLLM pod is failing to boot: container status + previous/current log, matched to known causes.

    Without namespace/is_name the runtime-config target is used.
    """
    if namespace and is_name:
        ns, name, resolved_cr = namespace, is_name, cr_type or runtime_config.cr_type
    else:
        ns, name, resolved_cr = auto_tuner.target
    adapter = get_cr_adapter(resolved_cr)
    resp = BootDiagnosisResponse(target={"namespace": ns, "name": name, "cr_type": resolved_cr})
    report = await read_boot_report(ns, adapter.pod_label_selector(name), adapter.model_container_name(), tail_lines)
    if report is None:
        return resp
    logs = report.pop("logs", None)
    resp.available = True
    resp.pod = report
    resp.diagnoses = diagnose_boot(logs, report)
    resp.log_tail = "\n".join(logs.splitlines()[-40:]) if logs else None
    return resp


@router.post("/model-analysis/explain", response_model=ModelAnalysisExplainResponse)
async def explain_model_analysis(body: ModelAnalysisResponse) -> ModelAnalysisExplainResponse:
    """Narrate an analysis with the analyst LLM (ANALYST_ENDPOINT). Numbers come only from the input."""
    assistant = get_llm_assistant()
    if not assistant.available or not body.available:
        return ModelAnalysisExplainResponse(markdown=None, analyst_available=assistant.available)
    payload = body.model_dump(exclude={"analyst_available"})
    payload["runtime"] = {k: v for k, v in body.runtime.items() if k != "current_args"}
    markdown = await assistant.explain_model_analysis(payload)
    return ModelAnalysisExplainResponse(markdown=markdown, analyst_available=True)


async def _build_tuning_config(body: TuningStartRequest, target: tuple[str, str, str]) -> tuple[TuningConfig, str]:
    import os

    if body.vllm_endpoint:
        vllm_endpoint = body.vllm_endpoint
    elif body.vllm_namespace and body.vllm_is_name:
        # Load must hit the CR the trials patch, not the process-wide default endpoint.
        vllm_endpoint = get_cr_adapter(target[2]).default_endpoint(target[1], target[0])
    else:
        vllm_endpoint = os.getenv("VLLM_ENDPOINT", "http://localhost:8000")

    analysis: ModelAnalysis | None = None
    analysis_resp: ModelAnalysisResponse | None = None
    served_model_name_warning: str | None = None
    try:
        analysis_resp, analysis, cr_spec, adapter = await _analyze_target(
            vllm_endpoint, body.accelerator_memory_gib, DEFAULT_UTILIZATION, target=target
        )
        if analysis and analysis.served_model_name and cr_spec is not None:
            cr_served_name = adapter.resolve_model_name(cr_spec, target[1])
            if analysis.served_model_name != cr_served_name:
                served_model_name_warning = (
                    f"--served-model-name 불일치: CR에 설정된 '{cr_served_name}'이(가) "
                    f"vLLM이 실제 서빙 중인 '{analysis.served_model_name}'과 다릅니다. "
                    f"CR의 --served-model-name을 수정하세요."
                )
    except Exception as e:
        logger.warning("[Tuner] Model analysis failed, using blind search: %s", e)

    model_max_position_embeddings = (analysis.context_limit or analysis.max_position_embeddings) if analysis else None
    if model_max_position_embeddings and body.max_model_len > model_max_position_embeddings:
        raise HTTPException(
            status_code=400,
            detail=ErrorResponse(
                error=f"max_model_len {body.max_model_len}이 모델 상한 {model_max_position_embeddings}을 넘습니다.",
                error_type="invalid_max_model_len",
            ).model_dump(),
        )
    memory_budget_gib = analysis_resp.memory_budget.get("gib") if analysis_resp else None
    analysis_summary: dict[str, Any] | None = None
    if analysis_resp and analysis_resp.available:
        analysis_summary = {
            "model": analysis_resp.model,
            "memory_budget": analysis_resp.memory_budget,
            "capacity": analysis_resp.capacity,
            "observed": analysis_resp.observed,
        }

    target_key = "/".join(target)
    try:
        learned_limits = await storage.get_learned_limits(target_key, LEARNED_LIMIT_TTL_S)
    except Exception as e:
        logger.warning("[Tuner] Could not load learned limits: %s", e)
        learned_limits = []

    config = TuningConfig(
        learned_limits=learned_limits,
        max_num_seqs_range=(body.max_num_seqs_min, body.max_num_seqs_max),
        gpu_memory_utilization_range=(body.gpu_memory_min, body.gpu_memory_max),
        max_num_batched_tokens_range=(body.max_num_batched_tokens_min, body.max_num_batched_tokens_max),
        max_model_len=body.max_model_len,
        eval_concurrency=body.eval_concurrency,
        p99_latency_sla_ms=body.p99_latency_sla_ms,
        max_tokens=body.max_tokens,
        eval_requests=body.eval_requests,
        n_trials=body.n_trials,
        model_max_position_embeddings=model_max_position_embeddings,
        model_weight_gib=analysis.model_weight_gib if analysis else None,
        memory_budget_gib=memory_budget_gib,
        memory_budget_dedicated_kv=bool(analysis_resp and analysis_resp.memory_budget.get("dedicated_kv")),
        memory_overhead_gib=float(analysis_resp.memory_budget.get("overhead_gib") or 0.0) if analysis_resp else 0.0,
        served_model_name_warning=served_model_name_warning,
        target_key=target_key,
        model_kv_bytes_per_token=analysis.kv_bytes_per_token if analysis else None,
        model_sliding_kv_bytes_per_token=analysis.sliding_kv_bytes_per_token if analysis else 0,
        model_sliding_window=analysis.sliding_window if analysis else None,
        model_linear_state_bytes_per_seq=analysis.boot_state_bytes_per_seq if analysis else 0,
        model_analysis=analysis_summary,
        enable_llm_assistant=body.enable_llm_assistant,
    )
    return config, vllm_endpoint


async def _run_preflight_or_raise() -> None:
    try:
        preflight = await auto_tuner._preflight_check()
    except (RuntimeError, ValueError, ApiException) as exc:
        raise HTTPException(
            status_code=400,
            detail=ErrorResponse(
                error=f"Preflight check failed: {exc}",
                error_type="preflight_error",
            ).model_dump(),
        ) from exc
    if not preflight.get("success"):
        raise HTTPException(
            status_code=400,
            detail=ErrorResponse(
                error=preflight.get("error", "Preflight check failed"),
                error_type=preflight.get("error_type", "preflight_error"),
            ).model_dump(),
        )


@router.post(
    "/start",
    response_model=TuningStartResponse,
    responses={
        400: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
    },
)
async def start_tuning(request: Request, body: TuningStartRequest) -> dict[str, Any]:
    """Start Bayesian optimization to find best vLLM parameters."""
    if auto_tuner.is_running:
        raise HTTPException(
            status_code=409,
            detail=ErrorResponse(
                error="Tuning is already running. Wait for it to complete or stop it first.",
                error_type="already_running",
            ).model_dump(),
        )
    await _auto_save_tuning_session()
    try:
        await storage.clear_trials()
    except (
        OSError,
        ValueError,
        RuntimeError,
    ) as e:  # intentional: fail-open, storage clear failure must not block new tuning session
        logger.warning("[Tuner] Failed to clear trials from storage before new session: %s", e)
    if body.vllm_namespace and body.vllm_is_name:
        target = (body.vllm_namespace, body.vllm_is_name, body.vllm_cr_type or runtime_config.cr_type)
    else:
        target = (
            runtime_config.vllm_namespace or "default",
            runtime_config.vllm_is_name or "llm-ov",
            runtime_config.cr_type,
        )
    # Trials patch/recreate this CR; it stays pinned afterwards so apply-best hits the tuned target.
    auto_tuner.set_target(*target)
    config, vllm_endpoint = await _build_tuning_config(body, target)
    await _run_preflight_or_raise()
    tuning_id = str(uuid.uuid4())
    auto_tuner._current_task = asyncio.create_task(
        auto_tuner.start(
            config,
            vllm_endpoint,
            auto_benchmark=body.auto_benchmark,
            skip_preflight=True,
        )
    )
    auto_tuner._current_task.add_done_callback(
        lambda t: logger.error("[AutoTuner] Task failed: %s", t.exception()) if t.exception() else None
    )
    return {
        "success": True,
        "message": f"Tuning started with {body.n_trials} trials",
        "tuning_id": tuning_id,
    }


@router.get("/status", response_model=TunerStatusFrontendResponse)
async def get_tuner_status() -> TunerStatusFrontendResponse:
    """Get current auto-tuning status."""
    # Frontend-friendly status payload
    best_info = None
    if auto_tuner.best is not None:
        best_info = BestTrialInfo(
            params=auto_tuner.best.params,
            tps=auto_tuner.best.tps,
            p99_latency=auto_tuner.best.p99_latency * 1000,
            sla_met=auto_tuner.best.score >= 0,
        )
    status_value = "running" if auto_tuner.is_running else "idle"
    return TunerStatusFrontendResponse(
        running=auto_tuner.is_running,
        trials_completed=sum(1 for t in auto_tuner.trials if t.status != "skipped"),
        best=best_info,
        status=status_value,
        best_score_history=getattr(auto_tuner, "_best_score_history", []),
        last_rollback_trial=auto_tuner._last_rollback_trial,
    )


@router.get("/trials", response_model=list[TrialFrontendInfo])
async def get_tuning_trials(
    limit: int = Query(default=20, ge=1),
    offset: int = Query(default=0, ge=0),
    response: Response = None,
) -> list[TrialFrontendInfo]:
    """Get list of tuning trials."""
    try:
        all_trials = await storage.get_trials()
        if not all_trials:
            all_trials = auto_tuner.trials
    except (OSError, ValueError, RuntimeError):  # intentional: fail-open, in-memory fallback when storage unavailable
        all_trials = auto_tuner.trials
    total = len(all_trials)
    # most-recent first: reverse, slice, then return
    trials_desc = list(reversed(all_trials))
    trials = trials_desc[offset : offset + limit]
    if response is not None:
        response.headers["X-Total-Count"] = str(total)
    return [
        TrialFrontendInfo(
            id=t.trial_id,
            tps=t.tps,
            p99_latency=t.p99_latency * 1000,
            params=t.params,
            score=t.score,
            status=t.status,
            sla_met=t.score >= 0 if t.status in ("completed", "pruned") else None,
            pruned=getattr(t, "pruned", False),
            failure=getattr(t, "failure", None),
        )
        for t in trials
    ]


@router.delete("/learned-limits")
async def clear_learned_limits() -> dict[str, int]:
    """Forget search-space limits learned from earlier boot failures of the current target."""
    return {"cleared": await storage.clear_learned_limits("/".join(auto_tuner.target))}


@router.post("/stop")
async def stop_tuning() -> dict[str, Any]:
    """Stop the running auto-tuning process."""
    return await auto_tuner.stop()


@router.get("/stream")
async def stream_tuner_events() -> StreamingResponse:
    """Stream tuning events via Server-Sent Events (SSE)."""

    async def event_generator():
        """Async generator that streams tuner progress events via SSE."""
        q = await auto_tuner.subscribe()
        try:
            yield f"data: {json.dumps({'type': 'connected', 'data': {'running': auto_tuner.is_running}})}\n\n"

            keepalive_count = 0
            while True:
                try:
                    event = await asyncio.wait_for(q.get(), timeout=30.0)
                    yield f"data: {json.dumps(event)}\n\n"

                    event_type = event.get("type")
                    if event_type == "tuning_complete":
                        break
                    if event_type == "error" and not event.get("data", {}).get("recoverable", True):
                        break
                except TimeoutError:
                    yield ": keepalive\n\n"
                    keepalive_count += 1
                    if keepalive_count > 20:  # Max 10 minutes of keepalive
                        break
        except asyncio.CancelledError:
            logger.debug("[SSE] Tuner stream client disconnected, cleaning up")
            raise
        finally:
            await auto_tuner.unsubscribe(q)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/importance")
async def get_parameter_importance() -> dict[str, Any]:
    """Get parameter importance from tuning trials (actual implementation)."""
    # Use the AutoTuner's implementation which computes importances via Optuna
    # FAnova if enough trials have been run. Returns {} when not enough data.
    return await auto_tuner.get_importance()


@router.get("/all", response_model=TunerAllResponse)
async def get_tuner_all() -> TunerAllResponse:
    """Get combined tuner state: status, trials, and importance in one request."""
    status = await get_tuner_status()
    trials = await get_tuning_trials()
    importance = await get_parameter_importance()
    return TunerAllResponse(status=status, trials=trials, importance=importance)


@router.post("/apply-best", response_model=ApplyBestResponse)
async def apply_best_parameters() -> ApplyBestResponse:
    """Apply the best parameters found by auto-tuning to vLLM deployment."""

    # If no best trial is available yet
    if auto_tuner.best is None:
        return ApplyBestResponse(
            success=False,
            message="No best trial available. Run tuning first.",
            applied_parameters=None,
            deployment_name=None,
        )
    # If tuning is currently running, do not apply
    if auto_tuner.is_running:
        return ApplyBestResponse(
            success=False,
            message="Tuning is in progress. Wait for completion or stop first.",
            applied_parameters=None,
            deployment_name=None,
        )

    result = await auto_tuner._apply_params(auto_tuner.best.params)
    if isinstance(result, dict) and result.get("success"):
        namespace, is_name, _cr_type = auto_tuner.target
        return ApplyBestResponse(
            success=True,
            message="Best parameters applied successfully.",
            applied_parameters=auto_tuner.best.params,
            deployment_name=f"{namespace}/{is_name}",
        )
    return ApplyBestResponse(
        success=False,
        message=result.get("error", "Failed to apply parameters."),
        applied_parameters=None,
        deployment_name=None,
    )


@router.get("/sessions", response_model=list[TuningSessionSummary])
async def list_tuning_sessions(
    limit: int = Query(default=20, ge=1),
    offset: int = Query(default=0, ge=0),
    response: Response = None,
) -> list[TuningSessionSummary]:
    """List all saved tuning sessions with pagination."""
    total = await storage.count_tuning_sessions()
    rows = await storage.list_tuning_sessions(limit=limit, offset=offset)
    if response is not None:
        response.headers["X-Total-Count"] = str(total)
    return [TuningSessionSummary(**row) for row in rows]


@router.get("/sessions/{session_id}", response_model=TuningSessionDetail)
async def get_tuning_session(session_id: int) -> TuningSessionDetail:
    """Retrieve detailed tuning session data by ID."""
    row = await storage.get_tuning_session(session_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
    return TuningSessionDetail(**row)


@router.delete("/sessions/{session_id}")
async def delete_tuning_session(session_id: int) -> dict[str, Any]:
    """Delete a tuning session by ID."""
    deleted = await storage.delete_tuning_session(session_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
    return {"success": True, "id": session_id}
