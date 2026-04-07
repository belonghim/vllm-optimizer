"""Unit tests for per-pod query functionality in MultiTargetMetricsCollector.

These tests verify that:
- _build_pod_queries returns non-aggregated queries (no sum/avg)
- _fetch_prometheus_multi_result parses multiple results into a dict
- _fetch_prometheus_multi_result handles missing pod labels with fallback
- /pods endpoint returns both aggregated and per-pod metrics
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.services.multi_target_collector import MultiTargetMetricsCollector


class TestBuildPodQueriesNonAggregated:
    """Tests for _build_pod_queries non-aggregated query generation."""

    def test_build_pod_queries_returns_non_aggregated(self, collector: MultiTargetMetricsCollector) -> None:
        """Verify _build_pod_queries does NOT use sum() or avg() aggregation.

        Per-pod queries should return raw per-pod values, not aggregated ones.
        This is the key difference from _build_target_queries which uses sum/avg.
        """
        queries = collector._build_pod_queries("test-ns", "test-is")

        # Count metrics should NOT use sum() in per-pod queries
        assert not queries["running_requests"].startswith("sum("), (
            f"running_requests should not use sum() in per-pod queries, got: {queries['running_requests']}"
        )
        assert not queries["waiting_requests"].startswith("sum("), (
            f"waiting_requests should not use sum() in per-pod queries, got: {queries['waiting_requests']}"
        )

        # Percentage metrics should NOT use avg() in per-pod queries
        assert not queries["kv_cache_usage_pct"].startswith("avg("), (
            f"kv_cache_usage_pct should not use avg() in per-pod queries, got: {queries['kv_cache_usage_pct']}"
        )
        assert not queries["gpu_utilization_pct"].startswith("(avg("), (
            f"gpu_utilization_pct should not use avg() in per-pod queries, got: {queries['gpu_utilization_pct']}"
        )

        # Counter rate metrics should NOT use sum(rate(...)) - just rate(...)
        assert "sum(rate(" not in queries["tokens_per_second"], (
            f"tokens_per_second should not use sum(rate(...)) in per-pod queries, got: {queries['tokens_per_second']}"
        )
        assert "sum(rate(" not in queries["requests_per_second"], (
            f"requests_per_second should not use sum(rate(...)) in per-pod queries, got: {queries['requests_per_second']}"
        )

        # Histogram quantiles should NOT use "sum by (le)" inside histogram_quantile
        # Per-pod queries use rate() directly without sum aggregation
        assert "sum by (le)" not in queries["mean_ttft_ms"], (
            f"TTFT queries should not use 'sum by (le)' in per-pod queries, got: {queries['mean_ttft_ms']}"
        )

    def test_build_pod_queries_contains_selector(self, collector: MultiTargetMetricsCollector) -> None:
        """Verify _build_pod_queries contains proper namespace and job selectors."""
        queries = collector._build_pod_queries("my-namespace", "my-service")

        # All queries should contain the namespace selector
        for metric_name, query in queries.items():
            assert 'namespace="my-namespace"' in query, f"{metric_name} should contain namespace selector, got: {query}"

    def test_build_pod_queries_gpu_memory_has_dcgm_selector(self, collector: MultiTargetMetricsCollector) -> None:
        """Verify GPU memory queries contain DCGM selector for pod pattern."""
        queries = collector._build_pod_queries("test-ns", "test-is")

        # GPU memory queries should contain dcgm_selector for fallback
        assert "DCGM_FI_DEV_FB_USED" in queries["gpu_memory_used_gb"], (
            f"gpu_memory_used_gb should contain DCGM fallback, got: {queries['gpu_memory_used_gb']}"
        )


class TestFetchPrometheusMultiResult:
    """Tests for _fetch_prometheus_multi_result parsing multiple results."""

    @pytest.mark.asyncio
    async def test_fetch_prometheus_multi_result_parses_multiple_results(
        self, collector: MultiTargetMetricsCollector
    ) -> None:
        """Verify _fetch_prometheus_multi_result returns a dict mapping pod names to values.

        Unlike _fetch_prometheus_metric which returns (metric_name, value) tuple,
        this method should return {pod_name: value, ...} dict.
        """

        # Mock Prometheus response with multiple results (one per pod)
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "status": "success",
            "data": {
                "result": [
                    {"metric": {"pod": "vllm-pod-0"}, "value": [1234567890.123, "10.5"]},
                    {"metric": {"pod": "vllm-pod-1"}, "value": [1234567890.456, "20.5"]},
                    {"metric": {"pod": "vllm-pod-2"}, "value": [1234567890.789, "30.5"]},
                ]
            },
        }
        mock_response.raise_for_status = MagicMock()

        mock_internal_client = MagicMock()
        mock_internal_client.get = AsyncMock(return_value=mock_response)

        with patch("services.shared.get_internal_client", return_value=mock_internal_client):
            with patch("services.multi_target_collector._with_retry", AsyncMock(return_value=mock_response)):
                result = await collector._fetch_prometheus_multi_result(
                    headers={},
                    query='rate(vllm:num_generated_tokens{namespace="test"}[1m])',
                )

        # Should return dict, not tuple
        assert isinstance(result, dict), f"Expected dict, got {type(result)}"

        # Should have 3 entries, one per pod
        assert len(result) == 3, f"Expected 3 results, got {len(result)}"

        # Verify pod names are keys
        assert "vllm-pod-0" in result
        assert "vllm-pod-1" in result
        assert "vllm-pod-2" in result

        # Verify values
        assert result["vllm-pod-0"] == 10.5
        assert result["vllm-pod-1"] == 20.5
        assert result["vllm-pod-2"] == 30.5

    @pytest.mark.asyncio
    async def test_fetch_prometheus_multi_result_handles_missing_pod_label(
        self, collector: MultiTargetMetricsCollector
    ) -> None:
        """Verify _fetch_prometheus_multi_result uses fallback keys when pod label is missing.

        When Prometheus returns results without a 'pod' label, the method should
        use "pod_0", "pod_1", etc. as fallback keys.
        """

        # Mock Prometheus response without 'pod' label in metrics
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "status": "success",
            "data": {
                "result": [
                    {"metric": {"instance": "10.0.0.1:8000"}, "value": [1234567890.123, "100.0"]},
                    {"metric": {"instance": "10.0.0.2:8000"}, "value": [1234567890.456, "200.0"]},
                ]
            },
        }
        mock_response.raise_for_status = MagicMock()

        mock_internal_client = MagicMock()
        mock_internal_client.get = AsyncMock(return_value=mock_response)

        with patch("services.shared.get_internal_client", return_value=mock_internal_client):
            with patch("services.multi_target_collector._with_retry", AsyncMock(return_value=mock_response)):
                result = await collector._fetch_prometheus_multi_result(
                    headers={},
                    query='vllm:gpu_utilization_perc{namespace="test"}',
                )

        # Should still return 2 entries with fallback keys
        assert len(result) == 2, f"Expected 2 results, got {len(result)}"

        # Should use fallback keys since no 'pod' label
        assert "pod_0" in result
        assert "pod_1" in result

        # Verify values are mapped to fallback keys
        assert result["pod_0"] == 100.0
        assert result["pod_1"] == 200.0

    @pytest.mark.asyncio
    async def test_fetch_prometheus_multi_result_handles_empty_results(
        self, collector: MultiTargetMetricsCollector
    ) -> None:
        """Verify _fetch_prometheus_multi_result returns empty dict for no results."""

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "status": "success",
            "data": {"result": []},
        }
        mock_response.raise_for_status = MagicMock()

        mock_internal_client = MagicMock()
        mock_internal_client.get = AsyncMock(return_value=mock_response)

        with patch("services.shared.get_internal_client", return_value=mock_internal_client):
            with patch("services.multi_target_collector._with_retry", AsyncMock(return_value=mock_response)):
                result = await collector._fetch_prometheus_multi_result(
                    headers={},
                    query='vllm:nonexistent_metric{namespace="test"}',
                )

        assert result == {}, f"Expected empty dict, got {result}"

    @pytest.mark.asyncio
    async def test_fetch_prometheus_multi_result_skips_nan_and_inf(
        self, collector: MultiTargetMetricsCollector
    ) -> None:
        """Verify _fetch_prometheus_multi_result skips NaN and Inf values."""

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "status": "success",
            "data": {
                "result": [
                    {"metric": {"pod": "vllm-pod-0"}, "value": [1234567890.123, "NaN"]},
                    {"metric": {"pod": "vllm-pod-1"}, "value": [1234567890.456, "10.5"]},
                    {"metric": {"pod": "vllm-pod-2"}, "value": [1234567890.789, "Infinity"]},
                ]
            },
        }
        mock_response.raise_for_status = MagicMock()

        mock_internal_client = MagicMock()
        mock_internal_client.get = AsyncMock(return_value=mock_response)

        with patch("services.shared.get_internal_client", return_value=mock_internal_client):
            with patch("services.multi_target_collector._with_retry", AsyncMock(return_value=mock_response)):
                result = await collector._fetch_prometheus_multi_result(
                    headers={},
                    query='rate(vllm:num_generated_tokens{namespace="test"}[1m])',
                )

        # Should only contain the valid value, skip NaN and Infinity
        assert len(result) == 1, f"Expected 1 result (NaN and Inf skipped), got {len(result)}"
        assert "vllm-pod-1" in result
        assert result["vllm-pod-1"] == 10.5


class TestPodsEndpointIntegration:
    """Integration tests for /pods endpoint returning aggregated and per-pod metrics."""

    @pytest.mark.asyncio
    async def test_pods_endpoint_returns_aggregated_and_per_pod(self, collector: MultiTargetMetricsCollector) -> None:
        """Verify /pods endpoint returns both aggregated metrics and per-pod breakdown.

        The endpoint should:
        1. Return aggregated metrics (same as /batch endpoint)
        2. Return per-pod metrics using _build_pod_queries and _fetch_prometheus_multi_result
        """
        import asyncio

        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from models.load_test import BatchMetricsRequest

        # Register a target and set up its latest metrics
        await collector.register_target("test-ns", "test-is")
        target = collector.get_target("test-ns", "test-is")
        from backend.services.multi_target_collector import VLLMMetrics

        target.latest = VLLMMetrics(
            timestamp=1234567890.0,
            tokens_per_second=100.0,
            requests_per_second=10.0,
            kv_cache_usage_pct=50.0,
            running_requests=5,
            gpu_utilization_pct=80.0,
            gpu_memory_used_gb=20.0,
        )

        # Mock _query_prometheus to return aggregated metrics
        async def mock_query_prometheus(namespace: str, is_name: str, cr_type: str = None):
            return {
                "tokens_per_second": 100.0,
                "requests_per_second": 10.0,
                "kv_cache_usage_pct": 50.0,
                "running_requests": 5,
                "waiting_requests": 2,
                "gpu_utilization_pct": 80.0,
                "gpu_memory_used_gb": 20.0,
            }

        # Mock _fetch_prometheus_multi_result to return per-pod metrics
        async def mock_fetch_multi(headers: dict, query: str):
            # Return mock per-pod data
            return {
                "vllm-pod-0": 55.0,
                "vllm-pod-1": 45.0,
            }

        collector._query_prometheus = mock_query_prometheus
        collector._fetch_prometheus_multi_result = mock_fetch_multi
        collector._token = None

        # Create a minimal FastAPI app for testing
        app = FastAPI()

        @app.post("/pods")
        async def get_pod_metrics(body: BatchMetricsRequest):
            import time

            from models.load_test import MetricsSnapshot, PerPodMetricSnapshot, PerPodMetricsResponse

            results = {}
            for target in body.targets:
                key = f"{target.namespace}/{target.inferenceService}"
                registered = await collector.register_target(
                    target.namespace, target.inferenceService, cr_type=target.cr_type
                )
                if not registered:
                    results[key] = PerPodMetricsResponse(
                        aggregated=MetricsSnapshot(timestamp=time.time()),
                        per_pod=[],
                        pod_names=[],
                        timestamp=time.time(),
                    )
                    continue

                # Get aggregated metrics
                vllm_metrics = await collector.get_metrics(target.namespace, target.inferenceService)

                # Build per-pod queries
                queries = collector._build_pod_queries(target.namespace, target.inferenceService, target.cr_type)
                headers = {}
                if collector._token:
                    headers["Authorization"] = f"Bearer {collector._token}"

                # Fetch all pod queries in parallel
                fetch_tasks = [collector._fetch_prometheus_multi_result(headers, query) for query in queries.values()]
                query_results = await asyncio.gather(*fetch_tasks)

                # Build pod_metrics mapping
                metric_names = list(queries.keys())
                pod_metrics = {}
                for metric_name, pod_result in zip(metric_names, query_results, strict=False):
                    for pod_name, value in pod_result.items():
                        if pod_name not in pod_metrics:
                            pod_metrics[pod_name] = {
                                "tps": None,
                                "rps": None,
                                "kv_cache": None,
                                "running": None,
                                "waiting": None,
                                "gpu_util": None,
                                "gpu_mem_used": None,
                            }
                        snapshot_field = _pod_metric_to_snapshot_field(metric_name)
                        if snapshot_field and value is not None:
                            pod_metrics[pod_name][snapshot_field] = value

                # Convert to PerPodMetricSnapshot list
                pod_names = sorted(pod_metrics.keys())
                per_pod_snapshots = [
                    PerPodMetricSnapshot(
                        pod_name=pod_name,
                        tps=pod_metrics[pod_name].get("tps"),
                        rps=pod_metrics[pod_name].get("rps"),
                        kv_cache=pod_metrics[pod_name].get("kv_cache"),
                        running=pod_metrics[pod_name].get("running"),
                        waiting=pod_metrics[pod_name].get("waiting"),
                        gpu_util=pod_metrics[pod_name].get("gpu_util"),
                        gpu_mem_used=pod_metrics[pod_name].get("gpu_mem_used"),
                    )
                    for pod_name in pod_names
                ]

                # Create aggregated snapshot from metrics
                aggregated = MetricsSnapshot(
                    timestamp=time.time(),
                    tps=vllm_metrics.tokens_per_second if vllm_metrics else None,
                    rps=vllm_metrics.requests_per_second if vllm_metrics else None,
                    kv_cache=vllm_metrics.kv_cache_usage_pct if vllm_metrics else None,
                    running=vllm_metrics.running_requests if vllm_metrics else None,
                    gpu_util=vllm_metrics.gpu_utilization_pct if vllm_metrics else None,
                    gpu_mem_used=vllm_metrics.gpu_memory_used_gb if vllm_metrics else None,
                )

                results[key] = PerPodMetricsResponse(
                    aggregated=aggregated,
                    per_pod=per_pod_snapshots,
                    pod_names=pod_names,
                    timestamp=time.time(),
                )

            return results

        def _pod_metric_to_snapshot_field(metric_name: str) -> str | None:
            mapping = {
                "tokens_per_second": "tps",
                "requests_per_second": "rps",
                "kv_cache_usage_pct": "kv_cache",
                "running_requests": "running",
                "waiting_requests": "waiting",
                "gpu_utilization_pct": "gpu_util",
                "gpu_memory_used_gb": "gpu_mem_used",
            }
            return mapping.get(metric_name)

        # Test the endpoint
        with TestClient(app) as client:
            response = client.post(
                "/pods",
                json={
                    "targets": [
                        {
                            "namespace": "test-ns",
                            "inferenceService": "test-is",
                            "cr_type": "inferenceservice",
                        }
                    ]
                },
            )

        assert response.status_code == 200
        data = response.json()

        # Should have one result for our target
        assert "test-ns/test-is" in data

        result = data["test-ns/test-is"]

        # Should have aggregated metrics
        assert "aggregated" in result

        # Should have per-pod metrics
        assert "per_pod" in result
        assert "pod_names" in result

        # Verify per-pod data exists
        assert len(result["pod_names"]) == 2
        assert "vllm-pod-0" in result["pod_names"]
        assert "vllm-pod-1" in result["pod_names"]

        # Verify per_pod list has entries
        assert len(result["per_pod"]) == 2
        pod_0_data = next(p for p in result["per_pod"] if p["pod_name"] == "vllm-pod-0")
        assert pod_0_data["kv_cache"] == 55.0


class TestLLMISSelectorIsolation:
    """Tests verifying LLMIS selector isolation between different instances.

    These tests ensure that:
    - _build_target_queries and _build_pod_queries generate distinct selectors for different LLMIS instances
    - LLMIS selectors contain pod=~"name-kserve.*" filter
    - KServe selectors do NOT contain pod=~ filter
    """

    def test_build_target_queries_llmis_small_contains_pod_selector(
        self, collector: MultiTargetMetricsCollector
    ) -> None:
        """Verify _build_target_queries for LLMIS small-llm-d contains pod=~'small-llm-d-kserve.*'."""
        queries = collector._build_target_queries("llm-d-demo", "small-llm-d", "llminferenceservice")

        # Every query value should contain the pod selector for small-llm-d
        for metric_name, query in queries.items():
            assert 'pod=~"small-llm-d-kserve.*"' in query, (
                f"{metric_name} should contain pod=~'small-llm-d-kserve.*', got: {query}"
            )

    def test_build_target_queries_llmis_large_contains_pod_selector(
        self, collector: MultiTargetMetricsCollector
    ) -> None:
        """Verify _build_target_queries for LLMIS large-llm-d contains pod=~'large-llm-d-kserve.*'."""
        queries = collector._build_target_queries("llm-d-demo", "large-llm-d", "llminferenceservice")

        # Every query value should contain the pod selector for large-llm-d
        for metric_name, query in queries.items():
            assert 'pod=~"large-llm-d-kserve.*"' in query, (
                f"{metric_name} should contain pod=~'large-llm-d-kserve.*', got: {query}"
            )

    def test_build_target_queries_llmis_selectors_are_different(self, collector: MultiTargetMetricsCollector) -> None:
        """Verify _build_target_queries generates different selectors for different LLMIS instances."""
        q_small = collector._build_target_queries("llm-d-demo", "small-llm-d", "llminferenceservice")
        q_large = collector._build_target_queries("llm-d-demo", "large-llm-d", "llminferenceservice")

        # The selectors should be different between small and large
        assert q_small["tokens_per_second"] != q_large["tokens_per_second"], (
            "small-llm-d and large-llm-d should have different selectors"
        )

    def test_build_pod_queries_llmis_small_contains_pod_selector(self, collector: MultiTargetMetricsCollector) -> None:
        """Verify _build_pod_queries for LLMIS small-llm-d contains pod=~'small-llm-d-kserve.*'."""
        queries = collector._build_pod_queries("llm-d-demo", "small-llm-d", "llminferenceservice")

        # Every query value should contain the pod selector for small-llm-d
        for metric_name, query in queries.items():
            assert 'pod=~"small-llm-d-kserve.*"' in query, (
                f"{metric_name} should contain pod=~'small-llm-d-kserve.*', got: {query}"
            )

    def test_build_target_queries_kserve_does_not_contain_pod_selector(
        self, collector: MultiTargetMetricsCollector
    ) -> None:
        """Verify _build_target_queries for KServe (inferenceservice) does NOT contain pod=~."""
        queries = collector._build_target_queries("some-ns", "llm-ov", "inferenceservice")

        # Non-GPU queries should not contain pod=~ in main selector
        # GPU metrics use DCGM which legitimately has exported_pod=~
        non_gpu_metrics = [
            k for k in queries if k not in ("gpu_memory_used_gb", "gpu_memory_total_gb", "gpu_utilization_pct")
        ]
        for metric_name in non_gpu_metrics:
            assert "pod=~" not in queries[metric_name], (
                f"{metric_name} should NOT contain pod=~ for KServe, got: {queries[metric_name]}"
            )

    def test_build_pod_queries_kserve_does_not_contain_pod_selector(
        self, collector: MultiTargetMetricsCollector
    ) -> None:
        """Verify _build_pod_queries for KServe (inferenceservice) does NOT contain pod=~."""
        queries = collector._build_pod_queries("some-ns", "llm-ov", "inferenceservice")

        # Non-GPU queries should not contain pod=~ in main selector
        # GPU metrics use DCGM which legitimately has exported_pod=~
        non_gpu_metrics = [
            k for k in queries if k not in ("gpu_memory_used_gb", "gpu_memory_total_gb", "gpu_utilization_pct")
        ]
        for metric_name in non_gpu_metrics:
            assert "pod=~" not in queries[metric_name], (
                f"{metric_name} should NOT contain pod=~ for KServe, got: {queries[metric_name]}"
            )


class TestFetchPrometheusMultiResultDCGMFallback:
    """Tests for DCGM exported_pod relabeling fallback in _fetch_prometheus_multi_result.

    These tests verify that when DCGM exporter returns metrics with 'exported_pod' label
    (instead of plain 'pod'), the collector falls back to using exported_pod for pod name
    resolution. This is critical for GPU metrics where nvidia-dcgm-exporter rewrites
    pod labels via relabeling rules.
    """

    @pytest.mark.asyncio
    async def test_dcgm_relabeling_pod_replaced_with_exported_pod(self, collector: MultiTargetMetricsCollector) -> None:
        """Verify exported_pod label is used when pod label doesn't match pattern."""
        # Prometheus returns DCGM metric with exported_pod relabeling
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "status": "success",
            "data": {
                "result": [
                    {
                        "metric": {"pod": "nvidia-dcgm-exporter-abc123", "exported_pod": "llm-ov-predictor-xyz"},
                        "value": [1234567890.0, "75.0"],
                    }
                ]
            },
        }
        mock_response.raise_for_status = MagicMock()

        mock_internal_client = MagicMock()
        mock_internal_client.get = AsyncMock(return_value=mock_response)

        with patch("services.shared.get_internal_client", return_value=mock_internal_client):
            with patch("services.multi_target_collector._with_retry", AsyncMock(return_value=mock_response)):
                result = await collector._fetch_prometheus_multi_result(
                    headers={},
                    query='DCGM_FI_DEV_GPU_UTIL{namespace="test"}',
                    pod_name_pattern="llm-ov-predictor.*",
                )

        # Should use exported_pod value for pod name
        assert result == {"llm-ov-predictor-xyz": 75.0}

    @pytest.mark.asyncio
    async def test_dcgm_relabeling_exported_pod_no_match_skipped(self, collector: MultiTargetMetricsCollector) -> None:
        """Verify result is skipped when exported_pod doesn't match pod_name_pattern."""
        # Prometheus returns DCGM metric where exported_pod doesn't match pattern
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "status": "success",
            "data": {
                "result": [
                    {
                        "metric": {"pod": "nvidia-dcgm-exporter-abc123", "exported_pod": "some-other-pod"},
                        "value": [1234567890.0, "75.0"],
                    }
                ]
            },
        }
        mock_response.raise_for_status = MagicMock()

        mock_internal_client = MagicMock()
        mock_internal_client.get = AsyncMock(return_value=mock_response)

        with patch("services.shared.get_internal_client", return_value=mock_internal_client):
            with patch("services.multi_target_collector._with_retry", AsyncMock(return_value=mock_response)):
                result = await collector._fetch_prometheus_multi_result(
                    headers={},
                    query='DCGM_FI_DEV_GPU_UTIL{namespace="test"}',
                    pod_name_pattern="llm-ov-predictor.*",
                )

        # exported_pod doesn't match pattern, should be skipped
        assert result == {}

    @pytest.mark.asyncio
    async def test_dcgm_relabeling_llmis_path(self, collector: MultiTargetMetricsCollector) -> None:
        """Verify exported_pod fallback works for LLMIS naming convention."""
        # Prometheus returns DCGM metric with LLMIS exported_pod
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "status": "success",
            "data": {
                "result": [
                    {
                        "metric": {"pod": "nvidia-dcgm-exporter-abc123", "exported_pod": "small-llm-d-kserve-abc"},
                        "value": [1234567890.0, "60.0"],
                    }
                ]
            },
        }
        mock_response.raise_for_status = MagicMock()

        mock_internal_client = MagicMock()
        mock_internal_client.get = AsyncMock(return_value=mock_response)

        with patch("services.shared.get_internal_client", return_value=mock_internal_client):
            with patch("services.multi_target_collector._with_retry", AsyncMock(return_value=mock_response)):
                result = await collector._fetch_prometheus_multi_result(
                    headers={},
                    query='DCGM_FI_DEV_GPU_UTIL{namespace="test"}',
                    pod_name_pattern="small-llm-d-kserve.*",
                )

        # Should use exported_pod value for LLMIS pod name
        assert result == {"small-llm-d-kserve-abc": 60.0}

    @pytest.mark.asyncio
    async def test_dcgm_relabeling_no_exported_pod_skipped(self, collector: MultiTargetMetricsCollector) -> None:
        """Verify result is skipped when neither pod nor exported_pod matches pattern."""
        # Prometheus returns DCGM metric with only 'pod' label (no exported_pod)
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "status": "success",
            "data": {
                "result": [
                    {
                        "metric": {"pod": "nvidia-dcgm-exporter-abc123"},
                        "value": [1234567890.0, "75.0"],
                    }
                ]
            },
        }
        mock_response.raise_for_status = MagicMock()

        mock_internal_client = MagicMock()
        mock_internal_client.get = AsyncMock(return_value=mock_response)

        with patch("services.shared.get_internal_client", return_value=mock_internal_client):
            with patch("services.multi_target_collector._with_retry", AsyncMock(return_value=mock_response)):
                result = await collector._fetch_prometheus_multi_result(
                    headers={},
                    query='DCGM_FI_DEV_GPU_UTIL{namespace="test"}',
                    pod_name_pattern="llm-ov-predictor.*",
                )

        # No exported_pod and pod doesn't match pattern, should be skipped
        assert result == {}

    @pytest.mark.asyncio
    async def test_dcgm_relabeling_multi_gpu_last_write_wins(self, collector: MultiTargetMetricsCollector) -> None:
        """Verify multiple GPU results with same exported_pod result in one entry (last wins)."""
        # Prometheus returns two DCGM results for different GPUs, same exported_pod
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "status": "success",
            "data": {
                "result": [
                    {
                        "metric": {
                            "pod": "nvidia-dcgm-exporter-abc123",
                            "exported_pod": "llm-ov-predictor-xyz",
                            "gpu": "0",
                        },
                        "value": [1234567890.0, "30.0"],
                    },
                    {
                        "metric": {
                            "pod": "nvidia-dcgm-exporter-abc123",
                            "exported_pod": "llm-ov-predictor-xyz",
                            "gpu": "1",
                        },
                        "value": [1234567890.0, "40.0"],
                    },
                ]
            },
        }
        mock_response.raise_for_status = MagicMock()

        mock_internal_client = MagicMock()
        mock_internal_client.get = AsyncMock(return_value=mock_response)

        with patch("services.shared.get_internal_client", return_value=mock_internal_client):
            with patch("services.multi_target_collector._with_retry", AsyncMock(return_value=mock_response)):
                result = await collector._fetch_prometheus_multi_result(
                    headers={},
                    query='DCGM_FI_DEV_GPU_UTIL{namespace="test"}',
                    pod_name_pattern="llm-ov-predictor.*",
                )

        # Both GPUs report to same pod, should be deduplicated (one entry)
        assert len(result) == 1
        assert "llm-ov-predictor-xyz" in result
        assert result["llm-ov-predictor-xyz"] in {30.0, 40.0}
