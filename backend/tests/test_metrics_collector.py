import os
from unittest.mock import AsyncMock, MagicMock

import pytest

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
            assert 'job="is-a-metrics"' in query

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
        _name, value_nan = await collector._fetch_prometheus_metric(
            client_instance,
            "mean_ttft_ms",
            "query",
        )
        assert value_nan is None

        response.json.return_value = {
            "status": "success",
            "data": {"result": [{"value": [os.times().elapsed, "+Inf"]}]},
        }
        _name, value_inf = await collector._fetch_prometheus_metric(
            client_instance,
            "mean_ttft_ms",
            "query",
        )
        assert value_inf is None

        response.json.return_value = {
            "status": "success",
            "data": {"result": [{"value": [os.times().elapsed, "123.456"]}]},
        }
        _name, value_ok = await collector._fetch_prometheus_metric(
            client_instance,
            "mean_ttft_ms",
            "query",
        )
        assert value_ok == 123.456
