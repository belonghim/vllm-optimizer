import os
import json
import time
import subprocess
from collections.abc import Iterator
from typing import cast

import pytest
import httpx

BACKEND_URL = os.getenv("PERF_TEST_BACKEND_URL", "http://vllm-optimizer-backend.vllm-optimizer-dev.svc.cluster.local:8000")
VLLM_NAMESPACE = os.getenv("VLLM_NAMESPACE", "vllm")
VLLM_ENDPOINT = os.getenv("VLLM_ENDPOINT", "http://llm-ov-predictor.vllm.svc.cluster.local:8080")
VLLM_MODEL = os.getenv("VLLM_MODEL", "Qwen2.5-Coder-3B-Instruct-int4-ov")
OPTIMIZER_NAMESPACE = os.getenv("OPTIMIZER_NAMESPACE", "vllm-optimizer-dev")


@pytest.fixture(scope="session")
def backend_url() -> str:
    return BACKEND_URL


@pytest.fixture(scope="session")
def http_client(backend_url: str) -> Iterator[httpx.Client]:
    with httpx.Client(base_url=backend_url, timeout=30) as client:
        yield client


@pytest.fixture(scope="session")
def async_http_client(backend_url: str) -> str:
    # async fixture가 아닌 이유: session scope에서 event loop 충돌 방지
    # 각 테스트 함수에서 async with httpx.AsyncClient() 사용 권장
    return backend_url


@pytest.fixture(scope="module", autouse=True)
def warm_up_vllm(http_client: httpx.Client) -> None:
    """vLLM이 cold start 상태일 수 있으므로 warm-up 요청 5회 전송."""
    for _ in range(5):
        try:
            resp = http_client.get("/health", timeout=120)
            if resp.status_code == 200:
                time.sleep(2)
                continue
        except Exception:
            pass
        time.sleep(5)
    # 최종 확인
    try:
        resp = http_client.get("/health")
        if resp.status_code != 200:
            pytest.fail(f"vLLM optimizer backend not ready after warm-up: {resp.status_code}")
    except Exception as e:
        pytest.fail(f"vLLM optimizer backend unreachable after warm-up: {e}")


@pytest.fixture(scope="function")
def backup_restore_vllm_config() -> Iterator[dict[str, object] | None]:
    """테스트 전 vLLM ConfigMap 백업, 테스트 후 복원."""
    backup: dict[str, object] | None = None
    try:
        result: subprocess.CompletedProcess[str] = subprocess.run(
            ["oc", "get", "configmap", "vllm-config", "-n", VLLM_NAMESPACE, "-o", "json"],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0:
            backup = cast(dict[str, object], json.loads(result.stdout))
    except Exception:
        pass

    yield backup

    if backup:
        try:
            _ = subprocess.run(
                ["oc", "apply", "-f", "-", "-n", VLLM_NAMESPACE],
                input=json.dumps(backup), capture_output=True, text=True, timeout=30
            )
        except Exception:
            pass


@pytest.fixture(scope="function")
def skip_if_overloaded(http_client: httpx.Client) -> None:
    """vLLM이 과부하 상태이면 최대 60초 대기 후 skip."""
    for attempt in range(24):  # 24 * 5s = 120s max wait
        try:
            resp = http_client.get("/api/metrics/latest")
            if resp.status_code == 200:
                data = cast(dict[str, object], resp.json())
                latency = data.get("latency_p99", 0)
                if isinstance(latency, (int, float)) and latency > 2000:
                    if attempt < 11:
                        time.sleep(5)
                        continue
                    else:
                        pytest.skip(f"vLLM overloaded after 60s wait: p99 latency > 2s ({latency:.0f}ms)")
        except Exception:
            pass
        break  # Not overloaded (or metrics unavailable) — proceed


@pytest.fixture(scope="session")
def performance_baseline() -> dict[str, object]:
    """baseline.dev.json 로드. 없으면 빈 dict 반환."""
    baseline_path = os.getenv(
        "PERF_BASELINE_FILE",
        os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "baseline.dev.json")
    )
    if os.path.exists(baseline_path):
        with open(baseline_path) as f:
            return cast(dict[str, object], json.load(f))
    return {}


@pytest.fixture(scope="session")
def vllm_endpoint() -> str:
    return VLLM_ENDPOINT


@pytest.fixture(scope="session")
def vllm_model() -> str:
    return VLLM_MODEL
