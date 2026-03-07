# 백엔드 테스트 수리 계획

**플랜 ID**: fix-backend-tests
**생성일**: 2026-03-06
**우선순위**: P1 (개발 인프라)
**예상 기간**: 30분
**수정 파일**: 2개 (pyproject.toml 신규, test_dev_metrics_endpoint.py 수정)
**프로덕션 코드 변경**: 없음

---

## TL;DR

> **현재 상태**: 37개 테스트 중 29개만 통과, 5개 수집 에러, 8개 실패
>
> **근본 원인 3가지**:
> 1. PYTHONPATH 미설정 → `from models.load_test import ...` 해석 실패 (5개 수집 에러)
> 2. `asyncio_mode` 미설정 → async 테스트가 "not natively supported" (6개 실패)
> 3. monkeypatch 대상 오류 → `generate_metrics` 패치가 이미 바인딩된 참조에 적용 안 됨 (2개 실패)
>
> **수정**: `pyproject.toml` 1개 생성 + `test_dev_metrics_endpoint.py` 1개 수정 = **37/37 통과**
>
> **프로덕션 코드 변경 없음. Dockerfile 변경 없음.**

---

## 사전 조건

- Python 3.14+ 환경에 `pytest >= 9.0`, `pytest-asyncio >= 1.3.0` 설치 확인
- `requirements.txt`에 이미 명시되어 있음: `pytest>=8.3.0`, `pytest-asyncio>=0.24.0`
- **주의**: `pytest-asyncio 1.3.0`이 최신 버전임 (0.x → 1.0 → 1.3.0). 업그레이드 불필요.

---

## 실행 작업

### Task 1: pyproject.toml 생성 (프로젝트 루트)

**What**: 프로젝트 루트(`/home/user/project/vllm-optimizer/pyproject.toml`)에 pytest 설정 파일 생성

**파일 내용** (정확히 이대로):
```toml
[tool.pytest.ini_options]
pythonpath = ["backend"]
asyncio_mode = "auto"
```

**이 설정이 해결하는 문제**:
- `pythonpath = ["backend"]` → pytest 실행 시 `backend/` 디렉토리를 Python 경로에 추가. `from models.load_test import ...` 같은 bare import가 해석됨. 5개 수집 에러 해결.
- `asyncio_mode = "auto"` → async def 테스트 함수에 `@pytest.mark.asyncio` 없어도 자동 인식. 6개 async 테스트 실패 해결.

**절대 하지 말 것**:
- `setup.py`, `setup.cfg` 생성하지 말 것
- `[build-system]` 이나 `[project]` 섹션 추가하지 말 것
- `[tool.pytest.ini_options]` 외 다른 설정 추가하지 말 것

**QA**:
```bash
# pyproject.toml 존재 확인
cat pyproject.toml

# PYTHONPATH 없이 테스트 수집 확인 (에러 0개)
unset PYTHONPATH && python3 -m pytest backend/tests/ --collect-only 2>&1 | tail -3
# 예상: "37 tests collected" (에러 없음)
```

---

### Task 2: test_dev_metrics_endpoint.py monkeypatch 수정

**What**: `backend/tests/test_dev_metrics_endpoint.py`의 두 테스트에서 monkeypatch 대상을 변경

**문제 분석**:
- `main.py`에서 `from metrics.prometheus_metrics import generate_metrics`로 import → `main.generate_metrics`에 함수 참조가 바인딩됨
- 테스트가 `prom.generate_metrics` (원본 모듈)을 패치하지만 `main.generate_metrics` (이미 바인딩된 참조)는 변경되지 않음
- **핵심 원칙**: "Patch where it's used, not where it lives"

**수정 상세**:

#### test_metrics_endpoint_plaintext (함수 1):

**현재 코드** (라인 5-60 부근):
```python
def test_metrics_endpoint_plaintext(monkeypatch):
    """Test /api/metrics endpoint returns correct Prometheus format"""
    from ..metrics import prometheus_metrics as prom
    
    # ... fake_metrics_output 정의 ...

    def fake_generate_metrics():
        return fake_metrics_output
    
    monkeypatch.setattr(prom, 'generate_metrics', fake_generate_metrics)

    from ..main import app
    client = TestClient(app)
    resp = client.get("/api/metrics")
```

**변경할 코드**:
```python
def test_metrics_endpoint_plaintext(monkeypatch):
    """Test /api/metrics endpoint returns correct Prometheus format"""
    
    # ... fake_metrics_output 정의 (그대로 유지) ...

    def fake_generate_metrics():
        return fake_metrics_output
    
    # Patch where it's used (main module), not where it lives (prometheus_metrics module)
    import backend.main
    monkeypatch.setattr(backend.main, 'generate_metrics', fake_generate_metrics)

    from ..main import app
    client = TestClient(app)
    resp = client.get("/api/metrics")
```

**변경 요약**: 
- `from ..metrics import prometheus_metrics as prom` 삭제
- `monkeypatch.setattr(prom, 'generate_metrics', ...)` → `monkeypatch.setattr(backend.main, 'generate_metrics', ...)`
- `import backend.main` 추가

#### test_metrics_endpoint_no_server_required (함수 2):

**현재 코드** (라인 129-144 부근):
```python
def test_metrics_endpoint_no_server_required(monkeypatch):
    """Test that endpoint works without requiring external server or backend services"""
    import backend.metrics.prometheus_metrics as prom
    
    def fake_generate_metrics():
        return b"# HELP test_metric Test metric\n# TYPE test_metric gauge\ntest_metric 1.0\n"
    
    monkeypatch.setattr(prom, 'generate_metrics', fake_generate_metrics)

    from backend.main import app
    client = TestClient(app)
```

**변경할 코드**:
```python
def test_metrics_endpoint_no_server_required(monkeypatch):
    """Test that endpoint works without requiring external server or backend services"""
    
    def fake_generate_metrics():
        return b"# HELP test_metric Test metric\n# TYPE test_metric gauge\ntest_metric 1.0\n"
    
    # Patch where it's used (main module), not where it lives (prometheus_metrics module)
    import backend.main
    monkeypatch.setattr(backend.main, 'generate_metrics', fake_generate_metrics)

    from backend.main import app
    client = TestClient(app)
```

**변경 요약**:
- `import backend.metrics.prometheus_metrics as prom` 삭제
- `monkeypatch.setattr(prom, 'generate_metrics', ...)` → `monkeypatch.setattr(backend.main, 'generate_metrics', ...)`
- `import backend.main` 추가

**절대 하지 말 것**:
- `main.py`의 import 구조를 변경하지 말 것
- 새로운 테스트를 추가하지 말 것
- `conftest.py`를 수정하지 말 것
- 다른 테스트 파일을 수정하지 말 것

**QA**:
```bash
python3 -m pytest backend/tests/test_dev_metrics_endpoint.py -v --tb=short
# 예상: 2 passed, 0 failed
```

---

## Final Verification Wave

모든 Task 완료 후 아래 명령어로 전체 검증:

```bash
# 1. 전체 테스트 실행 (PYTHONPATH 없이)
unset PYTHONPATH && python3 -m pytest backend/tests/ -v --tb=short 2>&1 | tail -5
# 예상: "37 passed" (failed/error 없음)

# 2. 이전에 수집 에러났던 5개 파일 확인
python3 -m pytest backend/tests/test_benchmark.py backend/tests/test_integration_metrics_e2e.py backend/tests/test_load_test.py backend/tests/test_metrics.py backend/tests/test_tuner.py -v --tb=short 2>&1 | grep -cE "PASSED"
# 예상: 전부 PASSED

# 3. Async 테스트 6개 확인
python3 -m pytest backend/tests/test_metrics_collector.py -v --tb=short 2>&1 | grep -cE "PASSED"
# 예상: 6

# 4. Monkeypatch 테스트 2개 확인
python3 -m pytest backend/tests/test_dev_metrics_endpoint.py -v --tb=short 2>&1 | grep -cE "PASSED"
# 예상: 2

# 5. 기존 통과 테스트 회귀 확인
python3 -m pytest backend/tests/test_stub.py backend/tests/test_service_monitor_config.py backend/tests/test_prometheus_metrics.py -v --tb=short 2>&1 | grep -cE "PASSED"
# 예상: 7 이상
```

---

## 스코프 경계

**IN SCOPE**:
- `pyproject.toml` 신규 생성 (pytest 설정만)
- `backend/tests/test_dev_metrics_endpoint.py` monkeypatch 대상 수정
- 전체 테스트 통과 검증

**OUT OF SCOPE**:
- 프로덕션 코드 (`main.py`, `routers/`, `services/`, `models/`, `metrics/`) 수정
- Dockerfile 수정
- 새로운 테스트 추가
- `conftest.py` 수정
- `requirements.txt` 수정 (이미 올바른 버전 명시)
- Import 패턴 리팩토링 (bare → relative 전환 등)
- CI/CD 파이프라인 수정
