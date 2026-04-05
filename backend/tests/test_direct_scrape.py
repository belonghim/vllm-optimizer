from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from services.multi_target_collector import MultiTargetMetricsCollector


@pytest.fixture
def collector():
    with patch.object(MultiTargetMetricsCollector, "_init_k8s", return_value=None):
        with patch.object(MultiTargetMetricsCollector, "_register_default_target", return_value=None):
            c = MultiTargetMetricsCollector()
            c._targets = {}
            return c


def _make_mock_client(text: str):
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.text = text
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.get = AsyncMock(return_value=mock_response)
    return mock_client, mock_response


async def test_scrape_pod_metrics_returns_gauge_fields(collector, vllm_metrics_text):
    mock_client, _ = _make_mock_client(vllm_metrics_text)
    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await collector._scrape_pod_metrics("1.2.3.4", 8080)
    assert isinstance(result.get("kv_cache_usage_pct"), float)
    assert result["kv_cache_usage_pct"] > 0
    assert isinstance(result.get("running_requests"), float)
    assert result["running_requests"] > 0
    assert isinstance(result.get("waiting_requests"), float)
    assert result["waiting_requests"] > 0


async def test_scrape_pod_metrics_returns_counter_raw_values(collector, vllm_metrics_text):
    mock_client, _ = _make_mock_client(vllm_metrics_text)
    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await collector._scrape_pod_metrics("1.2.3.4", 8080)
    assert result.get("tokens_per_second", 0) > 0
    assert result.get("requests_per_second", 0) > 0


async def test_scrape_pod_metrics_connection_error_returns_empty(collector):
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.get = AsyncMock(side_effect=httpx.ConnectError("connection refused"))
    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await collector._scrape_pod_metrics("1.2.3.4", 8080)
    assert result == {}


async def test_scrape_pod_metrics_http_error_returns_empty(collector):
    mock_client, mock_response = _make_mock_client("")
    mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "500 Server Error", request=MagicMock(), response=MagicMock()
    )
    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await collector._scrape_pod_metrics("1.2.3.4", 8080)
    assert result == {}


_GAUGE_ONLY_TEXT = """\
# HELP vllm:num_requests_running Number of requests running.
# TYPE vllm:num_requests_running gauge
vllm:num_requests_running{pod="pod-0"} 3.0
# HELP vllm:kv_cache_usage_perc KV-cache usage.
# TYPE vllm:kv_cache_usage_perc gauge
vllm:kv_cache_usage_perc{pod="pod-0"} 0.45
"""


async def test_scrape_pod_metrics_partial_metrics_ok(collector):
    mock_client, _ = _make_mock_client(_GAUGE_ONLY_TEXT)
    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await collector._scrape_pod_metrics("1.2.3.4", 8080)
    assert result.get("running_requests") == 3.0
    assert result.get("kv_cache_usage_pct") == 0.45
    assert result.get("tokens_per_second", 0) == 0


async def test_scrape_pod_metrics_multi_pod_aggregation(collector, vllm_metrics_text):
    mock_client, _ = _make_mock_client(vllm_metrics_text)
    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await collector._scrape_pod_metrics("1.2.3.4", 8080)
    assert result["running_requests"] == 5.0


def test_compute_rates_first_call_returns_zero(collector):
    from services.multi_target_collector import TargetCache

    target = TargetCache(key="k", namespace="ns", is_name="is")
    rates = collector._compute_rates("1.2.3.4", target, {"tokens_per_second": 5000.0}, 1000.0)
    assert rates["tokens_per_second"] == 0.0


def test_compute_rates_normal_delta(collector):
    from services.multi_target_collector import TargetCache

    target = TargetCache(key="k", namespace="ns", is_name="is")
    collector._compute_rates("1.2.3.4", target, {"tokens_per_second": 5000.0}, 1000.0)
    rates = collector._compute_rates("1.2.3.4", target, {"tokens_per_second": 5100.0}, 1005.0)
    assert rates["tokens_per_second"] == pytest.approx(20.0, rel=1e-3)


def test_compute_rates_counter_reset_returns_zero(collector):
    from services.multi_target_collector import TargetCache

    target = TargetCache(key="k", namespace="ns", is_name="is")
    collector._compute_rates("1.2.3.4", target, {"tokens_per_second": 5000.0}, 1000.0)
    rates = collector._compute_rates("1.2.3.4", target, {"tokens_per_second": 100.0}, 1005.0)
    assert rates["tokens_per_second"] == 0.0


def test_compute_histogram_mean_ttft(collector):
    result = collector._compute_histogram_stats({"ttft_sum": 0.6, "ttft_count": 10.0})
    assert result["mean_ttft_ms"] == pytest.approx(60.0, rel=1e-3)


def test_compute_histogram_mean_latency(collector):
    result = collector._compute_histogram_stats({"latency_sum": 12.0, "latency_count": 10.0})
    assert result["mean_e2e_latency_ms"] == pytest.approx(1200.0, rel=1e-3)


async def test_collect_target_uses_thanos_by_default(collector, monkeypatch):
    from services.multi_target_collector import TargetCache

    monkeypatch.delenv("METRICS_SOURCE", raising=False)
    target = TargetCache(key="ns/is/inferenceservice", namespace="ns", is_name="is", cr_type="inferenceservice")
    called = []

    async def _fake_thanos(t):
        called.append("thanos")

    collector._collect_target_thanos = _fake_thanos
    await collector._collect_target(target)
    assert called == ["thanos"]


async def test_collect_target_uses_direct_when_env_set(collector, monkeypatch):
    from services.multi_target_collector import TargetCache

    monkeypatch.setenv("METRICS_SOURCE", "direct")
    target = TargetCache(key="ns/is/inferenceservice", namespace="ns", is_name="is", cr_type="inferenceservice")
    called = []

    async def _fake_direct(t):
        called.append("direct")

    collector._collect_target_direct = _fake_direct
    await collector._collect_target(target)
    assert called == ["direct"]


async def test_collect_target_direct_k8s_unavailable_returns_stale(collector, monkeypatch):
    from services.multi_target_collector import TargetCache, VLLMMetrics

    monkeypatch.setenv("METRICS_SOURCE", "direct")
    collector._k8s_available = False
    stale = VLLMMetrics(timestamp=1000.0, tokens_per_second=42.0)
    target = TargetCache(key="ns/is/inferenceservice", namespace="ns", is_name="is", cr_type="inferenceservice")
    target.latest = stale

    await collector._collect_target_direct(target)
    assert target.latest is stale


async def test_collect_target_direct_kserve(collector, monkeypatch, vllm_metrics_text):
    import types

    from services.multi_target_collector import TargetCache

    monkeypatch.setenv("METRICS_SOURCE", "direct")
    collector._k8s_available = True

    pod = types.SimpleNamespace(
        status=types.SimpleNamespace(
            phase="Running",
            pod_ip="10.0.0.1",
            container_statuses=[types.SimpleNamespace(ready=True)],
        )
    )
    pod_list = types.SimpleNamespace(items=[pod])

    async def _fake_list(*args, **kwargs):
        return pod_list

    collector._k8s_core = types.SimpleNamespace(list_namespaced_pod=lambda **kw: pod_list)

    mock_client, _ = _make_mock_client(vllm_metrics_text)
    target = TargetCache(key="ns/is/inferenceservice", namespace="ns", is_name="is", cr_type="inferenceservice")

    with patch("httpx.AsyncClient", return_value=mock_client):
        await collector._collect_target_direct(target)

    assert target.latest is not None
    assert target.latest.running_requests == 5
    assert target.latest.pod_count == 1
