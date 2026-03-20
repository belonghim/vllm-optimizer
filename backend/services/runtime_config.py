"""
Runtime configuration singleton for vLLM optimizer.

Manages runtime settings with environment variable defaults and in-memory overrides.
Use `from services.shared import runtime_config` to access the singleton instance.
"""
import os


class RuntimeConfig:
    """
    Singleton runtime configuration class.

    Loads defaults from environment variables on initialization,
    supports in-memory overrides via setters.
    """

    def __init__(self) -> None:
        self._vllm_namespace: str = os.getenv("K8S_NAMESPACE", "vllm-lab-dev")
        self._vllm_endpoint: str = os.getenv(
            "VLLM_ENDPOINT", "http://llm-ov-predictor.vllm-lab-dev.svc.cluster.local:8080"
        )
        self._vllm_is_name: str = os.getenv("VLLM_DEPLOYMENT_NAME", "llm-ov")

    @property
    def vllm_namespace(self) -> str:
        return self._vllm_namespace

    def set_vllm_namespace(self, value: str) -> None:
        self._vllm_namespace = value

    @property
    def vllm_endpoint(self) -> str:
        return self._vllm_endpoint

    def set_vllm_endpoint(self, value: str) -> None:
        self._vllm_endpoint = value

    @property
    def vllm_is_name(self) -> str:
        return self._vllm_is_name

    def set_vllm_is_name(self, value: str) -> None:
        self._vllm_is_name = value
