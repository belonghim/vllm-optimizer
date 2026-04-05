import time
from unittest.mock import AsyncMock, MagicMock, patch

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
        assert collector.build_target_key("test-ns", "test-is") in collector._targets

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

        key = collector.build_target_key("new-ns", "new-is")
        assert collector._targets[key].has_monitoring_label is False

    @pytest.mark.asyncio
    async def test_register_target_new_target_is_not_default(self) -> None:
        collector = _build_collector()

        with patch.object(collector, "_ensure_collect_loop", new_callable=AsyncMock):
            await collector.register_target("extra-ns", "extra-is")

        key = collector.build_target_key("extra-ns", "extra-is")
        assert collector._targets[key].is_default is False


class TestRemoveTarget:
    @pytest.mark.asyncio
    async def test_remove_existing_target_returns_true(self) -> None:
        collector = _build_collector()

        with patch.object(collector, "_ensure_collect_loop", new_callable=AsyncMock):
            await collector.register_target("rm-ns", "rm-is")

        result = await collector.remove_target("rm-ns", "rm-is")

        assert result is True
        assert collector.build_target_key("rm-ns", "rm-is") not in collector._targets

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

        key = collector.build_target_key("test-ns", "test-is")
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
        assert collector.build_target_key("new-ns", "new-is") in collector._targets

    def test_set_default_target_partial_update_namespace_only(self) -> None:
        collector = _build_collector()
        default_target = collector._get_default_target()
        assert default_target is not None
        original_is_name = default_target.is_name

        collector.set_default_target(namespace="only-ns-change")
        default = collector._get_default_target()

        assert default is not None
        assert default.namespace == "only-ns-change"
        assert default.is_name == original_is_name


class TestTargetKey:
    def test_target_key_format(self) -> None:
        collector = _build_collector()
        assert (
            collector.build_target_key("my-namespace", "my-is-name", "inferenceservice")
            == "my-namespace/my-is-name/inferenceservice"
        )

    def test_target_key_used_consistently(self) -> None:
        collector = _build_collector()
        key1 = collector.build_target_key("ns", "is")
        key2 = collector.build_target_key("ns", "is")
        assert key1 == key2

    def test_target_key_includes_cr_type(self) -> None:
        collector = _build_collector()
        assert collector.build_target_key("ns", "name", "inferenceservice") == "ns/name/inferenceservice"

    def test_target_key_defaults_to_inferenceservice(self) -> None:
        collector = _build_collector()
        assert collector.build_target_key("ns", "name").endswith("/inferenceservice")

    def test_target_key_prevents_collision(self) -> None:
        collector = _build_collector()
        assert collector.build_target_key("ns", "name", "inferenceservice") != collector.build_target_key(
            "ns", "name", "llminferenceservice"
        )


class TestCrType:
    @pytest.mark.asyncio
    async def test_register_target_stores_cr_type(self) -> None:
        collector = _build_collector()

        with patch.object(collector, "_ensure_collect_loop", new_callable=AsyncMock):
            await collector.register_target("test-ns", "test-is", cr_type="llminferenceservice")

        key = collector.build_target_key("test-ns", "test-is", "llminferenceservice")
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

    @pytest.mark.asyncio
    async def test_resolve_model_name_isvc_from_served_model_name(self) -> None:
        collector = _build_collector()
        collector._k8s_available = True
        collector._k8s_custom = MagicMock()
        collector._k8s_custom.get_namespaced_custom_object.return_value = {
            "spec": {
                "predictor": {
                    "model": {
                        "args": [
                            "--served-model-name=OpenVINO/Phi-4-mini-instruct-int4-ov",
                            "--max-num-seqs=256",
                        ]
                    }
                }
            }
        }

        model_name = await collector._resolve_model_name("vllm-lab-dev", "llm-ov", "inferenceservice")

        assert model_name == "OpenVINO/Phi-4-mini-instruct-int4-ov"

    @pytest.mark.asyncio
    async def test_resolve_model_name_llmis_from_spec_model_name(self) -> None:
        collector = _build_collector()
        collector._k8s_available = True
        collector._k8s_custom = MagicMock()
        collector._k8s_custom.get_namespaced_custom_object.return_value = {
            "spec": {
                "model": {
                    "name": "OpenVINO/Phi-4-mini-instruct-int4-ov",
                }
            }
        }

        model_name = await collector._resolve_model_name("llm-d-demo", "small-llm-d", "llminferenceservice")

        assert model_name == "OpenVINO/Phi-4-mini-instruct-int4-ov"


class TestBuildTargetQueries:
    def test_isvc_uses_vllm_metric_prefix(self) -> None:
        collector = _build_collector()
        queries = collector._build_target_queries("test-ns", "my-svc", "inferenceservice")

        assert all("vllm:" in q for q in queries.values())
        assert 'job="my-svc-metrics"' in queries["tokens_per_second"]
        assert 'namespace="test-ns"' in queries["tokens_per_second"]

    def test_llmis_uses_kserve_vllm_metric_prefix(self) -> None:
        collector = _build_collector()
        queries = collector._build_target_queries("test-ns", "my-svc", "llminferenceservice")

        assert all("kserve_vllm:" in q for q in queries.values())
        assert 'job="kserve-llm-isvc-vllm-engine"' in queries["tokens_per_second"]
        assert 'namespace="test-ns"' in queries["tokens_per_second"]

    def test_isvc_dcgm_pod_pattern_uses_predictor_suffix(self) -> None:
        collector = _build_collector()
        queries = collector._build_target_queries("test-ns", "my-svc", "inferenceservice")

        assert "my-svc-predictor.*" in queries["gpu_memory_used_gb"]

    def test_llmis_dcgm_pod_pattern_uses_kserve_suffix(self) -> None:
        collector = _build_collector()
        queries = collector._build_target_queries("test-ns", "my-svc", "llminferenceservice")

        assert "my-svc-kserve.*" in queries["gpu_memory_used_gb"]

    def test_query_keys_are_identical_between_cr_types(self) -> None:
        collector = _build_collector()
        isvc_queries = collector._build_target_queries("ns", "svc", "inferenceservice")
        llmis_queries = collector._build_target_queries("ns", "svc", "llminferenceservice")

        assert set(isvc_queries.keys()) == set(llmis_queries.keys())
        assert len(isvc_queries) == 13


class TestQueryKubernetesPods:
    """Tests for _query_kubernetes_pods K8s API interaction."""

    @pytest.mark.asyncio
    async def test_returns_count_and_ready_for_running_pods(self) -> None:
        collector = _build_collector()
        collector._k8s_available = True
        collector._k8s_core = MagicMock()

        mock_pod = MagicMock()
        mock_pod.status.phase = "Running"
        mock_container = MagicMock()
        mock_container.ready = True
        mock_pod.status.container_statuses = [mock_container]

        mock_pod_list = MagicMock()
        mock_pod_list.items = [mock_pod]
        collector._k8s_core.list_namespaced_pod.return_value = mock_pod_list

        with patch("services.cr_adapter.get_cr_adapter") as mock_adapter:
            adapter = MagicMock()
            adapter.pod_label_selector.return_value = "app=test"
            mock_adapter.return_value = adapter

            result = await collector._query_kubernetes_pods("test-ns", "test-svc", "inferenceservice")

        assert result == {"pod_count": 1, "pod_ready": 1}

    @pytest.mark.asyncio
    async def test_empty_container_statuses_not_counted_as_ready(self) -> None:
        collector = _build_collector()
        collector._k8s_available = True
        collector._k8s_core = MagicMock()

        mock_pod = MagicMock()
        mock_pod.status.phase = "Running"
        mock_pod.status.container_statuses = []

        mock_pod_list = MagicMock()
        mock_pod_list.items = [mock_pod]
        collector._k8s_core.list_namespaced_pod.return_value = mock_pod_list

        with patch("services.cr_adapter.get_cr_adapter") as mock_adapter:
            adapter = MagicMock()
            adapter.pod_label_selector.return_value = "app=test"
            mock_adapter.return_value = adapter

            result = await collector._query_kubernetes_pods("test-ns", "test-svc", "inferenceservice")

        assert result == {"pod_count": 1, "pod_ready": 0}

    @pytest.mark.asyncio
    async def test_none_container_statuses_not_counted_as_ready(self) -> None:
        collector = _build_collector()
        collector._k8s_available = True
        collector._k8s_core = MagicMock()

        mock_pod = MagicMock()
        mock_pod.status.phase = "Running"
        mock_pod.status.container_statuses = None

        mock_pod_list = MagicMock()
        mock_pod_list.items = [mock_pod]
        collector._k8s_core.list_namespaced_pod.return_value = mock_pod_list

        with patch("services.cr_adapter.get_cr_adapter") as mock_adapter:
            adapter = MagicMock()
            adapter.pod_label_selector.return_value = "app=test"
            mock_adapter.return_value = adapter

            result = await collector._query_kubernetes_pods("test-ns", "test-svc", "inferenceservice")

        assert result == {"pod_count": 1, "pod_ready": 0}

    @pytest.mark.asyncio
    async def test_pending_pod_not_counted_as_ready(self) -> None:
        collector = _build_collector()
        collector._k8s_available = True
        collector._k8s_core = MagicMock()

        mock_pod = MagicMock()
        mock_pod.status.phase = "Pending"
        mock_container = MagicMock()
        mock_container.ready = True
        mock_pod.status.container_statuses = [mock_container]

        mock_pod_list = MagicMock()
        mock_pod_list.items = [mock_pod]
        collector._k8s_core.list_namespaced_pod.return_value = mock_pod_list

        with patch("services.cr_adapter.get_cr_adapter") as mock_adapter:
            adapter = MagicMock()
            adapter.pod_label_selector.return_value = "app=test"
            mock_adapter.return_value = adapter

            result = await collector._query_kubernetes_pods("test-ns", "test-svc", "inferenceservice")

        assert result == {"pod_count": 1, "pod_ready": 0}

    @pytest.mark.asyncio
    async def test_uses_correct_label_selector_per_cr_type(self) -> None:
        """Verify _query_kubernetes_pods passes the correct label selector for each CR type."""
        from services.cr_adapter import InferenceServiceAdapter, LLMInferenceServiceAdapter

        collector = _build_collector()
        collector._k8s_available = True
        collector._k8s_core = MagicMock()

        mock_pod_list = MagicMock()
        mock_pod_list.items = []
        collector._k8s_core.list_namespaced_pod.return_value = mock_pod_list

        await collector._query_kubernetes_pods("ns", "my-svc", "inferenceservice")
        collector._k8s_core.list_namespaced_pod.assert_called_with(
            namespace="ns",
            label_selector=InferenceServiceAdapter().pod_label_selector("my-svc"),
        )

        await collector._query_kubernetes_pods("ns", "my-svc", "llminferenceservice")
        collector._k8s_core.list_namespaced_pod.assert_called_with(
            namespace="ns",
            label_selector=LLMInferenceServiceAdapter().pod_label_selector("my-svc"),
        )


class TestGetTargetWarning:
    @pytest.mark.asyncio
    async def test_get_target_returns_none_for_unknown_key(self, caplog: pytest.LogCaptureFixture) -> None:
        collector = _build_collector()
        import logging

        with caplog.at_level(logging.WARNING, logger="services.multi_target_collector"):
            result = collector.get_target("nonexistent-ns", "nonexistent-is")

        assert result is None
        assert any("Target not found" in r.message for r in caplog.records)

    @pytest.mark.asyncio
    async def test_get_history_returns_data_after_collection(self) -> None:
        import time

        collector = _build_collector()
        with patch.object(collector, "_ensure_collect_loop", new_callable=AsyncMock):
            await collector.register_target("hist-ns", "hist-is")

        key = collector.build_target_key("hist-ns", "hist-is")
        target = collector._targets[key]
        fake = VLLMMetrics(timestamp=time.time(), tokens_per_second=42.0)
        target.history.append(fake)

        key = collector.build_target_key("hist-ns", "hist-is")
        assert key in collector._targets
        history = list(collector._targets[key].history)
        assert len(history) > 0
        assert history[-1].tokens_per_second == 42.0
