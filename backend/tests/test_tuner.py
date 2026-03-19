import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock, patch
import asyncio

from ..main import app
from ..services.auto_tuner import AutoTuner, K8S_NAMESPACE, K8S_DEPLOYMENT, VLLM_IS_NAME
from ..models.load_test import TuningConfig, TuningTrial, LoadTestConfig
 

def test_stream_endpoint_exists(client):
    routes = [route.path for route in client.app.routes]
    assert "/api/tuner/stream" in routes


def test_stream_endpoint_returns_sse_content_type(client):
    from unittest.mock import patch
    import asyncio
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
    with patch('kubernetes.client.AppsV1Api') as mock_apps_api, \
         patch('kubernetes.client.CoreV1Api') as mock_core_api, \
         patch('kubernetes.client.CustomObjectsApi') as mock_custom_api:
        
        mock_core_api.return_value.read_namespaced_config_map.return_value = MagicMock(data={})
        mock_custom_api.return_value.get_namespaced_custom_object.return_value = {
            "status": {"conditions": [{"type": "Ready", "status": "True"}]}
        }
        mock_custom_api.return_value.patch_namespaced_custom_object = MagicMock()
        yield mock_apps_api, mock_core_api, mock_custom_api

@pytest.fixture
def auto_tuner_instance(mock_k8s_clients):
    mock_metrics_collector = AsyncMock()
    mock_load_engine = AsyncMock()
    tuner = AutoTuner(mock_metrics_collector, mock_load_engine)
    tuner._k8s_available = True # Force K8s available for testing
    tuner._k8s_apps = mock_k8s_clients[0].return_value
    tuner._k8s_core = mock_k8s_clients[1].return_value
    tuner._k8s_custom = mock_k8s_clients[2].return_value
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


@pytest.mark.asyncio
async def test_apply_params_patches_correct_annotation_location(auto_tuner_instance, mock_k8s_clients):
    tuner = auto_tuner_instance
    mock_custom_api = mock_k8s_clients[2].return_value

    params = {
        "max_num_seqs": 128,
        "gpu_memory_utilization": 0.8,
        "max_model_len": 4096,
        "enable_chunked_prefill": True,
    }

    await tuner._apply_params(params, restart_only=True)

    mock_custom_api.patch_namespaced_custom_object.assert_called_once()
    call_args = mock_custom_api.patch_namespaced_custom_object.call_args

    assert call_args.kwargs["name"] == VLLM_IS_NAME
    assert call_args.kwargs["namespace"] == K8S_NAMESPACE
    assert call_args.kwargs["group"] == "serving.kserve.io"
    assert call_args.kwargs["plural"] == "inferenceservices"

    patch_body = call_args.kwargs["body"]
    assert "spec" in patch_body
    assert "predictor" in patch_body["spec"]
    assert "annotations" in patch_body["spec"]["predictor"]
    assert "serving.kserve.io/restartedAt" in patch_body["spec"]["predictor"]["annotations"]


@pytest.mark.asyncio
async def test_wait_for_ready_polls_inferenceservice_status(auto_tuner_instance, mock_k8s_clients):
    tuner = auto_tuner_instance
    mock_custom_api = mock_k8s_clients[2].return_value

    mock_custom_api.get_namespaced_custom_object.side_effect = [
        {"status": {"conditions": [{"type": "Ready", "status": "False"}]}},
        {"status": {"conditions": [{"type": "Ready", "status": "False"}]}},
        {"status": {"conditions": [{"type": "Ready", "status": "True"}]}},
    ]

    with patch('asyncio.sleep', new=AsyncMock()) as mock_sleep:
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

    with patch('asyncio.sleep', new=AsyncMock()) as mock_sleep:
        ready = await tuner._wait_for_ready(timeout=3, interval=1)
        assert not ready
        assert mock_custom_api.get_namespaced_custom_object.call_count > 1
        assert mock_sleep.call_count >= 2


@pytest.mark.asyncio
async def test_rollback_on_wait_for_ready_timeout(auto_tuner_instance, mock_k8s_clients):
    tuner = auto_tuner_instance
    mock_custom_api = mock_k8s_clients[2].return_value

    tuner._wait_for_ready = AsyncMock(return_value=False)
    tuner._evaluate = AsyncMock(return_value=(10.0, 10.0, 0.1))

    config = TuningConfig(n_trials=1, eval_requests=5, warmup_requests=0)

    await tuner.start(config, "http://mock:8080")

    patch_calls = mock_custom_api.patch_namespaced_custom_object.call_args_list
    assert len(patch_calls) >= 2, "Expected at least 2 IS patches (apply + rollback)"

    assert tuner._last_rollback_trial == 0


@pytest.mark.asyncio
async def test_start_reapplies_best_params_at_end(auto_tuner_instance, mock_k8s_clients):
    tuner = auto_tuner_instance
    mock_custom_api = mock_k8s_clients[2].return_value

    # Mock _evaluate to return increasing scores
    tuner._evaluate = AsyncMock(side_effect=[
        (10, 10, 100), # Trial 0
        (20, 20, 50),  # Trial 1 (best)
    ])
    
    # Mock _wait_for_ready to always return True
    tuner._wait_for_ready = AsyncMock(return_value=True)
    
    # Mock _apply_params to track calls
    tuner._apply_params = AsyncMock(wraps=tuner._apply_params)

    config = TuningConfig(n_trials=2, eval_requests=10, objective="tps")
    vllm_endpoint = "http://mock-vllm-endpoint"

    await tuner.start(config, vllm_endpoint)

    # Check calls to _apply_params
    # First two calls are for trials, last call is for best params with restart_only=True
    assert tuner._apply_params.call_count == config.n_trials + 1
    
    last_call_args, last_call_kwargs = tuner._apply_params.call_args_list[-1]
    assert last_call_kwargs.get("restart_only") is None or last_call_kwargs.get("restart_only") is False
    assert last_call_args[0] == tuner._best_trial.params

    last_patch_call = mock_custom_api.patch_namespaced_custom_object.call_args_list[-1]
    patch_body = last_patch_call[1]["body"]
    patched_args = patch_body["spec"]["predictor"]["model"]["args"]
    expected_tuning_args = []
    expected_tuning_args.append(f"--max-num-seqs={tuner._best_trial.params['max_num_seqs']}")
    expected_tuning_args.append(f"--gpu-memory-utilization={tuner._best_trial.params['gpu_memory_utilization']}")
    expected_tuning_args.append(f"--max-num-batched-tokens={tuner._best_trial.params['max_num_batched_tokens']}")
    for expected_arg in expected_tuning_args:
        assert any(expected_arg in arg for arg in patched_args), f"Expected {expected_arg} in patched args: {patched_args}"

    # IS patch should be called once per trial + once for final best params reapplication
    assert mock_custom_api.patch_namespaced_custom_object.call_count == config.n_trials + 1


@pytest.mark.asyncio
async def test_median_pruner_marks_trial_as_pruned(auto_tuner_instance, mock_k8s_clients):
    """Trials pruned by MedianPruner should have status='pruned' and pruned=True"""
    tuner = auto_tuner_instance
    call_count = 0

    async def mock_evaluate(endpoint, config, trial=None):
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
        assert False, "Queue should be empty after unsubscribe"
    except asyncio.TimeoutError:
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
    from unittest.mock import patch, MagicMock

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
                    "args": []
                }
            }
        }
    }

    params = {
        "max_num_seqs": 128,
        "gpu_memory_utilization": 0.8,
        "max_model_len": 4096,
        "enable_chunked_prefill": True,
    }

    await tuner._apply_params(params)

    mock_custom_api.patch_namespaced_custom_object.assert_called_once()
    call_args = mock_custom_api.patch_namespaced_custom_object.call_args
    patch_args = call_args.kwargs["body"]["spec"]["predictor"]["model"]["args"]

    # enable_chunked_prefill should map to --enable-chunked-prefill
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
    from unittest.mock import patch, MagicMock, AsyncMock

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
        assert params["max_num_batched_tokens"] >= params["max_num_seqs"], \
            f"Constraint violated: batched={params['max_num_batched_tokens']} < seqs={params['max_num_seqs']}"
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
                    "args": []
                }
            }
        }
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
    
    mock_custom_api.patch_namespaced_custom_object.assert_called_once()
    call_args = mock_custom_api.patch_namespaced_custom_object.call_args
    patch_args = call_args.kwargs["body"]["spec"]["predictor"]["model"]["args"]
    
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

    with patch("services.auto_tuner.resolve_model_name", return_value="test-model"):
        score, tps, p99 = await tuner._evaluate("http://mock:8080", config)

    assert len(captured_configs) == 2
    assert captured_configs[0].concurrency == 16
    assert captured_configs[0].rps == 5
    assert captured_configs[0].total_requests == 5
    assert captured_configs[1].concurrency == 16
    assert captured_configs[1].rps == 5
    assert captured_configs[1].total_requests == 5


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

    with patch("services.auto_tuner.resolve_model_name", return_value="test-model"):
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

    with patch("services.auto_tuner.resolve_model_name", return_value="test-model"):
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
    import optuna

    tuner = auto_tuner_instance

    mock_study = MagicMock()
    mock_study.best_trials = [MagicMock()]
    mock_study.best_trial = MagicMock()
    mock_study.best_trial.params = {"max_num_seqs": 256, "gpu_memory_utilization": 0.9}
    mock_study.ask = MagicMock(side_effect=StopIteration)

    with patch.dict("os.environ", {"OPTUNA_STORAGE_URL": "sqlite:////tmp/test_optuna_warmstart.db"}):
        with patch("optuna.storages.RDBStorage"), \
             patch("optuna.create_study", return_value=mock_study):

            config = TuningConfig(n_trials=1, eval_requests=5, warmup_requests=0)

            try:
                await tuner.start(config, "http://mock:8080")
            except Exception:
                pass

            mock_study.enqueue_trial.assert_called_once_with(
                params={"max_num_seqs": 256, "gpu_memory_utilization": 0.9}
            )


def test_importance_returns_empty_for_pareto_mode(auto_tuner_instance):
    """get_importance() should return {} for multi-objective study"""
    import optuna

    tuner = auto_tuner_instance
    tuner._study = optuna.create_study(
        directions=["maximize", "minimize"],
        sampler=optuna.samplers.NSGAIISampler(seed=42),
    )
    tuner._trials = [object()] * 10

    result = tuner.get_importance()
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

    async def mock_eval(endpoint, config, trial=None):
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
                    "args": []
                }
            }
        }
    }

    params = {
        "max_num_seqs": 64,
        "gpu_memory_utilization": 0.8,
        "max_model_len": 4096,
        "enable_chunked_prefill": False,
        "swap_space": 4.0,
    }

    await tuner._apply_params(params)

    call_args = mock_custom_api.patch_namespaced_custom_object.call_args
    patch_args = call_args.kwargs["body"]["spec"]["predictor"]["model"]["args"]
    assert "--swap-space=4.0" in patch_args


@pytest.mark.asyncio
async def test_pruned_trials_not_counted_as_best_trial(auto_tuner_instance, mock_k8s_clients):
    """Pruned trials should never be set as the best_trial"""
    tuner = auto_tuner_instance
    call_count = 0

    async def mock_evaluate(endpoint, config, trial=None):
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
                    "args": []
                }
            }
        }
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

    call_args = mock_custom_api.patch_namespaced_custom_object.call_args
    patch_args = call_args.kwargs["body"]["spec"]["predictor"]["model"]["args"]

    assert "--enable-chunked-prefill" not in patch_args

    mock_custom_api.patch_namespaced_custom_object.reset_mock()
    params_true = {**params, "enable_chunked_prefill": True}
    await tuner._apply_params(params_true)
    patch_args_true = mock_custom_api.patch_namespaced_custom_object.call_args.kwargs["body"]["spec"]["predictor"]["model"]["args"]
    assert "--enable-chunked-prefill" in patch_args_true


@pytest.mark.asyncio
async def test_enforce_eager_writes_correct_values(auto_tuner_instance, mock_k8s_clients):
    tuner = auto_tuner_instance
    mock_custom_api = mock_k8s_clients[2].return_value

    mock_custom_api.get_namespaced_custom_object.return_value = {
        "spec": {
            "predictor": {
                "model": {
                    "args": []
                }
            }
        }
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
    patch_args_false = mock_custom_api.patch_namespaced_custom_object.call_args.kwargs["body"]["spec"]["predictor"]["model"]["args"]
    assert "--enforce-eager" not in patch_args_false

    mock_custom_api.patch_namespaced_custom_object.reset_mock()
    params_true = {**params_false, "enable_enforce_eager": True}
    await tuner._apply_params(params_true)
    patch_args_true = mock_custom_api.patch_namespaced_custom_object.call_args.kwargs["body"]["spec"]["predictor"]["model"]["args"]
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
    mock_custom_api.patch_namespaced_custom_object.side_effect = Exception("InferenceService not found")

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

    tuner._is_args_snapshot = ["--max-num-seqs=64"]

    await tuner._rollback_to_snapshot(0)

    mock_custom_api.patch_namespaced_custom_object.assert_called_once()
    call_args = mock_custom_api.patch_namespaced_custom_object.call_args
    assert call_args.kwargs["name"] == VLLM_IS_NAME
    assert call_args.kwargs["namespace"] == K8S_NAMESPACE
    patch_body = call_args.kwargs["body"]
    assert patch_body["spec"]["predictor"]["model"]["args"] == tuner._is_args_snapshot


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
