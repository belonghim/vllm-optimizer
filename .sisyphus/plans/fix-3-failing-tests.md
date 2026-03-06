# Plan: 3개 실패 테스트 수정 — 모듈 이중 임포트 문제

**Created**: 2026-03-06
**Status**: Ready for execution
**Estimated Tasks**: 2 (병렬 실행 가능)
**Scope**: `backend/tests/` 만 수정 — 프로덕션 코드 변경 없음

---

## TL;DR

> 39개 테스트 중 3개 실패. 근본 원인은 **Python 모듈 이중 임포트** 문제.
> `conftest.py`가 `backend/`를 `sys.path`에 추가하여 같은 파일이 `services.metrics_collector`와
> `backend.services.metrics_collector`로 **2개의 다른 모듈 인스턴스**로 로드됨.
> monkeypatch/patch가 한쪽 인스턴스만 수정하여 패치가 무효화됨.
>
> **프로덕션 코드 변경 없음. 테스트 파일 2개만 수정.**

---

## 근본 원인 분석

### 핵심 문제: 모듈 이중 인스턴스

`conftest.py` line 21:
```python
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
```

이로 인해:
- `import services.metrics_collector` → `sys.modules['services.metrics_collector']`
- `import backend.services.metrics_collector` → `sys.modules['backend.services.metrics_collector']`
- **두 모듈은 같은 파일이지만 서로 다른 Python 객체** (검증 완료: `m1 is m2` = `False`)

### 실패 1: `test_detect_version_013x`

- **파일**: `backend/tests/test_metrics_collector.py` line 30, 51-53
- fixture가 `patch('backend.services.metrics_collector.PROMETHEUS_URL', "http://mock-prometheus")` 적용
- 하지만 `_detect_version()` 함수의 `__globals__`는 `services.metrics_collector` 모듈을 참조
- 따라서 함수 실행 시 **패치되지 않은** 원본 `PROMETHEUS_URL`(`https://thanos-querier...`)을 사용
- `assert_called_once_with`에서 URL 불일치로 실패

### 실패 2, 3: `test_metrics_endpoint_plaintext`, `test_metrics_endpoint_no_server_required`

- **파일**: `backend/tests/test_dev_metrics_endpoint.py` line 57, 139
- `monkeypatch.setattr(backend.main, 'generate_metrics', fake)` 적용
- `main.py`의 `from metrics.prometheus_metrics import generate_metrics` (bare import)
- `plaintext_metrics_root()` 함수의 `__globals__`가 참조하는 모듈과 패치 대상 모듈이 불일치할 수 있음
- 또한 `isolated_client`의 `importlib.reload()`로 인한 모듈 상태 오염 가능

---

## Scope

### IN
- `backend/tests/test_metrics_collector.py` — PROMETHEUS_URL 패치 경로 수정
- `backend/tests/test_dev_metrics_endpoint.py` — generate_metrics 패치 방식 수정

### OUT
- 프로덕션 코드 (`main.py`, `metrics_collector.py`, `prometheus_metrics.py` 등)
- `conftest.py` — 기존 구조 유지
- 다른 테스트 파일
- sys.path 구조 변경 (이중 임포트 근본 해결은 별도 작업)

---

## Wave 1 — Parallel (No Dependencies)

### Task 1: PROMETHEUS_URL 패치 경로 수정

**Category**: `quick`
**Skills**: `[]`
**File**: `backend/tests/test_metrics_collector.py`
**Depends**: None

#### What to do

`mock_metrics_collector` fixture의 `PROMETHEUS_URL` 패치 대상을 **bare import 경로**로 변경.

**File: `backend/tests/test_metrics_collector.py`**

**현재 코드** (line 28-30):
```python
with patch('backend.services.metrics_collector.MetricsCollector._load_token', return_value=None), \
     patch('backend.services.metrics_collector.MetricsCollector._init_k8s', return_value=None), \
     patch('backend.services.metrics_collector.PROMETHEUS_URL', "http://mock-prometheus"):
```

**변경할 코드**:
```python
with patch('backend.services.metrics_collector.MetricsCollector._load_token', return_value=None), \
     patch('backend.services.metrics_collector.MetricsCollector._init_k8s', return_value=None), \
     patch('backend.services.metrics_collector.PROMETHEUS_URL', "http://mock-prometheus"), \
     patch('services.metrics_collector.PROMETHEUS_URL', "http://mock-prometheus"):
```

**또한** line 51-53의 assertion URL 참조를 하드코딩된 값으로 변경:

**현재 코드**:
```python
mock_httpx_client.get.assert_called_once_with(
    f"{backend.services.metrics_collector.PROMETHEUS_URL}/api/v1/query",
    params={"query": "vllm:kv_cache_usage_perc"},
)
```

**변경할 코드**:
```python
mock_httpx_client.get.assert_called_once_with(
    "http://mock-prometheus/api/v1/query",
    params={"query": "vllm:kv_cache_usage_perc"},
)
```

**이유**: `backend.services.metrics_collector.PROMETHEUS_URL`은 테스트 시점에 패치가 활성화되어 있더라도, 모듈 이중 인스턴스 문제로 예상치 못한 값이 반환될 수 있음. 하드코딩이 더 명확하고 안전함.

#### ⚠️ 주의사항

- `_load_token`, `_init_k8s` 패치 경로는 **변경하지 말 것** — 이들은 `MetricsCollector` 클래스의 메서드이므로 클래스 레벨에서 패치되어 양쪽 모듈에 모두 적용됨
- `TestMetricsCollectorQuerySelection` 클래스의 fixture는 `PROMETHEUS_URL`을 패치하지 않으므로 **수정 불필요**

#### QA (필수 실행)

```bash
python3 -m pytest backend/tests/test_metrics_collector.py -v --tb=short
# 예상: 6 passed, 0 failed
```

---

### Task 2: generate_metrics 패치 방식 수정

**Category**: `quick`
**Skills**: `[]`
**File**: `backend/tests/test_dev_metrics_endpoint.py`
**Depends**: None

#### What to do

`generate_metrics` 패치를 **모듈 reload에 안전한 방식**으로 변경.
핵심: 패치 적용 후 **현재 sys.modules에서 app을 가져오고**, `plaintext_metrics_root` 함수의
글로벌이 올바른 모듈을 참조하는지 확인.

**File: `backend/tests/test_dev_metrics_endpoint.py`**

#### test_metrics_endpoint_plaintext (line 5-128):

**현재 코드** (line 55-61):
```python
# Patch where it's used (main module), not where it lives (prometheus_metrics module)
import backend.main
monkeypatch.setattr(backend.main, 'generate_metrics', fake_generate_metrics)

from ..main import app
client = TestClient(app)
resp = client.get("/api/metrics")
```

**변경할 코드**:
```python
# Reload to get a clean module, then patch
import importlib
import backend.main
importlib.reload(backend.main)
monkeypatch.setattr(backend.main, 'generate_metrics', fake_generate_metrics)

app = backend.main.app
client = TestClient(app)
resp = client.get("/api/metrics")
```

**변경 포인트**:
1. `importlib.reload(backend.main)` 추가 — 다른 테스트에서 reload된 상태를 초기화
2. `from ..main import app` → `app = backend.main.app` — 동일한 모듈 인스턴스에서 app 참조 보장
3. `import importlib` 추가 (파일 상단)

#### test_metrics_endpoint_no_server_required (line 130-146):

**현재 코드** (line 137-143):
```python
# Patch where it's used (main module), not where it lives (prometheus_metrics module)
import backend.main
monkeypatch.setattr(backend.main, 'generate_metrics', fake_generate_metrics)

from backend.main import app
client = TestClient(app)
```

**변경할 코드**:
```python
# Reload to get a clean module, then patch
import importlib
import backend.main
importlib.reload(backend.main)
monkeypatch.setattr(backend.main, 'generate_metrics', fake_generate_metrics)

app = backend.main.app
client = TestClient(app)
```

**변경 포인트**: Task 2a와 동일한 패턴 적용.

#### 파일 상단 import 추가:

line 1-2에 `import importlib` 추가:
```python
import importlib

import pytest
from fastapi.testclient import TestClient
```

#### ⚠️ 주의사항

- `importlib.reload()`는 모듈을 완전히 재실행함 — `generate_metrics` 임포트 + `app` 생성 + 라우터 등록이 모두 다시 수행됨
- reload 후 `backend.main.app`은 **새로운 FastAPI 인스턴스** — 이전 app 참조 사용 금지
- `from ..main import app` 패턴은 reload 이전의 app을 가져올 수 있으므로 **사용 금지**
- 기존 `fake_metrics_output` 정의와 assertion 로직은 **변경하지 말 것**

#### QA (필수 실행)

```bash
python3 -m pytest backend/tests/test_dev_metrics_endpoint.py -v --tb=short
# 예상: 2 passed, 0 failed
```

---

## Final Verification Wave

모든 Task 완료 후 최종 검증:

```bash
# 1. 전체 테스트 실행
python3 -m pytest backend/tests/ -v --tb=short
# 예상: 39 passed, 0 failed

# 2. 이전 실패 테스트 개별 확인
python3 -m pytest backend/tests/test_dev_metrics_endpoint.py backend/tests/test_metrics_collector.py -v --tb=short
# 예상: 8 passed (2 + 6), 0 failed

# 3. 기존 통과 테스트 회귀 확인
python3 -m pytest backend/tests/test_load_test.py backend/tests/test_tuner.py backend/tests/test_benchmark.py -v --tb=short
# 예상: 전부 PASSED
```

## Definition of Done

- [x] `test_detect_version_013x` PASSED
- [x] `test_metrics_endpoint_plaintext` PASSED
- [x] `test_metrics_endpoint_no_server_required` PASSED
- [x] 기존 36개 테스트 전부 회귀 없이 PASSED
- [x] 프로덕션 코드 변경 없음
