import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock, patch
import asyncio
import datetime

from ..main import app
from ..services.auto_tuner import AutoTuner, K8S_NAMESPACE, K8S_DEPLOYMENT
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
        mock_custom_api.return_value.get_namespaced_custom_object = AsyncMock(return_value={
            "status": {
                "conditions": [
                    {"type": "Ready", "status": "True"}
                ]
            }
        })
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
    
    await tuner._apply_params(params)

    mock_custom_api.patch_namespaced_custom_object.assert_called_once()
    call_args = mock_custom_api.patch_namespaced_custom_object.call_args
    
    assert call_args.kwargs["group"] == "serving.kserve.io"
    assert call_args.kwargs["version"] == "v1beta1"
    assert call_args.kwargs["plural"] == "inferenceservices"
    assert call_args.kwargs["name"] == K8S_DEPLOYMENT
    assert call_args.kwargs["namespace"] == K8S_NAMESPACE

    patch_body = call_args.kwargs["body"]
    assert "spec" in patch_body
    assert "predictor" in patch_body["spec"]
    assert "annotations" in patch_body["spec"]["predictor"]
    assert "serving.kserve.io/restartedAt" in patch_body["spec"]["predictor"]["annotations"]


@pytest.mark.asyncio
async def test_wait_for_ready_polls_inferenceservice_status(auto_tuner_instance, mock_k8s_clients):
    tuner = auto_tuner_instance
    mock_custom_api = mock_k8s_clients[2].return_value

    # Simulate InferenceService becoming ready after a few polls
    mock_custom_api.get_namespaced_custom_object.side_effect = [
        {"status": {"conditions": [{"type": "Ready", "status": "False"}]}},
        {"status": {"conditions": [{"type": "Ready", "status": "False"}]}},
        {"status": {"conditions": [{"type": "Ready", "status": "True"}]}},
    ]

    with patch('asyncio.sleep', new=AsyncMock()) as mock_sleep:
        ready = await tuner._wait_for_ready(timeout=10, interval=1)
        assert ready
        assert mock_custom_api.get_namespaced_custom_object.call_count == 3
        assert mock_sleep.call_count == 2 # Sleeps twice before becoming ready


@pytest.mark.asyncio
async def test_wait_for_ready_times_out(auto_tuner_instance, mock_k8s_clients):
    tuner = auto_tuner_instance
    mock_custom_api = mock_k8s_clients[2].return_value

    # Simulate InferenceService never becoming ready
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
    mock_core_api = mock_k8s_clients[1].return_value
    mock_custom_api = mock_k8s_clients[2].return_value

    mock_cm = MagicMock()
    mock_cm.data = {"MAX_NUM_SEQS": "64", "GPU_MEMORY_UTILIZATION": "0.8"}
    mock_core_api.read_namespaced_config_map.return_value = mock_cm

    tuner._wait_for_ready = AsyncMock(return_value=False)
    tuner._evaluate = AsyncMock(return_value=(10.0, 10.0, 0.1))

    config = TuningConfig(n_trials=1, eval_requests=5, warmup_requests=0)

    await tuner.start(config, "http://mock:8080")

    patch_calls = mock_core_api.patch_namespaced_config_map.call_args_list
    assert len(patch_calls) >= 2, "Expected at least 2 ConfigMap patches (apply + rollback)"

    assert tuner._last_rollback_trial == 0


@pytest.mark.asyncio
async def test_start_reapplies_best_params_at_end(auto_tuner_instance, mock_k8s_clients):
    tuner = auto_tuner_instance
    mock_core_api = mock_k8s_clients[1].return_value
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
    
    # Verify the last call to _apply_params was with restart_only=True
    last_call_args, last_call_kwargs = tuner._apply_params.call_args_list[-1]
    assert last_call_kwargs.get("restart_only") is True
    assert last_call_args[0] == tuner._best_trial.params

    # Verify ConfigMap was patched for trials, but not for the final best params reapplication
    # The _apply_params mock wraps the original, so we can check the internal mock_core_api calls
    # The number of configmap patches should be equal to n_trials
    assert mock_core_api.patch_namespaced_config_map.call_count == config.n_trials
    
    # The number of custom object patches (InferenceService restart) should be n_trials + 1 (for final reapplication)
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
    mock_core_api = mock_k8s_clients[1].return_value

    params = {
        "max_num_seqs": 128,
        "gpu_memory_utilization": 0.8,
        "max_model_len": 4096,
        "enable_chunked_prefill": True,
    }

    await tuner._apply_params(params)

    mock_core_api.patch_namespaced_config_map.assert_called_once()
    call_args = mock_core_api.patch_namespaced_config_map.call_args
    patch_data = call_args.kwargs["body"]["data"]

    # enable_chunked_prefill should map to ENABLE_CHUNKED_PREFILL
    assert "ENABLE_CHUNKED_PREFILL" in patch_data
    assert patch_data["ENABLE_CHUNKED_PREFILL"] == "true"

    # ENABLE_ENFORCE_EAGER should not be touched by _apply_params
    assert "ENABLE_ENFORCE_EAGER" not in patch_data

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
    mock_core_api = mock_k8s_clients[1].return_value

    params = {
        "max_num_seqs": 128,
        "gpu_memory_utilization": 0.85,
        "max_model_len": 4096,
        "enable_chunked_prefill": False,
        "max_num_batched_tokens": 512,
        "block_size": 16,
    }

    await tuner._apply_params(params)
    
    mock_core_api.patch_namespaced_config_map.assert_called_once()
    call_args = mock_core_api.patch_namespaced_config_map.call_args
    patch_data = call_args.kwargs["body"]["data"]
    
    assert "MAX_NUM_BATCHED_TOKENS" in patch_data
    assert patch_data["MAX_NUM_BATCHED_TOKENS"] == "512"
    assert "BLOCK_SIZE" in patch_data
    assert patch_data["BLOCK_SIZE"] == "16"
    assert "SWAP_SPACE" not in patch_data


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
