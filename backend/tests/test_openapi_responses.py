"""
Tests to validate OpenAPI spec includes ErrorResponse schema on error endpoints.
"""

import pytest
from fastapi.testclient import TestClient
from main import app


@pytest.fixture
def client():
    """Create a TestClient for the app."""
    return TestClient(app)


def test_errorresponse_schema_in_components(client):
    """Verify ErrorResponse schema is defined in OpenAPI components."""
    spec = app.openapi()
    schemas = spec.get("components", {}).get("schemas", {})

    assert "ErrorResponse" in schemas, "ErrorResponse schema not found in components"

    error_response = schemas["ErrorResponse"]
    assert "properties" in error_response
    assert "error" in error_response["properties"]
    assert error_response["properties"]["error"]["type"] == "string"


def test_benchmark_endpoints_have_error_schemas(client):
    """Verify benchmark endpoints have error response schemas."""
    spec = app.openapi()
    paths = spec.get("paths", {})

    assert "/api/benchmark/list" in paths
    get_responses = paths["/api/benchmark/list"]["get"]["responses"]
    assert "500" in get_responses
    assert "$ref" in get_responses["500"]["content"]["application/json"]["schema"]
    assert "ErrorResponse" in get_responses["500"]["content"]["application/json"]["schema"]["$ref"]

    assert "/api/benchmark/save" in paths
    post_responses = paths["/api/benchmark/save"]["post"]["responses"]
    assert "500" in post_responses
    assert "$ref" in post_responses["500"]["content"]["application/json"]["schema"]

    assert "/api/benchmark/by-model" in paths
    get_responses = paths["/api/benchmark/by-model"]["get"]["responses"]
    assert "500" in get_responses

    assert "/api/benchmark/{benchmark_id}" in paths
    get_responses = paths["/api/benchmark/{benchmark_id}"]["get"]["responses"]
    assert "404" in get_responses
    assert "500" in get_responses
    assert "ErrorResponse" in get_responses["404"]["content"]["application/json"]["schema"]["$ref"]

    assert "delete" in paths["/api/benchmark/{benchmark_id}"]
    delete_responses = paths["/api/benchmark/{benchmark_id}"]["delete"]["responses"]
    assert "404" in delete_responses
    assert "500" in delete_responses


def test_load_test_start_has_error_schemas(client):
    """Verify /api/load_test/start has 400 and 409 error schemas."""
    spec = app.openapi()
    paths = spec.get("paths", {})

    assert "/api/load_test/start" in paths
    responses = paths["/api/load_test/start"]["post"]["responses"]

    assert "400" in responses, "400 response not found for /api/load_test/start"
    assert "$ref" in responses["400"]["content"]["application/json"]["schema"]
    assert "ErrorResponse" in responses["400"]["content"]["application/json"]["schema"]["$ref"]

    assert "409" in responses, "409 response not found for /api/load_test/start"
    assert "$ref" in responses["409"]["content"]["application/json"]["schema"]
    assert "ErrorResponse" in responses["409"]["content"]["application/json"]["schema"]["$ref"]


def test_load_test_history_has_error_schema(client):
    """Verify /api/load_test/history has 500 error schema."""
    spec = app.openapi()
    paths = spec.get("paths", {})

    assert "/api/load_test/history" in paths
    responses = paths["/api/load_test/history"]["get"]["responses"]

    assert "500" in responses, "500 response not found for /api/load_test/history"
    assert "$ref" in responses["500"]["content"]["application/json"]["schema"]
    assert "ErrorResponse" in responses["500"]["content"]["application/json"]["schema"]["$ref"]


def test_metrics_latest_has_error_schema(client):
    """Verify /api/metrics/latest has 409 error schema."""
    spec = app.openapi()
    paths = spec.get("paths", {})

    assert "/api/metrics/latest" in paths
    responses = paths["/api/metrics/latest"]["get"]["responses"]

    assert "409" in responses, "409 response not found for /api/metrics/latest"
    assert "$ref" in responses["409"]["content"]["application/json"]["schema"]
    assert "ErrorResponse" in responses["409"]["content"]["application/json"]["schema"]["$ref"]


def test_tuner_start_has_error_schemas(client):
    """Verify /api/tuner/start has 400 and 409 error schemas."""
    spec = app.openapi()
    paths = spec.get("paths", {})

    assert "/api/tuner/start" in paths
    responses = paths["/api/tuner/start"]["post"]["responses"]

    assert "400" in responses, "400 response not found for /api/tuner/start"
    assert "$ref" in responses["400"]["content"]["application/json"]["schema"]
    assert "ErrorResponse" in responses["400"]["content"]["application/json"]["schema"]["$ref"]

    assert "409" in responses, "409 response not found for /api/tuner/start"
    assert "$ref" in responses["409"]["content"]["application/json"]["schema"]
    assert "ErrorResponse" in responses["409"]["content"]["application/json"]["schema"]["$ref"]


def test_contract_get_config(isolated_client):
    """GET /api/config returns 200 with expected ConfigResponse fields."""
    response = isolated_client.get("/api/config")
    assert response.status_code == 200
    body = response.json()
    for field in (
        "vllm_endpoint",
        "vllm_namespace",
        "vllm_is_name",
        "vllm_model_name",
        "resolved_model_name",
        "cr_type",
    ):
        assert field in body, f"Expected field '{field}' missing from /api/config response"


def test_contract_get_vllm_config(isolated_client):
    """GET /api/vllm-config returns 200 and VllmConfigResponse shape."""
    response = isolated_client.get("/api/vllm-config")
    assert response.status_code == 200, f"Unexpected status {response.status_code}"
    body = response.json()
    for field in ("success", "data", "resources", "extraArgs", "modelName", "resolvedModelName"):
        assert field in body, f"Expected field '{field}' missing from /api/vllm-config response"


def test_contract_get_metrics_history(isolated_client):
    """GET /api/metrics/history returns 200 with a list body."""
    response = isolated_client.get("/api/metrics/history")
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list), "Expected /api/metrics/history to return a list"


def test_contract_get_sla_profiles(isolated_client):
    """GET /api/sla/profiles returns 200 with a list body."""
    response = isolated_client.get("/api/sla/profiles")
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list), "Expected /api/sla/profiles to return a list"


def test_contract_get_tuner_status(isolated_client):
    """GET /api/tuner/status returns 200 with status-related fields."""
    response = isolated_client.get("/api/tuner/status")
    assert response.status_code == 200
    body = response.json()
    for field in ("running", "trials_completed", "status"):
        assert field in body, f"Expected field '{field}' missing from /api/tuner/status response"
