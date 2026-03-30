import asyncio
from unittest.mock import MagicMock, patch

import pytest
from kubernetes.client.exceptions import ApiException

from ..services import k8s_operator as k8s_operator_module
from ..services.k8s_operator import K8sOperator


def _make_runtime_config(namespace: str = "test-ns", is_name: str = "test-isvc") -> MagicMock:
    rc = MagicMock()
    rc.vllm_namespace = namespace
    rc.vllm_is_name = is_name
    return rc


def _make_cr_adapter() -> MagicMock:
    adapter = MagicMock()
    adapter.api_group.return_value = "serving.kserve.io"
    adapter.api_version.return_value = "v1beta1"
    adapter.api_plural.return_value = "inferenceservices"
    adapter.snapshot_args.return_value = {"--max-num-seqs": "64"}
    adapter.build_args_patch.return_value = {"spec": {"predictor": {"model": {"args": []}}}}
    adapter.build_rollback_patch.return_value = {"spec": {"predictor": {"model": {"args": []}}}}
    return adapter


@pytest.fixture
def mock_k8s():
    with (
        patch.object(k8s_operator_module.k8s_config, "load_incluster_config", return_value=None),
        patch.object(k8s_operator_module.k8s_config, "load_kube_config", return_value=None),
        patch.object(k8s_operator_module.k8s_client, "AppsV1Api") as mock_apps_cls,
        patch.object(k8s_operator_module.k8s_client, "CustomObjectsApi") as mock_custom_cls,
    ):
        mock_apps = MagicMock()
        mock_custom = MagicMock()
        mock_apps_cls.return_value = mock_apps
        mock_custom_cls.return_value = mock_custom
        mock_custom.get_namespaced_custom_object.return_value = {
            "spec": {"predictor": {"model": {"args": []}}},
            "status": {},
        }
        mock_custom.patch_namespaced_custom_object.return_value = {}
        yield {"apps": mock_apps, "custom": mock_custom}


@pytest.fixture
def operator(mock_k8s: dict) -> K8sOperator:
    return K8sOperator()


@pytest.mark.asyncio
async def test_apply_params_happy_path(operator: K8sOperator, mock_k8s: dict) -> None:
    with (
        patch.object(k8s_operator_module, "runtime_config", _make_runtime_config()),
        patch.object(k8s_operator_module, "get_cr_adapter", return_value=_make_cr_adapter()),
    ):
        lock = asyncio.Lock()
        result = await operator.apply_params(
            {"max_num_seqs": 64, "gpu_memory_utilization": 0.8, "max_model_len": 4096},
            lock,
        )

    assert result["success"] is True
    mock_k8s["custom"].patch_namespaced_custom_object.assert_called_once()


@pytest.mark.asyncio
async def test_apply_params_403_returns_rbac_error(operator: K8sOperator, mock_k8s: dict) -> None:
    mock_k8s["custom"].get_namespaced_custom_object.side_effect = ApiException(status=403)

    with (
        patch.object(k8s_operator_module, "runtime_config", _make_runtime_config()),
        patch.object(k8s_operator_module, "get_cr_adapter", return_value=_make_cr_adapter()),
    ):
        lock = asyncio.Lock()
        result = await operator.apply_params({"max_num_seqs": 64}, lock)

    assert result["success"] is False
    assert result["error_type"] == "rbac"


@pytest.mark.asyncio
async def test_apply_params_k8s_unavailable_returns_error() -> None:
    op = K8sOperator.__new__(K8sOperator)
    op._k8s_available = False
    op._k8s_apps = None
    op._k8s_custom = None
    op._is_args_snapshot = None
    op._last_rollback_trial = None
    op._wait_durations = []
    op._total_wait_seconds = 0.0
    op._poll_count = 0
    op._cooldown_secs = 30

    lock = asyncio.Lock()
    result = await op.apply_params({"max_num_seqs": 64}, lock)

    assert result["success"] is False
    assert result["error_type"] == "k8s_unavailable"


@pytest.mark.asyncio
async def test_rollback_to_snapshot_success(operator: K8sOperator, mock_k8s: dict) -> None:
    operator._is_args_snapshot = {"--max-num-seqs": "64"}

    with (
        patch.object(k8s_operator_module, "runtime_config", _make_runtime_config()),
        patch.object(k8s_operator_module, "get_cr_adapter", return_value=_make_cr_adapter()),
    ):
        lock = asyncio.Lock()
        result = await operator.rollback_to_snapshot(trial_num=1, k8s_lock=lock)

    assert result is True
    assert operator._last_rollback_trial == 1
    mock_k8s["custom"].patch_namespaced_custom_object.assert_called_once()


def test_params_to_args_generates_correct_flags(operator: K8sOperator) -> None:
    params = {
        "max_num_seqs": 128,
        "gpu_memory_utilization": 0.85,
        "max_model_len": 4096,
        "enable_chunked_prefill": True,
        "enable_enforce_eager": False,
    }
    args = operator.params_to_args(params)

    assert "--max-num-seqs=128" in args
    assert "--gpu-memory-utilization=0.85" in args
    assert "--max-model-len=4096" in args
    assert "--enable-chunked-prefill" in args
    assert "--enforce-eager" not in args
