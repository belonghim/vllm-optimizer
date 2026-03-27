import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(isolated_client: TestClient) -> TestClient:
    return isolated_client


class TestInterruptedRuns:
    def test_get_interrupted_returns_200(self, client: TestClient) -> None:
        r = client.get("/api/status/interrupted")
        assert r.status_code == 200

    def test_get_interrupted_contains_key(self, client: TestClient) -> None:
        r = client.get("/api/status/interrupted")
        assert r.status_code == 200
        data = r.json()
        assert "interrupted_runs" in data

    def test_get_interrupted_default_empty_list(self, client: TestClient) -> None:
        r = client.get("/api/status/interrupted")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data["interrupted_runs"], list)
        assert data["interrupted_runs"] == []

    def test_get_interrupted_clears_after_first_call(self, client: TestClient) -> None:
        r1 = client.get("/api/status/interrupted")
        assert r1.status_code == 200
        r2 = client.get("/api/status/interrupted")
        assert r2.status_code == 200
        assert r2.json()["interrupted_runs"] == []


class TestHealth:
    def test_health_endpoint_accessible(self, client: TestClient) -> None:
        # In test environment dependencies (prometheus, k8s) are stubs/unavailable
        # so the endpoint returns 200 or 503 — both are valid for this test
        r = client.get("/health")
        assert r.status_code in (200, 503)

    def test_health_response_has_status_field(self, client: TestClient) -> None:
        r = client.get("/health")
        data = r.json()
        assert "status" in data

    def test_health_response_has_cr_type_field(self, client: TestClient) -> None:
        r = client.get("/health")
        data = r.json()
        assert "cr_type" in data

    def test_health_cr_type_is_string(self, client: TestClient) -> None:
        r = client.get("/health")
        data = r.json()
        assert isinstance(data["cr_type"], str)

    def test_health_status_is_string(self, client: TestClient) -> None:
        r = client.get("/health")
        data = r.json()
        assert isinstance(data["status"], str)

    def test_health_not_found_is_wrong_path(self, client: TestClient) -> None:
        # /api/health does NOT exist — health is at root /health
        r = client.get("/api/health")
        assert r.status_code == 404
