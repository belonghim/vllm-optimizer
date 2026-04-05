"""
LLMIS (LLMInferenceService) 어댑터 경로 테스트.

KServe InferenceServiceAdapter 테스트는 test_vllm_config.py에 유지.
"""

from unittest.mock import MagicMock, patch

import pytest
from services.cr_adapter import LLMInferenceServiceAdapter

# Reuse fixtures and helper from test_vllm_config to avoid duplication and test isolation issues
from .test_vllm_config import _get_vllm_config_globals, client, client_with_vllm_config  # noqa: F401


def test_get_vllm_config_resolves_model_name_for_llmisvc(client_with_vllm_config):
    mock_custom = MagicMock()
    mock_custom.get_namespaced_custom_object.return_value = {
        "spec": {
            "model": {
                "name": "OpenVINO/Phi-4-mini-instruct-int4-ov",
                "uri": "oci://test-registry/test-model",
            }
        }
    }

    handler_globals = _get_vllm_config_globals(client_with_vllm_config)
    if handler_globals is None:
        pytest.skip("Route /api/vllm-config not found")

    with patch.dict(
        handler_globals,
        {
            "_get_k8s_custom": lambda: mock_custom,
            "_get_vllm_is_name": lambda: "small-llm-d",
            "get_cr_adapter": lambda: LLMInferenceServiceAdapter(),
        },
    ):
        resp = client_with_vllm_config.get("/api/vllm-config")
        assert resp.status_code == 200
        body = resp.json()
        assert body["modelName"] == "OpenVINO/Phi-4-mini-instruct-int4-ov"


def test_get_vllm_config_model_name_fallback_for_llmisvc(client_with_vllm_config):
    mock_custom = MagicMock()
    mock_custom.get_namespaced_custom_object.return_value = {
        "spec": {
            "model": {
                "uri": "oci://test-registry/test-model",
            }
        }
    }

    handler_globals = _get_vllm_config_globals(client_with_vllm_config)
    if handler_globals is None:
        pytest.skip("Route /api/vllm-config not found")

    with patch.dict(
        handler_globals,
        {
            "_get_k8s_custom": lambda: mock_custom,
            "_get_vllm_is_name": lambda: "small-llm-d",
            "get_cr_adapter": lambda: LLMInferenceServiceAdapter(),
        },
    ):
        resp = client_with_vllm_config.get("/api/vllm-config")
        assert resp.status_code == 200
        body = resp.json()
        assert body["modelName"] == "small-llm-d"
