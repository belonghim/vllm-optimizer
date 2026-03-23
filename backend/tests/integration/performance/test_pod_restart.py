"""
E2E 파드 재기동 검증 테스트

클러스터에서 실행:
    PERF_TEST_BACKEND_URL=http://localhost:8000 \
    VLLM_NAMESPACE=vllm \
    OPTIMIZER_NAMESPACE=vllm-optimizer-dev \
    python3 -m pytest backend/tests/integration/performance/test_pod_restart.py -v -m integration
"""
import os
import time

import httpx
import pytest

from .conftest import BACKEND_URL, VLLM_NAMESPACE

VLLM_POD_LABEL = os.getenv("VLLM_POD_LABEL", "app=isvc.llm-ov-predictor")
POD_RESTART_TIMEOUT = int(os.getenv("POD_RESTART_TIMEOUT", "300"))
POD_POLL_INTERVAL = 10


def _get_pod_uids(namespace: str, label: str) -> set[str]:
    """oc get pods로 현재 vLLM 파드 UID 목록 반환."""
    import subprocess

    result = subprocess.run(
        ["oc", "get", "pods", "-n", namespace, "-l", label,
         "-o", "jsonpath={.items[*].metadata.uid}"],
        capture_output=True, text=True, timeout=30
    )
    uids_str = result.stdout.strip()
    if not uids_str:
        return set()
    return set(uids_str.split())


def _wait_for_pod_restart(
    namespace: str, label: str, original_uids: set[str], timeout: int = 300
) -> bool:
    """파드 UID가 변경될 때까지 대기. 모든 original UID가 사라지면 성공."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        current_uids = _get_pod_uids(namespace, label)
        # 새 파드가 생겼고 기존 파드가 모두 사라졌으면 성공
        if current_uids and current_uids.isdisjoint(original_uids):
            return True
        time.sleep(POD_POLL_INTERVAL)
    return False


@pytest.mark.integration
def test_pod_restart_on_tuner_apply(
    http_client: httpx.Client,
    _backup_restore_is_args: None,
):
    """
    자동 파라미터 튜닝 1 trial 실행 후 vLLM 파드 UID 변경 검증.

    검증 순서:
    1. 현재 파드 UID 수집
    2. /api/tuner/start로 1 trial 튜닝 실행
    3. 파드 UID 변경 대기 (최대 300초)
    4. 기존 UID가 모두 사라지고 새 UID가 생겼는지 검증
    """
    assert str(http_client.base_url) == BACKEND_URL

    # 1. 현재 파드 UID 수집
    original_uids = _get_pod_uids(VLLM_NAMESPACE, VLLM_POD_LABEL)
    assert original_uids, f"No vLLM pods found with label {VLLM_POD_LABEL} in namespace {VLLM_NAMESPACE}"

    # 2. 1-trial 튜닝 시작
    config = {
        "n_trials": 1,
        "eval_requests": 10,
        "warmup_requests": 0,
        "objective": "tps",
    }
    vllm_endpoint = os.getenv("VLLM_ENDPOINT", "http://llm-ov-predictor.vllm.svc.cluster.local:8080")
    resp = http_client.post(
        "/api/tuner/start",
        json={**config, "vllm_endpoint": vllm_endpoint},
        timeout=30
    )
    assert resp.status_code == 200, f"Failed to start tuner: {resp.text}"
    assert resp.json().get("success"), f"Tuner start failed: {resp.json()}"

    # 3. 파드 UID 변경 대기
    restarted = _wait_for_pod_restart(
        VLLM_NAMESPACE, VLLM_POD_LABEL,
        original_uids, timeout=POD_RESTART_TIMEOUT
    )

    # 4. 튜너가 완료될 때까지 대기 (최대 120초)
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        status_resp = http_client.get("/api/tuner/status", timeout=10)
        if status_resp.status_code == 200 and not status_resp.json().get("running"):
            break
        time.sleep(5)

    # 5. 파드 재기동 검증
    assert restarted, (
        f"vLLM pod did not restart within {POD_RESTART_TIMEOUT}s. "
        f"Original UIDs: {original_uids}, "
        f"Current UIDs: {_get_pod_uids(VLLM_NAMESPACE, VLLM_POD_LABEL)}"
    )

    # 6. 새 파드 존재 확인
    new_uids = _get_pod_uids(VLLM_NAMESPACE, VLLM_POD_LABEL)
    assert new_uids, "No pods found after restart"
    assert new_uids.isdisjoint(original_uids), "Pod UIDs did not change (no restart happened)"


@pytest.mark.integration
def test_vllm_config_patch_via_api(
    http_client: httpx.Client,
    _backup_restore_is_args: None,
):
    """
    /api/vllm-config PATCH로 IS args 수정 후 값 확인.
    파드 재기동은 수행하지 않음 (IS args 수정만).
    """
    resp = http_client.get("/api/vllm-config", timeout=30)
    assert resp.status_code == 200, f"Failed to get vllm-config: {resp.text}"
    original_data = resp.json().get("data", {})
    original_seqs = original_data.get("max_num_seqs", "256")

    new_value = "128" if original_seqs != "128" else "256"
    patch_resp = http_client.patch(
        "/api/vllm-config",
        json={"data": {"max_num_seqs": new_value}},
        timeout=30
    )
    assert patch_resp.status_code == 200, f"PATCH failed: {patch_resp.text}"
    assert patch_resp.json().get("success")
    assert "max_num_seqs" in patch_resp.json().get("updated_keys", [])

    verify_resp = http_client.get("/api/vllm-config", timeout=30)
    assert verify_resp.status_code == 200
    assert verify_resp.json()["data"].get("max_num_seqs") == new_value
