import time
from unittest.mock import AsyncMock, patch

import pytest

from ..services.multi_target_collector import MultiTargetMetricsCollector, TargetCache, VLLMMetrics


def _build_collector() -> MultiTargetMetricsCollector:
    collector = MultiTargetMetricsCollector()
    collector._k8s_available = False
    collector._k8s_core = None
    return collector


class TestRegisterTarget:
    @pytest.mark.asyncio
    async def test_register_new_target_adds_to_targets(self) -> None:
        collector = _build_collector()
        initial_count = len(collector._targets)

        with patch.object(collector, "_ensure_collect_loop", new_callable=AsyncMock):
            result = await collector.register_target("test-ns", "test-is")

        assert result is True
        assert len(collector._targets) == initial_count + 1
        assert collector._target_key("test-ns", "test-is") in collector._targets

    @pytest.mark.asyncio
    async def test_register_existing_target_returns_true_no_duplicate(self) -> None:
        collector = _build_collector()
        default = collector._get_default_target()
        assert default is not None
        before = len(collector._targets)

        with patch.object(collector, "_ensure_collect_loop", new_callable=AsyncMock):
            result = await collector.register_target(default.namespace, default.is_name)

        assert result is True
        assert len(collector._targets) == before

    @pytest.mark.asyncio
    async def test_register_target_max_limit_returns_false(self) -> None:
        collector = _build_collector()
        with patch.object(collector, "_ensure_collect_loop", new_callable=AsyncMock):
            for i in range(collector.MAX_TARGETS - 1):
                result = await collector.register_target(f"ns-{i}", f"is-{i}")
                assert result is True

            result = await collector.register_target("ns-overflow", "is-overflow")

        assert result is False
        assert len(collector._targets) == collector.MAX_TARGETS

    @pytest.mark.asyncio
    async def test_register_target_monitoring_label_false_when_k8s_unavailable(self) -> None:
        collector = _build_collector()

        with patch.object(collector, "_ensure_collect_loop", new_callable=AsyncMock):
            await collector.register_target("new-ns", "new-is")

        key = collector._target_key("new-ns", "new-is")
        assert collector._targets[key].has_monitoring_label is False

    @pytest.mark.asyncio
    async def test_register_target_new_target_is_not_default(self) -> None:
        collector = _build_collector()

        with patch.object(collector, "_ensure_collect_loop", new_callable=AsyncMock):
            await collector.register_target("extra-ns", "extra-is")

        key = collector._target_key("extra-ns", "extra-is")
        assert collector._targets[key].is_default is False


class TestRemoveTarget:
    @pytest.mark.asyncio
    async def test_remove_existing_target_returns_true(self) -> None:
        collector = _build_collector()

        with patch.object(collector, "_ensure_collect_loop", new_callable=AsyncMock):
            await collector.register_target("rm-ns", "rm-is")

        result = await collector.remove_target("rm-ns", "rm-is")

        assert result is True
        assert collector._target_key("rm-ns", "rm-is") not in collector._targets

    @pytest.mark.asyncio
    async def test_remove_nonexistent_target_returns_false(self) -> None:
        collector = _build_collector()

        result = await collector.remove_target("ghost-ns", "ghost-is")

        assert result is False

    @pytest.mark.asyncio
    async def test_remove_last_target_clears_targets_dict(self) -> None:
        collector = _build_collector()
        default = collector._get_default_target()
        assert default is not None

        result = await collector.remove_target(default.namespace, default.is_name)

        assert result is True
        assert len(collector._targets) == 0

    @pytest.mark.asyncio
    async def test_remove_non_default_target_leaves_default(self) -> None:
        collector = _build_collector()

        with patch.object(collector, "_ensure_collect_loop", new_callable=AsyncMock):
            await collector.register_target("extra-ns", "extra-is")

        await collector.remove_target("extra-ns", "extra-is")

        default = collector._get_default_target()
        assert default is not None
        assert default.is_default is True


class TestGetMetrics:
    @pytest.mark.asyncio
    async def test_get_metrics_unknown_target_returns_none(self) -> None:
        collector = _build_collector()

        result = await collector.get_metrics("unknown-ns", "unknown-is")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_metrics_registered_target_returns_none_before_collection(self) -> None:
        collector = _build_collector()

        with patch.object(collector, "_ensure_collect_loop", new_callable=AsyncMock):
            await collector.register_target("test-ns", "test-is")
            result = await collector.get_metrics("test-ns", "test-is")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_metrics_returns_latest_after_manual_set(self) -> None:
        collector = _build_collector()

        with patch.object(collector, "_ensure_collect_loop", new_callable=AsyncMock):
            await collector.register_target("test-ns", "test-is")

        key = collector._target_key("test-ns", "test-is")
        fake = VLLMMetrics(timestamp=time.time(), tokens_per_second=99.0)
        collector._targets[key].latest = fake

        with patch.object(collector, "_ensure_collect_loop", new_callable=AsyncMock):
            result = await collector.get_metrics("test-ns", "test-is")

        assert result is not None
        assert result.tokens_per_second == 99.0

    @pytest.mark.asyncio
    async def test_get_metrics_default_target_accessible(self) -> None:
        collector = _build_collector()
        default = collector._get_default_target()
        assert default is not None

        fake = VLLMMetrics(timestamp=time.time(), running_requests=3)
        default.latest = fake

        with patch.object(collector, "_ensure_collect_loop", new_callable=AsyncMock):
            result = await collector.get_metrics(default.namespace, default.is_name)

        assert result is not None
        assert result.running_requests == 3


class TestGetDefaultTarget:
    def test_get_default_target_returns_is_default_true(self) -> None:
        collector = _build_collector()

        default = collector._get_default_target()

        assert default is not None
        assert default.is_default is True

    def test_get_default_target_empty_targets_returns_none(self) -> None:
        collector = _build_collector()
        collector._targets.clear()

        result = collector._get_default_target()

        assert result is None

    def test_get_default_target_falls_back_to_first_when_no_is_default(self) -> None:
        collector = _build_collector()
        for t in collector._targets.values():
            t.is_default = False

        result = collector._get_default_target()

        assert result is not None

    def test_set_default_target_updates_namespace_and_key(self) -> None:
        collector = _build_collector()

        collector.set_default_target(namespace="new-ns", is_name="new-is")
        default = collector._get_default_target()

        assert default is not None
        assert default.namespace == "new-ns"
        assert default.is_name == "new-is"
        assert collector._target_key("new-ns", "new-is") in collector._targets

    def test_set_default_target_partial_update_namespace_only(self) -> None:
        collector = _build_collector()
        original_is_name = collector._get_default_target().is_name  # type: ignore[union-attr]

        collector.set_default_target(namespace="only-ns-change")
        default = collector._get_default_target()

        assert default is not None
        assert default.namespace == "only-ns-change"
        assert default.is_name == original_is_name


class TestTargetKey:
    def test_target_key_format(self) -> None:
        collector = _build_collector()
        assert collector._target_key("my-namespace", "my-is-name") == "my-namespace/my-is-name"

    def test_target_key_used_consistently(self) -> None:
        collector = _build_collector()
        key1 = collector._target_key("ns", "is")
        key2 = collector._target_key("ns", "is")
        assert key1 == key2


class TestCrType:
    @pytest.mark.asyncio
    async def test_register_target_stores_cr_type(self) -> None:
        collector = _build_collector()

        with patch.object(collector, "_ensure_collect_loop", new_callable=AsyncMock):
            await collector.register_target("test-ns", "test-is", cr_type="llminferenceservice")

        key = collector._target_key("test-ns", "test-is")
        assert collector._targets[key].cr_type == "llminferenceservice"

    def test_adapter_for_inferenceservice(self) -> None:
        from services.cr_adapter import InferenceServiceAdapter

        collector = _build_collector()
        target = TargetCache(key="ns/is", namespace="ns", is_name="is", cr_type="inferenceservice")

        adapter = collector._adapter_for(target)

        assert isinstance(adapter, InferenceServiceAdapter)

    def test_adapter_for_llminferenceservice(self) -> None:
        from services.cr_adapter import LLMInferenceServiceAdapter

        collector = _build_collector()
        target = TargetCache(key="ns/is", namespace="ns", is_name="is", cr_type="llminferenceservice")

        adapter = collector._adapter_for(target)

        assert isinstance(adapter, LLMInferenceServiceAdapter)

    def test_build_target_queries_cr_type_difference(self) -> None:
        collector = _build_collector()

        isvc_queries = collector._build_target_queries("ns", "my-svc", "inferenceservice")
        llmis_queries = collector._build_target_queries("ns", "my-svc", "llminferenceservice")

        assert isvc_queries["tokens_per_second"] != llmis_queries["tokens_per_second"]

    def test_register_default_target_uses_runtime_cr_type(self) -> None:
        import os

        collector = _build_collector()
        collector._targets.clear()

        with patch.dict(os.environ, {"VLLM_CR_TYPE": "inferenceservice"}):
            collector._register_default_target()

        default = collector._get_default_target()
        assert default is not None
        assert default.cr_type == "inferenceservice"
