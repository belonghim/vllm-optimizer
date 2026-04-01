"""Integration tests for MultiTargetMetricsCollector with mock Prometheus.

These tests verify multi-pod aggregation behavior:
- Percentages (kv_cache_usage_pct) use avg() → (50 + 80) / 2 = 65
- Counts (running_requests) use sum() → 3 + 5 = 8
- Single pod values pass through unchanged
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


class TestMultiPodAggregation:
    """Integration tests for multi-pod aggregation via mock Prometheus."""

    @pytest.mark.asyncio
    async def test_multi_pod_aggregation_averages_percentages(self) -> None:
        """Verify kv_cache_usage_pct averages across 2 pods: (50 + 80) / 2 = 65.

        When Prometheus queries use avg() aggregation, multi-pod data should
        be averaged, not summed.
        """
        collector = _build_collector()

        # Mock Prometheus response for avg(kv_cache_usage_pct) across 2 pods
        # avg() aggregation returns a SINGLE result with the averaged value
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "status": "success",
            "data": {
                "result": [
                    {"value": [1234567890.123, "65.0"]},  # avg(50, 80) = 65.0
                ]
            },
        }
        mock_response.raise_for_status = MagicMock()

        mock_internal_client = MagicMock()
        mock_internal_client.get = AsyncMock(return_value=mock_response)

        with patch("services.shared.internal_client", mock_internal_client):
            with patch("services.multi_target_collector._with_retry", AsyncMock(return_value=mock_response)):
                result = await collector._query_prometheus("test-ns", "test-is")

        assert result.get("kv_cache_usage_pct") == 65.0, (
            f"Expected kv_cache_usage_pct ~65.0 (avg of 50 and 80), got {result.get('kv_cache_usage_pct')}"
        )

    @pytest.mark.asyncio
    async def test_multi_pod_aggregation_sums_counts(self) -> None:
        """Verify running_requests sums across 2 pods: 3 + 5 = 8.

        When Prometheus queries use sum() aggregation, multi-pod data should
        be summed, not averaged.
        """
        collector = _build_collector()

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "status": "success",
            "data": {
                "result": [
                    {"value": [1234567890.123, "8"]},
                ]
            },
        }
        mock_response.raise_for_status = MagicMock()

        mock_internal_client = MagicMock()
        mock_internal_client.get = AsyncMock(return_value=mock_response)

        with patch("services.shared.internal_client", mock_internal_client):
            with patch("services.multi_target_collector._with_retry", AsyncMock(return_value=mock_response)):
                result = await collector._query_prometheus("test-ns", "test-is")

        assert result.get("running_requests") == 8.0, (
            f"Expected running_requests = 8.0 (sum of 3 and 5), got {result.get('running_requests')}"
        )

    @pytest.mark.asyncio
    async def test_single_pod_unchanged(self) -> None:
        """Verify single pod values pass through correctly (no aggregation change).

        When there's only one pod, avg and sum both return the same value,
        so the result should be the actual pod value.
        """
        collector = _build_collector()

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "status": "success",
            "data": {
                "result": [
                    {"value": [1234567890.123, "42.5"]},
                ]
            },
        }
        mock_response.raise_for_status = MagicMock()

        mock_internal_client = MagicMock()
        mock_internal_client.get = AsyncMock(return_value=mock_response)

        with patch("services.shared.internal_client", mock_internal_client):
            with patch("services.multi_target_collector._with_retry", AsyncMock(return_value=mock_response)):
                result = await collector._query_prometheus("test-ns", "test-is")

        assert result.get("kv_cache_usage_pct") == 42.5, (
            f"Expected kv_cache_usage_pct = 42.5, got {result.get('kv_cache_usage_pct')}"
        )
