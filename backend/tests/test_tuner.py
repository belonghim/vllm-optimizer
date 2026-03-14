import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock, patch
import asyncio
import datetime

from ..main import app
from ..services.auto_tuner import AutoTuner, K8S_NAMESPACE, K8S_DEPLOYMENT
from ..models.load_test import TuningConfig, TuningTrial, LoadTestConfig


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


def test_tuner_status_has_running_field(client):
    resp = client.get("/api/tuner/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "running" in data
    assert isinstance(data["running"], bool)
    assert data["running"] is False


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
