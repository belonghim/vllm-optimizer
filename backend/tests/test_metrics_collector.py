import pytest_asyncio
import httpx 
from unittest.mock import AsyncMock, patch, MagicMock
from collections.abc import AsyncGenerator

import backend.services.metrics_collector 
from backend.services.metrics_collector import MetricsCollector, _build_queries

class TestMetricsCollectorVersionDetection:
    @pytest_asyncio.fixture
    async def mock_httpx_client(self) -> AsyncGenerator[AsyncMock, None]:
        with patch('httpx.AsyncClient') as mock_client_cls:
            mock_client_instance = AsyncMock()
            mock_client_cls.return_value = mock_client_instance

            # Mock the async context manager methods
            mock_client_instance.__aenter__.return_value = mock_client_instance
            mock_client_instance.__aexit__.return_value = None

            mock_response = MagicMock()
            mock_response.json = MagicMock()
            mock_client_instance.get.return_value = mock_response
            yield mock_client_instance

    @pytest_asyncio.fixture
    async def mock_metrics_collector(self, mock_httpx_client: AsyncMock) -> AsyncGenerator[MetricsCollector, None]:
        # Mock _load_token and _init_k8s to prevent actual K8s interaction
        with patch('backend.services.metrics_collector.MetricsCollector._load_token', return_value=None), \
             patch('backend.services.metrics_collector.MetricsCollector._init_k8s', return_value=None), \
             patch.dict(MetricsCollector._detect_version.__globals__, {'PROMETHEUS_URL': "http://mock-prometheus"}):
            collector = MetricsCollector()
            yield collector

    async def test_detect_version_013x_gpu(self, mock_httpx_client: AsyncMock, mock_metrics_collector: MetricsCollector):
        # GPU metric present -> vLLM 0.13.x
        mock_httpx_client.get.return_value.json.return_value = {
            "status": "success",
            "data": {
                "resultType": "vector",
                "result": [
                    {
                        "metric": {},
                        "value": [1678886400, "1073741824"]
                    }
                ]
            }
        }

        version = await mock_metrics_collector._detect_version()
        assert version == "0.13.x"
        mock_httpx_client.get.assert_called_once_with(
            "http://mock-prometheus/api/v1/query",
            params={"query": "vllm:gpu_memory_usage_bytes"},
        )

    async def test_detect_version_013x_cpu(self, mock_httpx_client: AsyncMock, mock_metrics_collector: MetricsCollector):
        # GPU metric missing but KV cache metric present -> vLLM 0.13.x-cpu
        mock_httpx_client.get.return_value.json.side_effect = [
            {"status": "success", "data": {"resultType": "vector", "result": []}},
            {"status": "success", "data": {"resultType": "vector", "result": [{"metric": {}, "value": [1678886400, "0.5"]}]}}
        ]

        version = await mock_metrics_collector._detect_version()
        assert version == "0.13.x-cpu"
        assert mock_httpx_client.get.call_count == 2
        assert mock_httpx_client.get.call_args_list[0][0][0] == "http://mock-prometheus/api/v1/query"
        assert mock_httpx_client.get.call_args_list[0][1]["params"] == {"query": "vllm:gpu_memory_usage_bytes"}
        assert mock_httpx_client.get.call_args_list[1][1]["params"] == {"query": "vllm:kv_cache_usage_perc"}

    async def test_detect_version_fallback_to_011x_on_empty_result(self, mock_httpx_client: AsyncMock, mock_metrics_collector: MetricsCollector):
        # Both probes return empty -> fallback to 0.11.x
        mock_httpx_client.get.return_value.json.side_effect = [
            {"status": "success", "data": {"resultType": "vector", "result": []}},
            {"status": "success", "data": {"resultType": "vector", "result": []}},
        ]

        version = await mock_metrics_collector._detect_version()
        assert version == "0.11.x"
        assert mock_httpx_client.get.call_count == 2

    async def test_detect_version_fallback_to_011x_on_exception(self, mock_httpx_client: AsyncMock, mock_metrics_collector: MetricsCollector):
        # Mock httpx.get to raise an exception
        mock_httpx_client.get.side_effect = httpx.RequestError("Connection error", request=httpx.Request("GET", "http://test"))

        version = await mock_metrics_collector._detect_version()
        assert version == "0.11.x"
        assert mock_httpx_client.get.call_count == 2
        assert mock_httpx_client.get.call_args_list[0][1]["params"] == {"query": "vllm:gpu_memory_usage_bytes"}
        assert mock_httpx_client.get.call_args_list[1][1]["params"] == {"query": "vllm:kv_cache_usage_perc"}

class TestMetricsCollectorQuerySelection:
    @pytest_asyncio.fixture
    async def mock_metrics_collector(self) -> AsyncGenerator[MetricsCollector, None]:
        # Mock _load_token and _init_k8s to prevent actual K8s interaction
        with patch('backend.services.metrics_collector.MetricsCollector._load_token', return_value=None), \
             patch('backend.services.metrics_collector.MetricsCollector._init_k8s', return_value=None):
            collector = MetricsCollector()
            yield collector

    async def test_queries_set_based_on_version_011x(self, mock_metrics_collector: MetricsCollector):
        with patch.object(mock_metrics_collector, '_detect_version', return_value="0.11.x"):
            await mock_metrics_collector._post_init()
            assert mock_metrics_collector._version == "0.11.x"
            assert mock_metrics_collector._current_queries == _build_queries("vllm-lab-dev")["0.11.x"]

    async def test_queries_set_based_on_version_013x(self, mock_metrics_collector: MetricsCollector):
        with patch.object(mock_metrics_collector, '_detect_version', return_value="0.13.x"):
            await mock_metrics_collector._post_init()
            assert mock_metrics_collector._version == "0.13.x"
            assert mock_metrics_collector._current_queries == _build_queries("vllm-lab-dev")["0.13.x"]

    async def test_queries_set_based_on_unknown_version_falls_back_to_011x(self, mock_metrics_collector: MetricsCollector):
        with patch.object(mock_metrics_collector, '_detect_version', return_value="99.99.x"):
            await mock_metrics_collector._post_init()
            assert mock_metrics_collector._version == "99.99.x"
            assert mock_metrics_collector._current_queries == _build_queries("vllm-lab-dev")["0.11.x"]

    async def test_queries_contain_namespace_filter(self, mock_metrics_collector: MetricsCollector):
        with patch.object(mock_metrics_collector, '_detect_version', return_value="0.13.x-cpu"):
            await mock_metrics_collector._post_init()
            queries = mock_metrics_collector._current_queries
            assert queries is not None
            for key, query in queries.items():
                assert 'namespace=' in query, f"Query '{key}' missing namespace filter: {query}"

class TestMetricsCollectorNaNFiltering:
    @pytest_asyncio.fixture
    async def mock_httpx_client(self) -> AsyncGenerator[AsyncMock, None]:
        with patch('httpx.AsyncClient') as mock_client_cls:
            mock_client_instance = AsyncMock()
            mock_client_cls.return_value = mock_client_instance
            mock_client_instance.__aenter__.return_value = mock_client_instance
            mock_client_instance.__aexit__.return_value = None
            mock_response = MagicMock()
            mock_response.json = MagicMock()
            mock_client_instance.get.return_value = mock_response
            yield mock_client_instance

    @pytest_asyncio.fixture
    async def mock_metrics_collector(self, mock_httpx_client: AsyncMock) -> AsyncGenerator[MetricsCollector, None]:
        with patch('backend.services.metrics_collector.MetricsCollector._load_token', return_value=None), \
             patch('backend.services.metrics_collector.MetricsCollector._init_k8s', return_value=None):
            collector = MetricsCollector()
            yield collector

    async def test_fetch_prometheus_metric_filters_nan(self, mock_httpx_client: AsyncMock, mock_metrics_collector: MetricsCollector):
        # Prometheus returns "NaN" string
        mock_httpx_client.get.return_value.json.return_value = {
            "status": "success",
            "data": {"resultType": "vector", "result": [{"metric": {}, "value": [1678886400, "NaN"]}]}
        }
        name, value = await mock_metrics_collector._fetch_prometheus_metric(
            client=mock_httpx_client, metric_name="mean_ttft_ms", query="test_query"
        )
        assert name == "mean_ttft_ms"
        assert value is None  # NaN must be filtered to None

    async def test_fetch_prometheus_metric_filters_positive_inf(self, mock_httpx_client: AsyncMock, mock_metrics_collector: MetricsCollector):
        # Prometheus returns "+Inf" string
        mock_httpx_client.get.return_value.json.return_value = {
            "status": "success",
            "data": {"resultType": "vector", "result": [{"metric": {}, "value": [1678886400, "+Inf"]}]}
        }
        name, value = await mock_metrics_collector._fetch_prometheus_metric(
            client=mock_httpx_client, metric_name="p99_latency", query="test_query"
        )
        assert name == "p99_latency"
        assert value is None  # +Inf must be filtered to None

    async def test_fetch_prometheus_metric_filters_negative_inf(self, mock_httpx_client: AsyncMock, mock_metrics_collector: MetricsCollector):
        # Prometheus returns "-Inf" string
        mock_httpx_client.get.return_value.json.return_value = {
            "status": "success",
            "data": {"resultType": "vector", "result": [{"metric": {}, "value": [1678886400, "-Inf"]}]}
        }
        name, value = await mock_metrics_collector._fetch_prometheus_metric(
            client=mock_httpx_client, metric_name="latency_mean", query="test_query"
        )
        assert name == "latency_mean"
        assert value is None  # -Inf must be filtered to None

    async def test_fetch_prometheus_metric_accepts_valid_values(self, mock_httpx_client: AsyncMock, mock_metrics_collector: MetricsCollector):
        # Prometheus returns valid numeric value
        mock_httpx_client.get.return_value.json.return_value = {
            "status": "success",
            "data": {"resultType": "vector", "result": [{"metric": {}, "value": [1678886400, "500.123"]}]}
        }
        name, value = await mock_metrics_collector._fetch_prometheus_metric(
            client=mock_httpx_client, metric_name="mean_ttft_ms", query="test_query"
        )
        assert name == "mean_ttft_ms"
        assert value == 500.123  # Valid value should pass through
