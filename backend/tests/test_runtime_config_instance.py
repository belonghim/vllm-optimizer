import pytest
import services.runtime_config_instance as rci
from services.runtime_config import RuntimeConfig


def test_runtime_config_is_instance_of_runtime_config():
    assert isinstance(rci.runtime_config, RuntimeConfig)


def test_runtime_config_is_singleton():
    import services.runtime_config_instance as rci2

    assert rci.runtime_config is rci2.runtime_config


def test_vllm_namespace_reads_env_var(monkeypatch):
    monkeypatch.setenv("VLLM_NAMESPACE", "my-test-ns")
    monkeypatch.delenv("K8S_NAMESPACE", raising=False)
    config = RuntimeConfig(None)
    assert config.vllm_namespace == "my-test-ns"


def test_vllm_namespace_falls_back_to_default(monkeypatch):
    monkeypatch.delenv("VLLM_NAMESPACE", raising=False)
    config = RuntimeConfig(None)
    assert config.vllm_namespace == "vllm-lab-dev"


def test_cr_type_defaults_to_inferenceservice(monkeypatch):
    monkeypatch.delenv("VLLM_CR_TYPE", raising=False)
    config = RuntimeConfig(None)
    assert config.cr_type == "inferenceservice"


def test_set_cr_type_raises_on_invalid_value():
    config = RuntimeConfig(None)
    with pytest.raises(ValueError, match="Invalid cr_type"):
        config.set_cr_type("bad-type")


def test_set_and_reset_cr_type_override(monkeypatch):
    monkeypatch.delenv("VLLM_CR_TYPE", raising=False)
    config = RuntimeConfig(None)
    config.set_cr_type("llminferenceservice")
    assert config.cr_type == "llminferenceservice"
    config.reset_cr_type()
    assert config.cr_type == "inferenceservice"
