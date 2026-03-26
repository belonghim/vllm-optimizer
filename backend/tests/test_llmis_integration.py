from typing import cast
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from services.cr_adapter import LLMInferenceServiceAdapter


_MOCK_LLMIS = {
    "spec": {
        "template": {
            "containers": [
                {
                    "name": "main",
                    "env": [
                        {
                            "name": "VLLM_ADDITIONAL_ARGS",
                            "value": "--max-num-seqs=128 --gpu-memory-utilization=0.85",
                        }
                    ],
                    "resources": {
                        "requests": {"cpu": "4", "memory": "16Gi"},
                        "limits": {"cpu": "8", "memory": "32Gi"},
                    },
                }
            ]
        },
        "model": {
            "uri": "oci://quay.io/test/model",
        },
    }
}


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


def test_get_vllm_config_llmis(isolated_client: TestClient, monkeypatch):
    monkeypatch.setenv("VLLM_CR_TYPE", "llminferenceservice")

    mock_custom = MagicMock()
    mock_custom.get_namespaced_custom_object.return_value = _MOCK_LLMIS

    handler_globals = _get_vllm_config_globals(isolated_client)
    if handler_globals is None:
        pytest.skip("Route /api/vllm-config not found")

    with patch.dict(handler_globals, {"_get_k8s_custom": lambda: mock_custom}):
        resp = isolated_client.get("/api/vllm-config")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["data"]["max_num_seqs"] == "128"
        assert data["data"]["gpu_memory_utilization"] == "0.85"
        assert data["storageUri"] == "oci://quay.io/test/model"
        assert data["resources"]["requests"]["cpu"] == "4"


def test_patch_vllm_config_llmis_args(isolated_client: TestClient, monkeypatch):
    monkeypatch.setenv("VLLM_CR_TYPE", "llminferenceservice")

    mock_custom = MagicMock()
    mock_custom.get_namespaced_custom_object.return_value = _MOCK_LLMIS
    mock_custom.patch_namespaced_custom_object.return_value = {}

    handler_globals = _get_vllm_config_globals(isolated_client, method="PATCH")
    if handler_globals is None:
        pytest.skip("PATCH /api/vllm-config route not found")

    with patch.dict(handler_globals, {"_get_k8s_custom": lambda: mock_custom}):
        resp = isolated_client.patch("/api/vllm-config", json={"data": {"max_num_seqs": "256"}})
        assert resp.status_code == 200

        assert mock_custom.patch_namespaced_custom_object.called
        body = mock_custom.patch_namespaced_custom_object.call_args.kwargs["body"]
        containers = body["spec"]["template"]["containers"]
        main = next(c for c in containers if c["name"] == "main")
        env_entry = next(e for e in main["env"] if e["name"] == "VLLM_ADDITIONAL_ARGS")
        assert "--max-num-seqs=256" in env_entry["value"]


def test_patch_vllm_config_llmis_resources(isolated_client: TestClient, monkeypatch):
    monkeypatch.setenv("VLLM_CR_TYPE", "llminferenceservice")

    mock_custom = MagicMock()
    mock_custom.patch_namespaced_custom_object.return_value = {}

    handler_globals = _get_vllm_config_globals(isolated_client, method="PATCH")
    if handler_globals is None:
        pytest.skip("PATCH /api/vllm-config route not found")

    with patch.dict(handler_globals, {"_get_k8s_custom": lambda: mock_custom}):
        resp = isolated_client.patch(
            "/api/vllm-config",
            json={"resources": {"requests": {"cpu": "8"}, "limits": {"cpu": "16"}}},
        )
        assert resp.status_code == 200

        body = mock_custom.patch_namespaced_custom_object.call_args.kwargs["body"]
        containers = body["spec"]["template"]["containers"]
        main = next(c for c in containers if c["name"] == "main")
        assert "resources" in main


def test_patch_vllm_config_llmis_model_uri(isolated_client: TestClient, monkeypatch):
    monkeypatch.setenv("VLLM_CR_TYPE", "llminferenceservice")

    mock_custom = MagicMock()
    mock_custom.patch_namespaced_custom_object.return_value = {}

    handler_globals = _get_vllm_config_globals(isolated_client, method="PATCH")
    if handler_globals is None:
        pytest.skip("PATCH /api/vllm-config route not found")

    with patch.dict(handler_globals, {"_get_k8s_custom": lambda: mock_custom}):
        resp = isolated_client.patch("/api/vllm-config", json={"storageUri": "oci://new/model"})
        assert resp.status_code == 200

        body = mock_custom.patch_namespaced_custom_object.call_args.kwargs["body"]
        assert body["spec"]["model"]["uri"] == "oci://new/model"


def test_auto_tuner_snapshot_llmis():
    adapter = LLMInferenceServiceAdapter()
    result = adapter.snapshot_args(_MOCK_LLMIS["spec"])
    assert result == "--max-num-seqs=128 --gpu-memory-utilization=0.85"


def test_auto_tuner_rollback_llmis():
    adapter = LLMInferenceServiceAdapter()
    patch_body = adapter.build_rollback_patch("--max-num-seqs=128")
    containers = patch_body["spec"]["template"]["containers"]
    assert containers[0]["env"][0]["name"] == "VLLM_ADDITIONAL_ARGS"
    assert containers[0]["env"][0]["value"] == "--max-num-seqs=128"


def test_collector_pod_selector_llmis():
    adapter = LLMInferenceServiceAdapter()
    assert adapter.pod_label_selector("small-llm-d") == "app.kubernetes.io/name=small-llm-d"


def test_collector_prometheus_job_llmis():
    adapter = LLMInferenceServiceAdapter()
    assert adapter.prometheus_job("small-llm-d") == "small-llm-d-kserve-workload-svc"
    assert adapter.dcgm_pod_pattern("small-llm-d") == "small-llm-d-kserve.*"
