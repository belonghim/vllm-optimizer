# pyright: reportImportCycles=false
import abc
import copy
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
_SERVER_MANAGED_METADATA_FIELDS = {
    "resourceVersion",
    "uid",
    "creationTimestamp",
    "generation",
    "managedFields",
}
_SERVER_MANAGED_TOP_LEVEL_FIELDS = _SERVER_MANAGED_METADATA_FIELDS | {"status"}


def _split_space_args(value: str) -> list[str]:
    if not value:
        return []
    try:
        return shlex.split(value)
    except ValueError:
        return value.split()


def _extract_served_model_name(args: Any) -> str | None:
    parsed_args: list[str]
    if isinstance(args, str):
        parsed_args = _split_space_args(args)
    elif isinstance(args, list):
        parsed_args = [arg for arg in args if isinstance(arg, str)]
    else:
        return None

    last_name: str | None = None
    for i, arg in enumerate(parsed_args):
        if arg.startswith("--served-model-name="):
            val = arg.split("=", 1)[1].strip()
            if val:
                last_name = val
        elif arg == "--served-model-name" and i + 1 < len(parsed_args):
            val = parsed_args[i + 1].strip()
            if val and not val.startswith("--"):
                last_name = val
    return last_name


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


def _clean_cr_for_create(cr_obj: dict[str, Any]) -> dict[str, Any]:
    cleaned = copy.deepcopy(cr_obj)
    metadata = cleaned.get("metadata")
    if isinstance(metadata, dict):
        for key in _SERVER_MANAGED_METADATA_FIELDS:
            metadata.pop(key, None)

    for key in _SERVER_MANAGED_TOP_LEVEL_FIELDS:
        cleaned.pop(key, None)
    return cleaned


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge two dicts; override takes precedence."""
    result = dict(base)
    for k, v in override.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = deep_merge(result[k], v)
        else:
            result[k] = v
    return result


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
    def apply_args_to_cr(self, cr_obj: dict[str, Any], new_config: dict[str, Any]) -> dict[str, Any]:
        """Apply new_config args to full CR object. Returns clean CR body for create."""
        raise NotImplementedError

    @abc.abstractmethod
    def restore_cr_from_snapshot(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        """Return clean CR body from snapshot for restore/rollback."""
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
    def prometheus_job(self, name: str, namespace: str = "") -> str:
        raise NotImplementedError

    @abc.abstractmethod
    def dcgm_pod_pattern(self, name: str) -> str:
        raise NotImplementedError

    @abc.abstractmethod
    def metrics_port(self) -> int:
        raise NotImplementedError

    @abc.abstractmethod
    def metrics_scheme(self) -> str:
        raise NotImplementedError

    @abc.abstractmethod
    def metric_prefix(self) -> str:
        raise NotImplementedError

    @abc.abstractmethod
    def check_ready(self, status: dict[str, Any]) -> bool:
        raise NotImplementedError

    @abc.abstractmethod
    def read_extra_args(self, spec: dict[str, Any]) -> list[str]:
        raise NotImplementedError

    @abc.abstractmethod
    def resolve_model_name(self, spec: dict[str, Any], fallback_name: str) -> str:
        raise NotImplementedError

    @abc.abstractmethod
    def metric_extra_selector(self, name: str) -> str:
        """Additional Prometheus selector fragment to differentiate this CR's metrics.

        Returns an empty string if the job label alone identifies the instance
        (KServe), or a comma-prefixed fragment like ', pod=~"<pattern>"' when
        the job label is shared across instances in the same namespace (LLMIS).
        """
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

    def apply_args_to_cr(self, cr_obj: dict[str, Any], new_config: dict[str, Any]) -> dict[str, Any]:
        patch = self.build_args_patch(cr_obj.get("spec", {}), new_config)
        args = patch.get("spec", {}).get("predictor", {}).get("model", {}).get("args") or []

        spec = cr_obj.setdefault("spec", {})
        predictor = spec.setdefault("predictor", {})
        model = predictor.setdefault("model", {})
        model["args"] = args

        return _clean_cr_for_create(cr_obj)

    def restore_cr_from_snapshot(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        return _clean_cr_for_create(snapshot)

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

    def prometheus_job(self, name: str, namespace: str = "") -> str:
        return f"{name}-metrics"

    def metric_extra_selector(self, name: str) -> str:
        return ""

    def metrics_port(self) -> int:
        return 8080

    def metrics_scheme(self) -> str:
        return "http"

    def metric_prefix(self) -> str:
        return "vllm:"

    def dcgm_pod_pattern(self, name: str) -> str:
        return f"{name}-predictor.*"

    def check_ready(self, status: dict[str, Any]) -> bool:
        return _is_ready_condition(status)

    def read_extra_args(self, spec: dict[str, Any]) -> list[str]:
        args = spec.get("predictor", {}).get("model", {}).get("args") or []
        return [arg for arg in args if not arg.startswith(TUNING_ARG_PREFIXES)]

    def resolve_model_name(self, spec: dict[str, Any], fallback_name: str) -> str:
        args = spec.get("predictor", {}).get("model", {}).get("args") or []
        return _extract_served_model_name(args) or fallback_name


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

    def apply_args_to_cr(self, cr_obj: dict[str, Any], new_config: dict[str, Any]) -> dict[str, Any]:
        patch = self.build_args_patch(cr_obj.get("spec", {}), new_config)
        patched_env = patch.get("spec", {}).get("template", {}).get("containers", [{}])[0].get("env", [])
        new_value = ""
        for env in patched_env:
            if env.get("name") == self._ADDITIONAL_ARGS_ENV_NAME:
                new_value = env.get("value") or ""
                break

        spec = cr_obj.setdefault("spec", {})
        template = spec.setdefault("template", {})
        containers = template.setdefault("containers", [])

        main_container = None
        for container in containers:
            if container.get("name") == self._MAIN_CONTAINER_NAME:
                main_container = container
                break

        if main_container is None:
            main_container = {"name": self._MAIN_CONTAINER_NAME, "env": []}
            containers.append(main_container)

        env_list = main_container.get("env")
        if not isinstance(env_list, list):
            env_list = []
            main_container["env"] = env_list

        updated = False
        for env in env_list:
            if env.get("name") == self._ADDITIONAL_ARGS_ENV_NAME:
                env["value"] = new_value
                updated = True
                break
        if not updated:
            env_list.append({"name": self._ADDITIONAL_ARGS_ENV_NAME, "value": new_value})

        return _clean_cr_for_create(cr_obj)

    def restore_cr_from_snapshot(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        return _clean_cr_for_create(snapshot)

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
        return f"app.kubernetes.io/name={name},kserve.io/component=workload"

    def deployment_name(self, name: str) -> str:
        return f"{name}-kserve"

    def prometheus_job(self, name: str, namespace: str = "") -> str:
        # LLMIS job label includes namespace prefix: "{namespace}/kserve-llm-isvc-vllm-engine"
        prefix = f"{namespace}/" if namespace else ""
        return f"{prefix}kserve-llm-isvc-vllm-engine"

    def metric_extra_selector(self, name: str) -> str:
        return f', pod=~"{name}-kserve.*"'

    def metrics_port(self) -> int:
        return 8000

    def metrics_scheme(self) -> str:
        return "https"

    def metric_prefix(self) -> str:
        return "kserve_vllm:"

    def dcgm_pod_pattern(self, name: str) -> str:
        return f"{name}-kserve.*"

    def check_ready(self, status: dict[str, Any]) -> bool:
        return _is_ready_condition(status)

    def read_extra_args(self, spec: dict[str, Any]) -> list[str]:
        value = self._get_additional_args_value(spec)
        args = _split_space_args(value)
        return [arg for arg in args if not arg.startswith(TUNING_ARG_PREFIXES)]

    def resolve_model_name(self, spec: dict[str, Any], fallback_name: str) -> str:
        model_name = spec.get("model", {}).get("name")
        if isinstance(model_name, str) and model_name.strip():
            return model_name
        return fallback_name


def get_cr_adapter(cr_type: str | None = None) -> CRAdapter:
    if cr_type is None:
        from services.shared import runtime_config

        cr_type = runtime_config.cr_type
    resolved = cr_type
    if resolved == "inferenceservice":
        return InferenceServiceAdapter()
    if resolved == "llminferenceservice":
        return LLMInferenceServiceAdapter()
    raise ValueError(f"Unknown VLLM_CR_TYPE: {resolved!r}. Expected 'inferenceservice' or 'llminferenceservice'.")
