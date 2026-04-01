"""Unit tests for aggregation logic in MultiTargetMetricsCollector.

These tests verify that:
- Counts (running_requests, waiting_requests) use sum() aggregation
- Percentages (kv_cache_usage_pct, gpu_utilization_pct) use avg() aggregation
- Histogram quantiles (TTFT, latency) remain unchanged (histogram_quantile with sum)
- Counter rates (tokens_per_second, requests_per_second) remain unchanged (sum with rate)
- _fetch_prometheus_metric correctly extracts results[0]
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.services.multi_target_collector import MultiTargetMetricsCollector


def _build_collector() -> MultiTargetMetricsCollector:
    """Build a collector instance with k8s disabled."""
    collector = MultiTargetMetricsCollector()
    collector._k8s_available = False
    collector._k8s_core = None
    return collector


class TestBuildTargetQueriesAggregation:
    """Tests for _build_target_queries aggregation function selection."""

    def test_build_queries_uses_sum_for_counts(self) -> None:
        """Verify running_requests and waiting_requests use sum() aggregation.

        Counts should use sum() to aggregate values across all pods.
        """
        collector = _build_collector()
        queries = collector._build_target_queries("test-ns", "test-is")

        # Count metrics should use sum()
        assert queries["running_requests"].startswith("sum("), (
            f"running_requests should use sum(), got: {queries['running_requests']}"
        )
        assert queries["waiting_requests"].startswith("sum("), (
            f"waiting_requests should use sum(), got: {queries['waiting_requests']}"
        )

    def test_build_queries_uses_avg_for_percentages(self) -> None:
        """Verify kv_cache_usage_pct and gpu_utilization_pct use avg() aggregation.

        Percentage/average metrics should use avg() to get mean utilization across pods.
        """
        collector = _build_collector()
        queries = collector._build_target_queries("test-ns", "test-is")

        # Percentage metrics should use avg()
        assert queries["kv_cache_usage_pct"].startswith("avg("), (
            f"kv_cache_usage_pct should use avg(), got: {queries['kv_cache_usage_pct']}"
        )
        assert queries["gpu_utilization_pct"].startswith("(avg("), (
            f"gpu_utilization_pct should use avg(), got: {queries['gpu_utilization_pct']}"
        )

    def test_build_queries_histogram_quantiles_unchanged(self) -> None:
        """Verify TTFT and latency queries use histogram_quantile with sum unchanged.

        Histogram quantiles should still use histogram_quantile with sum(rate(...))
        to compute percentiles correctly.
        """
        collector = _build_collector()
        queries = collector._build_target_queries("test-ns", "test-is")

        # TTFT queries should use histogram_quantile
        assert "histogram_quantile(0.5" in queries["mean_ttft_ms"], (
            f"mean_ttft_ms should use histogram_quantile, got: {queries['mean_ttft_ms']}"
        )
        assert "histogram_quantile(0.99" in queries["p99_ttft_ms"], (
            f"p99_ttft_ms should use histogram_quantile, got: {queries['p99_ttft_ms']}"
        )

        # E2E latency queries should use histogram_quantile
        assert "histogram_quantile(0.5" in queries["mean_e2e_latency_ms"], (
            f"mean_e2e_latency_ms should use histogram_quantile, got: {queries['mean_e2e_latency_ms']}"
        )
        assert "histogram_quantile(0.99" in queries["p99_e2e_latency_ms"], (
            f"p99_e2e_latency_ms should use histogram_quantile, got: {queries['p99_e2e_latency_ms']}"
        )

        # Should still use sum(rate(...)) inside histogram_quantile
        assert "sum by (le)" in queries["mean_ttft_ms"], (
            f"TTFT queries should use 'sum by (le)' inside histogram_quantile, got: {queries['mean_ttft_ms']}"
        )

    def test_build_queries_counter_rate_unchanged(self) -> None:
        """Verify tokens_per_second and requests_per_second use sum(rate(...)) unchanged.

        Counter rate metrics should still use sum(rate(...)) to get rates.
        """
        collector = _build_collector()
        queries = collector._build_target_queries("test-ns", "test-is")

        # Counter rate metrics should use sum(rate(...))
        assert "sum(rate(" in queries["tokens_per_second"], (
            f"tokens_per_second should use sum(rate(...)), got: {queries['tokens_per_second']}"
        )
        assert "sum(rate(" in queries["requests_per_second"], (
            f"requests_per_second should use sum(rate(...)), got: {queries['requests_per_second']}"
        )


class TestFetchPrometheusMetric:
    """Tests for _fetch_prometheus_metric result extraction."""

    @pytest.mark.asyncio
    async def test_fetch_prometheus_metric_extracts_first_result(self) -> None:
        """Verify _fetch_prometheus_metric extracts value from results[0].

        For aggregated queries, Prometheus returns exactly ONE result because
        aggregation reduces all matching series into a single value.
        """
        collector = _build_collector()

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "status": "success",
            "data": {
                "result": [
                    {"value": [1234567890.123, "42.5"]},
                    {"value": [1234567890.456, "99.9"]},
                ]
            },
        }
        mock_response.raise_for_status = MagicMock()

        mock_internal_client = MagicMock()
        mock_internal_client.get = AsyncMock(return_value=mock_response)

        with patch("services.shared.get_internal_client", return_value=mock_internal_client):
            with patch("services.multi_target_collector._with_retry", AsyncMock(return_value=mock_response)):
                metric_name, value = await collector._fetch_prometheus_metric(
                    headers={},
                    metric_name="test_metric",
                    query="sum(rate(test_metric[5m]))",
                )

        assert value == 42.5, f"Expected 42.5 (first result), got {value}"
        assert metric_name == "test_metric"

    @pytest.mark.asyncio
    async def test_fetch_prometheus_metric_handles_single_result(self) -> None:
        """Verify _fetch_prometheus_metric works with single result (normal case)."""
        collector = _build_collector()

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "status": "success",
            "data": {
                "result": [
                    {"value": [1234567890.123, "100.0"]},
                ]
            },
        }
        mock_response.raise_for_status = MagicMock()

        mock_internal_client = MagicMock()
        mock_internal_client.get = AsyncMock(return_value=mock_response)

        with patch("services.shared.get_internal_client", return_value=mock_internal_client):
            with patch("services.multi_target_collector._with_retry", AsyncMock(return_value=mock_response)):
                metric_name, value = await collector._fetch_prometheus_metric(
                    headers={},
                    metric_name="single_result_metric",
                    query="avg(test_metric)",
                )

        assert value == 100.0
        assert metric_name == "single_result_metric"

    @pytest.mark.asyncio
    async def test_fetch_prometheus_metric_handles_empty_results(self) -> None:
        """Verify _fetch_prometheus_metric returns None for empty results."""
        collector = _build_collector()

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "status": "success",
            "data": {
                "result": []
            },
        }
        mock_response.raise_for_status = MagicMock()

        mock_internal_client = MagicMock()
        mock_internal_client.get = AsyncMock(return_value=mock_response)

        with patch("services.shared.get_internal_client", return_value=mock_internal_client):
            with patch("services.multi_target_collector._with_retry", AsyncMock(return_value=mock_response)):
                metric_name, value = await collector._fetch_prometheus_metric(
                    headers={},
                    metric_name="empty_metric",
                    query="avg(nonexistent_metric)",
                )

        assert value is None
        assert metric_name == "empty_metric"

    @pytest.mark.asyncio
    async def test_fetch_prometheus_metric_logs_warning_for_multiple_results(self) -> None:
        """Verify _fetch_prometheus_metric logs warning when multiple results returned."""
        collector = _build_collector()

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "status": "success",
            "data": {
                "result": [
                    {"value": [1234567890.123, "10.0"]},
                    {"value": [1234567890.456, "20.0"]},
                    {"value": [1234567890.789, "30.0"]},
                ]
            },
        }
        mock_response.raise_for_status = MagicMock()

        mock_internal_client = MagicMock()
        mock_internal_client.get = AsyncMock(return_value=mock_response)

        with patch("services.shared.get_internal_client", return_value=mock_internal_client):
            with patch("services.multi_target_collector._with_retry", AsyncMock(return_value=mock_response)):
                with patch("backend.services.multi_target_collector.logger") as mock_logger:
                    metric_name, value = await collector._fetch_prometheus_metric(
                        headers={},
                        metric_name="multi_result_metric",
                        query="sum(rate(test_metric[5m]))",
                    )

            mock_logger.warning.assert_called_once()
            warning_call_args = str(mock_logger.warning.call_args)
            assert "multiple results" in warning_call_args.lower() or "3 results" in warning_call_args
            assert value == 10.0
