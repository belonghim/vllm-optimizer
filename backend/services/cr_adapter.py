import abc
import os
import shlex
from typing import Any


_ARG_TO_KEY = {
    "--max-num-seqs": "max_num_seqs",
    "--gpu-memory-utilization": "gpu_memory_utilization",
    "--max-model-len": "max_model_len",
    "--max-num-batched-tokens": "max_num_batched_tokens",
    "--block-size": "block_size",
    "--swap-space": "swap_space",
    "--enable-chunked-prefill": "enable_chunked_prefill",
    "--enforce-eager": "enable_enforce_eager",
}
_KEY_TO_ARG = {v: k for k, v in _ARG_TO_KEY.items()}
TUNING_ARG_PREFIXES = tuple(_ARG_TO_KEY.keys())


def _split_space_args(value: str) -> list[str]:
    if not value:
        return []
    try:
        return shlex.split(value)
    except ValueError:
        return value.split()


def args_list_to_config_dict(args: list[str]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for arg in args:
        for cli_flag, config_key in _ARG_TO_KEY.items():
            if arg == cli_flag:
                result[config_key] = "true"
                break
            if arg.startswith(cli_flag + "="):
                result[config_key] = arg.split("=", 1)[1]
                break
    return result


def config_dict_to_args_list(config: dict[str, Any]) -> list[str]:
    result: list[str] = []
    for key, value in config.items():
        cli_flag = _KEY_TO_ARG.get(key)
        if cli_flag is None:
            continue

        if key in ("enable_chunked_prefill", "enable_enforce_eager"):
            if str(value).lower() in ("true", "1", "yes"):
                result.append(cli_flag)
            continue

        if value is not None and str(value):
            result.append(f"{cli_flag}={value}")
    return result


def space_str_to_config_dict(value: str) -> dict[str, Any]:
    return args_list_to_config_dict(_split_space_args(value))


def config_dict_to_space_str(config: dict[str, Any], static_prefix: str = "") -> str:
    static_parts = _split_space_args(static_prefix)
    tuning_parts = config_dict_to_args_list(config)
    return " ".join(static_parts + tuning_parts)


def _is_ready_condition(status: dict[str, Any]) -> bool:
    for condition in status.get("conditions", []) or []:
        if condition.get("type") == "Ready":
            return str(condition.get("status", "")).lower() == "true"
    return False


class CRAdapter(abc.ABC):
    @abc.abstractmethod
    def api_group(self) -> str:
        raise NotImplementedError

    @abc.abstractmethod
    def api_version(self) -> str:
        raise NotImplementedError

    @abc.abstractmethod
    def api_plural(self) -> str:
        raise NotImplementedError

    @abc.abstractmethod
    def read_args(self, spec: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    @abc.abstractmethod
    def build_args_patch(self, current_spec: dict[str, Any], new_config: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    @abc.abstractmethod
    def read_resources(self, spec: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    @abc.abstractmethod
    def build_resources_patch(self, resources: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    @abc.abstractmethod
    def read_model_uri(self, spec: dict[str, Any]) -> str | None:
        raise NotImplementedError

    @abc.abstractmethod
    def build_model_uri_patch(self, uri: str) -> dict[str, Any]:
        raise NotImplementedError

    @abc.abstractmethod
    def snapshot_args(self, spec: dict[str, Any]) -> Any:
        raise NotImplementedError

    @abc.abstractmethod
    def build_rollback_patch(self, snapshot: Any) -> dict[str, Any]:
        raise NotImplementedError

    @abc.abstractmethod
    def pod_label_selector(self, name: str) -> str:
        raise NotImplementedError

    @abc.abstractmethod
    def deployment_name(self, name: str) -> str:
        raise NotImplementedError

    @abc.abstractmethod
    def prometheus_job(self, name: str) -> str:
        raise NotImplementedError

    @abc.abstractmethod
    def dcgm_pod_pattern(self, name: str) -> str:
        raise NotImplementedError

    @abc.abstractmethod
    def check_ready(self, status: dict[str, Any]) -> bool:
        raise NotImplementedError


class InferenceServiceAdapter(CRAdapter):
    def api_group(self) -> str:
        return "serving.kserve.io"

    def api_version(self) -> str:
        return "v1beta1"

    def api_plural(self) -> str:
        return "inferenceservices"

    def read_args(self, spec: dict[str, Any]) -> dict[str, Any]:
        args = spec.get("predictor", {}).get("model", {}).get("args") or []
        return args_list_to_config_dict(args)

    def build_args_patch(self, current_spec: dict[str, Any], new_config: dict[str, Any]) -> dict[str, Any]:
        current_args = current_spec.get("predictor", {}).get("model", {}).get("args") or []
        static_args = [arg for arg in current_args if not arg.startswith(TUNING_ARG_PREFIXES)]

        current_config = args_list_to_config_dict(current_args)
        current_config.update(new_config)
        tuning_args = config_dict_to_args_list(current_config)

        return {"spec": {"predictor": {"model": {"args": static_args + tuning_args}}}}

    def read_resources(self, spec: dict[str, Any]) -> dict[str, Any]:
        return spec.get("predictor", {}).get("model", {}).get("resources") or {}

    def build_resources_patch(self, resources: dict[str, Any]) -> dict[str, Any]:
        return {"spec": {"predictor": {"model": {"resources": resources}}}}

    def read_model_uri(self, spec: dict[str, Any]) -> str | None:
        return spec.get("predictor", {}).get("model", {}).get("storageUri")

    def build_model_uri_patch(self, uri: str) -> dict[str, Any]:
        return {"spec": {"predictor": {"model": {"storageUri": uri}}}}

    def snapshot_args(self, spec: dict[str, Any]) -> Any:
        return list(spec.get("predictor", {}).get("model", {}).get("args") or [])

    def build_rollback_patch(self, snapshot: Any) -> dict[str, Any]:
        return {"spec": {"predictor": {"model": {"args": snapshot}}}}

    def pod_label_selector(self, name: str) -> str:
        return f"serving.kserve.io/inferenceservice={name}"

    def deployment_name(self, name: str) -> str:
        return f"{name}-predictor"

    def prometheus_job(self, name: str) -> str:
        return f"{name}-metrics"

    def dcgm_pod_pattern(self, name: str) -> str:
        return f"{name}-predictor.*"

    def check_ready(self, status: dict[str, Any]) -> bool:
        return _is_ready_condition(status)


class LLMInferenceServiceAdapter(CRAdapter):
    _MAIN_CONTAINER_NAME = "main"
    _ADDITIONAL_ARGS_ENV_NAME = "VLLM_ADDITIONAL_ARGS"

    def _find_main_container(self, spec: dict[str, Any]) -> dict[str, Any] | None:
        containers = spec.get("template", {}).get("containers") or []
        for container in containers:
            if container.get("name") == self._MAIN_CONTAINER_NAME:
                return container
        return None

    def _get_additional_args_value(self, spec: dict[str, Any]) -> str:
        container = self._find_main_container(spec)
        if not container:
            return ""

        for env in container.get("env") or []:
            if env.get("name") == self._ADDITIONAL_ARGS_ENV_NAME:
                return env.get("value") or ""
        return ""

    def api_group(self) -> str:
        return "serving.kserve.io"

    def api_version(self) -> str:
        return "v1alpha1"

    def api_plural(self) -> str:
        return "llminferenceservices"

    def read_args(self, spec: dict[str, Any]) -> dict[str, Any]:
        return space_str_to_config_dict(self._get_additional_args_value(spec))

    def build_args_patch(self, current_spec: dict[str, Any], new_config: dict[str, Any]) -> dict[str, Any]:
        current_value = self._get_additional_args_value(current_spec)
        current_parts = _split_space_args(current_value)
        static_parts = [arg for arg in current_parts if not arg.startswith(TUNING_ARG_PREFIXES)]

        current_config = space_str_to_config_dict(current_value)
        current_config.update(new_config)
        new_value = config_dict_to_space_str(current_config, static_prefix=" ".join(static_parts))

        return {
            "spec": {
                "template": {
                    "containers": [
                        {
                            "name": self._MAIN_CONTAINER_NAME,
                            "env": [{"name": self._ADDITIONAL_ARGS_ENV_NAME, "value": new_value}],
                        }
                    ]
                }
            }
        }

    def read_resources(self, spec: dict[str, Any]) -> dict[str, Any]:
        container = self._find_main_container(spec)
        if not container:
            return {}
        return container.get("resources") or {}

    def build_resources_patch(self, resources: dict[str, Any]) -> dict[str, Any]:
        return {
            "spec": {
                "template": {
                    "containers": [
                        {
                            "name": self._MAIN_CONTAINER_NAME,
                            "resources": resources,
                        }
                    ]
                }
            }
        }

    def read_model_uri(self, spec: dict[str, Any]) -> str | None:
        return spec.get("model", {}).get("uri")

    def build_model_uri_patch(self, uri: str) -> dict[str, Any]:
        return {"spec": {"model": {"uri": uri}}}

    def snapshot_args(self, spec: dict[str, Any]) -> Any:
        return self._get_additional_args_value(spec)

    def build_rollback_patch(self, snapshot: Any) -> dict[str, Any]:
        return {
            "spec": {
                "template": {
                    "containers": [
                        {
                            "name": self._MAIN_CONTAINER_NAME,
                            "env": [{"name": self._ADDITIONAL_ARGS_ENV_NAME, "value": snapshot}],
                        }
                    ]
                }
            }
        }

    def pod_label_selector(self, name: str) -> str:
        return f"app.kubernetes.io/name={name}"

    def deployment_name(self, name: str) -> str:
        return f"{name}-kserve"

    def prometheus_job(self, name: str) -> str:
        return f"{name}-kserve-workload-svc"

    def dcgm_pod_pattern(self, name: str) -> str:
        return f"{name}-kserve.*"

    def check_ready(self, status: dict[str, Any]) -> bool:
        return _is_ready_condition(status)


def get_cr_adapter(cr_type: str | None = None) -> CRAdapter:
    resolved = cr_type or os.getenv("VLLM_CR_TYPE", "inferenceservice")
    if resolved == "inferenceservice":
        return InferenceServiceAdapter()
    if resolved == "llminferenceservice":
        return LLMInferenceServiceAdapter()
    raise ValueError(f"Unknown VLLM_CR_TYPE: {resolved!r}. Expected 'inferenceservice' or 'llminferenceservice'.")
