# Plan: Enhanced Performance Integration Tests v2

**Created**: 2026-03-07
**Status**: Ready for execution
**Estimated Tasks**: 10
**Scope**: 성능 통합 테스트 인프라 구축 + 실제 클러스터 테스트 5개 시나리오
**Target**: OpenShift 4.x + vLLM 클러스터

---

## TL;DR

> 기존 39개 단위 테스트를 넘어 **실제 OpenShift + vLLM 클러스터**에서 성능을 검증하는 통합 테스트 5개 시나리오를 구현한다.
> 부하 테스트 처리량, 메트릭 수집 성능, AutoTuner 효과, SSE 스트리밍, 클러스터 건강성을 검증.
> LoadTestEngine과 AutoTuner에 최소 코드 변경을 추가하여 CPU/GPU 메트릭과 wait_metrics를 노출한다.

---

## Scope

### IN
- `backend/tests/integration/performance/` 테스트 디렉토리 + conftest
- pytest 마커 등록 (`integration`, `performance`, `slow`)
- 프로덕션 코드 변경: LoadTestEngine CPU/GPU 샘플링, AutoTuner wait_metrics, metrics timing
- 5개 테스트 시나리오 (Health, LoadTest, Metrics, AutoTuner, SSE)
- `scripts/run_performance_tests.sh` 실행 스크립트
- `openshift/tekton/performance-pipeline.yaml` (별도 파이프라인, soft-fail)
- `docs/integration_test_guide.md` 확장 (Performance Testing 섹션 추가)
- `baseline.dev.json` 기준값 저장

### OUT
- Dynamic Wait 시나리오 (제외 — 코드 변경 대비 가치 낮음)
- 프로덕션 환경 테스트 (dev 클러스터만)
- 고급 통계 분석 (median-of-3 이상)
- 멀티 모델 동시 테스트
- Grafana 대시보드 연동

---

## Pre-Wave: Conventions & Patterns

모든 Task에서 따를 규칙:

### pytest 규칙
- 마커: `@pytest.mark.integration`, `@pytest.mark.performance`, `@pytest.mark.slow`
- `pyproject.toml`에 `addopts = "--strict-markers"` 추가
- `asyncio_mode = "auto"` 유지

### 테스트 파일 위치
- 성능 테스트: `backend/tests/integration/performance/`
- conftest: `backend/tests/integration/__init__.py` + `performance/__init__.py` + `performance/conftest.py`

### Warm-up Fixture (conftest.py)
- `scope="module"`, `autouse=True`
- 5개 warm-up 요청 (`max_tokens=5`), 60초 타임아웃
- 실패 시 `pytest.fail()` (skip 아님)

### Safety Guardrails (conftest.py)
- 테스트 전: vLLM ConfigMap 백업
- 테스트 후: ConfigMap 복원 + backend 재시작
- vLLM 과부하 시 (p99 > 2s): skip

### SSE 파싱 패턴
```python
buffer = ""
async for chunk in response.aiter_text():
    buffer += chunk
    while "\n\n" in buffer:
        event, buffer = buffer.split("\n\n", 1)
        for line in event.split("\n"):
            if line.startswith("data: "):
                data = json.loads(line[6:])
```

### Tekton Soft-Fail 패턴
```yaml
pytest ... -m performance || true
jq -e '.summary.failed > 0' results.json && STATUS="FAIL" || STATUS="PASS"
echo -n "$STATUS" > $(results.performance-test-status.path)
```

---

## Wave 1 — Infrastructure (No Dependencies)

### Task 1: 테스트 디렉토리 + conftest + pytest 설정

**Category**: `deep`
**Skills**: `[]`
**Files**:
- `backend/tests/integration/__init__.py` (빈 파일)
- `backend/tests/integration/performance/__init__.py` (빈 파일)
- `backend/tests/integration/performance/conftest.py`
- `pyproject.toml` (마커 등록)
**Depends**: None

#### What to do

**1. pyproject.toml 수정**

기존 `[tool.pytest.ini_options]` 섹션에 추가:
```toml
[tool.pytest.ini_options]
pythonpath = ["backend"]
asyncio_mode = "auto"
addopts = "--strict-markers"
markers = [
    "integration: Integration tests requiring OpenShift cluster",
    "performance: Performance measurement tests",
    "slow: Tests that take >30 seconds",
]
```

먼저 기존 테스트에서 미등록 마커 경고가 없는지 확인:
```bash
python3 -m pytest backend/tests/ --co -q 2>&1 | grep -i "warning\|PytestUnknownMarkWarning"
```
경고가 있으면 해당 마커도 등록에 포함.

**2. 디렉토리 + __init__.py 생성**

```
backend/tests/integration/__init__.py          # 빈 파일
backend/tests/integration/performance/__init__.py  # 빈 파일
```

**3. conftest.py 생성**

`backend/tests/integration/performance/conftest.py`:

```python
import os
import json
import time
import subprocess
import pytest
import httpx

BACKEND_URL = os.getenv("PERF_TEST_BACKEND_URL", "http://vllm-optimizer-backend.vllm-optimizer-dev.svc.cluster.local:8000")
VLLM_NAMESPACE = os.getenv("VLLM_NAMESPACE", "vllm")
OPTIMIZER_NAMESPACE = os.getenv("OPTIMIZER_NAMESPACE", "vllm-optimizer-dev")


@pytest.fixture(scope="session")
def backend_url():
    return BACKEND_URL


@pytest.fixture(scope="session")
def http_client(backend_url):
    with httpx.Client(base_url=backend_url, timeout=30) as client:
        yield client


@pytest.fixture(scope="session")
def async_http_client(backend_url):
    # async fixture 가 아닌 이유: session scope 에서 event loop 충돌 방지
    # 각 테스트 함수에서 async with httpx.AsyncClient() 사용 권장
    return backend_url


@pytest.fixture(scope="module", autouse=True)
def warm_up_vllm(http_client):
    """vLLM이 cold start 상태일 수 있으므로 warm-up 요청 5회 전송."""
    for i in range(5):
        try:
            resp = http_client.get("/health", timeout=60)
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
def backup_restore_vllm_config():
    """테스트 전 vLLM ConfigMap 백업, 테스트 후 복원."""
    backup = None
    try:
        result = subprocess.run(
            ["oc", "get", "configmap", "vllm-config", "-n", VLLM_NAMESPACE, "-o", "json"],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0:
            backup = json.loads(result.stdout)
    except Exception:
        pass

    yield backup

    if backup:
        try:
            subprocess.run(
                ["oc", "apply", "-f", "-", "-n", VLLM_NAMESPACE],
                input=json.dumps(backup), capture_output=True, text=True, timeout=30
            )
        except Exception:
            pass


@pytest.fixture(scope="function")
def skip_if_overloaded(http_client):
    """vLLM이 과부하 상태이면 테스트 skip."""
    try:
        resp = http_client.get("/api/metrics/latest")
        if resp.status_code == 200:
            data = resp.json()
            if data.get("latency_p99", 0) > 2000:
                pytest.skip("vLLM overloaded: p99 latency > 2s")
    except Exception:
        pass


@pytest.fixture(scope="session")
def performance_baseline():
    """baseline.dev.json 로드. 없으면 빈 dict 반환."""
    baseline_path = os.getenv(
        "PERF_BASELINE_FILE",
        os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "baseline.dev.json")
    )
    if os.path.exists(baseline_path):
        with open(baseline_path) as f:
            return json.load(f)
    return {}
```

#### QA

```bash
# __init__.py와 conftest.py 생성 확인
ls backend/tests/integration/performance/

# pyproject.toml 파싱 확인
python3 -m pytest backend/tests/ --co -q 2>&1 | head -5

# 기존 테스트 회귀 없음
python3 -m pytest backend/tests/ -v --tb=short -m "not integration"
# 예상: 39 passed
```

---

### Task 2: baseline 유틸리티 + baseline.dev.json

**Category**: `quick`
**Skills**: `[]`
**Files**:
- `backend/tests/integration/performance/utils/__init__.py`
- `backend/tests/integration/performance/utils/baseline.py`
- `baseline.dev.json`
**Depends**: Task 1

#### What to do

**1. baseline.py** — 비교 로직:

```python
import json
import os
from typing import Any


def load_baseline(env: str = "dev") -> dict[str, Any]:
    path = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "..", f"baseline.{env}.json")
    if not os.path.exists(path):
        return {}
    with open(path) as f:
        return json.load(f)


def save_baseline(env: str, metrics: dict[str, Any]) -> None:
    path = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "..", f"baseline.{env}.json")
    bak = path + ".bak"
    if os.path.exists(path):
        os.rename(path, bak)
    with open(path, "w") as f:
        json.dump(metrics, f, indent=2)


def compare_metrics(baseline: dict[str, Any], current: dict[str, Any]) -> dict[str, dict]:
    result = {}
    for key in baseline:
        if key in current and isinstance(baseline[key], (int, float)) and isinstance(current[key], (int, float)):
            base_val = baseline[key]
            curr_val = current[key]
            if base_val != 0:
                pct_change = ((curr_val - base_val) / abs(base_val)) * 100
            else:
                pct_change = 0.0
            result[key] = {
                "baseline": base_val,
                "current": curr_val,
                "pct_change": round(pct_change, 2),
            }
    return result
```

**2. baseline.dev.json** (프로젝트 루트):

```json
{
  "throughput_rps": 0,
  "avg_latency_ms": 0,
  "p95_latency_ms": 0,
  "tokens_per_sec": 0,
  "gpu_utilization_avg": 0,
  "metrics_collection_duration_seconds": 0,
  "_note": "Initial placeholder. Run scripts/collect_baseline.sh to populate with real data."
}
```

#### QA

```bash
python3 -c "from backend.tests.integration.performance.utils.baseline import load_baseline, compare_metrics; print('OK')"
```

---

## Wave 2 — Production Code Enhancements (Depends: Wave 1 pytest config)

### Task 3: LoadTestEngine에 CPU/GPU 메트릭 샘플링 추가

**Category**: `deep`
**Skills**: `[]`
**Files**:
- `backend/services/load_engine.py`
- `backend/models/load_test.py`
**Depends**: None (Wave 1과 병렬 가능)

#### What to do

**1. `models/load_test.py` — `LoadTestResult`에 필드 추가:**

```python
class LoadTestResult(BaseModel):
    elapsed: float
    total: int
    success: int
    failed: int
    rps_actual: float
    latency: LatencyStats
    ttft: LatencyStats
    tps: TpsStats
    # 새로 추가
    backend_cpu_avg: float = 0.0
    gpu_utilization_avg: float = 0.0
    tokens_per_sec: float = 0.0
```

**2. `services/load_engine.py` — `run()` 메서드에 샘플링 추가:**

- `run()` 시작 시 백그라운드 샘플링 태스크 시작
- 30초 간격으로 `psutil.Process(os.getpid()).cpu_percent()` 호출 → 평균 계산
- 30초 간격으로 내부 `httpx.AsyncClient`로 `/api/metrics/latest` 호출 → `gpu_util` 수집 → 평균
- `run()` 종료 시 샘플링 태스크 취소, 결과를 final_stats에 포함

구현 패턴:
```python
import psutil
import asyncio

async def _sample_metrics(self, samples: list, stop_event: asyncio.Event):
    proc = psutil.Process(os.getpid())
    while not stop_event.is_set():
        cpu = proc.cpu_percent()
        gpu = 0.0
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get("http://localhost:8000/api/metrics/latest")
                if resp.status_code == 200:
                    gpu = resp.json().get("gpu_util", 0.0)
        except Exception:
            pass
        samples.append({"cpu": cpu, "gpu": gpu})
        await asyncio.sleep(30)
```

- `final_stats["backend_cpu_avg"]` = CPU 샘플 평균
- `final_stats["gpu_utilization_avg"]` = GPU 샘플 평균
- `final_stats["tokens_per_sec"]` = `final_stats["tps"]["mean"]` (이미 계산됨, 명시적 복사)

**3. `requirements.txt` 에 `psutil` 추가 (없으면)**

#### ⚠️ 주의사항
- `psutil`이 이미 설치되어 있는지 먼저 확인
- `/api/metrics/latest` 호출 시 localhost 사용 (동일 Pod 내)
- 샘플링 태스크는 반드시 `stop_event`로 정리 (메모리 누수 방지)
- 기존 `run()` 반환 형태(dict)를 유지하고 필드만 추가

#### QA

```bash
python3 -m pytest backend/tests/test_load_test.py -v --tb=short
# 예상: 기존 테스트 모두 통과 (새 필드는 기본값 0.0)
```

---

### Task 4: AutoTuner에 wait_metrics 노출

**Category**: `deep`
**Skills**: `[]`
**Files**:
- `backend/services/auto_tuner.py`
- `backend/routers/tuner.py`
**Depends**: None (Wave 1과 병렬 가능)

#### What to do

**1. `services/auto_tuner.py` — wait 추적 추가:**

AutoTuner의 trial 루프에서 vLLM readiness를 기다리는 부분에 타이밍 추가:

```python
# AutoTuner 클래스에 인스턴스 변수 추가:
self._wait_durations: list[float] = []
self._total_wait_seconds: float = 0.0
self._poll_count: int = 0
```

기존 `asyncio.sleep()` 또는 readiness check 루프에서:
```python
wait_start = time.time()
# ... 기존 대기 로직 ...
wait_duration = time.time() - wait_start
self._wait_durations.append(wait_duration)
self._total_wait_seconds += wait_duration
self._poll_count += 1
```

Property 추가:
```python
@property
def wait_metrics(self) -> dict:
    return {
        "total_wait_seconds": round(self._total_wait_seconds, 2),
        "poll_count": self._poll_count,
        "per_trial_waits": [round(d, 2) for d in self._wait_durations],
    }
```

**2. `routers/tuner.py` — `/api/tuner/status` 응답에 wait_metrics 포함:**

기존 TunerStatusResponse에 필드 추가:
```python
class TunerStatusResponse(BaseModel):
    status: str
    current_trial: int | None = None
    total_trials: int | None = None
    best_metric: float | None = None
    elapsed_seconds: float | None = None
    message: str | None = None
    wait_metrics: dict | None = None  # 새로 추가
```

status 엔드포인트에서:
```python
wait_metrics=tuner.wait_metrics if hasattr(tuner, 'wait_metrics') else None
```

#### QA

```bash
python3 -m pytest backend/tests/test_tuner.py -v --tb=short
# 예상: 기존 테스트 모두 통과
```

---

### Task 5: Metrics Collection Timing 추가

**Category**: `quick`
**Skills**: `[]`
**Files**:
- `backend/services/metrics_collector.py`
- `backend/metrics/prometheus_metrics.py`
**Depends**: None (Wave 1과 병렬 가능)

#### What to do

**1. `metrics/prometheus_metrics.py` — 히스토그램 메트릭 추가:**

```python
metrics_collection_duration_metric = Histogram(
    'vllm_optimizer:metrics_collection_duration_seconds',
    'Time spent collecting metrics from Prometheus/K8s',
    registry=_registry
)
```

**2. `services/metrics_collector.py` — `_collect()` 에 타이밍:**

```python
import time

async def _collect(self) -> VLLMMetrics:
    start = time.monotonic()
    # ... 기존 수집 로직 ...
    duration = time.monotonic() - start
    self._last_collection_duration = duration
    try:
        from metrics.prometheus_metrics import metrics_collection_duration_metric
        metrics_collection_duration_metric.observe(duration)
    except Exception:
        pass
    return metrics
```

`MetricsCollector` 클래스에 속성 추가:
```python
self._last_collection_duration: float = 0.0

@property
def last_collection_duration(self) -> float:
    return self._last_collection_duration
```

#### QA

```bash
python3 -m pytest backend/tests/test_metrics_collector.py backend/tests/test_prometheus_metrics.py -v --tb=short
# 예상: 기존 테스트 통과
```

---

## Wave 3 — Test Scenarios (Depends: Wave 1 conftest + Wave 2 code changes)

### Task 6: 5개 테스트 시나리오 구현

**Category**: `deep`
**Skills**: `[]`
**Files**:
- `backend/tests/integration/performance/test_cluster_health.py`
- `backend/tests/integration/performance/test_load_test_throughput.py`
- `backend/tests/integration/performance/test_metrics_collection.py`
- `backend/tests/integration/performance/test_auto_tuner.py`
- `backend/tests/integration/performance/test_sse_streaming.py`
**Depends**: Tasks 1, 3, 4, 5

#### What to do

**모든 테스트에 공통 마커:**
```python
import pytest
pytestmark = [pytest.mark.integration, pytest.mark.performance]
```

---

**6a. `test_cluster_health.py` — 클러스터 건강성 검증**

```python
@pytest.mark.integration
@pytest.mark.performance
class TestClusterHealth:

    def test_backend_health_deep(self, http_client):
        """GET /health?deep=1 → Prometheus + K8s 연결 확인."""
        start = time.time()
        resp = http_client.get("/health", params={"deep": "1"}, timeout=10)
        elapsed = time.time() - start
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert elapsed < 5.0, f"Health check too slow: {elapsed:.1f}s"

    def test_metrics_endpoint_accessible(self, http_client):
        """GET /api/metrics/latest → MetricsSnapshot 반환."""
        resp = http_client.get("/api/metrics/latest")
        assert resp.status_code == 200
        data = resp.json()
        assert "timestamp" in data
        assert "tps" in data
        assert "gpu_util" in data

    def test_prometheus_metrics_plaintext(self, http_client):
        """GET /api/metrics → Prometheus 포맷 반환."""
        resp = http_client.get("/api/metrics")
        assert resp.status_code == 200
        assert "text/plain" in resp.headers.get("content-type", "")
```

---

**6b. `test_load_test_throughput.py` — 부하 테스트 처리량 검증**

```python
@pytest.mark.integration
@pytest.mark.performance
@pytest.mark.slow
class TestLoadTestThroughput:

    def test_load_test_completes_successfully(self, http_client, skip_if_overloaded):
        """실제 vLLM 대상 부하 테스트 실행 및 결과 검증."""
        config = {
            "endpoint": os.getenv("VLLM_ENDPOINT", "http://vllm.vllm.svc.cluster.local:8000/v1/completions"),
            "model": os.getenv("VLLM_MODEL", "default"),
            "prompt_template": "Hello, how are you?",
            "total_requests": 20,
            "concurrency": 4,
            "rps": 2,
            "max_tokens": 50,
            "temperature": 0.7,
            "stream": False,
        }

        # 부하 테스트 시작
        resp = http_client.post("/api/load_test/start", json=config, timeout=10)
        assert resp.status_code == 200
        data = resp.json()
        test_id = data.get("test_id")
        assert test_id

        # 완료 대기 (최대 120초)
        for _ in range(24):
            time.sleep(5)
            status_resp = http_client.get("/api/load_test/status")
            if status_resp.status_code == 200:
                status = status_resp.json()
                if not status.get("running", True):
                    break
        else:
            pytest.fail("Load test did not complete within 120 seconds")

        # 결과 검증
        history_resp = http_client.get("/api/load_test/history")
        assert history_resp.status_code == 200
        history = history_resp.json()
        assert len(history) > 0

        latest = history[-1]
        result = latest.get("result", {})
        assert result.get("total", 0) > 0
        assert result.get("success", 0) > 0
        assert result.get("rps_actual", 0) > 0
        assert result["latency"]["mean"] > 0
        assert result["latency"]["p95"] > 0
```

---

**6c. `test_metrics_collection.py` — 메트릭 수집 성능 측정**

```python
@pytest.mark.integration
@pytest.mark.performance
class TestMetricsCollection:

    def test_metrics_response_time(self, http_client):
        """GET /api/metrics/latest 응답 시간 측정 (5회 median)."""
        times = []
        for _ in range(5):
            start = time.time()
            resp = http_client.get("/api/metrics/latest")
            elapsed = time.time() - start
            assert resp.status_code == 200
            times.append(elapsed)
            time.sleep(1)

        median_time = sorted(times)[len(times) // 2]
        assert median_time < 5.0, f"Median metrics response time too slow: {median_time:.2f}s"

    def test_prometheus_scrape_format_valid(self, http_client):
        """Prometheus 포맷 출력이 파싱 가능한지 확인."""
        resp = http_client.get("/api/metrics")
        assert resp.status_code == 200
        text = resp.text
        # 최소한 HELP + TYPE 라인이 있어야 함
        assert "# HELP" in text
        assert "# TYPE" in text
```

---

**6d. `test_auto_tuner.py` — AutoTuner 효과 검증**

```python
@pytest.mark.integration
@pytest.mark.performance
@pytest.mark.slow
class TestAutoTuner:

    def test_auto_tuner_completes_with_results(self, http_client, backup_restore_vllm_config, skip_if_overloaded):
        """AutoTuner 2 trial 실행 후 best_metric > 0 확인."""
        start_resp = http_client.post("/api/tuner/start", json={
            "n_trials": 2,
            "eval_requests": 10,
            "objective": "throughput",
        }, timeout=10)
        assert start_resp.status_code == 200

        # 완료 대기 (최대 300초 — trial당 ~120초)
        for _ in range(60):
            time.sleep(5)
            status_resp = http_client.get("/api/tuner/status")
            if status_resp.status_code == 200:
                status = status_resp.json()
                if status.get("status") != "running":
                    break
        else:
            pytest.fail("AutoTuner did not complete within 300 seconds")

        # 결과 검증
        assert status.get("best_metric") is not None
        assert status["best_metric"] > 0

        # trials 확인
        trials_resp = http_client.get("/api/tuner/trials")
        assert trials_resp.status_code == 200
        trials = trials_resp.json()
        assert len(trials) >= 2

        # wait_metrics 확인 (Task 4에서 추가)
        if "wait_metrics" in status:
            wm = status["wait_metrics"]
            assert wm["total_wait_seconds"] >= 0
            assert wm["poll_count"] >= 0
```

---

**6e. `test_sse_streaming.py` — SSE 이벤트 스트리밍 검증**

```python
import asyncio
import json
import httpx
import pytest

@pytest.mark.integration
@pytest.mark.performance
class TestSSEStreaming:

    @pytest.mark.asyncio
    async def test_load_test_sse_events(self, async_http_client, skip_if_overloaded):
        """부하 테스트 중 SSE 이벤트가 정상적으로 수신되는지 확인."""
        base_url = async_http_client  # conftest에서 URL string 반환

        async with httpx.AsyncClient(base_url=base_url, timeout=60) as client:
            # 짧은 부하 테스트 시작
            config = {
                "endpoint": os.getenv("VLLM_ENDPOINT", "http://vllm.vllm.svc.cluster.local:8000/v1/completions"),
                "model": "default",
                "prompt_template": "Test prompt",
                "total_requests": 10,
                "concurrency": 2,
                "rps": 1,
                "max_tokens": 20,
                "temperature": 0.7,
                "stream": False,
            }
            resp = await client.post("/api/load_test/start", json=config)
            assert resp.status_code == 200

            # SSE 스트림 연결 + 이벤트 수집
            events = []
            buffer = ""
            try:
                async with client.stream("GET", "/api/load_test/stream", timeout=60) as stream:
                    async for chunk in stream.aiter_text():
                        buffer += chunk
                        while "\n\n" in buffer:
                            event_str, buffer = buffer.split("\n\n", 1)
                            for line in event_str.split("\n"):
                                if line.startswith("data: "):
                                    try:
                                        data = json.loads(line[6:])
                                        events.append(data)
                                    except json.JSONDecodeError:
                                        pass
                            if len(events) >= 3:
                                break
                    # 3개 이벤트 수집되면 중단
            except (httpx.ReadTimeout, httpx.RemoteProtocolError):
                pass

            assert len(events) >= 1, f"Expected at least 1 SSE event, got {len(events)}"
            # 이벤트에 기본 필드 존재 확인
            for event in events:
                assert isinstance(event, dict)
```

#### ⚠️ 주의사항
- 모든 테스트는 `@pytest.mark.integration` + `@pytest.mark.performance` 필수
- `test_load_test_throughput.py`와 `test_auto_tuner.py`는 `@pytest.mark.slow` 추가
- vLLM 엔드포인트, 모델명은 환경변수로 설정 가능해야 함
- SSE 파싱은 반드시 double-newline 버퍼 방식 사용 (Pre-Wave 참조)
- `test_auto_tuner.py`는 `backup_restore_vllm_config` fixture 사용 필수

#### QA

```bash
# 테스트 파일 수집 확인 (클러스터 없이)
python3 -m pytest backend/tests/integration/performance/ --co -q
# 예상: 7-8 tests collected

# 클러스터 접속 시 실제 실행
python3 -m pytest backend/tests/integration/performance/ -v --tb=short -m "integration and performance"
```

---

## Wave 4 — Orchestration & Documentation (Depends: Wave 3 tests)

### Task 7: 실행 스크립트 생성

**Category**: `quick`
**Skills**: `[]`
**Files**:
- `scripts/run_performance_tests.sh`
- `scripts/collect_baseline.sh`
**Depends**: Task 6

#### What to do

**1. `scripts/run_performance_tests.sh`:**

```bash
#!/bin/bash
set -euo pipefail

ENV="${1:-dev}"
REPORT_DIR="reports/$(date +%Y-%m-%dT%H-%M-%S)"
mkdir -p "$REPORT_DIR"

echo "=== Performance Tests: env=$ENV ==="

export PERF_TEST_BACKEND_URL="${PERF_TEST_BACKEND_URL:-http://vllm-optimizer-backend.vllm-optimizer-${ENV}.svc.cluster.local:8000}"
export PERF_BASELINE_FILE="baseline.${ENV}.json"

python3 -m pytest backend/tests/integration/performance/ \
    -v --tb=short \
    -m "integration and performance" \
    --junitxml="$REPORT_DIR/results.xml" \
    2>&1 | tee "$REPORT_DIR/output.log"

echo "=== Results saved to $REPORT_DIR ==="
```

**2. `scripts/collect_baseline.sh`:**

```bash
#!/bin/bash
set -euo pipefail

ENV="${1:-dev}"
BACKEND_URL="${PERF_TEST_BACKEND_URL:-http://vllm-optimizer-backend.vllm-optimizer-${ENV}.svc.cluster.local:8000}"

echo "Collecting baseline from $BACKEND_URL..."

# 메트릭 스냅샷 수집
METRICS=$(curl -s "$BACKEND_URL/api/metrics/latest")

# baseline 파일 생성
python3 -c "
import json, sys
m = json.loads('$METRICS')
baseline = {
    'throughput_rps': m.get('rps', 0),
    'avg_latency_ms': m.get('latency_mean', 0),
    'p95_latency_ms': m.get('latency_p99', 0),
    'tokens_per_sec': m.get('tps', 0),
    'gpu_utilization_avg': m.get('gpu_util', 0),
    'metrics_collection_duration_seconds': 0,
}
with open(f'baseline.${ENV}.json', 'w') as f:
    json.dump(baseline, f, indent=2)
print(f'Baseline saved to baseline.${ENV}.json')
"
```

두 파일 모두 `chmod +x` 필요.

#### QA

```bash
bash -n scripts/run_performance_tests.sh
bash -n scripts/collect_baseline.sh
```

---

### Task 8: Tekton 성능 파이프라인 생성

**Category**: `deep`
**Skills**: `[]`
**Files**:
- `openshift/tekton/performance-pipeline.yaml`
**Depends**: Task 7

#### What to do

별도 Tekton Pipeline `vllm-optimizer-performance-pipeline` 생성.

핵심 구조:
```yaml
apiVersion: tekton.dev/v1beta1
kind: Pipeline
metadata:
  name: vllm-optimizer-performance-pipeline
  namespace: vllm-optimizer-dev
spec:
  params:
    - name: ENVIRONMENT
      default: dev
    - name: BACKEND_URL
      default: "http://vllm-optimizer-backend.vllm-optimizer-dev.svc.cluster.local:8000"
  tasks:
    - name: check-prerequisites
      # oc get pods -n vllm → vLLM ready 확인
    - name: backup-config
      # oc get configmap vllm-config -n vllm -o json > backup.json
    - name: run-performance-tests
      # pytest ... || true (soft-fail)
      # jq로 결과 파싱 → Tekton result에 PASS/FAIL 기록
    - name: restore-config
      runAfter: [run-performance-tests]
      # oc apply -f backup.json
```

- 메인 CI 파이프라인(`pipeline.yaml`)과 **완전히 분리**
- 수동 실행: `tkn pipeline start vllm-optimizer-performance-pipeline -n vllm-optimizer-dev`
- soft-fail: `pytest ... || true` → 배포 차단하지 않음
- `pytest-json-report` 결과를 Tekton TaskResult에 기록

#### ⚠️ 주의사항
- OpenShift Route 사용 (Ingress 금지)
- 컨테이너 이미지는 UBI9 기반
- non-root 실행
- `psutil`, `httpx`, `pytest`, `pytest-json-report` 설치 필요

#### QA

```bash
oc apply --dry-run=client -f openshift/tekton/performance-pipeline.yaml
```

---

### Task 9: docs/integration_test_guide.md 확장

**Category**: `writing`
**Skills**: `[]`
**Files**:
- `docs/integration_test_guide.md` (기존 파일에 섹션 추가)
**Depends**: Task 7

#### What to do

기존 `docs/integration_test_guide.md` 파일 끝에 "Performance Testing" 섹션 추가:

```markdown
## Performance Testing

### 개요

성능 통합 테스트는 실제 OpenShift + vLLM 클러스터에서 5개 시나리오를 검증합니다:
1. 클러스터 건강성 (Health + Connectivity)
2. 부하 테스트 처리량 (LoadTest Throughput)
3. 메트릭 수집 성능 (Metrics Collection)
4. AutoTuner 효과 (Tuning Effectiveness)
5. SSE 스트리밍 (Real-time Events)

### 실행 방법

```bash
# 전체 실행
./scripts/run_performance_tests.sh dev

# 특정 시나리오만
python3 -m pytest backend/tests/integration/performance/test_cluster_health.py -v

# slow 테스트 제외
python3 -m pytest backend/tests/integration/performance/ -v -m "not slow"
```

### 환경변수

| 변수 | 설명 | 기본값 |
|------|------|--------|
| `PERF_TEST_BACKEND_URL` | Backend URL | `http://...svc.cluster.local:8000` |
| `VLLM_ENDPOINT` | vLLM completions endpoint | `http://vllm.vllm.svc:8000/v1/completions` |
| `VLLM_MODEL` | vLLM 모델명 | `default` |
| `PERF_BASELINE_FILE` | Baseline JSON 경로 | `baseline.dev.json` |

### Baseline 관리

```bash
# 현재 성능 기준값 수집
./scripts/collect_baseline.sh dev

# 이전 baseline 비교
python3 -c "from backend.tests.integration.performance.utils.baseline import *; ..."
```

### 문제 해결

- **vLLM not ready**: 모델 다운로드 상태 확인 (`oc get pods -n vllm`)
- **테스트 skip**: `p99 > 2s` 과부하 상태 — 부하 줄인 후 재시도
- **AutoTuner timeout**: trial 수 줄이거나 타임아웃 늘리기
```

#### QA

```bash
# 파일 존재 확인
test -f docs/integration_test_guide.md && echo "OK"
```

---

### Task 10: 기존 플랜 파일 정리

**Category**: `quick`
**Skills**: `[]`
**Files**:
- `.sisyphus/plans/enhanced-performance-integration-tests.md` → archive로 이동
**Depends**: Task 9

#### What to do

기존 543줄 플랜 파일을 archive로 이동:
```bash
mv .sisyphus/plans/enhanced-performance-integration-tests.md .sisyphus/plans/archive/
```

#### QA
```bash
test -f .sisyphus/plans/archive/enhanced-performance-integration-tests.md && echo "OK"
```

---

## Final Verification Wave

모든 Task 완료 후 최종 검증:

```bash
# 1. 기존 39개 테스트 회귀 확인
python3 -m pytest backend/tests/ -v --tb=short -m "not integration"
# 예상: 39 passed

# 2. 성능 테스트 dry-run (클러스터 없이 collect만)
python3 -m pytest backend/tests/integration/performance/ --co -q
# 예상: 5+ tests collected

# 3. 클러스터 접속 가능 시 실제 실행
./scripts/run_performance_tests.sh --env dev
# 예상: 5 scenarios passed
```

## Definition of Done

- [ ] `backend/tests/integration/performance/` 디렉토리 및 conftest 생성
- [ ] pytest 마커 (`integration`, `performance`, `slow`) 등록 + `--strict-markers`
- [ ] LoadTestEngine에 CPU/GPU 샘플링 추가
- [ ] AutoTuner에 wait_metrics 노출
- [ ] metrics collection timing 추가
- [ ] 5개 테스트 시나리오 구현
- [ ] `scripts/run_performance_tests.sh` 생성
- [ ] `openshift/tekton/performance-pipeline.yaml` 생성
- [ ] `docs/integration_test_guide.md` Performance Testing 섹션 추가
- [ ] 기존 39개 테스트 회귀 없음
