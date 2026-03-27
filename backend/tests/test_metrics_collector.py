import os
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from kubernetes.client.exceptions import ApiException

from ..services.multi_target_collector import MultiTargetMetricsCollector


def _build_collector() -> MultiTargetMetricsCollector:
    collector = MultiTargetMetricsCollector()
    collector._k8s_available = False
    collector._k8s_core = None
    return collector


class TestMultiTargetMetricsCollector:
    def test_registers_default_target_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("K8S_NAMESPACE", "env-namespace")
        monkeypatch.setenv("VLLM_DEPLOYMENT_NAME", "env-is")

        collector = _build_collector()
        default_target = collector._get_default_target()

        assert default_target is not None
        assert default_target.namespace == "env-namespace"
        assert default_target.is_name == "env-is"
        assert default_target.is_default is True

    def test_build_target_queries_include_namespace_and_job(self) -> None:
        collector = _build_collector()
        queries = collector._build_target_queries("ns-a", "is-a")

        assert queries
        for query in queries.values():
            assert 'namespace="ns-a"' in query
            assert 'job="kserve-llm-isvc-vllm-engine"' in query

    @pytest.mark.asyncio
    async def test_fetch_prometheus_metric_filters_nan_and_inf(self) -> None:
        collector = _build_collector()

        response = MagicMock()
        response.raise_for_status.return_value = None
        client_instance = AsyncMock()
        client_instance.get.return_value = response

        response.json.return_value = {
            "status": "success",
            "data": {"result": [{"value": [os.times().elapsed, "NaN"]}]},
        }
        with patch("services.shared.internal_client", client_instance):
            _name, value_nan = await collector._fetch_prometheus_metric(
                {},
                "mean_ttft_ms",
                "query",
            )
        assert value_nan is None

        response.json.return_value = {
            "status": "success",
            "data": {"result": [{"value": [os.times().elapsed, "+Inf"]}]},
        }
        with patch("services.shared.internal_client", client_instance):
            _name, value_inf = await collector._fetch_prometheus_metric(
                {},
                "mean_ttft_ms",
                "query",
            )
        assert value_inf is None

        response.json.return_value = {
            "status": "success",
            "data": {"result": [{"value": [os.times().elapsed, "123.456"]}]},
        }
        with patch("services.shared.internal_client", client_instance):
            _name, value_ok = await collector._fetch_prometheus_metric(
                {},
                "mean_ttft_ms",
                "query",
            )
        assert value_ok == 123.456

    @pytest.mark.asyncio
    async def test_query_prometheus_connection_error(self) -> None:
        collector = _build_collector()

        async def raise_connect_error(*args: object, **kwargs: object) -> None:
            raise httpx.ConnectError("Connection refused")

        mock_client = AsyncMock()
        mock_client.get.side_effect = raise_connect_error
        with patch("services.shared.internal_client", mock_client):
            result = await collector._query_prometheus("test-ns", "test-is")

        assert result == {}

    @pytest.mark.asyncio
    async def test_query_prometheus_auth_failure(self) -> None:
        collector = _build_collector()

        mock_response = MagicMock()
        mock_request = MagicMock()
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "403 Forbidden",
            request=mock_request,
            response=MagicMock(status_code=403),
        )

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response
        with patch("services.shared.internal_client", mock_client):
            result = await collector._query_prometheus("test-ns", "test-is")

        assert result == {}

    @pytest.mark.asyncio
    async def test_query_prometheus_malformed_json(self) -> None:
        collector = _build_collector()

        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.side_effect = ValueError("Expecting value: line 1")

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response
        with patch("services.shared.internal_client", mock_client):
            result = await collector._query_prometheus("test-ns", "test-is")

        assert result == {}

    @pytest.mark.asyncio
    async def test_query_kubernetes_pods_api_exception(self) -> None:
        collector = _build_collector()
        collector._k8s_available = True
        collector._k8s_core = MagicMock()
        collector._k8s_core.list_namespaced_pod.side_effect = ApiException(status=403, reason="Forbidden")

        result = await collector._query_kubernetes_pods("test-ns", "test-is")

        assert result == {}

    @pytest.mark.asyncio
    async def test_check_namespace_monitoring_label_exception(self) -> None:
        collector = _build_collector()
        collector._k8s_available = True
        collector._k8s_core = MagicMock()
        collector._k8s_core.read_namespace.side_effect = ApiException(status=404, reason="Not Found")

        result = await collector.check_namespace_monitoring_label("nonexistent-ns")

        assert result is False
