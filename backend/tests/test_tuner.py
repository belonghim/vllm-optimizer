import asyncio
import contextlib
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from kubernetes.client import AppsV1Api, CoreV1Api, CustomObjectsApi
from pydantic import ValidationError

from ..main import app
from ..models.load_test import LoadTestConfig, SweepConfig, SweepResult, TuningConfig, TuningTrial
from ..services.auto_tuner import AutoTuner, _get_k8s_namespace, _get_vllm_is_name
from ..services.load_engine import LoadTestEngine
from ..services.multi_target_collector import MultiTargetMetricsCollector

pytestmark = pytest.mark.slow


def _extract_tuning_args_from_created_cr(body: dict[str, Any]) -> list[str]:
    spec = body.get("spec", {})
    predictor_args = spec.get("predictor", {}).get("model", {}).get("args")
    if isinstance(predictor_args, list) and predictor_args:
        return predictor_args

    containers = spec.get("template", {}).get("containers", [])
    for container in containers:
        if container.get("name") != "main":
            continue
        for env in container.get("env", []):
            if env.get("name") == "VLLM_ADDITIONAL_ARGS":
                return str(env.get("value") or "").split()

    if isinstance(predictor_args, list):
        return predictor_args
    return []


def test_stream_endpoint_exists(client):
    routes = [route.path for route in client.app.routes]
    assert "/api/tuner/stream" in routes


def test_stream_endpoint_returns_sse_content_type(client):
    import asyncio
    from unittest.mock import patch

    class DummyAutoTuner:
        is_running = False

        async def subscribe(self):
            q = asyncio.Queue()

            async def pump():
                await asyncio.sleep(0.05)
                await q.put({"type": "test_event", "data": {"value": 42}})
                await asyncio.sleep(0.2)
                await q.put({"type": "tuning_complete"})

            asyncio.create_task(pump())
            return q

        async def unsubscribe(self, q):
            pass

    handler_globals = None
    for route in client.app.routes:
        if getattr(route, "path", None) == "/api/tuner/stream":
            handler_globals = route.endpoint.__globals__
            break
    assert handler_globals is not None
    with patch.dict(handler_globals, {"auto_tuner": DummyAutoTuner()}):
        with client.stream("GET", "/api/tuner/stream") as response:
            assert response.status_code == 200
            assert "text/event-stream" in response.headers.get("content-type", "")


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def mock_k8s_clients():
    with (
        patch("kubernetes.client.AppsV1Api") as mock_apps_api,
        patch("kubernetes.client.CoreV1Api") as mock_core_api,
        patch("kubernetes.client.CustomObjectsApi") as mock_custom_api,
    ):
        mock_apps_api.return_value = MagicMock(spec=AppsV1Api)
        mock_core_api.return_value = MagicMock(spec=CoreV1Api)
        mock_custom_api.return_value = MagicMock(spec=CustomObjectsApi)

        mock_custom_api.return_value.get_namespaced_custom_object.return_value = {
            "spec": {
                "template": {
                    "containers": [
                        {
                            "name": "main",
                            "env": [
                                {
                                    "name": "VLLM_ADDITIONAL_ARGS",
                                    "value": "",
                                }
                            ],
                        }
                    ]
                },
            },
            "status": {"conditions": [{"type": "Ready", "status": "True"}]},
        }
        mock_custom_api.return_value.delete_namespaced_custom_object = MagicMock()
        mock_custom_api.return_value.create_namespaced_custom_object = MagicMock()
        yield mock_apps_api, mock_core_api, mock_custom_api


@pytest.fixture
def auto_tuner_instance(mock_k8s_clients):
    mock_metrics_collector = AsyncMock(spec=MultiTargetMetricsCollector)
    mock_load_engine = AsyncMock(spec=LoadTestEngine)
    tuner = AutoTuner(mock_metrics_collector, mock_load_engine)
    tuner._k8s_available = True  # Force K8s available for testing
    tuner._cooldown_secs = 0  # Skip cooldown in tests
    tuner._k8s_apps = mock_k8s_clients[0].return_value
    tuner._k8s_core = mock_k8s_clients[1].return_value  # type: ignore  # Mock attr assignment, _k8s_core is K8s CoreV1Api
    tuner._k8s_custom = mock_k8s_clients[2].return_value
    tuner._k8s_operator._wait_for_deletion = AsyncMock(return_value=None)
    return tuner


def test_tuner_status_endpoint(client):
    resp = client.get("/api/tuner/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("status") in {"idle", "running", "completed", "error"}
    assert "running" in data
    assert isinstance(data["running"], bool)
    assert "trials_completed" in data
    assert isinstance(data["trials_completed"], int)
    assert "best" in data


def test_rollback_trial_exposed_in_status(client):
    resp = client.get("/api/tuner/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "last_rollback_trial" in data
    assert data["last_rollback_trial"] is None


def test_tuner_trials_endpoint_returns_list(client):
    resp = client.get("/api/tuner/trials")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)


def test_tuner_apply_best_response(client):
    resp = client.post("/api/tuner/apply-best")
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("success") is False
    assert "No best trial available" in data.get("message", "")


def test_tuner_start_endpoint(client):
    """Test starting auto-tuning with flat schema"""
    request_data = {
        "objective": "balanced",
        "n_trials": 2,
        "eval_requests": 10,
        "vllm_endpoint": "http://localhost:8000",
        "max_num_seqs_min": 64,
        "max_num_seqs_max": 512,
        "gpu_memory_min": 0.80,
        "gpu_memory_max": 0.95,
    }
    resp = client.post("/api/tuner/start", json=request_data)
    assert resp.status_code == 200
    data = resp.json()
    assert "success" in data
    assert "message" in data
    assert data["success"] is True


def test_tuner_start_endpoint_rejects_when_sweep_running(client):
    request_data = {
        "objective": "balanced",
        "evaluation_mode": "sweep",
        "n_trials": 1,
        "eval_requests": 10,
        "vllm_endpoint": "http://localhost:8000",
        "sweep_config": {
            "endpoint": "http://localhost:8000",
            "model": "auto",
            "rps_start": 10,
            "rps_end": 20,
            "rps_step": 5,
            "requests_per_step": 10,
            "concurrency": 4,
            "max_tokens": 64,
            "stream": True,
            "prompt": "hello",
            "saturation_error_rate": 0.1,
            "saturation_latency_factor": 3.0,
            "min_stable_steps": 1,
        },
        "max_num_seqs_min": 64,
        "max_num_seqs_max": 512,
        "gpu_memory_min": 0.80,
        "gpu_memory_max": 0.95,
    }

    handler_globals = None
    for route in client.app.routes:
        if getattr(route, "path", None) == "/api/tuner/start":
            endpoint = route.endpoint
            handler_globals = getattr(endpoint, "__wrapped__", endpoint).__globals__
            break
    assert handler_globals is not None

    mock_tuner = MagicMock()
    mock_tuner.is_running = False

    mock_load_engine = MagicMock()
    mock_load_engine.is_sweep_running.return_value = True

    with patch.dict(handler_globals, {"auto_tuner": mock_tuner, "load_engine": mock_load_engine}):
        resp = client.post("/api/tuner/start", json=request_data)

    assert resp.status_code == 409
    data = resp.json()
    assert "detail" in data
    assert data["detail"]["error_type"] == "already_running"


@pytest.mark.asyncio
async def test_wait_for_ready_polls_inferenceservice_status(auto_tuner_instance, mock_k8s_clients):
    tuner = auto_tuner_instance
    mock_custom_api = mock_k8s_clients[2].return_value

    mock_custom_api.get_namespaced_custom_object.side_effect = [
        {"status": {"conditions": [{"type": "Ready", "status": "False"}]}},
        {"status": {"conditions": [{"type": "Ready", "status": "False"}]}},
        {"status": {"conditions": [{"type": "Ready", "status": "True"}]}},
    ]

    with patch("asyncio.sleep", new=AsyncMock()) as mock_sleep:
        ready = await tuner._wait_for_ready(timeout=10, interval=1)
        assert ready
        assert mock_custom_api.get_namespaced_custom_object.call_count == 3
        assert mock_sleep.call_count == 2


@pytest.mark.asyncio
async def test_wait_for_ready_times_out(auto_tuner_instance, mock_k8s_clients):
    tuner = auto_tuner_instance
    mock_custom_api = mock_k8s_clients[2].return_value

    mock_custom_api.get_namespaced_custom_object.return_value = {
        "status": {"conditions": [{"type": "Ready", "status": "False"}]}
    }

    with patch("asyncio.sleep", new=AsyncMock()) as mock_sleep:
        ready = await tuner._wait_for_ready(timeout=3, interval=1)
        assert not ready
        assert mock_custom_api.get_namespaced_custom_object.call_count > 1
        assert mock_sleep.call_count >= 2


@pytest.mark.asyncio
async def test_rollback_on_wait_for_ready_timeout(auto_tuner_instance, mock_k8s_clients):
    tuner = auto_tuner_instance
    mock_custom_api = mock_k8s_clients[2].return_value

    # First call is pre-tuning health check (should pass), second call is trial (should fail)
    tuner._wait_for_ready = AsyncMock(side_effect=[True, False])
    tuner._evaluate = AsyncMock(return_value=(10.0, 10.0, 0.1))

    config = TuningConfig(n_trials=1, eval_requests=5, warmup_requests=0)

    await tuner.start(config, "http://mock:8080")

    create_calls = mock_custom_api.create_namespaced_custom_object.call_args_list
    assert len(create_calls) >= 2, "Expected at least 2 IS recreates (apply + rollback)"

    assert tuner._last_rollback_trial == 0


@pytest.mark.asyncio
async def test_start_reapplies_best_params_at_end(auto_tuner_instance, mock_k8s_clients):
    tuner = auto_tuner_instance
    mock_custom_api = mock_k8s_clients[2].return_value

    # Mock _evaluate to return increasing scores
    tuner._evaluate = AsyncMock(
        side_effect=[
            (10, 10, 100),  # Trial 0
            (20, 20, 50),  # Trial 1 (best)
        ]
    )

    # Mock _wait_for_ready to always return True
    tuner._wait_for_ready = AsyncMock(return_value=True)

    # Mock _apply_params to track calls
    tuner._apply_params = AsyncMock(wraps=tuner._apply_params)

    config = TuningConfig(n_trials=2, eval_requests=10, objective="tps")
    vllm_endpoint = "http://mock-vllm-endpoint"

    await tuner.start(config, vllm_endpoint)

    # Check calls to _apply_params
    # First two calls are for trials, last call is for best params
    assert tuner._apply_params.call_count == config.n_trials + 1

    last_call_args, _ = tuner._apply_params.call_args_list[-1]
    assert last_call_args[0] == tuner._best_trial.params

    last_create_call = mock_custom_api.create_namespaced_custom_object.call_args_list[-1]
    patch_body = last_create_call[1]["body"]
    patched_args = _extract_tuning_args_from_created_cr(patch_body)
    expected_tuning_args = []
    expected_tuning_args.append(f"--max-num-seqs={tuner._best_trial.params['max_num_seqs']}")
    expected_tuning_args.append(f"--gpu-memory-utilization={tuner._best_trial.params['gpu_memory_utilization']}")
    expected_tuning_args.append(f"--max-num-batched-tokens={tuner._best_trial.params['max_num_batched_tokens']}")
    for expected_arg in expected_tuning_args:
        assert expected_arg in patched_args, f"Expected {expected_arg} in patched args: {patched_args}"

    assert mock_custom_api.create_namespaced_custom_object.call_count == config.n_trials + 1


@pytest.mark.asyncio
async def test_auto_benchmark_saves_on_completion(auto_tuner_instance, mock_k8s_clients):
    tuner = auto_tuner_instance
    tuner._evaluate = AsyncMock(return_value=(120.0, 60.0, 0.2))
    tuner._wait_for_ready = AsyncMock(return_value=True)
    tuner._apply_params = AsyncMock(return_value={"success": True})

    from ..services import auto_tuner as _at_mod

    save_benchmark_mock = AsyncMock(return_value=MagicMock(id=321))
    q = await tuner.subscribe()
    with patch.object(_at_mod.storage, "save_benchmark", save_benchmark_mock):
        with patch.object(_at_mod, "resolve_model_name", new=AsyncMock(return_value="llm-ov")):
            config = TuningConfig(n_trials=1, eval_requests=5, warmup_requests=0)
            result = await tuner.start(config, "http://mock:8080", auto_benchmark=True)

    events = []
    while not q.empty():
        events.append(q.get_nowait())
    await tuner.unsubscribe(q)

    assert result["completed"] is True
    save_benchmark_mock.assert_awaited_once()
    benchmark_events = [e for e in events if e.get("type") == "benchmark_saved"]
    assert len(benchmark_events) == 1
    assert benchmark_events[0]["data"]["benchmark_id"] == 321


@pytest.mark.asyncio
async def test_auto_benchmark_skipped_when_false(auto_tuner_instance, mock_k8s_clients):
    tuner = auto_tuner_instance
    tuner._evaluate = AsyncMock(return_value=(120.0, 60.0, 0.2))
    tuner._wait_for_ready = AsyncMock(return_value=True)
    tuner._apply_params = AsyncMock(return_value={"success": True})

    from ..services import auto_tuner as _at_mod

    save_benchmark_mock = AsyncMock(return_value=MagicMock(id=321))
    with patch.object(_at_mod.storage, "save_benchmark", save_benchmark_mock):
        config = TuningConfig(n_trials=1, eval_requests=5, warmup_requests=0)
        result = await tuner.start(config, "http://mock:8080", auto_benchmark=False)

    assert result["completed"] is True
    save_benchmark_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_median_pruner_marks_trial_as_pruned(auto_tuner_instance, mock_k8s_clients):
    """Trials pruned by MedianPruner should have status='pruned' and pruned=True"""
    tuner = auto_tuner_instance
    call_count = 0

    async def mock_evaluate(endpoint, config, trial=None, trial_num=0):
        nonlocal call_count
        call_count += 1
        if trial:
            trial.report(100.0 if call_count <= 3 else 1.0, step=0)
        if call_count <= 3:
            return 100.0, 100.0, 0.1
        return 1.0, 1.0, 5.0

    tuner._evaluate = mock_evaluate
    tuner._wait_for_ready = AsyncMock(return_value=True)
    tuner._apply_params = AsyncMock(return_value={"success": True})

    config = TuningConfig(n_trials=5, eval_requests=10, warmup_requests=0, objective="tps")

    await tuner.start(config, "http://mock:8080")

    pruned_trials = [t for t in tuner.trials if t.pruned]
    assert len(tuner.trials) == 5
    assert pruned_trials
    assert all(t.status == "pruned" for t in pruned_trials)


@pytest.mark.asyncio
async def test_best_score_history_length_matches_trials(auto_tuner_instance, mock_k8s_clients):
    """_best_score_history should have an entry for each trial"""
    tuner = auto_tuner_instance
    tuner._evaluate = AsyncMock(return_value=(50.0, 50.0, 0.2))
    tuner._wait_for_ready = AsyncMock(return_value=True)
    tuner._apply_params = AsyncMock(return_value={"success": True})

    n_trials = 3
    config = TuningConfig(n_trials=n_trials, eval_requests=5, warmup_requests=0)

    await tuner.start(config, "http://mock:8080")

    assert len(tuner._best_score_history) == n_trials


def test_tuner_status_has_running_field(client):
    resp = client.get("/api/tuner/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "running" in data
    assert isinstance(data["running"], bool)
    assert data["running"] is False


@pytest.mark.asyncio
async def test_subscribe_receives_broadcast_events(auto_tuner_instance):
    """subscribe() then _broadcast() should deliver event to queue"""
    tuner = auto_tuner_instance
    q = await tuner.subscribe()
    test_event = {"type": "test", "data": {"value": 42}}
    await tuner._broadcast(test_event)
    result = await q.get()
    assert result == test_event


@pytest.mark.asyncio
async def test_unsubscribe_stops_events(auto_tuner_instance):
    """After unsubscribe(), queue should not receive further events"""
    tuner = auto_tuner_instance
    q = await tuner.subscribe()
    await tuner.unsubscribe(q)
    await tuner._broadcast({"type": "should_not_arrive"})
    import asyncio

    try:
        # If any event arrives, this will succeed and fail the test
        await asyncio.wait_for(q.get(), timeout=0.2)
        raise AssertionError("Queue should be empty after unsubscribe")
    except TimeoutError:
        pass


def test_tuner_status_has_trials_completed(client):
    resp = client.get("/api/tuner/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "trials_completed" in data
    assert isinstance(data["trials_completed"], int)
    assert data["trials_completed"] == 0


def test_tuner_status_best_is_null_when_idle(client):
    resp = client.get("/api/tuner/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "best" in data
    assert data["best"] is None


def test_tuner_trials_item_shape_with_data(client):
    from unittest.mock import MagicMock, patch

    trial = TuningTrial(
        trial_id=0,
        params={"max_num_seqs": 128, "gpu_memory_utilization": 0.85},
        tps=42.5,
        p99_latency=0.5,
        score=100.0,
        status="completed",
    )

    mock_tuner = MagicMock()
    mock_tuner.trials = [trial]

    handler_globals = None
    for route in client.app.routes:
        if getattr(route, "path", None) == "/api/tuner/trials":
            handler_globals = route.endpoint.__globals__
            break
    assert handler_globals is not None, "Could not find /api/tuner/trials route"

    with patch.dict(handler_globals, {"auto_tuner": mock_tuner}):
        resp = client.get("/api/tuner/trials")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) > 0
        item = data[-1]

        assert "id" in item
        assert "tps" in item
        assert "p99_latency" in item
        assert "params" in item
        assert "score" in item
        assert "status" in item

        assert "trial_number" not in item
        assert "parameters" not in item
        assert "metrics" not in item

        assert item["id"] == 0
        assert item["tps"] == 42.5
        assert item["p99_latency"] == pytest.approx(500.0)
    assert item["status"] == "completed"


@pytest.mark.asyncio
async def test_apply_params_uses_correct_configmap_keys(auto_tuner_instance, mock_k8s_clients):
    tuner = auto_tuner_instance
    mock_custom_api = mock_k8s_clients[2].return_value

    mock_custom_api.get_namespaced_custom_object.return_value = {
        "spec": {
            "predictor": {
                "model": {
                    "args": [],
                }
            },
        },
    }

    params = {
        "max_num_seqs": 128,
        "gpu_memory_utilization": 0.8,
        "max_model_len": 4096,
        "enable_chunked_prefill": True,
    }

    await tuner._apply_params(params)

    mock_custom_api.create_namespaced_custom_object.assert_called_once()
    call_args = mock_custom_api.create_namespaced_custom_object.call_args
    patch_args = _extract_tuning_args_from_created_cr(call_args.kwargs["body"])

    assert "--enable-chunked-prefill" in patch_args


def test_importance_returns_empty_when_no_trials(client):
    """When no trials have been run, /importance should return {}"""
    resp = client.get("/api/tuner/importance")
    assert resp.status_code == 200
    data = resp.json()
    assert data == {}


def test_importance_not_hardcoded(client):
    """Verify /importance does NOT return the old hardcoded values"""
    resp = client.get("/api/tuner/importance")
    assert resp.status_code == 200
    data = resp.json()
    assert data != {"max_num_seqs": 0.4, "gpu_memory_utilization": 0.35, "max_model_len": 0.25}


def test_apply_best_returns_no_best_message_when_idle(client):
    """When no tuning has run, /apply-best should return failure with proper message"""
    resp = client.post("/api/tuner/apply-best")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is False
    assert "No best trial available" in data["message"]
    assert data["applied_parameters"] is None


def test_apply_best_with_existing_trial(client):
    """When best trial exists, /apply-best should attempt to apply it"""
    from unittest.mock import AsyncMock, MagicMock, patch

    best_trial = TuningTrial(
        trial_id=0,
        params={"max_num_seqs": 128, "gpu_memory_utilization": 0.85},
        tps=50.0,
        p99_latency=0.3,
        score=150.0,
        status="completed",
    )

    handler_globals = None
    for route in client.app.routes:
        if getattr(route, "path", None) == "/api/tuner/apply-best":
            handler_globals = route.endpoint.__globals__
            break
    assert handler_globals is not None

    mock_tuner = MagicMock()
    mock_tuner.best = best_trial
    mock_tuner.is_running = False
    mock_tuner._apply_params = AsyncMock(return_value={"success": True})

    with patch.dict(handler_globals, {"auto_tuner": mock_tuner}):
        resp = client.post("/api/tuner/apply-best")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["applied_parameters"] == best_trial.params
        mock_tuner._apply_params.assert_called_once_with(best_trial.params)


@pytest.mark.asyncio
async def test_suggest_params_batched_tokens_constraint(auto_tuner_instance, mock_k8s_clients):
    import optuna

    config = TuningConfig()
    study = optuna.create_study(sampler=optuna.samplers.TPESampler(seed=42))

    for _ in range(10):
        trial = study.ask()
        params = auto_tuner_instance._suggest_params(trial, config)
        assert params["max_num_batched_tokens"] >= params["max_num_seqs"], (
            f"Constraint violated: batched={params['max_num_batched_tokens']} < seqs={params['max_num_seqs']}"
        )
        study.tell(trial, 0)


@pytest.mark.asyncio
async def test_suggest_params_swap_space_excluded_by_default(auto_tuner_instance, mock_k8s_clients):
    import optuna

    config = TuningConfig()
    study = optuna.create_study()
    trial = study.ask()
    params = auto_tuner_instance._suggest_params(trial, config)
    assert "swap_space" not in params, f"swap_space should not be in params: {params}"


def test_suggest_params_empty_model_len_no_crash(auto_tuner_instance):
    import optuna

    config = TuningConfig(max_model_len_range=(10000, 16384))
    study = optuna.create_study()
    trial = study.ask()
    try:
        params = auto_tuner_instance._suggest_params(trial, config)
        assert "max_model_len" in params
    except ValueError as e:
        pytest.fail(f"_suggest_params raised ValueError: {e}")


@pytest.mark.asyncio
async def test_apply_params_includes_new_configmap_keys(auto_tuner_instance, mock_k8s_clients):
    tuner = auto_tuner_instance
    mock_custom_api = mock_k8s_clients[2].return_value

    mock_custom_api.get_namespaced_custom_object.return_value = {
        "spec": {
            "predictor": {
                "model": {
                    "args": [],
                }
            },
        },
    }

    params = {
        "max_num_seqs": 128,
        "gpu_memory_utilization": 0.85,
        "max_model_len": 4096,
        "enable_chunked_prefill": False,
        "max_num_batched_tokens": 512,
        "block_size": 16,
    }

    await tuner._apply_params(params)

    mock_custom_api.create_namespaced_custom_object.assert_called_once()
    call_args = mock_custom_api.create_namespaced_custom_object.call_args
    patch_args = _extract_tuning_args_from_created_cr(call_args.kwargs["body"])

    assert "--max-num-batched-tokens=512" in patch_args
    assert "--block-size=16" in patch_args
    assert "--enable-chunked-prefill" not in patch_args


@pytest.mark.asyncio
async def test_eval_uses_config_concurrency_and_rps(auto_tuner_instance, mock_k8s_clients):
    tuner = auto_tuner_instance

    captured_configs = []

    async def mock_run(load_config):
        captured_configs.append(load_config)
        return {"tps": {"total": 50.0}, "latency": {"p99": 0.2}}

    tuner._load_engine.run = mock_run

    config = TuningConfig(eval_concurrency=16, eval_rps=5, eval_requests=10, warmup_requests=0)
    tuner._config = config
    from ..services import auto_tuner as _at_mod

    with patch.object(_at_mod, "resolve_model_name", new=AsyncMock(return_value="test-model")):
        score, tps, p99 = await tuner._evaluate("http://mock:8080", config)

    assert len(captured_configs) == 2
    assert captured_configs[0].concurrency == 16
    assert captured_configs[0].rps == 5
    assert captured_configs[0].total_requests == 5
    assert captured_configs[1].concurrency == 16
    assert captured_configs[1].rps == 5
    assert captured_configs[1].total_requests == 5


@pytest.mark.asyncio
async def test_objective_uses_run_sweep_when_evaluation_mode_sweep(auto_tuner_instance, mock_k8s_clients):
    tuner = auto_tuner_instance

    sweep_config = SweepConfig(
        endpoint="http://mock:8080",
        model="auto",
        rps_start=10,
        rps_end=20,
        rps_step=5,
        requests_per_step=10,
        concurrency=4,
        max_tokens=64,
    )
    sweep_result = SweepResult(config=sweep_config, steps=[], optimal_rps=42.0, total_duration=1.2)

    tuner.evaluation_mode = "sweep"
    tuner._sweep_config = sweep_config
    tuner._load_engine.run_sweep = AsyncMock(return_value=sweep_result)
    tuner._evaluate = AsyncMock(return_value=(1.0, 1.0, 0.1))

    config = TuningConfig(eval_requests=10, warmup_requests=0)
    score, tps, p99 = await tuner._objective("http://mock:8080", config, trial=None, trial_num=0)

    tuner._load_engine.run_sweep.assert_awaited_once_with(sweep_config)
    tuner._evaluate.assert_not_awaited()
    assert score == 42.0
    assert tps == 42.0
    assert p99 == 0.0


@pytest.mark.asyncio
async def test_warmup_runs_before_evaluation(auto_tuner_instance, mock_k8s_clients):
    tuner = auto_tuner_instance

    call_count = 0
    captured_total_requests: list[int] = []

    async def mock_run(load_config):
        nonlocal call_count
        call_count += 1
        captured_total_requests.append(load_config.total_requests)
        return {"tps": {"total": 50.0}, "latency": {"p99": 0.2}}

    tuner._load_engine.run = mock_run

    config = TuningConfig(warmup_requests=5, eval_requests=10, eval_concurrency=8, eval_rps=0)
    from ..services import auto_tuner as _at_mod

    with patch.object(_at_mod, "resolve_model_name", new=AsyncMock(return_value="test-model")):
        score, tps, p99 = await tuner._evaluate("http://mock:8080", config)

    assert call_count == 3
    assert captured_total_requests == [5, 5, 5]


@pytest.mark.asyncio
async def test_no_warmup_when_zero(auto_tuner_instance, mock_k8s_clients):
    tuner = auto_tuner_instance

    call_count = 0
    captured_total_requests: list[int] = []

    async def mock_run(load_config):
        nonlocal call_count
        call_count += 1
        captured_total_requests.append(load_config.total_requests)
        return {"tps": {"total": 50.0}, "latency": {"p99": 0.2}}

    tuner._load_engine.run = mock_run

    config = TuningConfig(warmup_requests=0, eval_requests=10)
    from ..services import auto_tuner as _at_mod

    with patch.object(_at_mod, "resolve_model_name", new=AsyncMock(return_value="test-model")):
        score, tps, p99 = await tuner._evaluate("http://mock:8080", config)

    assert call_count == 2
    assert captured_total_requests == [5, 5]


def test_start_uses_inmemory_when_no_storage_url(auto_tuner_instance, mock_k8s_clients):
    import os

    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("OPTUNA_STORAGE_URL", None)
        assert auto_tuner_instance is not None


@pytest.mark.asyncio
async def test_warmstart_enqueues_previous_best(auto_tuner_instance, mock_k8s_clients):

    tuner = auto_tuner_instance

    mock_study = MagicMock()
    mock_study.best_trials = [MagicMock()]
    mock_study.best_trial = MagicMock()
    mock_study.best_trial.params = {"max_num_seqs": 256, "gpu_memory_utilization": 0.9}
    mock_study.ask = MagicMock(side_effect=StopIteration)

    with patch.dict("os.environ", {"OPTUNA_STORAGE_URL": "sqlite:////tmp/test_optuna_warmstart.db"}):
        with patch("optuna.storages.RDBStorage"), patch("optuna.create_study", return_value=mock_study):
            config = TuningConfig(n_trials=1, eval_requests=5, warmup_requests=0)

            with contextlib.suppress(Exception):
                await tuner.start(config, "http://mock:8080")

            mock_study.enqueue_trial.assert_called_once_with(
                params={"max_num_seqs": 256, "gpu_memory_utilization": 0.9}
            )


@pytest.mark.asyncio
async def test_importance_returns_empty_for_pareto_mode(auto_tuner_instance):
    """get_importance() should return {} for multi-objective study"""
    import optuna

    tuner = auto_tuner_instance
    tuner._study = optuna.create_study(
        directions=["maximize", "minimize"],
        sampler=optuna.samplers.NSGAIISampler(seed=42),
    )
    tuner._trials = [object()] * 10

    result = await tuner.get_importance()
    assert result == {}, f"Expected empty dict for Pareto mode, got: {result}"


def test_start_accepts_pareto_objective(client):
    """POST /api/tuner/start with objective='pareto' should return success=true"""
    request_data = {
        "objective": "pareto",
        "n_trials": 2,
        "eval_requests": 5,
        "vllm_endpoint": "http://mock-vllm:8080",
        "max_num_seqs_min": 64,
        "max_num_seqs_max": 512,
    }
    resp = client.post("/api/tuner/start", json=request_data)
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True, f"Expected success=true, got: {data}"


@pytest.mark.asyncio
async def test_suggest_params_new_params_included(auto_tuner_instance, mock_k8s_clients):
    """New params (block_size, max_num_batched_tokens) should appear in suggested params"""
    import optuna

    tuner = auto_tuner_instance
    config = TuningConfig(block_size_options=[16], eval_concurrency=8, eval_rps=0)
    study = optuna.create_study()
    trial = study.ask()
    params = tuner._suggest_params(trial, config)

    assert "block_size" in params
    assert params["block_size"] == 16
    assert "max_num_batched_tokens" in params


def test_status_response_includes_new_fields(client):
    """Status response should include best_score_history, pareto_front_size, last_rollback_trial"""
    resp = client.get("/api/tuner/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "best_score_history" in data
    assert isinstance(data["best_score_history"], list)
    assert "pareto_front_size" in data
    assert "last_rollback_trial" in data


@pytest.mark.asyncio
async def test_best_score_history_monotonically_nondecreasing_for_tps(auto_tuner_instance, mock_k8s_clients):
    """For tps objective (maximize), best_score_history should be non-decreasing"""
    tuner = auto_tuner_instance
    scores = [10.0, 30.0, 20.0, 50.0, 40.0]
    call_idx = [0]

    async def mock_eval(endpoint, config, trial=None, trial_num=0):
        idx = call_idx[0]
        call_idx[0] += 1
        score = scores[idx % len(scores)]
        if trial and config.objective != "pareto":
            trial.report(score, step=0)
        return score, score, 0.1

    tuner._evaluate = mock_eval
    tuner._wait_for_ready = AsyncMock(return_value=True)
    tuner._apply_params = AsyncMock(return_value={"success": True})

    config = TuningConfig(n_trials=5, eval_requests=5, warmup_requests=0, objective="tps")
    await tuner.start(config, "http://mock:8080")

    history = tuner._best_score_history
    assert len(history) == 5
    for i in range(1, len(history)):
        assert history[i] >= history[i - 1], f"History not monotone at {i}: {history}"


def test_apply_best_returns_error_when_tuning_running(client):
    """If tuning is running, /apply-best should return failure"""
    best_trial = TuningTrial(
        trial_id=0,
        params={"max_num_seqs": 128},
        tps=50.0,
        p99_latency=0.3,
        score=50.0,
        status="completed",
    )

    mock_tuner = MagicMock()
    mock_tuner.best = best_trial
    mock_tuner.is_running = True

    handler_globals = None
    for route in client.app.routes:
        if getattr(route, "path", None) == "/api/tuner/apply-best":
            handler_globals = route.endpoint.__globals__
            break

    assert handler_globals is not None
    with patch.dict(handler_globals, {"auto_tuner": mock_tuner}):
        resp = client.post("/api/tuner/apply-best")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert "progress" in data["message"].lower() or "running" in data["message"].lower()


def test_stop_endpoint_returns_failure_when_not_running(client):
    """POST /stop when not running should return success=false"""
    resp = client.post("/api/tuner/stop")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is False


@pytest.mark.asyncio
async def test_rollback_to_snapshot_no_snapshot_returns_false(auto_tuner_instance):
    tuner = auto_tuner_instance
    tuner._is_args_snapshot = None
    result = await tuner._rollback_to_snapshot(trial_num=0)
    assert result is False


@pytest.mark.asyncio
async def test_multiple_subscribers_all_receive_broadcast(auto_tuner_instance):
    """All active subscribers should receive the same broadcast event"""
    tuner = auto_tuner_instance
    q1 = await tuner.subscribe()
    q2 = await tuner.subscribe()

    event = {"type": "trial_complete", "data": {"trial_id": 0, "score": 42.0}}
    await tuner._broadcast(event)

    result1 = await q1.get()
    result2 = await q2.get()

    assert result1 == event
    assert result2 == event

    await tuner.unsubscribe(q1)
    await tuner.unsubscribe(q2)


@pytest.mark.asyncio
async def test_suggest_params_swap_space_enabled_by_flag(auto_tuner_instance, mock_k8s_clients):
    """swap_space should appear in suggested params when include_swap_space=True"""
    import optuna

    config = TuningConfig(include_swap_space=True, swap_space_range=(1.0, 8.0))
    study = optuna.create_study()
    trial = study.ask()
    params = auto_tuner_instance._suggest_params(trial, config)
    assert "swap_space" in params, f"Expected swap_space in params: {params}"
    assert 1.0 <= params["swap_space"] <= 8.0


@pytest.mark.asyncio
async def test_pareto_front_size_set_after_pareto_trials(auto_tuner_instance, mock_k8s_clients):
    """After running pareto trials, _pareto_front_size should be set and >= 1"""
    tuner = auto_tuner_instance
    tuner._evaluate = AsyncMock(return_value=(50.0, 50.0, 0.5))
    tuner._wait_for_ready = AsyncMock(return_value=True)
    tuner._apply_params = AsyncMock(return_value={"success": True})

    config = TuningConfig(n_trials=3, eval_requests=5, warmup_requests=0, objective="pareto")
    await tuner.start(config, "http://mock:8080")

    assert tuner._pareto_front_size is not None
    assert tuner._pareto_front_size >= 1


@pytest.mark.asyncio
async def test_broadcast_trial_start_event_for_each_trial(auto_tuner_instance, mock_k8s_clients):
    """Each trial in start() should broadcast a trial_start event"""
    tuner = auto_tuner_instance
    tuner._evaluate = AsyncMock(return_value=(50.0, 50.0, 0.2))
    tuner._wait_for_ready = AsyncMock(return_value=True)
    tuner._apply_params = AsyncMock(return_value={"success": True})

    q = await tuner.subscribe()

    n_trials = 2
    config = TuningConfig(n_trials=n_trials, eval_requests=5, warmup_requests=0, objective="tps")
    await tuner.start(config, "http://mock:8080")

    # Drain all events queued during start()
    events = []
    while not q.empty():
        events.append(q.get_nowait())

    await tuner.unsubscribe(q)

    trial_start_events = [e for e in events if e.get("type") == "trial_start"]
    assert len(trial_start_events) == n_trials


@pytest.mark.asyncio
async def test_apply_params_swap_space_configmap_key(auto_tuner_instance, mock_k8s_clients):
    tuner = auto_tuner_instance
    mock_custom_api = mock_k8s_clients[2].return_value

    mock_custom_api.get_namespaced_custom_object.return_value = {
        "spec": {
            "predictor": {
                "model": {
                    "args": [],
                }
            },
        },
    }

    params = {
        "max_num_seqs": 64,
        "gpu_memory_utilization": 0.8,
        "max_model_len": 4096,
        "enable_chunked_prefill": False,
        "swap_space": 4.0,
    }

    await tuner._apply_params(params)

    call_args = mock_custom_api.create_namespaced_custom_object.call_args
    patch_args = _extract_tuning_args_from_created_cr(call_args.kwargs["body"])
    assert "--swap-space=4.0" in patch_args


@pytest.mark.asyncio
async def test_pruned_trials_not_counted_as_best_trial(auto_tuner_instance, mock_k8s_clients):
    """Pruned trials should never be set as the best_trial"""
    tuner = auto_tuner_instance
    call_count = 0

    async def mock_evaluate(endpoint, config, trial=None, trial_num=0):
        nonlocal call_count
        call_count += 1
        if trial:
            trial.report(100.0 if call_count <= 3 else 1.0, step=0)
        if call_count <= 3:
            return 100.0, 100.0, 0.1
        return 1.0, 1.0, 5.0

    tuner._evaluate = mock_evaluate
    tuner._wait_for_ready = AsyncMock(return_value=True)
    tuner._apply_params = AsyncMock(return_value={"success": True})

    config = TuningConfig(n_trials=5, eval_requests=10, warmup_requests=0, objective="tps")
    await tuner.start(config, "http://mock:8080")

    pruned_trials = [t for t in tuner.trials if t.pruned]
    assert len(pruned_trials) > 0, "Expected at least one pruned trial for this test to be meaningful"

    if tuner._best_trial is not None:
        assert not tuner._best_trial.pruned, "Best trial should not be marked as pruned"
        assert tuner._best_trial.status != "pruned"


@pytest.mark.asyncio
async def test_chunked_prefill_false_writes_empty_string(auto_tuner_instance, mock_k8s_clients):
    tuner = auto_tuner_instance
    mock_custom_api = mock_k8s_clients[2].return_value

    mock_custom_api.get_namespaced_custom_object.return_value = {
        "spec": {
            "predictor": {
                "model": {
                    "args": [],
                }
            },
        },
    }

    params = {
        "max_num_seqs": 64,
        "gpu_memory_utilization": 0.8,
        "max_model_len": 4096,
        "enable_chunked_prefill": False,
        "enable_enforce_eager": False,
        "max_num_batched_tokens": 512,
    }

    await tuner._apply_params(params)

    call_args = mock_custom_api.create_namespaced_custom_object.call_args
    patch_args = _extract_tuning_args_from_created_cr(call_args.kwargs["body"])

    assert "--enable-chunked-prefill" not in patch_args

    mock_custom_api.create_namespaced_custom_object.reset_mock()
    params_true = {**params, "enable_chunked_prefill": True}
    await tuner._apply_params(params_true)
    patch_args_true = _extract_tuning_args_from_created_cr(
        mock_custom_api.create_namespaced_custom_object.call_args.kwargs["body"]
    )
    assert "--enable-chunked-prefill" in patch_args_true


@pytest.mark.asyncio
async def test_enforce_eager_writes_correct_values(auto_tuner_instance, mock_k8s_clients):
    tuner = auto_tuner_instance
    mock_custom_api = mock_k8s_clients[2].return_value

    mock_custom_api.get_namespaced_custom_object.return_value = {
        "spec": {
            "predictor": {
                "model": {
                    "args": [],
                }
            },
        },
    }

    params_false = {
        "max_num_seqs": 64,
        "gpu_memory_utilization": 0.8,
        "max_model_len": 4096,
        "enable_chunked_prefill": False,
        "enable_enforce_eager": False,
        "max_num_batched_tokens": 512,
    }

    await tuner._apply_params(params_false)
    patch_args_false = _extract_tuning_args_from_created_cr(
        mock_custom_api.create_namespaced_custom_object.call_args.kwargs["body"]
    )
    assert "--enforce-eager" not in patch_args_false

    mock_custom_api.create_namespaced_custom_object.reset_mock()
    params_true = {**params_false, "enable_enforce_eager": True}
    await tuner._apply_params(params_true)
    patch_args_true = _extract_tuning_args_from_created_cr(
        mock_custom_api.create_namespaced_custom_object.call_args.kwargs["body"]
    )
    assert "--enforce-eager" in patch_args_true


def test_suggest_params_includes_enforce_eager(auto_tuner_instance):
    tuner = auto_tuner_instance
    trial_mock = MagicMock()
    trial_mock.suggest_int.side_effect = lambda name, low, high, step=1: low
    trial_mock.suggest_float.side_effect = lambda name, low, high: low
    trial_mock.suggest_categorical.side_effect = lambda name, choices: choices[0]

    config = TuningConfig()
    params = tuner._suggest_params(trial_mock, config)

    assert "enable_enforce_eager" in params
    assert params["enable_enforce_eager"] in [True, False]


@pytest.mark.asyncio
async def test_phase_events_broadcast_in_start(auto_tuner_instance, mock_k8s_clients):
    tuner = auto_tuner_instance

    tuner._evaluate = AsyncMock(return_value=(50.0, 50.0, 0.2))
    tuner._wait_for_ready = AsyncMock(return_value=True)
    tuner._apply_params = AsyncMock(return_value={"success": True})

    q = await tuner.subscribe()

    config = TuningConfig(n_trials=1, eval_requests=5, warmup_requests=0)
    await tuner.start(config, "http://mock:8080")

    await tuner.unsubscribe(q)

    events = []
    while not q.empty():
        events.append(q.get_nowait())

    event_types = [e.get("type") for e in events]
    assert "trial_start" in event_types
    assert "trial_complete" in event_types

    phase_events = [e for e in events if e.get("type") == "phase"]
    phase_names = [e["data"]["phase"] for e in phase_events]
    assert "applying_config" in phase_names
    assert "restarting" in phase_names
    assert "waiting_ready" in phase_names


@pytest.mark.asyncio
async def test_apply_params_returns_failure_when_is_patch_throws(auto_tuner_instance, mock_k8s_clients):
    tuner = auto_tuner_instance
    mock_custom_api = mock_k8s_clients[2].return_value
    mock_custom_api.create_namespaced_custom_object.side_effect = Exception("InferenceService not found")

    params = {
        "max_num_seqs": 64,
        "gpu_memory_utilization": 0.8,
        "max_model_len": 4096,
        "enable_chunked_prefill": False,
        "enable_enforce_eager": False,
    }

    result = await tuner._apply_params(params)

    assert result["success"] is False
    assert "error" in result
    assert "InferenceService" in result["error"]


@pytest.mark.asyncio
async def test_rollback_uses_inferenceservice_annotation(auto_tuner_instance, mock_k8s_clients):
    tuner = auto_tuner_instance
    mock_custom_api = mock_k8s_clients[2].return_value

    tuner._is_args_snapshot = {
        "metadata": {"name": _get_vllm_is_name(), "namespace": _get_k8s_namespace()},
        "spec": {"predictor": {"model": {"args": ["--max-num-seqs=64"]}}},
    }

    await tuner._rollback_to_snapshot(0)

    mock_custom_api.create_namespaced_custom_object.assert_called_once()
    call_args = mock_custom_api.create_namespaced_custom_object.call_args
    assert call_args.kwargs["namespace"] == _get_k8s_namespace()
    patch_body = call_args.kwargs["body"]
    assert patch_body["spec"]["predictor"]["model"]["args"] == ["--max-num-seqs=64"]


def test_config_has_resolved_model_name(client):
    resp = client.get("/api/config")
    assert resp.status_code == 200
    data = resp.json()
    assert "resolved_model_name" in data


def test_config_vllm_model_name_not_deployment_name(client):
    resp = client.get("/api/config")
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("vllm_model_name") != "llm-ov-predictor"
    assert data.get("vllm_model_name") != "vllm-deployment"


# ── Preflight & Circuit Breaker Error Scenario Tests ──────────────────────────


@pytest.mark.asyncio
async def test_preflight_fails_when_k8s_unavailable(auto_tuner_instance):
    tuner = auto_tuner_instance
    tuner._k8s_available = False
    config = TuningConfig(n_trials=2, eval_requests=5, warmup_requests=0)
    result = await tuner.start(config, "http://mock:8080")
    assert "error" in result
    assert len(tuner.trials) == 0


@pytest.mark.asyncio
async def test_preflight_fails_on_rbac_403(auto_tuner_instance, mock_k8s_clients):
    tuner = auto_tuner_instance
    from kubernetes.client.exceptions import ApiException

    mock_custom_api = mock_k8s_clients[2].return_value
    mock_custom_api.get_namespaced_custom_object.side_effect = ApiException(status=403)
    config = TuningConfig(n_trials=2, eval_requests=5, warmup_requests=0)
    result = await tuner.start(config, "http://mock:8080")
    assert "error" in result
    assert result.get("error_type") == "rbac"
    assert len(tuner.trials) == 0


@pytest.mark.asyncio
async def test_preflight_fails_on_is_not_found_404(auto_tuner_instance, mock_k8s_clients):
    tuner = auto_tuner_instance
    from kubernetes.client.exceptions import ApiException

    mock_custom_api = mock_k8s_clients[2].return_value
    mock_custom_api.get_namespaced_custom_object.side_effect = ApiException(status=404)
    config = TuningConfig(n_trials=2, eval_requests=5, warmup_requests=0)
    result = await tuner.start(config, "http://mock:8080")
    assert "error" in result
    assert result.get("error_type") == "not_found"
    assert len(tuner.trials) == 0


@pytest.mark.asyncio
async def test_circuit_breaker_stops_on_consecutive_rbac_failure(auto_tuner_instance, mock_k8s_clients):
    tuner = auto_tuner_instance
    from kubernetes.client.exceptions import ApiException

    tuner._preflight_check = AsyncMock(return_value={"success": True})
    tuner._wait_for_ready = AsyncMock(return_value=True)
    mock_custom_api = mock_k8s_clients[2].return_value
    mock_custom_api.get_namespaced_custom_object.return_value = {
        "spec": {
            "template": {
                "containers": [
                    {
                        "name": "main",
                        "env": [{"name": "VLLM_ADDITIONAL_ARGS", "value": ""}],
                    }
                ]
            },
        },
    }
    mock_custom_api.create_namespaced_custom_object.side_effect = ApiException(status=403)
    config = TuningConfig(n_trials=3, eval_requests=5, warmup_requests=0)
    await tuner.start(config, "http://mock:8080")
    assert tuner._cancel_event.is_set()
    assert len(tuner.trials) == 0


@pytest.mark.asyncio
async def test_sse_broadcasts_tuning_error_on_preflight_fail(auto_tuner_instance, mock_k8s_clients):
    tuner = auto_tuner_instance
    from kubernetes.client.exceptions import ApiException

    mock_custom_api = mock_k8s_clients[2].return_value
    mock_custom_api.get_namespaced_custom_object.side_effect = ApiException(status=403)
    q = await tuner.subscribe()
    config = TuningConfig(n_trials=2, eval_requests=5, warmup_requests=0)
    await tuner.start(config, "http://mock:8080")
    events = []
    while not q.empty():
        events.append(q.get_nowait())
    tuning_error_events = [e for e in events if e.get("type") == "tuning_error"]
    assert len(tuning_error_events) >= 1
    assert tuning_error_events[0]["data"].get("error_type") == "rbac"


@pytest.mark.asyncio
async def test_wait_for_ready_stops_polling_on_403(auto_tuner_instance, mock_k8s_clients):
    tuner = auto_tuner_instance
    from kubernetes.client.exceptions import ApiException

    mock_custom_api = mock_k8s_clients[2].return_value
    mock_custom_api.get_namespaced_custom_object.side_effect = ApiException(status=403)
    with patch("asyncio.sleep", new=AsyncMock()):
        ready = await tuner._wait_for_ready(timeout=10, interval=1)
    assert not ready
    assert mock_custom_api.get_namespaced_custom_object.call_count == 1


@pytest.mark.asyncio
async def test_apply_params_returns_error_when_k8s_unavailable(auto_tuner_instance):
    tuner = auto_tuner_instance
    tuner._k8s_available = False
    result = await tuner._apply_params({"max_num_seqs": 128})
    assert result["success"] is False
    assert "K8s" in result.get("error", "")


# ── T8: Error Path Tests (A2, B2, C1–C3, D1–D3) ─────────────────────────────


@pytest.mark.asyncio
async def test_404_circuit_break_stops_tuning(auto_tuner_instance, mock_k8s_clients):
    """A2: create_namespaced_custom_object raises 404 → cancel + tuning_error SSE, no trials."""
    tuner = auto_tuner_instance
    from kubernetes.client.exceptions import ApiException

    tuner._preflight_check = AsyncMock(return_value={"success": True})
    tuner._wait_for_ready = AsyncMock(return_value=True)

    mock_custom = mock_k8s_clients[2].return_value
    mock_custom.get_namespaced_custom_object.return_value = {
        "spec": {
            "template": {
                "containers": [
                    {
                        "name": "main",
                        "env": [{"name": "VLLM_ADDITIONAL_ARGS", "value": ""}],
                    }
                ]
            },
        },
        "status": {"conditions": [{"type": "Ready", "status": "True"}]},
    }
    mock_custom.create_namespaced_custom_object.side_effect = ApiException(status=404)

    q = await tuner.subscribe()
    config = TuningConfig(n_trials=3, eval_requests=5, warmup_requests=0)
    await tuner.start(config, "http://mock:8080")

    assert tuner._cancel_event.is_set()
    assert len(tuner.trials) == 0

    events = []
    while not q.empty():
        events.append(q.get_nowait())
    error_events = [e for e in events if e.get("type") == "tuning_error"]
    assert len(error_events) >= 1
    assert error_events[0]["data"].get("error_type") == "not_found"


@pytest.mark.asyncio
async def test_non_rbac_apply_failure_broadcasts_sse(auto_tuner_instance, mock_k8s_clients):
    """C1: Non-RBAC apply failure (network error) → tuning_error SSE broadcast."""
    tuner = auto_tuner_instance

    tuner._preflight_check = AsyncMock(return_value={"success": True})
    tuner._wait_for_ready = AsyncMock(return_value=True)

    mock_custom = mock_k8s_clients[2].return_value
    mock_custom.get_namespaced_custom_object.return_value = {
        "spec": {
            "template": {
                "containers": [
                    {
                        "name": "main",
                        "env": [{"name": "VLLM_ADDITIONAL_ARGS", "value": ""}],
                    }
                ]
            },
        },
        "status": {"conditions": [{"type": "Ready", "status": "True"}]},
    }
    mock_custom.create_namespaced_custom_object.side_effect = Exception("Connection refused")

    q = await tuner.subscribe()
    config = TuningConfig(n_trials=2, eval_requests=5, warmup_requests=0)
    await tuner.start(config, "http://mock:8080")

    events = []
    while not q.empty():
        events.append(q.get_nowait())
    error_events = [e for e in events if e.get("type") == "tuning_error"]
    assert len(error_events) >= 1
    assert "Connection refused" in error_events[0]["data"].get("error", "")


@pytest.mark.asyncio
async def test_is_ready_failure_broadcasts_warning(auto_tuner_instance, mock_k8s_clients):
    """C2: IS ready failure → tuning_warning SSE with rollback message."""
    tuner = auto_tuner_instance

    tuner._preflight_check = AsyncMock(return_value={"success": True})

    tuner._wait_for_ready = AsyncMock(side_effect=[True, False])
    tuner._rollback_to_snapshot = AsyncMock(return_value=True)

    mock_custom = mock_k8s_clients[2].return_value
    mock_custom.get_namespaced_custom_object.return_value = {
        "spec": {
            "template": {
                "containers": [
                    {
                        "name": "main",
                        "env": [{"name": "VLLM_ADDITIONAL_ARGS", "value": ""}],
                    }
                ]
            },
        },
        "status": {"conditions": [{"type": "Ready", "status": "True"}]},
    }
    mock_custom.create_namespaced_custom_object.return_value = None

    q = await tuner.subscribe()
    config = TuningConfig(n_trials=1, eval_requests=5, warmup_requests=0)
    await tuner.start(config, "http://mock:8080")

    events = []
    while not q.empty():
        events.append(q.get_nowait())
    warning_events = [e for e in events if e.get("type") == "tuning_warning"]
    assert len(warning_events) >= 1
    assert any("롤백" in e["data"].get("message", "") for e in warning_events)


@pytest.mark.asyncio
async def test_trial_evaluation_failure_broadcasts_warning(auto_tuner_instance, mock_k8s_clients):
    """C3: _run_trial_evaluation failure → tuning_warning SSE + trial FAIL."""
    tuner = auto_tuner_instance

    tuner._preflight_check = AsyncMock(return_value={"success": True})
    tuner._wait_for_ready = AsyncMock(return_value=True)
    tuner._evaluate = AsyncMock(side_effect=RuntimeError("evaluation failed"))

    mock_custom = mock_k8s_clients[2].return_value
    mock_custom.get_namespaced_custom_object.return_value = {
        "spec": {
            "template": {
                "containers": [
                    {
                        "name": "main",
                        "env": [{"name": "VLLM_ADDITIONAL_ARGS", "value": ""}],
                    }
                ]
            },
        },
        "status": {"conditions": [{"type": "Ready", "status": "True"}]},
    }
    mock_custom.create_namespaced_custom_object.return_value = None

    q = await tuner.subscribe()
    config = TuningConfig(n_trials=1, eval_requests=5, warmup_requests=0)
    await tuner.start(config, "http://mock:8080")

    events = []
    while not q.empty():
        events.append(q.get_nowait())
    warning_events = [e for e in events if e.get("type") == "tuning_warning"]
    assert len(warning_events) >= 1
    assert any("평가 실패" in e["data"].get("message", "") for e in warning_events)
    assert len(tuner.trials) == 0


@pytest.mark.asyncio
async def test_storage_fallback_broadcasts_warning(auto_tuner_instance, mock_k8s_clients):
    """B2: SQLite storage failure → tuning_warning SSE (persistence warning)."""
    tuner = auto_tuner_instance

    tuner._preflight_check = AsyncMock(return_value={"success": True})
    tuner._wait_for_ready = AsyncMock(return_value=True)
    tuner._evaluate = AsyncMock(return_value=(100.0, 50.0, 0.5))

    mock_custom = mock_k8s_clients[2].return_value
    mock_custom.get_namespaced_custom_object.return_value = {
        "spec": {
            "template": {
                "containers": [
                    {
                        "name": "main",
                        "env": [{"name": "VLLM_ADDITIONAL_ARGS", "value": ""}],
                    }
                ]
            },
        },
        "status": {"conditions": [{"type": "Ready", "status": "True"}]},
    }
    mock_custom.create_namespaced_custom_object.return_value = None

    q = await tuner.subscribe()
    config = TuningConfig(n_trials=1, eval_requests=5, warmup_requests=0)

    from ..services import auto_tuner as _at_mod

    with patch.object(_at_mod, "storage") as mock_storage:
        mock_storage.set_running = AsyncMock(return_value=1)
        mock_storage.clear_running = AsyncMock(return_value=None)
        mock_storage.save_trial = AsyncMock(side_effect=OSError("disk full"))
        await tuner.start(config, "http://mock:8080")

    events = []
    while not q.empty():
        events.append(q.get_nowait())
    warning_events = [e for e in events if e.get("type") == "tuning_warning"]
    assert len(warning_events) >= 1
    assert any("저장" in e["data"].get("message", "") for e in warning_events)


@pytest.mark.asyncio
async def test_running_false_after_preflight_failure(auto_tuner_instance, mock_k8s_clients):
    """D1: After preflight failure, _running must be False."""
    tuner = auto_tuner_instance
    from kubernetes.client.exceptions import ApiException

    mock_custom = mock_k8s_clients[2].return_value
    mock_custom.get_namespaced_custom_object.side_effect = ApiException(status=403)

    config = TuningConfig(n_trials=2, eval_requests=5, warmup_requests=0)
    result = await tuner.start(config, "http://mock:8080")

    assert "error" in result
    assert tuner._running is False


@pytest.mark.asyncio
async def test_stop_awaits_current_task(auto_tuner_instance):
    """D2: stop() awaits _current_task and cleans it up."""
    tuner = auto_tuner_instance

    task_completed = asyncio.Event()

    async def slow_tuning():
        try:
            await asyncio.sleep(10)
        except asyncio.CancelledError:
            pass
        finally:
            task_completed.set()

    task = asyncio.create_task(slow_tuning())
    async with tuner._lock:
        tuner._running = True
        tuner._current_task = task

    result = await tuner.stop()
    assert result["success"] is True

    await asyncio.sleep(0.05)
    assert task.done()


@pytest.mark.asyncio
async def test_concurrent_start_rejected(auto_tuner_instance):
    """D3: Second start() call while running is rejected."""
    tuner = auto_tuner_instance

    async with tuner._lock:
        tuner._running = True

    config = TuningConfig(n_trials=2, eval_requests=5, warmup_requests=0)
    result = await tuner.start(config, "http://mock:8080")

    assert "error" in result
    assert "실행 중" in result["error"]


# ── Boundary Value Tests ──────────────────────────────────────────────────────


def test_config_boundary_values():
    """Minimum valid boundary values (ge=1) should be accepted."""
    load_cfg = LoadTestConfig(total_requests=1, concurrency=1, max_tokens=1)
    assert load_cfg.total_requests == 1
    assert load_cfg.concurrency == 1

    tuning_cfg = TuningConfig(n_trials=1, eval_requests=1, eval_concurrency=1)
    assert tuning_cfg.n_trials == 1
    assert tuning_cfg.eval_requests == 1


def test_config_rejects_boundary_violations():
    """Zero values should be rejected by Pydantic ge=1 validators."""
    with pytest.raises(ValidationError):
        LoadTestConfig(total_requests=0)

    with pytest.raises(ValidationError):
        LoadTestConfig(concurrency=0)

    with pytest.raises(ValidationError):
        TuningConfig(n_trials=0)

    with pytest.raises(ValidationError):
        TuningConfig(eval_requests=0)


@pytest.mark.asyncio
async def test_clear_running_called_on_exception_during_tuning(auto_tuner_instance, mock_k8s_clients):
    tuner = auto_tuner_instance

    tuner._preflight_check = AsyncMock(return_value={"success": True})
    tuner._wait_for_ready = AsyncMock(return_value=True)
    tuner._evaluate = AsyncMock(side_effect=RuntimeError("simulated mid-trial crash"))

    mock_custom = mock_k8s_clients[2].return_value
    mock_custom.get_namespaced_custom_object.return_value = {
        "spec": {"predictor": {"model": {"args": []}}},
        "status": {"conditions": [{"type": "Ready", "status": "True"}]},
    }
    mock_custom.create_namespaced_custom_object.return_value = None

    from ..services import auto_tuner as _at_mod

    mock_storage = MagicMock()
    mock_storage.set_running = AsyncMock(return_value=42)
    mock_storage.clear_running = AsyncMock()

    config = TuningConfig(n_trials=1, eval_requests=5, warmup_requests=0)

    with patch.object(_at_mod, "storage", mock_storage):
        await tuner.start(config, "http://mock:8080")

    mock_storage.set_running.assert_called_once_with("tuner")
    mock_storage.clear_running.assert_called_once_with(42)


@pytest.mark.asyncio
async def test_evaluate_raises_value_error_when_model_resolution_fails(auto_tuner_instance):
    tuner = auto_tuner_instance
    config = TuningConfig(eval_requests=10, warmup_requests=0)

    from ..services import auto_tuner as _at_mod

    with patch.dict("os.environ", {}, clear=False):
        import os

        os.environ.pop("VLLM_MODEL", None)
        with patch.object(_at_mod, "resolve_model_name", new=AsyncMock(side_effect=ValueError("Cannot resolve model name from http://mock:8080. Set VLLM_MODEL env var."))):
            with pytest.raises(ValueError, match="Cannot resolve model name"):
                await tuner._evaluate("http://mock:8080", config)


def test_wait_metrics_returns_empty_when_idle(auto_tuner_instance):
    """wait_metrics returns zeroed dict when no tuning has run."""
    tuner = auto_tuner_instance
    metrics = tuner.wait_metrics
    assert metrics["total_wait_seconds"] == 0
    assert metrics["poll_count"] == 0
    assert metrics["per_trial_waits"] == []


def test_wait_metrics_tracks_poll_count(auto_tuner_instance):
    """wait_metrics tracks poll count after internal state changes."""
    tuner = auto_tuner_instance
    tuner._total_wait_seconds = 12.5
    tuner._poll_count = 7
    tuner._wait_durations = [1.0, 2.5, 3.0, 1.5, 2.0, 1.0, 1.5]
    metrics = tuner.wait_metrics
    assert metrics["total_wait_seconds"] == 12.5
    assert metrics["poll_count"] == 7
    assert len(metrics["per_trial_waits"]) == 7
    assert metrics["per_trial_waits"][0] == 1.0


@pytest.mark.asyncio
async def test_stop_returns_error_when_not_running(auto_tuner_instance):
    """stop() returns success=False when tuner is not running."""
    tuner = auto_tuner_instance
    assert tuner.is_running is False
    result = await tuner.stop()
    assert result["success"] is False
    assert "message" in result


# ── T21/T19 Extracted Module Error-Path Tests ─────────────────────────────────


@pytest.mark.asyncio
async def test_preflight_check_returns_rbac_error_on_403(auto_tuner_instance):
    """preflight_check returns rbac error_type when K8s API returns 403."""
    tuner = auto_tuner_instance
    from kubernetes.client.exceptions import ApiException

    mock_custom = tuner._k8s_custom
    mock_custom.get_namespaced_custom_object.side_effect = ApiException(status=403, reason="Forbidden")
    result = await tuner._preflight_check()
    assert result["success"] is False
    assert result["error_type"] == "rbac"


@pytest.mark.asyncio
async def test_preflight_check_returns_not_found_on_404(auto_tuner_instance):
    """preflight_check returns not_found error_type when K8s API returns 404."""
    tuner = auto_tuner_instance
    from kubernetes.client.exceptions import ApiException

    mock_custom = tuner._k8s_custom
    mock_custom.get_namespaced_custom_object.side_effect = ApiException(status=404, reason="Not Found")
    result = await tuner._preflight_check()
    assert result["success"] is False
    assert result["error_type"] == "not_found"


def test_compute_trial_score_latency_objective():
    """compute_trial_score returns negative p99 for latency objective."""
    from unittest.mock import AsyncMock

    from ..models.load_test import TuningConfig
    from ..services.tuner_logic import TunerLogic

    logic = TunerLogic(load_engine=AsyncMock())
    config = TuningConfig(n_trials=1, objective="latency")
    result = {"tps": {"total": 100}, "latency": {"p99": 0.5}}
    score = logic.compute_trial_score(result, config)
    assert score == -0.5  # negative for minimization


def test_compute_trial_score_missing_data():
    """compute_trial_score handles missing tps/latency gracefully."""
    from unittest.mock import AsyncMock

    from ..models.load_test import TuningConfig
    from ..services.tuner_logic import TunerLogic

    logic = TunerLogic(load_engine=AsyncMock())
    config = TuningConfig(n_trials=1, objective="tps")
    result = {}  # empty result
    score = logic.compute_trial_score(result, config)
    assert score == 0  # default when tps missing
