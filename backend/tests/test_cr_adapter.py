import copy

import pytest

from services.cr_adapter import (
    InferenceServiceAdapter,
    LLMInferenceServiceAdapter,
    _extract_served_model_name,
    args_list_to_config_dict,
    config_dict_to_args_list,
    config_dict_to_space_str,
    get_cr_adapter,
    space_str_to_config_dict,
)


SAMPLE_IS_SPEC = {
    "predictor": {
        "model": {
            "args": [
                "--max-num-seqs=256",
                "--gpu-memory-utilization=0.80",
                "--enable-chunked-prefill",
                "--tensor-parallel-size=1",
            ],
            "resources": {
                "limits": {"cpu": "2", "memory": "8Gi"},
                "requests": {"cpu": "500m", "memory": "2Gi"},
            },
            "storageUri": "oci://registry.example.com/is-model:latest",
        }
    }
}


SAMPLE_LLMIS_SPEC = {
    "template": {
        "containers": [
            {
                "name": "main",
                "env": [
                    {"name": "HOME", "value": "/home"},
                    {
                        "name": "VLLM_ADDITIONAL_ARGS",
                        "value": "--gpu-memory-utilization=0.80 --max-model-len=8192 --tensor-parallel-size=1",
                    },
                ],
                "resources": {
                    "limits": {"cpu": "1", "memory": "4Gi", "nvidia.com/gpu": "1"},
                    "requests": {"cpu": "250m", "memory": "1Gi", "nvidia.com/gpu": "1"},
                },
            }
        ]
    },
    "model": {"uri": "oci://registry.example.com/model:latest"},
}


class TestArgHelpers:
    def test_args_list_to_config_dict(self):
        result = args_list_to_config_dict(
            [
                "--max-num-seqs=128",
                "--enable-chunked-prefill",
                "--tensor-parallel-size=1",
            ]
        )
        assert result == {
            "max_num_seqs": "128",
            "enable_chunked_prefill": "true",
        }

    def test_config_dict_to_args_list(self):
        result = config_dict_to_args_list(
            {
                "max_num_seqs": "512",
                "enable_chunked_prefill": "true",
                "enable_enforce_eager": "false",
                "unknown_key": "value",
            }
        )
        assert "--max-num-seqs=512" in result
        assert "--enable-chunked-prefill" in result
        assert "--enforce-eager" not in result
        assert len(result) == 2

    def test_space_helpers(self):
        value = "--gpu-memory-utilization=0.9 --max-model-len=4096 --tensor-parallel-size=1"
        config = space_str_to_config_dict(value)
        assert config == {
            "gpu_memory_utilization": "0.9",
            "max_model_len": "4096",
        }
        rebuilt = config_dict_to_space_str(config, static_prefix="--tensor-parallel-size=1")
        assert rebuilt == "--tensor-parallel-size=1 --gpu-memory-utilization=0.9 --max-model-len=4096"

    def test_extract_served_model_name_duplicate_uses_last_value(self):
        parsed_args = ["--served-model-name=alias", "--served-model-name=real-model"]
        assert _extract_served_model_name(parsed_args) == "real-model"

    def test_extract_served_model_name_space_separated(self):
        parsed_args = ["--served-model-name", "qwen3-5"]
        assert _extract_served_model_name(parsed_args) == "qwen3-5"

    def test_extract_served_model_name_missing_value_returns_none(self):
        parsed_args = ["--served-model-name"]
        assert _extract_served_model_name(parsed_args) is None

    def test_extract_served_model_name_followed_by_flag_returns_none(self):
        parsed_args = ["--served-model-name", "--tensor-parallel-size=4"]
        assert _extract_served_model_name(parsed_args) is None

    def test_extract_served_model_name_equals_format_regression(self):
        parsed_args = ["--served-model-name=qwen3-5"]
        assert _extract_served_model_name(parsed_args) == "qwen3-5"


class TestLLMInferenceServiceAdapter:
    def test_api_coordinates(self):
        adapter = LLMInferenceServiceAdapter()
        assert adapter.api_group() == "inference.io"
        assert adapter.api_version() == "v1"
        assert adapter.api_plural() == "llminferenceservices"

    def test_metric_prefix(self):
        adapter = LLMInferenceServiceAdapter()
        assert adapter.metric_prefix() == "kserve_vllm:"


class TestInferenceServiceAdapter:
    def test_api_coordinates(self):
        adapter = InferenceServiceAdapter()
        assert adapter.api_group() == "serving.kserve.io"
        assert adapter.api_version() == "v1beta1"
        assert adapter.api_plural() == "inferenceservices"

    def test_metric_prefix(self):
        adapter = InferenceServiceAdapter()
        assert adapter.metric_prefix() == "vllm:"

    def test_read_args_empty(self):
        adapter = InferenceServiceAdapter()
        assert adapter.read_args({}) == {}

    def test_read_args_with_values(self):
        adapter = InferenceServiceAdapter()
        result = adapter.read_args(SAMPLE_IS_SPEC)
        assert result["max_num_seqs"] == "256"
        assert result["gpu_memory_utilization"] == "0.80"
        assert result["enable_chunked_prefill"] == "true"

    def test_build_args_patch_preserves_static(self):
        adapter = InferenceServiceAdapter()
        patch = adapter.build_args_patch(SAMPLE_IS_SPEC, {"max_model_len": "16384"})
        patched_args = patch["spec"]["predictor"]["model"]["args"]
        assert "--tensor-parallel-size=1" in patched_args
        assert "--max-model-len=16384" in patched_args

    def test_build_args_patch_merges_config(self):
        adapter = InferenceServiceAdapter()
        patch = adapter.build_args_patch(SAMPLE_IS_SPEC, {"max_num_seqs": "512"})
        patched_args = patch["spec"]["predictor"]["model"]["args"]
        assert "--max-num-seqs=512" in patched_args
        assert "--gpu-memory-utilization=0.80" in patched_args
        assert "--enable-chunked-prefill" in patched_args
        assert "--max-num-seqs=256" not in patched_args

    def test_apply_args_to_cr_updates_full_cr_and_cleans_server_fields(self):
        adapter = InferenceServiceAdapter()
        cr_obj = {
            "apiVersion": "serving.kserve.io/v1beta1",
            "kind": "InferenceService",
            "metadata": {
                "name": "llm-ov",
                "namespace": "test-ns",
                "resourceVersion": "123",
                "uid": "abc",
                "creationTimestamp": "now",
                "generation": 2,
                "managedFields": [{"manager": "kube"}],
            },
            "spec": copy.deepcopy(SAMPLE_IS_SPEC),
            "status": {"conditions": []},
        }

        updated = adapter.apply_args_to_cr(cr_obj, {"max_num_seqs": "512"})
        updated_args = updated["spec"]["predictor"]["model"]["args"]

        assert "--max-num-seqs=512" in updated_args
        assert "--tensor-parallel-size=1" in updated_args
        assert "status" not in updated
        assert "resourceVersion" not in updated["metadata"]
        assert "uid" not in updated["metadata"]
        assert "creationTimestamp" not in updated["metadata"]
        assert "generation" not in updated["metadata"]
        assert "managedFields" not in updated["metadata"]

    def test_restore_cr_from_snapshot_cleans_server_fields(self):
        adapter = InferenceServiceAdapter()
        snapshot = {
            "apiVersion": "serving.kserve.io/v1beta1",
            "kind": "InferenceService",
            "metadata": {
                "name": "llm-ov",
                "namespace": "test-ns",
                "resourceVersion": "123",
                "uid": "abc",
                "creationTimestamp": "now",
                "generation": 2,
                "managedFields": [{"manager": "kube"}],
            },
            "spec": {"predictor": {"model": {"args": ["--max-num-seqs=64"]}}},
            "status": {"conditions": []},
        }

        restored = adapter.restore_cr_from_snapshot(snapshot)
        assert restored["spec"]["predictor"]["model"]["args"] == ["--max-num-seqs=64"]
        assert "status" not in restored
        assert "resourceVersion" not in restored["metadata"]
        assert "uid" not in restored["metadata"]
        assert "creationTimestamp" not in restored["metadata"]
        assert "generation" not in restored["metadata"]
        assert "managedFields" not in restored["metadata"]

    def test_read_resources(self):
        adapter = InferenceServiceAdapter()
        resources = adapter.read_resources(SAMPLE_IS_SPEC)
        assert resources["limits"]["cpu"] == "2"

    def test_build_resources_patch(self):
        adapter = InferenceServiceAdapter()
        resources = {"limits": {"cpu": "4"}}
        assert adapter.build_resources_patch(resources) == {"spec": {"predictor": {"model": {"resources": resources}}}}

    def test_read_model_uri(self):
        adapter = InferenceServiceAdapter()
        assert adapter.read_model_uri(SAMPLE_IS_SPEC) == "oci://registry.example.com/is-model:latest"

    def test_build_model_uri_patch(self):
        adapter = InferenceServiceAdapter()
        assert adapter.build_model_uri_patch("oci://new-uri") == {
            "spec": {"predictor": {"model": {"storageUri": "oci://new-uri"}}}
        }

    def test_snapshot_args(self):
        adapter = InferenceServiceAdapter()
        snapshot = adapter.snapshot_args(SAMPLE_IS_SPEC)
        assert snapshot == SAMPLE_IS_SPEC["predictor"]["model"]["args"]
        assert snapshot is not SAMPLE_IS_SPEC["predictor"]["model"]["args"]

    def test_build_rollback_patch(self):
        adapter = InferenceServiceAdapter()
        snapshot = ["--max-num-seqs=64"]
        assert adapter.build_rollback_patch(snapshot) == {
            "spec": {"predictor": {"model": {"args": ["--max-num-seqs=64"]}}}
        }

    def test_pod_label_selector(self):
        adapter = InferenceServiceAdapter()
        assert adapter.pod_label_selector("llm-ov") == "serving.kserve.io/inferenceservice=llm-ov"

    def test_deployment_name(self):
        adapter = InferenceServiceAdapter()
        assert adapter.deployment_name("llm-ov") == "llm-ov-predictor"

    def test_prometheus_job(self):
        adapter = InferenceServiceAdapter()
        assert adapter.prometheus_job("llm-ov") == "llm-ov-metrics"

    def test_dcgm_pod_pattern(self):
        adapter = InferenceServiceAdapter()
        assert adapter.dcgm_pod_pattern("llm-ov") == "llm-ov-predictor.*"

    def test_check_ready_true(self):
        adapter = InferenceServiceAdapter()
        status = {"conditions": [{"type": "Ready", "status": "True"}]}
        assert adapter.check_ready(status) is True

    def test_check_ready_false(self):
        adapter = InferenceServiceAdapter()
        status = {"conditions": [{"type": "Ready", "status": "False"}]}
        assert adapter.check_ready(status) is False

    def test_check_ready_no_conditions(self):
        adapter = InferenceServiceAdapter()
        assert adapter.check_ready({}) is False

    def test_resolve_model_name_from_served_model_name_arg(self):
        adapter = InferenceServiceAdapter()
        spec = {
            "predictor": {
                "model": {
                    "args": [
                        "--tensor-parallel-size=1",
                        "--served-model-name=qwen2-5-7b-instruct",
                    ]
                }
            }
        }
        assert adapter.resolve_model_name(spec, "llm-ov") == "qwen2-5-7b-instruct"

    def test_resolve_model_name_falls_back_to_is_name_for_isvc(self):
        adapter = InferenceServiceAdapter()
        spec = {"predictor": {"model": {"args": ["--max-num-seqs=256"]}}}
        assert adapter.resolve_model_name(spec, "llm-ov") == "llm-ov"

    def test_read_extra_args_returns_non_tuning_args(self):
        adapter = InferenceServiceAdapter()
        result = adapter.read_extra_args(SAMPLE_IS_SPEC)
        assert "--tensor-parallel-size=1" in result
        assert "--max-num-seqs=256" not in result
        assert "--gpu-memory-utilization=0.80" not in result


class TestLLMInferenceServiceAdapter:
    def test_api_coordinates(self):
        adapter = LLMInferenceServiceAdapter()
        assert adapter.api_group() == "serving.kserve.io"
        assert adapter.api_version() == "v1alpha1"
        assert adapter.api_plural() == "llminferenceservices"

    def test_read_args_empty(self):
        adapter = LLMInferenceServiceAdapter()
        assert adapter.read_args({}) == {}

    def test_read_args_from_env(self):
        adapter = LLMInferenceServiceAdapter()
        result = adapter.read_args(SAMPLE_LLMIS_SPEC)
        assert result["gpu_memory_utilization"] == "0.80"
        assert result["max_model_len"] == "8192"

    def test_read_args_missing_container(self):
        adapter = LLMInferenceServiceAdapter()
        spec = {"template": {"containers": [{"name": "worker", "env": []}]}}
        assert adapter.read_args(spec) == {}

    def test_read_args_missing_env(self):
        adapter = LLMInferenceServiceAdapter()
        spec = {"template": {"containers": [{"name": "main", "env": [{"name": "HOME", "value": "/home"}]}]}}
        assert adapter.read_args(spec) == {}

    def test_build_args_patch_format(self):
        adapter = LLMInferenceServiceAdapter()
        patch = adapter.build_args_patch(SAMPLE_LLMIS_SPEC, {"max_num_seqs": "128"})
        assert patch == {
            "spec": {
                "template": {
                    "containers": [
                        {
                            "name": "main",
                            "env": [
                                {
                                    "name": "VLLM_ADDITIONAL_ARGS",
                                    "value": "--tensor-parallel-size=1 --gpu-memory-utilization=0.80 --max-model-len=8192 --max-num-seqs=128",
                                }
                            ],
                        }
                    ]
                }
            }
        }

    def test_build_args_patch_preserves_non_tuning(self):
        adapter = LLMInferenceServiceAdapter()
        patch = adapter.build_args_patch(SAMPLE_LLMIS_SPEC, {"max_model_len": "16384"})
        value = patch["spec"]["template"]["containers"][0]["env"][0]["value"]
        assert "--tensor-parallel-size=1" in value
        assert "--max-model-len=16384" in value

    def test_build_args_patch_merges_config(self):
        adapter = LLMInferenceServiceAdapter()
        patch = adapter.build_args_patch(SAMPLE_LLMIS_SPEC, {"max_num_seqs": "256"})
        value = patch["spec"]["template"]["containers"][0]["env"][0]["value"]
        assert "--gpu-memory-utilization=0.80" in value
        assert "--max-model-len=8192" in value
        assert "--max-num-seqs=256" in value

    def test_apply_args_to_cr_updates_existing_env_and_cleans_server_fields(self):
        adapter = LLMInferenceServiceAdapter()
        cr_obj = {
            "apiVersion": "serving.kserve.io/v1alpha1",
            "kind": "LLMInferenceService",
            "metadata": {
                "name": "small-llm-d",
                "namespace": "test-ns",
                "resourceVersion": "123",
                "uid": "abc",
                "creationTimestamp": "now",
                "generation": 2,
                "managedFields": [{"manager": "kube"}],
            },
            "spec": copy.deepcopy(SAMPLE_LLMIS_SPEC),
            "status": {"conditions": []},
        }

        updated = adapter.apply_args_to_cr(cr_obj, {"max_num_seqs": "256"})
        main_container = next(c for c in updated["spec"]["template"]["containers"] if c["name"] == "main")
        env_map = {env["name"]: env["value"] for env in main_container["env"]}

        assert "HOME" in env_map
        assert "--max-num-seqs=256" in env_map["VLLM_ADDITIONAL_ARGS"]
        assert "--tensor-parallel-size=1" in env_map["VLLM_ADDITIONAL_ARGS"]
        assert "status" not in updated
        assert "resourceVersion" not in updated["metadata"]
        assert "uid" not in updated["metadata"]
        assert "creationTimestamp" not in updated["metadata"]
        assert "generation" not in updated["metadata"]
        assert "managedFields" not in updated["metadata"]

    def test_restore_cr_from_snapshot_for_llmis_cleans_server_fields(self):
        adapter = LLMInferenceServiceAdapter()
        snapshot = {
            "apiVersion": "serving.kserve.io/v1alpha1",
            "kind": "LLMInferenceService",
            "metadata": {
                "name": "small-llm-d",
                "namespace": "test-ns",
                "resourceVersion": "123",
                "uid": "abc",
                "creationTimestamp": "now",
                "generation": 2,
                "managedFields": [{"manager": "kube"}],
            },
            "spec": copy.deepcopy(SAMPLE_LLMIS_SPEC),
            "status": {"conditions": []},
        }

        restored = adapter.restore_cr_from_snapshot(snapshot)
        main_container = next(c for c in restored["spec"]["template"]["containers"] if c["name"] == "main")
        assert any(env["name"] == "VLLM_ADDITIONAL_ARGS" for env in main_container["env"])
        assert "status" not in restored
        assert "resourceVersion" not in restored["metadata"]
        assert "uid" not in restored["metadata"]
        assert "creationTimestamp" not in restored["metadata"]
        assert "generation" not in restored["metadata"]
        assert "managedFields" not in restored["metadata"]

    def test_read_resources(self):
        adapter = LLMInferenceServiceAdapter()
        resources = adapter.read_resources(SAMPLE_LLMIS_SPEC)
        assert resources["limits"]["nvidia.com/gpu"] == "1"

    def test_build_resources_patch(self):
        adapter = LLMInferenceServiceAdapter()
        resources = {"limits": {"cpu": "2"}}
        assert adapter.build_resources_patch(resources) == {
            "spec": {"template": {"containers": [{"name": "main", "resources": resources}]}}
        }

    def test_read_model_uri(self):
        adapter = LLMInferenceServiceAdapter()
        assert adapter.read_model_uri(SAMPLE_LLMIS_SPEC) == "oci://registry.example.com/model:latest"

    def test_build_model_uri_patch(self):
        adapter = LLMInferenceServiceAdapter()
        assert adapter.build_model_uri_patch("oci://new-uri") == {"spec": {"model": {"uri": "oci://new-uri"}}}

    def test_snapshot_args(self):
        adapter = LLMInferenceServiceAdapter()
        snapshot = adapter.snapshot_args(SAMPLE_LLMIS_SPEC)
        assert snapshot == "--gpu-memory-utilization=0.80 --max-model-len=8192 --tensor-parallel-size=1"

    def test_snapshot_args_missing_env(self):
        adapter = LLMInferenceServiceAdapter()
        spec = {"template": {"containers": [{"name": "main", "env": []}]}}
        assert adapter.snapshot_args(spec) == ""

    def test_build_rollback_patch(self):
        adapter = LLMInferenceServiceAdapter()
        assert adapter.build_rollback_patch("--max-model-len=4096") == {
            "spec": {
                "template": {
                    "containers": [
                        {
                            "name": "main",
                            "env": [{"name": "VLLM_ADDITIONAL_ARGS", "value": "--max-model-len=4096"}],
                        }
                    ]
                }
            }
        }

    def test_pod_label_selector(self):
        adapter = LLMInferenceServiceAdapter()
        assert adapter.pod_label_selector("small-llm-d") == "kserve.io/component=workload"

    def test_deployment_name(self):
        adapter = LLMInferenceServiceAdapter()
        assert adapter.deployment_name("small-llm-d") == "small-llm-d-kserve"

    def test_prometheus_job(self):
        adapter = LLMInferenceServiceAdapter()
        assert adapter.prometheus_job("small-llm-d") == "kserve-llm-isvc-vllm-engine"

    def test_dcgm_pod_pattern(self):
        adapter = LLMInferenceServiceAdapter()
        assert adapter.dcgm_pod_pattern("small-llm-d") == "small-llm-d-kserve.*"

    def test_check_ready_true(self):
        adapter = LLMInferenceServiceAdapter()
        status = {"conditions": [{"type": "Ready", "status": "True"}]}
        assert adapter.check_ready(status) is True

    def test_check_ready_false(self):
        adapter = LLMInferenceServiceAdapter()
        status = {"conditions": [{"type": "Ready", "status": "False"}]}
        assert adapter.check_ready(status) is False

    def test_check_ready_no_conditions(self):
        adapter = LLMInferenceServiceAdapter()
        assert adapter.check_ready({}) is False

    def test_resolve_model_name_from_spec_model_name_for_llmis(self):
        adapter = LLMInferenceServiceAdapter()
        spec = {"model": {"name": "qwen2-5-7b-instruct"}}
        assert adapter.resolve_model_name(spec, "small-llm-d") == "qwen2-5-7b-instruct"

    def test_resolve_model_name_falls_back_to_is_name_for_llmis(self):
        adapter = LLMInferenceServiceAdapter()
        spec = {"model": {"uri": "oci://registry.example.com/model:latest"}}
        assert adapter.resolve_model_name(spec, "small-llm-d") == "small-llm-d"

    def test_read_extra_args_returns_non_tuning_args(self):
        adapter = LLMInferenceServiceAdapter()
        result = adapter.read_extra_args(SAMPLE_LLMIS_SPEC)
        assert "--tensor-parallel-size=1" in result
        assert "--gpu-memory-utilization=0.80" not in result
        assert "--max-model-len=8192" not in result

    def test_read_extra_args_empty(self):
        adapter = LLMInferenceServiceAdapter()
        spec = {"template": {"containers": [{"name": "main", "env": [{"name": "VLLM_ADDITIONAL_ARGS", "value": ""}]}]}}
        assert adapter.read_extra_args(spec) == []

    def test_apply_args_to_cr_creates_main_container_when_missing(self):
        adapter = LLMInferenceServiceAdapter()
        cr_obj = {
            "apiVersion": "serving.kserve.io/v1alpha1",
            "kind": "LLMInferenceService",
            "metadata": {"name": "test-svc", "namespace": "test-ns"},
            "spec": {"template": {"containers": []}},
        }

        updated = adapter.apply_args_to_cr(cr_obj, {"max_num_seqs": "128"})
        main_container = next(c for c in updated["spec"]["template"]["containers"] if c["name"] == "main")
        assert any(env["name"] == "VLLM_ADDITIONAL_ARGS" for env in main_container["env"])

    def test_apply_args_to_cr_handles_env_as_none(self):
        adapter = LLMInferenceServiceAdapter()
        cr_obj = {
            "apiVersion": "serving.kserve.io/v1alpha1",
            "kind": "LLMInferenceService",
            "metadata": {"name": "test-svc", "namespace": "test-ns"},
            "spec": {"template": {"containers": [{"name": "main", "env": None}]}},
        }

        updated = adapter.apply_args_to_cr(cr_obj, {"max_num_seqs": "128"})
        main_container = next(c for c in updated["spec"]["template"]["containers"] if c["name"] == "main")
        assert any(env["name"] == "VLLM_ADDITIONAL_ARGS" for env in main_container["env"])


class TestFactory:
    def test_factory_inferenceservice(self):
        assert isinstance(get_cr_adapter("inferenceservice"), InferenceServiceAdapter)

    def test_factory_llminferenceservice(self):
        assert isinstance(get_cr_adapter("llminferenceservice"), LLMInferenceServiceAdapter)

    def test_factory_invalid(self):
        with pytest.raises(ValueError, match="Unknown VLLM_CR_TYPE"):
            get_cr_adapter("invalid")

    def test_factory_default_from_env(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("VLLM_CR_TYPE", "llminferenceservice")
        assert isinstance(get_cr_adapter(), LLMInferenceServiceAdapter)
