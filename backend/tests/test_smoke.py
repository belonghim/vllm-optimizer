"""Fast smoke tier: core feature contracts only.

Goal: verify that the main features (metrics, load test, benchmark, SLA,
tuner, targets) and dual-CR support still work end-to-end at the contract
level, with a minimal and fast suite.

Run:
    pytest backend/tests/test_smoke.py -q
or through the gate:
    ./scripts/check.sh --smoke

Full behavioral coverage lives in the regular test suite; this tier exists for
fast "did I break a core feature" feedback.
"""

from typing import Any

from fastapi.testclient import TestClient
from services.cr_adapter import get_cr_adapter


def _benchmark_payload() -> dict[str, Any]:
    return {
        "name": "smoke-benchmark",
        "config": {
            "endpoint": "http://localhost:8000",
            "model": "OpenVINO/Phi-4-mini-instruct-int4-ov",
            "prompt_template": "Hello",
            "total_requests": 1,
            "concurrency": 1,
            "rps": 0,
            "max_tokens": 16,
            "temperature": 0.0,
            "stream": False,
        },
        "result": {
            "elapsed": 0.1,
            "total": 1,
            "success": 1,
            "failed": 0,
            "rps_actual": 1.0,
            "latency": {"mean": 0.1, "p50": 0.1, "p95": 0.1, "p99": 0.1, "min": 0.1, "max": 0.1},
            "ttft": {"mean": 0.01, "p50": 0.01, "p95": 0.01, "p99": 0.01, "min": 0.01, "max": 0.01},
            "tps": {"mean": 10.0, "total": 10.0},
        },
    }


# --- HTTP feature contracts -------------------------------------------------


def test_health_contract(isolated_client: TestClient) -> None:
    response = isolated_client.get("/health")
    assert response.status_code == 200
    assert "cr_type" in response.json()


def test_config_contract(isolated_client: TestClient) -> None:
    response = isolated_client.get("/api/config")
    assert response.status_code == 200
    body = response.json()
    for key in ("vllm_endpoint", "vllm_model_name", "cr_type"):
        assert key in body, f"missing {key} in /api/config"


def test_metrics_latest_and_batch_contract(isolated_client: TestClient) -> None:
    targeted = isolated_client.get("/api/metrics/latest", params={"namespace": "smoke-ns", "is_name": "smoke-is"})
    assert targeted.status_code == 200
    assert targeted.json()["status"] in ("collecting", "ready")

    batch = isolated_client.post(
        "/api/metrics/batch",
        json={"targets": [{"namespace": "smoke-ns", "inferenceService": "smoke-is"}]},
    )
    assert batch.status_code == 200
    assert "smoke-ns/smoke-is/inferenceservice" in batch.json()["results"]


def test_load_test_status_contract(isolated_client: TestClient) -> None:
    response = isolated_client.get("/api/load_test/status")
    assert response.status_code == 200


def test_benchmark_save_list_delete_contract(isolated_client: TestClient) -> None:
    saved = isolated_client.post("/api/benchmark/save", json=_benchmark_payload())
    assert saved.status_code == 200, saved.text
    benchmark_id = saved.json()["id"]

    listed = isolated_client.get("/api/benchmark/list")
    assert listed.status_code == 200
    assert any(item["id"] == benchmark_id for item in listed.json())

    deleted = isolated_client.delete(f"/api/benchmark/{benchmark_id}")
    assert deleted.status_code in (200, 204)


def test_sla_profile_lifecycle_contract(isolated_client: TestClient) -> None:
    body = {
        "name": "smoke-profile",
        "thresholds": {
            "availability_min": 99.0,
            "p95_latency_max_ms": None,
            "error_rate_max_pct": None,
            "mean_e2e_latency_max_ms": None,
        },
    }
    created = isolated_client.post("/api/sla/profiles", json=body)
    assert created.status_code == 201, created.text
    profile_id = created.json()["id"]

    listed = isolated_client.get("/api/sla/profiles")
    assert listed.status_code == 200
    assert any(profile["id"] == profile_id for profile in listed.json())

    deleted = isolated_client.delete(f"/api/sla/profiles/{profile_id}")
    assert deleted.status_code in (200, 204)


def test_tuner_status_contract(isolated_client: TestClient) -> None:
    response = isolated_client.get("/api/tuner/status")
    assert response.status_code == 200
    assert "running" in response.json()


def test_targets_save_and_load_contract(isolated_client: TestClient) -> None:
    payload = {"targets": [{"namespace": "smoke-ns", "name": "smoke-is", "cr_type": "inferenceservice"}]}
    saved = isolated_client.post("/api/targets/save", json=payload)
    assert saved.status_code == 200, saved.text

    loaded = isolated_client.get("/api/targets/load")
    assert loaded.status_code == 200
    body = loaded.json()
    assert body["loaded"] is True
    assert body["targets"][0]["namespace"] == "smoke-ns"


# --- Dual-CR contract (no cluster required) ---------------------------------


def test_dual_cr_adapter_contract() -> None:
    isvc = get_cr_adapter("inferenceservice")
    llmis = get_cr_adapter("llminferenceservice")

    # Distinct API identities
    assert isvc.api_group() == "serving.kserve.io"
    assert (isvc.api_version(), isvc.api_plural()) == ("v1beta1", "inferenceservices")
    assert (llmis.api_version(), llmis.api_plural()) == ("v1alpha1", "llminferenceservices")

    # Distinct metrics contracts
    assert isvc.metric_prefix() == "vllm:"
    assert llmis.metric_prefix() == "kserve_vllm:"
    assert isvc.prometheus_job("m") != llmis.prometheus_job("m", "ns")
    assert isvc.default_endpoint("m", "ns") == "http://m-predictor.ns.svc.cluster.local"
    assert llmis.default_endpoint("m", "ns") == "https://m-kserve-workload-svc.ns.svc.cluster.local:8000"

    # KServe: args live in spec.predictor.model.args
    isvc_spec = {
        "predictor": {
            "model": {
                "args": ["--max-num-seqs=64", "--served-model-name=phi"],
                "resources": {"limits": {"nvidia.com/gpu": "1"}},
            }
        }
    }
    assert isvc.read_args(isvc_spec)["max_num_seqs"] == "64"
    assert isvc.resolve_model_name(isvc_spec, "fallback") == "phi"
    assert isvc.read_resources(isvc_spec)["limits"]["nvidia.com/gpu"] == "1"
    isvc_patch = isvc.build_args_patch(isvc_spec, {"gpu_memory_utilization": "0.8"})
    assert isvc_patch["spec"]["predictor"]["model"]["args"]
    assert isvc.deployment_name("phi") == "phi-predictor"

    # LLMIS: args live in spec.template.containers[main].env VLLM_ADDITIONAL_ARGS
    llmis_spec = {
        "model": {"name": "phi-x"},
        "template": {
            "containers": [
                {
                    "name": "main",
                    "env": [{"name": "VLLM_ADDITIONAL_ARGS", "value": "--max-num-seqs=32"}],
                }
            ]
        },
    }
    assert llmis.read_args(llmis_spec)["max_num_seqs"] == "32"
    assert llmis.resolve_model_name(llmis_spec, "fallback") == "phi-x"
    llmis_patch = llmis.build_args_patch(llmis_spec, {"gpu_memory_utilization": "0.7"})
    env = llmis_patch["spec"]["template"]["containers"][0]["env"][0]
    assert env["name"] == "VLLM_ADDITIONAL_ARGS"
    assert "--max-num-seqs=32" in env["value"]
    assert llmis.deployment_name("phi") == "phi-kserve"

    # Model analysis execs into the serving container that mounts /mnt/models
    assert isvc.model_container_name() == "kserve-container"
    assert llmis.model_container_name() == "main"


def test_tls_verify_off_unless_ca_bundle(monkeypatch) -> None:
    import ssl

    import certifi
    from services.tls import tls_verify

    monkeypatch.delenv("CA_BUNDLE", raising=False)
    assert tls_verify() is False
    assert tls_verify("") is False
    ctx = tls_verify(certifi.where())
    assert isinstance(ctx, ssl.SSLContext) and ctx.verify_mode == ssl.CERT_REQUIRED
