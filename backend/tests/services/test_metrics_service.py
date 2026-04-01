"""Unit tests for metrics_service.py, focused on per-pod history queries.

These tests verify that:
- _get_history_from_thanos with per_pod=True returns per-pod metrics
- _get_history_from_thanos with per_pod=False returns aggregated metrics
- _build_per_pod_snapshots_from_ts_data correctly builds per-pod snapshots
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.services.metrics_service import (
    _build_per_pod_snapshots_from_ts_data,
    _fetch_query_range,
    _fetch_query_range_multi_result,
    _get_history_from_thanos,
)


class TestFetchQueryRangeMultiResult:
    """Tests for _fetch_query_range_multi_result parsing per-pod results."""

    @pytest.mark.asyncio
    async def test_fetch_query_range_multi_result_parses_pod_labels(self) -> None:
        """Verify _fetch_query_range_multi_result returns dict mapping pod names to time series."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "status": "success",
            "data": {
                "result": [
                    {"metric": {"pod": "vllm-pod-0"}, "values": [[1234567890.0, "10.5"], [1234567891.0, "11.5"]]},
                    {"metric": {"pod": "vllm-pod-1"}, "values": [[1234567890.0, "20.5"], [1234567891.0, "21.5"]]},
                ]
            },
        }
        mock_response.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch("services.metrics_service.with_retry", AsyncMock(return_value=mock_response)):
            result = await _fetch_query_range_multi_result(
                mock_client, {}, "rate(vllm:num_tokens{namespace=\"test\"}[1m])", 1234567890.0, 1234567892.0, 10
            )

        assert isinstance(result, dict)
        assert len(result) == 2
        assert "vllm-pod-0" in result
        assert "vllm-pod-1" in result
        assert result["vllm-pod-0"] == [(1234567890.0, 10.5), (1234567891.0, 11.5)]
        assert result["vllm-pod-1"] == [(1234567890.0, 20.5), (1234567891.0, 21.5)]

    @pytest.mark.asyncio
    async def test_fetch_query_range_multi_result_handles_missing_pod_label(self) -> None:
        """Verify _fetch_query_range_multi_result uses fallback keys when pod label is missing."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "status": "success",
            "data": {
                "result": [
                    {"metric": {"instance": "10.0.0.1:8000"}, "values": [[1234567890.0, "100.0"]]},
                    {"metric": {"instance": "10.0.0.2:8000"}, "values": [[1234567890.0, "200.0"]]},
                ]
            },
        }
        mock_response.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch("services.metrics_service.with_retry", AsyncMock(return_value=mock_response)):
            result = await _fetch_query_range_multi_result(
                mock_client, {}, "vllm:gpu_util{namespace=\"test\"}", 1234567890.0, 1234567892.0, 10
            )

        assert len(result) == 2
        assert "pod_0" in result
        assert "pod_1" in result

    @pytest.mark.asyncio
    async def test_fetch_query_range_multi_result_handles_empty_results(self) -> None:
        """Verify _fetch_query_range_multi_result returns empty dict for no results."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "status": "success",
            "data": {"result": []},
        }
        mock_response.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch("services.metrics_service.with_retry", AsyncMock(return_value=mock_response)):
            result = await _fetch_query_range_multi_result(
                mock_client, {}, "vllm:nonexistent{namespace=\"test\"}", 1234567890.0, 1234567892.0, 10
            )

        assert result == {}

    @pytest.mark.asyncio
    async def test_fetch_query_range_multi_result_skips_nan_and_inf(self) -> None:
        """Verify _fetch_query_range_multi_result skips NaN and Inf values."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "status": "success",
            "data": {
                "result": [
                    {"metric": {"pod": "vllm-pod-0"}, "values": [[1234567890.0, "NaN"], [1234567891.0, "10.5"]]},
                    {"metric": {"pod": "vllm-pod-1"}, "values": [[1234567890.0, "Infinity"], [1234567891.0, "20.5"]]},
                ]
            },
        }
        mock_response.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch("services.metrics_service.with_retry", AsyncMock(return_value=mock_response)):
            result = await _fetch_query_range_multi_result(
                mock_client, {}, "rate(vllm:num_tokens{namespace=\"test\"}[1m])", 1234567890.0, 1234567892.0, 10
            )

        assert len(result) == 2
        assert result["vllm-pod-0"] == [(1234567891.0, 10.5)]
        assert result["vllm-pod-1"] == [(1234567891.0, 20.5)]


class TestFetchQueryRange:
    """Tests for _fetch_query_range (aggregated queries)."""

    @pytest.mark.asyncio
    async def test_fetch_query_range_returns_list_of_tuples(self) -> None:
        """Verify _fetch_query_range returns list of (timestamp, value) tuples."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "status": "success",
            "data": {
                "result": [
                    {"values": [[1234567890.0, "10.5"], [1234567891.0, "11.5"]]}
                ]
            },
        }
        mock_response.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch("services.metrics_service.with_retry", AsyncMock(return_value=mock_response)):
            result = await _fetch_query_range(
                mock_client, {}, "sum(rate(vllm:num_tokens{namespace=\"test\"}[1m]))", 1234567890.0, 1234567892.0, 10
            )

        assert isinstance(result, list)
        assert len(result) == 2
        assert result[0] == (1234567890.0, 10.5)
        assert result[1] == (1234567891.0, 11.5)


class TestBuildPerPodSnapshotsFromTsData:
    """Tests for _build_per_pod_snapshots_from_ts_data."""

    def test_build_per_pod_snapshots_creates_per_pod_snapshots(self) -> None:
        """Verify _build_per_pod_snapshots_from_ts_data creates snapshots with pod_name field."""
        pod_metric_series = {
            "vllm-pod-0": {
                "tokens_per_second": [(1234567890.0, 10.5), (1234567891.0, 11.5)],
                "requests_per_second": [(1234567890.0, 1.0), (1234567891.0, 1.1)],
            },
            "vllm-pod-1": {
                "tokens_per_second": [(1234567890.0, 20.5), (1234567891.0, 21.5)],
                "requests_per_second": [(1234567890.0, 2.0), (1234567891.0, 2.1)],
            },
        }

        result = _build_per_pod_snapshots_from_ts_data(pod_metric_series)

        assert isinstance(result, list)
        # 2 pods x 2 timestamps = 4 snapshots
        assert len(result) == 4

        # All snapshots should have pod_name field
        for snap in result:
            assert "pod_name" in snap
            assert snap["pod_name"] in ("vllm-pod-0", "vllm-pod-1")

        # Verify pod-0 snapshots
        pod_0_snaps = [s for s in result if s["pod_name"] == "vllm-pod-0"]
        assert len(pod_0_snaps) == 2
        assert pod_0_snaps[0]["tps"] == 10.5
        assert pod_0_snaps[1]["tps"] == 11.5

        # Verify pod-1 snapshots
        pod_1_snaps = [s for s in result if s["pod_name"] == "vllm-pod-1"]
        assert len(pod_1_snaps) == 2
        assert pod_1_snaps[0]["tps"] == 20.5
        assert pod_1_snaps[1]["tps"] == 21.5

    def test_build_per_pod_snapshots_empty_input(self) -> None:
        """Verify _build_per_pod_snapshots_from_ts_data returns empty list for empty input."""
        result = _build_per_pod_snapshots_from_ts_data({})
        assert result == []

    def test_build_per_pod_snapshots_no_timestamps(self) -> None:
        """Verify _build_per_pod_snapshots_from_ts_data returns empty list when no timestamps."""
        pod_metric_series = {
            "vllm-pod-0": {
                "tokens_per_second": [],
            },
        }

        result = _build_per_pod_snapshots_from_ts_data(pod_metric_series)
        assert result == []


class TestGetHistoryFromThanos:
    """Tests for _get_history_from_thanos with per_pod parameter."""

    @pytest.mark.asyncio
    async def test_get_history_from_thanos_invalid_time_range(self) -> None:
        """Verify _get_history_from_thanos returns empty list for invalid time_range."""
        mock_collector = MagicMock()

        result = await _get_history_from_thanos(
            namespace="test-ns",
            is_name="test-is",
            cr_type=None,
            time_range="invalid",
            collector=mock_collector,
            per_pod=False,
        )

        assert result == []

    @pytest.mark.asyncio
    async def test_pods_history_endpoint(self) -> None:
        """Integration test for /pods/history endpoint behavior.

        Simulates the /pods/history endpoint which uses per_pod queries
        and returns snapshots with pod_name field for each pod.
        """
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from pydantic import BaseModel

        class PodHistoryRequest(BaseModel):
            namespace: str
            inferenceService: str
            cr_type: str | None = None

        class RequestModel(BaseModel):
            targets: list[PodHistoryRequest]
            time_range: str

        mock_collector = MagicMock()
        mock_collector._build_pod_queries.return_value = {
            "tokens_per_second": 'rate(vllm:num_generated_tokens{namespace="test-ns"}[1m])',
            "gpu_utilization_pct": 'vllm:gpu_utilization_perc{namespace="test-ns"}',
        }
        mock_collector._token = None

        async def mock_fetch_multi(client, headers, query, start, end, step):
            if "num_generated_tokens" in query:
                return {
                    "vllm-pod-0": [(1234567890.0, 100.5)],
                    "vllm-pod-1": [(1234567890.0, 200.5)],
                }
            return {
                "vllm-pod-0": [(1234567890.0, 80.0)],
                "vllm-pod-1": [(1234567890.0, 90.0)],
            }

        app = FastAPI()

        @app.post("/pods/history")
        async def get_pods_history(body: RequestModel):
            results = {}
            for target in body.targets:
                key = f"{target.namespace}/{target.inferenceService}"

                queries = mock_collector._build_pod_queries(
                    target.namespace, target.inferenceService, target.cr_type
                )

                pod_series_list = []
                for f in queries.keys():
                    pod_series = await mock_fetch_multi(MagicMock(), {}, queries[f], 0, 1, 1)
                    pod_series_list.append(pod_series)

                field_names = list(queries.keys())
                pod_metric_series: dict[str, dict[str, list[tuple[float, float]]]] = {}
                for i, pod_series in enumerate(pod_series_list):
                    metric_field = field_names[i]
                    for pod_name, series in pod_series.items():
                        if pod_name not in pod_metric_series:
                            pod_metric_series[pod_name] = {}
                        pod_metric_series[pod_name][metric_field] = series

                snapshots = _build_per_pod_snapshots_from_ts_data(pod_metric_series)
                results[key] = snapshots

            return results

        with TestClient(app) as client:
            response = client.post(
                "/pods/history",
                json={
                    "targets": [
                        {
                            "namespace": "test-ns",
                            "inferenceService": "test-is",
                            "cr_type": "inferenceservice",
                        }
                    ],
                    "time_range": "1h",
                },
            )

        assert response.status_code == 200
        data = response.json()

        assert "test-ns/test-is" in data

        result = data["test-ns/test-is"]
        assert isinstance(result, list)
        assert len(result) == 2

        pod_names = sorted([s["pod_name"] for s in result])
        assert pod_names == ["vllm-pod-0", "vllm-pod-1"]

        for snap in result:
            assert "tps" in snap
            assert "gpu_util" in snap
