"""
Runtime configuration singleton for vLLM optimizer.

Manages runtime settings with environment variable defaults and in-memory overrides.
Use `from services.shared import runtime_config` to access the singleton instance.

NOTE: This module now delegates to MultiTargetCollector's first target (default target).
The actual values are stored in multi_target_collector._targets[0].
"""

import os


def _normalize_target_name(name: str, cr_type: str) -> str:
    if cr_type == "inferenceservice" and name.endswith("-predictor"):
        return name.removesuffix("-predictor")
    return name


class RuntimeConfig:
    """
    Singleton runtime configuration class.

    Delegates to MultiTargetCollector's first target (default target).
    Provides backward-compatible getter/setter interface.
    """

    def __init__(self, multi_target_collector=None) -> None:
        self._multi_target_collector = multi_target_collector
        default_cr_type = os.getenv("VLLM_CR_TYPE", "inferenceservice")
        raw_default_name = os.getenv("VLLM_DEPLOYMENT_NAME", "llm-ov-predictor")
        self._default_namespace: str = os.getenv("VLLM_NAMESPACE", os.getenv("K8S_NAMESPACE", "vllm-lab-dev"))
        self._default_endpoint: str = os.getenv(
            "VLLM_ENDPOINT",
            "http://llm-ov-predictor.vllm-lab-dev.svc.cluster.local:8080",
        )
        self._default_is_name: str = _normalize_target_name(raw_default_name, default_cr_type)
        self._cr_type_override: str | None = None

    def _get_default_target(self):
        if self._multi_target_collector is None:
            return None
        targets = list(self._multi_target_collector._targets.values())
        return next((t for t in targets if t.is_default), targets[0] if targets else None)

    @property
    def vllm_namespace(self) -> str:
        target = self._get_default_target()
        return target.namespace if target else self._default_namespace

    def set_vllm_namespace(self, value: str) -> None:
        self._default_namespace = value
        if self._multi_target_collector is not None and hasattr(self._multi_target_collector, "set_default_target"):
            self._multi_target_collector.set_default_target(namespace=value)
            return
        target = self._get_default_target()
        if target:
            target.namespace = value

    @property
    def vllm_endpoint(self) -> str:
        return self._default_endpoint

    def set_vllm_endpoint(self, value: str) -> None:
        self._default_endpoint = value

    @property
    def vllm_is_name(self) -> str:
        target = self._get_default_target()
        return target.is_name if target else self._default_is_name

    def set_vllm_is_name(self, value: str) -> None:
        self._default_is_name = value
        if self._multi_target_collector is not None and hasattr(self._multi_target_collector, "set_default_target"):
            self._multi_target_collector.set_default_target(is_name=value)
            return
        target = self._get_default_target()
        if target:
            target.is_name = value

    @property
    def cr_type(self) -> str:
        if self._cr_type_override is not None:
            return self._cr_type_override
        return os.getenv("VLLM_CR_TYPE", "inferenceservice")

    def set_cr_type(self, value: str) -> None:
        if value not in ("inferenceservice", "llminferenceservice"):
            raise ValueError(f"Invalid cr_type: {value}. Must be 'inferenceservice' or 'llminferenceservice'")
        self._cr_type_override = value

    def reset_cr_type(self) -> None:
        self._cr_type_override = None
