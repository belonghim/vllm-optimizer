"""
Unit tests for TPOT and Queue Time population in LoadTestEngine._finalize_results().

Tests that when:
- endpoints_match is True (load test target matches monitored endpoint)
- metrics_collector.latest returns valid data

Then final_stats should contain populated tpot and queue_time values.
"""

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from models.load_test import LoadTestConfig
from services.load_engine import LoadTestEngine
from services.multi_target_collector import VLLMMetrics


def _make_mock_httpx_client():
    """Simple mock that returns successful responses."""

    async def _post(url, json=None, **kwargs):
        resp = MagicMock()
        resp.json.return_value = {"usage": {"completion_tokens": 10}}
        return resp

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = _post
    _preflight_resp = MagicMock()
    _preflight_resp.status_code = 400
    mock_client.get = AsyncMock(return_value=_preflight_resp)
    return mock_client


class TestTPOTQueueTimePopulation:
    """Tests for TPOT and Queue Time population from metrics_collector."""

    @pytest.mark.asyncio
    async def test_tpot_queue_time_populated_when_endpoints_match(self):
        """When endpoints_match is True, tpot and queue_time should be populated from metrics_collector."""
        engine = LoadTestEngine()
        config = LoadTestConfig(
            total_requests=5,
            rps=0,
            concurrency=5,
            stream=False,
            endpoint="http://test-endpoint:8080/v1",
            model="test-model",
        )

        mock_metrics = VLLMMetrics(timestamp=time.time())
        mock_metrics.mean_tpot_ms = 50.0
        mock_metrics.p99_tpot_ms = 100.0
        mock_metrics.mean_queue_time_ms = 10.0
        mock_metrics.p99_queue_time_ms = 25.0

        mock_collector = MagicMock()
        mock_collector.latest = mock_metrics

        mock_shared = MagicMock()
        mock_shared.multi_target_collector = mock_collector
        mock_shared.runtime_config.vllm_endpoint = "http://test-endpoint:8080/v1"
        mock_shared.storage = MagicMock()
        mock_shared.storage.set_running = AsyncMock(return_value=1)
        mock_shared.storage.clear_running = AsyncMock()
        mock_shared.storage.save_load_test = AsyncMock()

        with patch("services.shared.external_client", _make_mock_httpx_client()):
            with patch("services.shared.runtime_config", mock_shared.runtime_config):
                with patch("services.shared.multi_target_collector", mock_collector):
                    with patch("services.shared.storage", mock_shared.storage):
                        final_stats = await engine.run(config, skip_preflight=True)

        assert final_stats.get("tpot") is not None
        assert final_stats["tpot"]["mean"] == pytest.approx(0.050, rel=0.01)
        assert final_stats["tpot"]["p95"] == pytest.approx(0.100, rel=0.01)

        assert final_stats.get("queue_time") is not None
        assert final_stats["queue_time"]["mean"] == pytest.approx(0.010, rel=0.01)
        assert final_stats["queue_time"]["p95"] == pytest.approx(0.025, rel=0.01)

    @pytest.mark.asyncio
    async def test_tpot_queue_time_not_populated_when_endpoints_differ(self):
        """When endpoints_match is False, tpot and queue_time should NOT be populated."""
        engine = LoadTestEngine()
        config = LoadTestConfig(
            total_requests=5,
            rps=0,
            concurrency=5,
            stream=False,
            endpoint="http://other-endpoint:8080/v1",
            model="test-model",
        )

        mock_metrics = VLLMMetrics(timestamp=time.time())
        mock_metrics.mean_tpot_ms = 50.0
        mock_metrics.p99_tpot_ms = 100.0
        mock_metrics.mean_queue_time_ms = 10.0
        mock_metrics.p99_queue_time_ms = 25.0

        mock_collector = MagicMock()
        mock_collector.latest = mock_metrics

        mock_shared = MagicMock()
        mock_shared.multi_target_collector = mock_collector
        mock_shared.runtime_config.vllm_endpoint = "http://test-endpoint:8080/v1"
        mock_shared.storage = MagicMock()
        mock_shared.storage.set_running = AsyncMock(return_value=1)
        mock_shared.storage.clear_running = AsyncMock()
        mock_shared.storage.save_load_test = AsyncMock()

        with patch("services.shared.external_client", _make_mock_httpx_client()):
            with patch("services.shared.runtime_config", mock_shared.runtime_config):
                with patch("services.shared.multi_target_collector", mock_collector):
                    with patch("services.shared.storage", mock_shared.storage):
                        final_stats = await engine.run(config, skip_preflight=True)

        assert final_stats.get("tpot") is None or final_stats["tpot"].get("mean") == 0
        assert final_stats.get("queue_time") is None or final_stats["queue_time"].get("mean") == 0

    @pytest.mark.asyncio
    async def test_tpot_queue_time_graceful_handling_on_collector_error(self):
        """When metrics_collector raises exception, should not crash - just skip population."""
        engine = LoadTestEngine()
        config = LoadTestConfig(
            total_requests=5,
            rps=0,
            concurrency=5,
            stream=False,
            endpoint="http://test-endpoint:8080/v1",
            model="test-model",
        )

        def raising_property():
            raise RuntimeError("Collector unavailable")

        mock_collector = MagicMock()
        type(mock_collector).latest = property(
            lambda self: (_ for _ in ()).throw(RuntimeError("Collector unavailable"))
        )

        mock_shared = MagicMock()
        mock_shared.multi_target_collector = mock_collector
        mock_shared.runtime_config.vllm_endpoint = "http://test-endpoint:8080/v1"
        mock_shared.storage = MagicMock()
        mock_shared.storage.set_running = AsyncMock(return_value=1)
        mock_shared.storage.clear_running = AsyncMock()
        mock_shared.storage.save_load_test = AsyncMock()

        with patch("services.shared.external_client", _make_mock_httpx_client()):
            with patch("services.shared.runtime_config", mock_shared.runtime_config):
                with patch("services.shared.multi_target_collector", mock_collector):
                    with patch("services.shared.storage", mock_shared.storage):
                        final_stats = await engine.run(config, skip_preflight=True)

        assert isinstance(final_stats, dict)
        assert "tpot" in final_stats
