"""Unit tests for GET/PATCH /api/config endpoints."""

import pytest

pytestmark = pytest.mark.slow


@pytest.fixture
def client(isolated_client):
    """Config tests use isolated_client directly."""
    yield isolated_client


class TestGetConfig:
    def test_get_config_returns_cr_type(self, client):
        """Test that GET /api/config returns cr_type."""
        r = client.get("/api/config")
        assert r.status_code == 200
        data = r.json()
        assert "cr_type" in data
        assert isinstance(data["cr_type"], str)

    def test_get_config_returns_all_required_fields(self, client):
        """Test that GET /api/config returns all required fields."""
        r = client.get("/api/config")
        assert r.status_code == 200
        data = r.json()
        required_fields = [
            "vllm_endpoint",
            "vllm_namespace",
            "vllm_is_name",
            "vllm_model_name",
            "resolved_model_name",
            "cr_type",
            "configmap_updated",
        ]
        for field in required_fields:
            assert field in data, f"Missing field: {field}"

    def test_get_config_configmap_updated_is_true(self, client):
        """Test that configmap_updated is True on GET (no write)."""
        r = client.get("/api/config")
        assert r.status_code == 200
        data = r.json()
        assert data["configmap_updated"] is True


class TestPatchConfig:
    def test_patch_valid_cr_type_inferenceservice(self, client):
        """Test PATCH with cr_type=inferenceservice."""
        r = client.patch("/api/config", json={"cr_type": "inferenceservice"})
        assert r.status_code == 200
        data = r.json()
        assert data["cr_type"] == "inferenceservice"
        assert "configmap_updated" in data

    def test_patch_valid_cr_type_llminferenceservice(self, client):
        """Test PATCH with cr_type=llminferenceservice."""
        r = client.patch("/api/config", json={"cr_type": "llminferenceservice"})
        assert r.status_code == 200
        data = r.json()
        assert data["cr_type"] == "llminferenceservice"
        assert "configmap_updated" in data

    def test_patch_invalid_cr_type_returns_422(self, client):
        """Test that invalid cr_type returns 422."""
        r = client.patch("/api/config", json={"cr_type": "invalid_value"})
        assert r.status_code == 422

    def test_patch_cr_type_while_tuner_running_returns_409(self, client):
        """Test that PATCH returns 409 when auto_tuner is running."""
        from routers.tuner import auto_tuner

        original = auto_tuner._running
        auto_tuner._running = True
        try:
            r = client.patch("/api/config", json={"cr_type": "llminferenceservice"})
            assert r.status_code == 409
            data = r.json()
            assert "detail" in data
        finally:
            auto_tuner._running = original

    def test_patch_configmap_failure_returns_200_with_flag_false(self, client):
        """Test that ConfigMap patch failure returns 200 with configmap_updated=False.

        The K8s API in conftest is stubbed (_DummyK8sApi) without patch_namespaced_config_map,
        so it naturally raises AttributeError which is caught as Exception.
        """
        r = client.patch("/api/config", json={"cr_type": "inferenceservice"})
        assert r.status_code == 200
        data = r.json()
        assert data["configmap_updated"] is False
        assert data["cr_type"] == "inferenceservice"

    def test_patch_empty_body_returns_200_noop(self, client):
        """Test PATCH with empty body is a no-op."""
        r = client.patch("/api/config", json={})
        assert r.status_code == 200
        data = r.json()
        assert "cr_type" in data

    def test_patch_vllm_endpoint(self, client):
        """Test patching vllm_endpoint."""
        r = client.patch("/api/config", json={"vllm_endpoint": "http://new-endpoint:8080"})
        assert r.status_code == 200
        data = r.json()
        assert data["vllm_endpoint"] == "http://new-endpoint:8080"

    def test_patch_vllm_namespace(self, client):
        """Test patching vllm_namespace."""
        r = client.patch("/api/config", json={"vllm_namespace": "new-namespace"})
        assert r.status_code == 200
        data = r.json()
        assert data["vllm_namespace"] == "new-namespace"

    def test_patch_vllm_is_name(self, client):
        """Test patching vllm_is_name."""
        r = client.patch("/api/config", json={"vllm_is_name": "new-is"})
        assert r.status_code == 200
        data = r.json()
        assert data["vllm_is_name"] == "new-is"

    def test_patch_multiple_fields(self, client):
        """Test patching multiple fields at once."""
        r = client.patch(
            "/api/config",
            json={
                "vllm_endpoint": "http://new:8080",
                "vllm_namespace": "new-ns",
                "vllm_is_name": "new-is",
                "cr_type": "inferenceservice",
            },
        )
        assert r.status_code == 200
        data = r.json()
        assert data["vllm_endpoint"] == "http://new:8080"
        assert data["vllm_namespace"] == "new-ns"
        assert data["vllm_is_name"] == "new-is"
        assert data["cr_type"] == "inferenceservice"

    def test_patch_cr_type_persists_across_calls(self, client):
        """Test that cr_type change persists in subsequent GET."""
        # First patch
        r1 = client.patch("/api/config", json={"cr_type": "llminferenceservice"})
        assert r1.status_code == 200
        assert r1.json()["cr_type"] == "llminferenceservice"

        # Verify it persists on next GET
        r2 = client.get("/api/config")
        assert r2.status_code == 200
        assert r2.json()["cr_type"] == "llminferenceservice"

    def test_patch_other_fields_persist_with_cr_type(self, client):
        """Test that non-cr_type fields are preserved when cr_type is patched."""
        # Patch endpoint first
        r1 = client.patch(
            "/api/config",
            json={"vllm_endpoint": "http://test:9000"},
        )
        assert r1.status_code == 200
        original_endpoint = r1.json()["vllm_endpoint"]

        # Now patch cr_type
        r2 = client.patch("/api/config", json={"cr_type": "llminferenceservice"})
        assert r2.status_code == 200
        assert r2.json()["cr_type"] == "llminferenceservice"
        # Endpoint should be preserved
        assert r2.json()["vllm_endpoint"] == original_endpoint

    def test_cr_type_persists_after_reset(self, client):
        """Test cr_type reset clears the in-memory override (simulating pod restart).

        Verifies the reset_cr_type() lifecycle:
        1. PATCH /api/config sets cr_type override
        2. Override is confirmed in runtime_config._cr_type_override
        3. reset_cr_type() clears the override to simulate pod restart fallback
        4. Internal state is cleared (override set to None)
        """
        from services.shared import runtime_config

        r1 = client.patch("/api/config", json={"cr_type": "llminferenceservice"})
        assert r1.status_code == 200
        assert r1.json()["cr_type"] == "llminferenceservice"

        assert runtime_config._cr_type_override == "llminferenceservice"

        runtime_config.reset_cr_type()

        assert runtime_config._cr_type_override is None


class TestGetDefaultTargets:
    def test_get_default_targets_returns_correct_structure(self, client):
        r = client.get("/api/config/default-targets")
        assert r.status_code == 200
        data = r.json()
        assert "isvc" in data
        assert "llmisvc" in data
        assert "name" in data["isvc"]
        assert "namespace" in data["isvc"]
        assert "name" in data["llmisvc"]
        assert "namespace" in data["llmisvc"]


class TestPatchDefaultTargets:
    def test_patch_isvc_default_target_returns_200(self, client):
        r = client.patch(
            "/api/config/default-targets",
            json={"isvc": {"name": "test-isvc", "namespace": "test-ns"}},
        )
        assert r.status_code == 200
        data = r.json()
        assert "isvc" in data
        assert "llmisvc" in data
        assert "configmap_updated" in data

    def test_patch_llmisvc_default_target_returns_200(self, client):
        r = client.patch(
            "/api/config/default-targets",
            json={"llmisvc": {"name": "test-llmisvc", "namespace": "test-ns"}},
        )
        assert r.status_code == 200
        data = r.json()
        assert "isvc" in data
        assert "llmisvc" in data
        assert "configmap_updated" in data

    def test_patch_empty_body_returns_current_values(self, client):
        r = client.patch("/api/config/default-targets", json={})
        assert r.status_code == 200
        data = r.json()
        assert "isvc" in data
        assert "llmisvc" in data

    def test_patch_both_targets_at_once_returns_200(self, client):
        r = client.patch(
            "/api/config/default-targets",
            json={
                "isvc": {"name": "isvc-name", "namespace": "isvc-ns"},
                "llmisvc": {"name": "llmisvc-name", "namespace": "llmisvc-ns"},
            },
        )
        assert r.status_code == 200
        data = r.json()
        assert "isvc" in data
        assert "llmisvc" in data
        assert "configmap_updated" in data

    def test_patch_configmap_failure_returns_200_with_flag_false(self, client):
        r = client.patch(
            "/api/config/default-targets",
            json={"isvc": {"name": "test-isvc", "namespace": "test-ns"}},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["configmap_updated"] is False
