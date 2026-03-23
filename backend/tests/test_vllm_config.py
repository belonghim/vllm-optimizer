import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from typing import cast
from unittest.mock import MagicMock, patch

from ..main import app


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def client_with_vllm_config(client):
    return client


def _get_vllm_config_globals(client: TestClient, method: str | None = None):
    for route in cast(FastAPI, client.app).routes:
        if getattr(route, "path", None) != "/api/vllm-config":
            continue
        if method and method not in getattr(route, "methods", set()):
            continue
        endpoint = getattr(route, "endpoint", None)
        if endpoint is not None:
            return endpoint.__globals__
    return None


_MOCK_IS = {
    "spec": {"predictor": {"model": {
        "storageUri": "oci://test-registry/test-model",
        "args": [
            "--max-num-seqs=256",
            "--gpu-memory-utilization=0.90",
            "--max-model-len=8192",
            "--max-num-batched-tokens=2048",
        ],
    }}}
}


def test_get_vllm_config_returns_data(client_with_vllm_config):
    mock_custom = MagicMock()
    mock_custom.get_namespaced_custom_object.return_value = _MOCK_IS

    handler_globals = _get_vllm_config_globals(client_with_vllm_config)
    if handler_globals is None:
        pytest.skip("Route /api/vllm-config not found")

    with patch.dict(handler_globals, {"_get_k8s_custom": lambda: mock_custom}):
        resp = client_with_vllm_config.get("/api/vllm-config")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "max_num_seqs" in data["data"]
        assert data["data"]["max_num_seqs"] == "256"


def test_patch_vllm_config_invalid_key_422(client):
    resp = client.patch("/api/vllm-config", json={"data": {"INVALID_KEY": "value"}})
    assert resp.status_code == 422


def test_patch_vllm_config_valid_key(client):
    mock_custom = MagicMock()
    mock_custom.get_namespaced_custom_object.return_value = _MOCK_IS
    mock_custom.patch_namespaced_custom_object.return_value = MagicMock()

    handler_globals = _get_vllm_config_globals(client, method="PATCH")
    if handler_globals is None:
        pytest.skip("PATCH /api/vllm-config route not found")

    with patch.dict(handler_globals, {"_get_k8s_custom": lambda: mock_custom}):
        resp = client.patch("/api/vllm-config", json={"data": {"max_num_seqs": "512"}})
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "max_num_seqs" in data["updated_keys"]


def test_patch_vllm_config_during_tuning_409(isolated_client: TestClient):
    mock_tuner = MagicMock()
    mock_tuner.is_running = True

    if _get_vllm_config_globals(isolated_client, method="PATCH") is None:
        pytest.skip("PATCH /api/vllm-config route not found")

    with patch("routers.tuner.auto_tuner", mock_tuner):
        resp = isolated_client.patch("/api/vllm-config", json={"data": {"max_num_seqs": "512"}})
        assert resp.status_code == 409


def test_get_vllm_config_returns_storage_uri(client_with_vllm_config):
    mock_custom = MagicMock()
    mock_custom.get_namespaced_custom_object.return_value = _MOCK_IS

    handler_globals = _get_vllm_config_globals(client_with_vllm_config)
    if handler_globals is None:
        pytest.skip("Route /api/vllm-config not found")

    with patch.dict(handler_globals, {"_get_k8s_custom": lambda: mock_custom}):
        resp = client_with_vllm_config.get("/api/vllm-config")
        assert resp.status_code == 200
        data = resp.json()
        assert "storageUri" in data
        assert data["storageUri"] == "oci://test-registry/test-model"


def test_patch_storage_uri_updates_is(client):
    mock_custom = MagicMock()
    mock_custom.patch_namespaced_custom_object.return_value = MagicMock()

    handler_globals = _get_vllm_config_globals(client, method="PATCH")
    if handler_globals is None:
        pytest.skip("PATCH /api/vllm-config route not found")

    with patch.dict(handler_globals, {"_get_k8s_custom": lambda: mock_custom}):
        resp = client.patch("/api/vllm-config", json={"storageUri": "oci://new-uri"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data.get("updated_storageUri") is True

        assert mock_custom.patch_namespaced_custom_object.called
        call_kwargs = mock_custom.patch_namespaced_custom_object.call_args.kwargs
        body = call_kwargs["body"]
        model_spec = body["spec"]["predictor"]["model"]
        assert "storageUri" in model_spec
        assert model_spec["storageUri"] == "oci://new-uri"


def test_patch_vllm_config_rejects_uppercase_key(client):
    """UPPERCASE 키는 422로 거부되어야 한다"""
    resp = client.patch("/api/vllm-config", json={"data": {"MAX_NUM_SEQS": "512"}})
    assert resp.status_code == 422


def test_patch_storage_uri_during_tuning_409(client: TestClient):
    mock_tuner = MagicMock()
    mock_tuner.is_running = True

    if _get_vllm_config_globals(client, method="PATCH") is None:
        pytest.skip("PATCH /api/vllm-config route not found")

    with patch("routers.tuner.auto_tuner", mock_tuner):
        resp = client.patch("/api/vllm-config", json={"storageUri": "oci://new-uri"})
        assert resp.status_code == 409


def test_patch_tuning_args_does_not_include_storage_uri_in_body(client):
    mock_custom = MagicMock()
    mock_custom.get_namespaced_custom_object.return_value = _MOCK_IS
    mock_custom.patch_namespaced_custom_object.return_value = MagicMock()

    handler_globals = _get_vllm_config_globals(client, method="PATCH")
    if handler_globals is None:
        pytest.skip("PATCH /api/vllm-config route not found")

    with patch.dict(handler_globals, {"_get_k8s_custom": lambda: mock_custom}):
        resp = client.patch("/api/vllm-config", json={"data": {"max_num_seqs": "512"}})
        assert resp.status_code == 200

        assert mock_custom.patch_namespaced_custom_object.called
        call_kwargs = mock_custom.patch_namespaced_custom_object.call_args.kwargs
        body = call_kwargs["body"]
        model_spec = body["spec"]["predictor"]["model"]
        assert "storageUri" not in model_spec
