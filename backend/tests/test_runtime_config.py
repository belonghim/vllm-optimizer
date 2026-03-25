import pytest
from fastapi.testclient import TestClient
from services.runtime_config import RuntimeConfig
from services.shared import runtime_config


@pytest.fixture(autouse=True)
def reset_runtime_config():
    """Reset runtime_config to defaults before each test."""
    runtime_config.set_vllm_namespace("vllm-lab-dev")
    runtime_config.set_vllm_endpoint("http://llm-ov-predictor.vllm-lab-dev.svc.cluster.local:8080")
    runtime_config.set_vllm_is_name("llm-ov")
    yield
    # Reset after test as well
    runtime_config.set_vllm_namespace("vllm-lab-dev")
    runtime_config.set_vllm_endpoint("http://llm-ov-predictor.vllm-lab-dev.svc.cluster.local:8080")
    runtime_config.set_vllm_is_name("llm-ov")


@pytest.fixture
def client():
    from main import app

    return TestClient(app)


class TestRuntimeConfigSingleton:
    def test_initial_vllm_namespace_default(self):
        cfg = RuntimeConfig()
        assert cfg.vllm_namespace == "vllm-lab-dev"

    def test_initial_vllm_endpoint_default(self):
        cfg = RuntimeConfig()
        expected = "http://llm-ov-predictor.vllm-lab-dev.svc.cluster.local:8080"
        assert cfg.vllm_endpoint == expected

    def test_initial_vllm_is_name_default(self):
        cfg = RuntimeConfig()
        assert cfg.vllm_is_name == "llm-ov"

    def test_set_vllm_namespace(self):
        cfg = RuntimeConfig()
        cfg.set_vllm_namespace("custom-ns")
        assert cfg.vllm_namespace == "custom-ns"

    def test_set_vllm_endpoint(self):
        cfg = RuntimeConfig()
        cfg.set_vllm_endpoint("http://custom-endpoint:9000")
        assert cfg.vllm_endpoint == "http://custom-endpoint:9000"

    def test_set_vllm_is_name(self):
        cfg = RuntimeConfig()
        cfg.set_vllm_is_name("custom-is")
        assert cfg.vllm_is_name == "custom-is"

    def test_setters_are_independent(self):
        cfg = RuntimeConfig()
        cfg.set_vllm_namespace("ns-only")
        cfg.set_vllm_endpoint("http://ep-only:8000")
        cfg.set_vllm_is_name("is-only")
        assert cfg.vllm_namespace == "ns-only"
        assert cfg.vllm_endpoint == "http://ep-only:8000"
        assert cfg.vllm_is_name == "is-only"


class TestGetConfigEndpoint:
    def test_get_config_returns_all_fields(self, client: TestClient):
        response = client.get("/api/config")
        assert response.status_code == 200
        data = response.json()
        assert "vllm_endpoint" in data
        assert "vllm_namespace" in data
        assert "vllm_is_name" in data
        assert "vllm_model_name" in data
        assert "resolved_model_name" in data

    def test_get_config_response_structure(self, client: TestClient):
        response = client.get("/api/config")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data["vllm_endpoint"], str)
        assert isinstance(data["vllm_namespace"], str)
        assert isinstance(data["vllm_is_name"], str)
        assert isinstance(data["vllm_model_name"], str)
        assert isinstance(data["resolved_model_name"], str)


class TestPatchConfigEndpoint:
    def test_patch_config_updates_endpoint(self, client: TestClient):
        patch_payload = {"vllm_endpoint": "http://patched-endpoint:9000"}
        response = client.patch("/api/config", json=patch_payload)
        assert response.status_code == 200
        data = response.json()
        assert data["vllm_endpoint"] == "http://patched-endpoint:9000"

    def test_patch_config_updates_namespace(self, client: TestClient):
        patch_payload = {"vllm_namespace": "patched-namespace"}
        response = client.patch("/api/config", json=patch_payload)
        assert response.status_code == 200
        data = response.json()
        assert data["vllm_namespace"] == "patched-namespace"

    def test_patch_config_updates_is_name(self, client: TestClient):
        patch_payload = {"vllm_is_name": "patched-is"}
        response = client.patch("/api/config", json=patch_payload)
        assert response.status_code == 200
        data = response.json()
        assert data["vllm_is_name"] == "patched-is"

    def test_patch_config_partial_update(self, client: TestClient):
        patch_payload = {"vllm_namespace": "partial-ns"}
        response = client.patch("/api/config", json=patch_payload)
        assert response.status_code == 200
        data = response.json()
        assert data["vllm_namespace"] == "partial-ns"

    def test_patch_config_empty_patch(self, client: TestClient):
        response = client.patch("/api/config", json={})
        assert response.status_code == 200
        data = response.json()
        assert "vllm_endpoint" in data
        assert "vllm_namespace" in data
        assert "vllm_is_name" in data

    def test_patch_config_returns_all_fields(self, client: TestClient):
        response = client.patch("/api/config", json={"vllm_endpoint": "http://test:8080"})
        assert response.status_code == 200
        data = response.json()
        assert set(data.keys()) == {
            "vllm_endpoint",
            "vllm_namespace",
            "vllm_is_name",
            "vllm_model_name",
            "resolved_model_name",
        }
