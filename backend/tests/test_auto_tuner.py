import os
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from kubernetes.client.exceptions import ApiException

from ..models.load_test import TuningConfig, TuningTrial
from ..services import auto_tuner as auto_tuner_module
from ..services import model_resolver as model_resolver_module
from ..services.auto_tuner import AutoTuner


class _DummyTrial:
    def __init__(self, number: int):
        self.number = number
        self.report = MagicMock()

    def should_prune(self) -> bool:
        return False


class _DummyStudy:
    def __init__(self, n_trials: int):
        self._trials = [_DummyTrial(i) for i in range(n_trials)]
        self._idx = 0
        self.tell_calls: list[dict[str, object]] = []
        self.optimize = MagicMock()

    def ask(self):
        trial = self._trials[self._idx]
        self._idx += 1
        return trial

    def tell(self, trial, value=None, state=None):
        self.tell_calls.append({"trial": trial, "value": value, "state": state})


@pytest.fixture
def mock_k8s_clients():
    with (
        patch.object(auto_tuner_module.k8s_config, "load_incluster_config", return_value=None),
        patch.object(auto_tuner_module.k8s_config, "load_kube_config", return_value=None),
        patch.object(auto_tuner_module.k8s_client, "AppsV1Api") as mock_apps_cls,
        patch.object(auto_tuner_module.k8s_client, "CustomObjectsApi") as mock_custom_cls,
    ):
        mock_apps_api = MagicMock()
        mock_custom_api = MagicMock()

        mock_custom_api.get_namespaced_custom_object.return_value = {
            "spec": {"predictor": {"model": {"args": []}}},
            "status": {"conditions": [{"type": "Ready", "status": "True"}]},
        }
        mock_custom_api.delete_namespaced_custom_object.return_value = {}
        mock_custom_api.create_namespaced_custom_object.return_value = {}

        mock_apps_cls.return_value = mock_apps_api
        mock_custom_cls.return_value = mock_custom_api

        yield {"apps": mock_apps_api, "custom": mock_custom_api}


@pytest.fixture
def auto_tuner_instance(mock_k8s_clients):
    metrics_collector = AsyncMock()
    load_engine = AsyncMock()
    tuner = AutoTuner(metrics_collector, load_engine)
    tuner._cooldown_secs = 0
    tuner._k8s_available = True
    tuner._k8s_operator._wait_for_deletion = AsyncMock(return_value=None)
    return tuner


@pytest.mark.asyncio
async def test_start_happy_path_two_trials_returns_best_result(auto_tuner_instance):
    tuner = auto_tuner_instance
    mock_study = _DummyStudy(n_trials=2)

    params_0 = {
        "max_num_seqs": 64,
        "gpu_memory_utilization": 0.8,
        "max_model_len": 2048,
        "max_num_batched_tokens": 256,
        "enable_chunked_prefill": False,
        "enable_enforce_eager": False,
    }
    params_1 = {
        "max_num_seqs": 128,
        "gpu_memory_utilization": 0.85,
        "max_model_len": 4096,
        "max_num_batched_tokens": 512,
        "enable_chunked_prefill": True,
        "enable_enforce_eager": False,
    }

    tuner._preflight_check = AsyncMock(return_value={"success": True})
    tuner._wait_for_ready = AsyncMock(return_value=True)
    tuner._apply_params = AsyncMock(return_value={"success": True})
    tuner._suggest_params = MagicMock(side_effect=[params_0, params_1])
    tuner._run_trial_evaluation = AsyncMock(side_effect=[(10.0, 50.0, 0.5), (20.0, 60.0, 0.3)])

    with (
        patch.object(auto_tuner_module.optuna, "create_study", return_value=mock_study) as create_study_mock,
        patch.object(auto_tuner_module.storage, "set_running", new=AsyncMock(return_value=101)),
        patch.object(auto_tuner_module.storage, "clear_running", new=AsyncMock()),
        patch.object(auto_tuner_module.storage, "save_trial", new=AsyncMock()),
    ):
        result = await tuner.start(
            TuningConfig(n_trials=2, eval_requests=5, warmup_requests=0, objective="tps"),
            "http://mock-vllm:8080",
        )

    assert result["completed"] is True
    assert result["trials"] == 2
    assert result["best_score"] == 20.0
    assert result["best_params"] == params_1
    create_study_mock.assert_called_once()
    mock_study.optimize.assert_not_called()


@pytest.mark.asyncio
async def test_apply_params_handles_k8s_api_exception_during_patch(auto_tuner_instance, mock_k8s_clients):
    tuner = auto_tuner_instance
    mock_custom_api = mock_k8s_clients["custom"]
    mock_custom_api.create_namespaced_custom_object.side_effect = ApiException(status=403, reason="Forbidden")

    result = await tuner._apply_params(
        {
            "max_num_seqs": 64,
            "gpu_memory_utilization": 0.8,
            "max_model_len": 2048,
            "max_num_batched_tokens": 256,
            "enable_chunked_prefill": False,
            "enable_enforce_eager": False,
        }
    )

    assert result["success"] is False
    assert result["error_type"] == "rbac"
    assert "403" in result["error"]


@pytest.mark.asyncio
async def test_start_handles_vllm_connect_error_gracefully(auto_tuner_instance):
    tuner = auto_tuner_instance
    mock_study = _DummyStudy(n_trials=1)

    tuner._preflight_check = AsyncMock(return_value={"success": True})
    tuner._wait_for_ready = AsyncMock(return_value=True)
    tuner._apply_params = AsyncMock(return_value={"success": True})
    tuner._suggest_params = MagicMock(
        return_value={
            "max_num_seqs": 64,
            "gpu_memory_utilization": 0.8,
            "max_model_len": 2048,
            "max_num_batched_tokens": 256,
            "enable_chunked_prefill": False,
            "enable_enforce_eager": False,
        }
    )
    tuner._run_trial_evaluation = AsyncMock(
        side_effect=httpx.ConnectError(
            "vLLM endpoint unreachable",
            request=httpx.Request("POST", "http://mock-vllm:8080/v1/completions"),
        )
    )

    with (
        patch.object(auto_tuner_module.optuna, "create_study", return_value=mock_study),
        patch.object(auto_tuner_module.storage, "set_running", new=AsyncMock(return_value=202)),
        patch.object(auto_tuner_module.storage, "clear_running", new=AsyncMock()),
        patch.object(auto_tuner_module.storage, "save_trial", new=AsyncMock()),
    ):
        result = await tuner.start(
            TuningConfig(n_trials=1, eval_requests=5, warmup_requests=0, objective="tps"),
            "http://mock-vllm:8080",
        )

    assert result["completed"] is True
    assert result["trials"] == 0
    assert result["best_score"] == 0
    assert len(mock_study.tell_calls) == 1
    assert mock_study.tell_calls[0]["state"] == auto_tuner_module.optuna.trial.TrialState.FAIL


@pytest.mark.asyncio
async def test_start_rejects_concurrent_execution_guard(auto_tuner_instance):
    tuner = auto_tuner_instance

    async with tuner._lock:
        tuner._running = True

    result = await tuner.start(
        TuningConfig(n_trials=1, eval_requests=5, warmup_requests=0),
        "http://mock-vllm:8080",
    )

    assert "error" in result
    assert "실행 중" in result["error"]


@pytest.mark.asyncio
async def test_save_auto_benchmark_uses_env_fallback_when_model_resolution_unavailable(auto_tuner_instance):
    tuner = auto_tuner_instance
    tuner._vllm_endpoint = "http://mock-vllm:8080"
    tuner._config = TuningConfig(n_trials=1, eval_requests=11, eval_concurrency=3, eval_rps=5, warmup_requests=0)
    tuner._best_trial = TuningTrial(
        trial_id=0,
        params={"max_num_seqs": 64},
        tps=42.0,
        p99_latency=0.25,
        score=42.0,
        status="completed",
    )

    connect_error = httpx.ConnectError(
        "cannot reach /v1/models",
        request=httpx.Request("GET", "http://mock-vllm:8080/v1/models"),
    )
    save_benchmark_mock = AsyncMock(return_value=MagicMock(id=777))

    with (
        patch.object(auto_tuner_module, "resolve_model_name", new=AsyncMock(side_effect=connect_error)) as resolve_mock,
        patch.object(auto_tuner_module.storage, "save_benchmark", new=save_benchmark_mock),
        patch.dict(os.environ, {"VLLM_MODEL": "env-model-fallback"}, clear=False),
    ):
        benchmark_id = await tuner._save_auto_benchmark()

    assert benchmark_id == 777
    resolve_mock.assert_awaited_once_with("http://mock-vllm:8080")
    saved_benchmark = save_benchmark_mock.call_args.args[0]
    assert saved_benchmark.config.model == "env-model-fallback"


@pytest.mark.asyncio
async def test_evaluate_uses_mocked_httpx_async_client_for_model_lookup(auto_tuner_instance):
    from ..services import auto_tuner as auto_tuner_module

    tuner = auto_tuner_instance
    tuner._load_engine.run = AsyncMock(return_value={"tps": {"total": 30.0}, "latency": {"p99": 0.2}})

    with patch.object(
        auto_tuner_module, "resolve_model_name", new=AsyncMock(return_value="resolved-model")
    ) as resolve_mock:
        score, tps, p99 = await tuner._evaluate(
            "http://mock-vllm:8080",
            TuningConfig(eval_requests=2, warmup_requests=0, eval_concurrency=1, eval_rps=0),
        )

    resolve_mock.assert_awaited_once_with("http://mock-vllm:8080")
    assert tuner._load_engine.run.await_count == 2
    first_load_cfg = tuner._load_engine.run.await_args_list[0].args[0]
    assert first_load_cfg.model == "resolved-model"
    assert score == pytest.approx(30.0)
    assert tps == 30.0
    assert p99 == 0.2
