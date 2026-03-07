import pytest_asyncio
import httpx 
from unittest.mock import AsyncMock, patch, MagicMock
from collections.abc import AsyncGenerator

import backend.services.metrics_collector 
from backend.services.metrics_collector import MetricsCollector, VLLM_QUERIES_BY_VERSION

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

    async def test_detect_version_013x(self, mock_httpx_client: AsyncMock, mock_metrics_collector: MetricsCollector):
        # Mock Prometheus response for 0.13.x
        mock_httpx_client.get.return_value.json.return_value = {
            "status": "success",
            "data": {
                "resultType": "vector",
                "result": [
                    {
                        "metric": {},
                        "value": [1678886400, "0.5"]
                    }
                ]
            }
        }

        version = await mock_metrics_collector._detect_version()
        assert version == "0.13.x"
        mock_httpx_client.get.assert_called_once_with(
            "http://mock-prometheus/api/v1/query",
            params={"query": "vllm:kv_cache_usage_perc"},
        )

    async def test_detect_version_fallback_to_011x_on_empty_result(self, mock_httpx_client: AsyncMock, mock_metrics_collector: MetricsCollector):
        # Mock Prometheus response with empty result
        mock_httpx_client.get.return_value.json.return_value = {
            "status": "success",
            "data": {
                "resultType": "vector",
                "result": []
            }
        }

        version = await mock_metrics_collector._detect_version()
        assert version == "0.11.x"
        mock_httpx_client.get.assert_called_once()

    async def test_detect_version_fallback_to_011x_on_exception(self, mock_httpx_client: AsyncMock, mock_metrics_collector: MetricsCollector):
        # Mock httpx.get to raise an exception
        mock_httpx_client.get.side_effect = httpx.RequestError("Connection error", request=httpx.Request("GET", "http://test"))

        version = await mock_metrics_collector._detect_version()
        assert version == "0.11.x"
        mock_httpx_client.get.assert_called_once()

class TestMetricsCollectorQuerySelection:
    @pytest_asyncio.fixture
    async def mock_metrics_collector(self) -> AsyncGenerator[MetricsCollector, None]:
        # Mock _load_token and _init_k8s to prevent actual K8s interaction
        with patch('backend.services.metrics_collector.MetricsCollector._load_token', return_value=None), \
             patch('backend.services.metrics_collector.MetricsCollector._init_k8s', return_value=None):
            collector = MetricsCollector()
            yield collector

    async def test_queries_set_based_on_version_011x(self, mock_metrics_collector: MetricsCollector):
        # Mock _detect_version to return "0.11.x"
        with patch.object(mock_metrics_collector, '_detect_version', return_value="0.11.x"):
            await mock_metrics_collector._post_init()
            assert mock_metrics_collector._version == "0.11.x"
            assert mock_metrics_collector._current_queries == VLLM_QUERIES_BY_VERSION["0.11.x"]

    async def test_queries_set_based_on_version_013x(self, mock_metrics_collector: MetricsCollector):
        # Mock _detect_version to return "0.13.x"
        with patch.object(mock_metrics_collector, '_detect_version', return_value="0.13.x"):
            await mock_metrics_collector._post_init()
            assert mock_metrics_collector._version == "0.13.x"
            assert mock_metrics_collector._current_queries == VLLM_QUERIES_BY_VERSION["0.13.x"]

    async def test_queries_set_based_on_unknown_version_falls_back_to_011x(self, mock_metrics_collector: MetricsCollector):
        # Mock _detect_version to return an unknown version
        with patch.object(mock_metrics_collector, '_detect_version', return_value="99.99.x"):
            await mock_metrics_collector._post_init()
            assert mock_metrics_collector._version == "99.99.x" # The version itself is stored
            assert mock_metrics_collector._current_queries == VLLM_QUERIES_BY_VERSION["0.11.x"] # But queries fall back
