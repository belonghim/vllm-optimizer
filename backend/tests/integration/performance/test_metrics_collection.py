import time
import pytest

pytestmark = [pytest.mark.integration, pytest.mark.performance]


class TestMetricsCollection:

    def test_metrics_response_time(self, http_client):
        """GET /api/metrics/latest 응답 시간 측정 (5회 median)."""
        times = []
        for _ in range(5):
            start = time.time()
            resp = http_client.get("/api/metrics/latest")
            elapsed = time.time() - start
            assert resp.status_code == 200
            times.append(elapsed)
            time.sleep(1)

        median_time = sorted(times)[len(times) // 2]
        assert median_time < 5.0, f"Median metrics response time too slow: {median_time:.2f}s"

    def test_prometheus_scrape_format_valid(self, http_client):
        """Prometheus 포맷 출력이 파싱 가능한지 확인."""
        resp = http_client.get("/api/metrics")
        assert resp.status_code == 200
        text = resp.text
        assert "# HELP" in text
        assert "# TYPE" in text
