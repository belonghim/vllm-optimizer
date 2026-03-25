import time

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.performance]


class TestClusterHealth:
    def test_backend_health_deep(self, http_client):
        """GET /health?deep=1 → Prometheus + K8s 연결 확인."""
        start = time.time()
        resp = http_client.get("/health", params={"deep": "1"}, timeout=10)
        elapsed = time.time() - start
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert elapsed < 5.0, f"Health check too slow: {elapsed:.1f}s"

    def test_metrics_endpoint_accessible(self, http_client):
        """GET /api/metrics/latest → MetricsSnapshot 반환."""
        resp = http_client.get("/api/metrics/latest")
        assert resp.status_code == 200
        data = resp.json()
        assert "timestamp" in data
        assert "tps" in data
        assert "gpu_util" in data

    def test_prometheus_metrics_plaintext(self, http_client):
        """GET /api/metrics → Prometheus 포맷 반환."""
        resp = http_client.get("/api/metrics")
        assert resp.status_code == 200
        assert "text/plain" in resp.headers.get("content-type", "")
