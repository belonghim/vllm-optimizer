from typing import cast
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

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
    "spec": {
        "predictor": {
            "model": {
                "storageUri": "oci://test-registry/test-model",
                "args": [
                    "--max-num-seqs=256",
                    "--gpu-memory-utilization=0.90",
                    "--max-model-len=8192",
                    "--max-num-batched-tokens=2048",
                ],
            }
        }
    }
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


def test_get_returns_resources(client_with_vllm_config):
    mock_is_with_resources = {
        "spec": {
            "predictor": {
                "model": {
                    "storageUri": "oci://test-registry/test-model",
                    "args": ["--max-num-seqs=256"],
                    "resources": {
                        "requests": {"cpu": "4", "memory": "8Gi"},
                        "limits": {"cpu": "8", "memory": "16Gi"},
                    },
                }
            }
        }
    }

    mock_custom = MagicMock()
    mock_custom.get_namespaced_custom_object.return_value = mock_is_with_resources

    handler_globals = _get_vllm_config_globals(client_with_vllm_config)
    if handler_globals is None:
        pytest.skip("Route /api/vllm-config not found")

    with patch.dict(handler_globals, {"_get_k8s_custom": lambda: mock_custom}):
        resp = client_with_vllm_config.get("/api/vllm-config")
        assert resp.status_code == 200
        data = resp.json()
        assert "resources" in data
        assert data["resources"]["requests"]["cpu"] == "4"
        assert data["resources"]["requests"]["memory"] == "8Gi"
        assert data["resources"]["limits"]["cpu"] == "8"
        assert data["resources"]["limits"]["memory"] == "16Gi"


def test_get_returns_empty_resources_when_absent(client_with_vllm_config):
    mock_custom = MagicMock()
    mock_custom.get_namespaced_custom_object.return_value = _MOCK_IS

    handler_globals = _get_vllm_config_globals(client_with_vllm_config)
    if handler_globals is None:
        pytest.skip("Route /api/vllm-config not found")

    with patch.dict(handler_globals, {"_get_k8s_custom": lambda: mock_custom}):
        resp = client_with_vllm_config.get("/api/vllm-config")
        assert resp.status_code == 200
        data = resp.json()
        assert "resources" in data
        assert data["resources"] == {}


def test_patch_partial_update_preserves_existing_args(client: TestClient):
    mock_is = {
        "spec": {
            "predictor": {
                "model": {
                    "args": [
                        "--max-num-seqs=256",
                        "--gpu-memory-utilization=0.90",
                        "--max-model-len=8192",
                    ]
                }
            }
        }
    }
    mock_custom = MagicMock()
    mock_custom.get_namespaced_custom_object.return_value = mock_is
    mock_custom.patch_namespaced_custom_object.return_value = MagicMock()

    handler_globals = _get_vllm_config_globals(client, method="PATCH")
    if handler_globals is None:
        pytest.skip("PATCH /api/vllm-config route not found")

    with patch.dict(handler_globals, {"_get_k8s_custom": lambda: mock_custom}):
        resp = client.patch("/api/vllm-config", json={"data": {"max_num_seqs": "512"}})
        assert resp.status_code == 200

        body = mock_custom.patch_namespaced_custom_object.call_args.kwargs["body"]
        patched_args = body["spec"]["predictor"]["model"]["args"]

        assert "--max-num-seqs=512" in patched_args
        assert "--gpu-memory-utilization=0.90" in patched_args
        assert "--max-model-len=8192" in patched_args
        assert "--max-num-seqs=256" not in patched_args
        assert len(patched_args) == 3


def test_patch_empty_data_preserves_all_args(client: TestClient):
    mock_custom = MagicMock()
    mock_custom.get_namespaced_custom_object.return_value = _MOCK_IS
    mock_custom.patch_namespaced_custom_object.return_value = MagicMock()

    handler_globals = _get_vllm_config_globals(client, method="PATCH")
    if handler_globals is None:
        pytest.skip("PATCH /api/vllm-config route not found")

    with patch.dict(handler_globals, {"_get_k8s_custom": lambda: mock_custom}):
        resp = client.patch("/api/vllm-config", json={"data": {}})
        assert resp.status_code == 200
        payload = resp.json()
        assert payload["success"] is True
        assert payload["updated_keys"] == []
        assert payload["updated_storageUri"] is False
        assert mock_custom.patch_namespaced_custom_object.call_count == 0


def test_patch_boolean_false_removes_flag(client: TestClient):
    mock_is = {
        "spec": {
            "predictor": {
                "model": {
                    "args": [
                        "--max-num-seqs=256",
                        "--enable-chunked-prefill",
                        "--max-model-len=8192",
                    ]
                }
            }
        }
    }
    mock_custom = MagicMock()
    mock_custom.get_namespaced_custom_object.return_value = mock_is
    mock_custom.patch_namespaced_custom_object.return_value = MagicMock()

    handler_globals = _get_vllm_config_globals(client, method="PATCH")
    if handler_globals is None:
        pytest.skip("PATCH /api/vllm-config route not found")

    with patch.dict(handler_globals, {"_get_k8s_custom": lambda: mock_custom}):
        resp = client.patch(
            "/api/vllm-config",
            json={"data": {"enable_chunked_prefill": "false"}},
        )
        assert resp.status_code == 200

        body = mock_custom.patch_namespaced_custom_object.call_args.kwargs["body"]
        patched_args = body["spec"]["predictor"]["model"]["args"]

        assert "--enable-chunked-prefill" not in patched_args
        assert "--max-num-seqs=256" in patched_args
        assert "--max-model-len=8192" in patched_args
        assert len(patched_args) == 2


def test_patch_resources_valid(client):
    mock_custom = MagicMock()
    mock_custom.patch_namespaced_custom_object.return_value = MagicMock()

    handler_globals = _get_vllm_config_globals(client, method="PATCH")
    if handler_globals is None:
        pytest.skip("PATCH /api/vllm-config route not found")

    with patch.dict(handler_globals, {"_get_k8s_custom": lambda: mock_custom}):
        resp = client.patch("/api/vllm-config", json={"resources": {"requests": {"cpu": "4"}}})
        assert resp.status_code == 200

        body = mock_custom.patch_namespaced_custom_object.call_args.kwargs["body"]
        model_spec = body["spec"]["predictor"]["model"]
        assert "resources" in model_spec
        assert model_spec["resources"]["requests"]["cpu"] == "4"


def test_patch_resources_invalid_key(client):
    handler_globals = _get_vllm_config_globals(client, method="PATCH")
    if handler_globals is None:
        pytest.skip("PATCH /api/vllm-config route not found")

    resp = client.patch("/api/vllm-config", json={"resources": {"requests": {"disk": "10Gi"}}})
    assert resp.status_code == 422


def test_patch_resources_only(client):
    mock_custom = MagicMock()
    mock_custom.patch_namespaced_custom_object.return_value = MagicMock()

    handler_globals = _get_vllm_config_globals(client, method="PATCH")
    if handler_globals is None:
        pytest.skip("PATCH /api/vllm-config route not found")

    with patch.dict(handler_globals, {"_get_k8s_custom": lambda: mock_custom}):
        resp = client.patch("/api/vllm-config", json={"resources": {"limits": {"memory": "32Gi"}}})
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert mock_custom.patch_namespaced_custom_object.called


def test_patch_combined_data_and_resources(client):
    mock_custom = MagicMock()
    mock_custom.get_namespaced_custom_object.return_value = _MOCK_IS
    mock_custom.patch_namespaced_custom_object.return_value = MagicMock()

    handler_globals = _get_vllm_config_globals(client, method="PATCH")
    if handler_globals is None:
        pytest.skip("PATCH /api/vllm-config route not found")

    with patch.dict(handler_globals, {"_get_k8s_custom": lambda: mock_custom}):
        resp = client.patch(
            "/api/vllm-config",
            json={"data": {"max_num_seqs": "512"}, "resources": {"limits": {"cpu": "8", "memory": "16Gi"}}},
        )
        assert resp.status_code == 200

        body = mock_custom.patch_namespaced_custom_object.call_args.kwargs["body"]
        model_spec = body["spec"]["predictor"]["model"]
        assert "args" in model_spec
        assert any("--max-num-seqs=512" in a for a in model_spec["args"])
        assert "resources" in model_spec
        assert model_spec["resources"]["limits"]["cpu"] == "8"
        assert model_spec["resources"]["limits"]["memory"] == "16Gi"
