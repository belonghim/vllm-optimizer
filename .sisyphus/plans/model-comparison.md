# 모델명 자동 해석 + GPU 효율 메트릭

## TL;DR

> **Quick Summary**: 부하 테스트 시 model "auto"를 vLLM `/v1/models` API로 실제 모델명 해석하고, 벤치마크에 GPU 효율(TPS/GPU사용률) 메트릭을 추가한다. 기존 벤치마크 탭에 모델명·GPU 효율 컬럼을 반영한다.
> 
> **Deliverables**:
> - 백엔드: 모델명 자동 해석 유틸리티, 벤치마크 모델별 그룹핑 API + GPU 효율 계산
> - 프론트엔드: 기존 벤치마크 탭에 모델명·GPU 효율 컬럼 추가, mock 데이터 보강
> - 테스트: 백엔드 pytest + 프론트엔드 vitest (tests-after)
> 
> **Estimated Effort**: Short
> **Parallel Execution**: YES — 2 waves
> **Critical Path**: Task 1 → Task 3 → Task 5 → Task 6 → Final

---

## Context

### Original Request
vLLM Optimizer에서 모델명 자동 해석과 GPU 효율(비용 효율) 메트릭을 지원하되, 전용 비교 탭 없이 기존 벤치마크 탭을 보강한다.

### Interview Summary
**Key Discussions**:
- 비교 메트릭: GPU 효율 = TPS / GPU 사용률 (자동 계산, 추가 입력 불필요)
- model "auto" → /v1/models로 실제 모델명 자동 해석
- 5번째 탭(모델 비교 전용 뷰) → **폐기**
- 기존 벤치마크 탭에 모델명 + GPU 효율 컬럼 추가로 대체
- Tests-after 전략 (pytest + vitest)

**Research Findings**:
- `Benchmark` 모델에 `config.model` 필드 존재 — 모델명이 이미 저장됨
- `LoadTestResult`에 `tokens_per_sec`, `gpu_utilization_avg` 이미 존재
- `auto_tuner.py:277-291`에 `/v1/models` 해석 패턴 존재 — 재사용 가능
- 기존 BenchmarkPage에서 Recharts BarChart로 비교 차트 이미 구현됨
- 저장소: 인메모리 리스트 (변경 없음)

### Metis Review
**Identified Gaps** (addressed):
- model "auto" 해석 실패 시 fallback: "auto"로 유지하되 경고 로그 남김
- GPU 사용률이 0인 경우: GPU 효율 = N/A 표시
- `auto_tuner.py`의 모델 해석 로직을 공통 유틸로 추출 (DRY 원칙)

---

## Work Objectives

### Core Objective
부하 테스트 시 모델명을 자동 해석하고, 벤치마크에 GPU 효율 메트릭을 추가하여 기존 UI에서 확인 가능하게 한다.

### Concrete Deliverables
- `backend/services/model_resolver.py` — 모델명 자동 해석 공통 유틸리티
- `backend/routers/benchmark.py` 확장 — 모델별 그룹핑 + GPU 효율 계산 API
- `backend/routers/load_test.py` 수정 — 테스트 시작 시 모델명 자동 해석
- `frontend/src/pages/BenchmarkPage.jsx` 수정 — 모델명 + GPU 효율 컬럼 추가
- `frontend/src/mockData.js` 수정 — config.model + gpu_efficiency 추가

### Definition of Done
- [x] model "auto"로 테스트 시 실제 모델명이 자동 해석되어 저장됨
- [x] 벤치마크 테이블에 모델명과 GPU 효율이 표시됨
- [x] `python3 -m pytest tests/ -x -q -m "not integration"` PASS
- [x] `cd frontend && npx vitest run` PASS

### Must Have
- 모델명 자동 해석 (/v1/models API 호출)
- GPU 효율 = TPS / GPU 사용률 (gpu_utilization_avg가 0이면 N/A)
- 벤치마크 모델별 그룹핑 API
- 기존 벤치마크 탭 테이블에 Model, GPU Eff. 컬럼 추가

### Must NOT Have (Guardrails)
- 새로운 페이지/탭 추가 (5번째 탭 폐기됨)
- 데이터베이스 마이그레이션 또는 영속성 레이어 변경
- 새로운 UI 라이브러리 추가
- 기존 auto_tuner.py의 동작 변경 (모델 해석 로직만 추출)
- 80/443 포트, root 실행, DockerHub 이미지, kubectl 사용
- 과도한 JSDoc/주석, 불필요한 추상화

---

## Verification Strategy

> **ZERO HUMAN INTERVENTION** — ALL verification is agent-executed. No exceptions.

### Test Decision
- **Infrastructure exists**: YES (pytest backend, vitest frontend)
- **Automated tests**: Tests-after
- **Framework**: pytest (backend), vitest (frontend)

### QA Policy
Every task MUST include agent-executed QA scenarios.
Evidence saved to `.sisyphus/evidence/task-{N}-{scenario-slug}.{ext}`.

- **Frontend/UI**: Use Playwright (playwright skill) — Navigate, interact, assert DOM, screenshot
- **API/Backend**: Use Bash (curl) — Send requests, assert status + response fields
- **Library/Module**: Use Bash (python REPL) — Import, call functions, compare output

---

## Execution Strategy

### Parallel Execution Waves

```
Wave 1 (Foundation — 모두 독립, 병렬 실행):
├── Task 1: 모델명 해석 공통 유틸리티 추출 [quick]
├── Task 2: 벤치마크 모델별 그룹핑 API + GPU 효율 [quick]
└── Task 3: mock 데이터 보강 (config.model + gpu_efficiency) [quick]

Wave 2 (적용 — Wave 1 완료 후):
├── Task 4: 부하 테스트 시작 시 모델명 자동 해석 적용 [quick]
└── Task 5: BenchmarkPage 모델명 + GPU 효율 컬럼 추가 [quick]

Wave 3 (Tests — Wave 2 완료 후):
└── Task 6: 백엔드 + 프론트엔드 테스트 [unspecified-high]

Wave FINAL (After ALL tasks — independent review):
├── Task F1: Plan compliance audit (oracle)
├── Task F2: Code quality review (unspecified-high)
├── Task F3: Real manual QA (unspecified-high)
└── Task F4: Scope fidelity check (deep)

Critical Path: Task 1 → Task 4 → Task 6 → Final
Parallel Speedup: ~50% faster than sequential
Max Concurrent: 3 (Wave 1)
```

### Dependency Matrix

| Task | Depends On | Blocks |
|------|-----------|--------|
| 1 | — | 4, 6 |
| 2 | — | 5, 6 |
| 3 | — | 5, 6 |
| 4 | 1 | 6 |
| 5 | 2, 3 | 6 |
| 6 | 4, 5 | F1-F4 |

### Agent Dispatch Summary

- **Wave 1**: **3** — T1 → `quick`, T2 → `quick`, T3 → `quick`
- **Wave 2**: **2** — T4 → `quick`, T5 → `quick`
- **Wave 3**: **1** — T6 → `unspecified-high`
- **FINAL**: **4** — F1 → `oracle`, F2 → `unspecified-high`, F3 → `unspecified-high`, F4 → `deep`

---

## TODOs

- [x] 1. 모델명 해석 공통 유틸리티 추출 (`model_resolver.py`)

  **What to do**:
  - `backend/services/model_resolver.py` 신규 생성
  - `auto_tuner.py:277-291`의 `/v1/models` 호출 로직을 공통 함수로 추출
  - `async def resolve_model_name(endpoint: str, fallback: str = "auto") -> str` 시그니처
  - httpx.AsyncClient(timeout=10, verify=False)로 `{endpoint}/v1/models` 호출
  - 성공 시 `data[0]["id"]` 반환, 실패 시 `fallback` 반환 + warning 로그
  - `auto_tuner.py`의 `_evaluate()` 메서드에서 새 유틸리티를 import하여 사용하도록 리팩터 (기존 동작 유지)

  **Must NOT do**:
  - auto_tuner.py의 다른 로직 변경
  - 새 의존성 추가

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: 단일 유틸리티 함수 추출 + 기존 코드 리팩터. 2개 파일만 수정.
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Tasks 2, 3)
  - **Blocks**: Tasks 4, 6
  - **Blocked By**: None

  **References**:

  **Pattern References**:
  - `backend/services/auto_tuner.py:277-291` — 기존 `/v1/models` 해석 패턴. 이 로직을 그대로 추출

  **API/Type References**:
  - `backend/models/load_test.py:14-24` — `LoadTestConfig` 모델. model 필드 기본값 "auto"

  **External References**:
  - vLLM `/v1/models` API: OpenAI 호환, `{"data": [{"id": "model-name", ...}]}` 형태 응답

  **WHY Each Reference Matters**:
  - `auto_tuner.py:277-291`: 이미 동작 검증된 패턴. 동일한 httpx 호출, 에러 처리, 로깅 유지
  - `LoadTestConfig`: model 기본값 "auto" 이해 → fallback 로직 설계

  **Acceptance Criteria**:
  - [x] `backend/services/model_resolver.py` 파일 생성
  - [x] `resolve_model_name()` 함수가 endpoint를 받아 모델명 반환
  - [x] `auto_tuner.py`에서 `from services.model_resolver import resolve_model_name` 사용
  - [x] `auto_tuner.py`의 기존 테스트 통과 (`python3 -m pytest tests/test_tuner.py -x -q -m "not integration"`)

  **QA Scenarios**:

  ```
  Scenario: resolve_model_name 함수 import 및 호출 가능
    Tool: Bash (python3)
    Preconditions: backend/ 디렉토리에서 실행
    Steps:
      1. python3 -c "from services.model_resolver import resolve_model_name; print('OK')"
      2. 출력에 "OK" 포함 확인
    Expected Result: "OK" 출력, ImportError 없음
    Failure Indicators: ImportError, ModuleNotFoundError
    Evidence: .sisyphus/evidence/task-1-import-check.txt

  Scenario: auto_tuner.py 기존 테스트 유지
    Tool: Bash
    Preconditions: backend/ 디렉토리
    Steps:
      1. python3 -m pytest tests/test_tuner.py -x -q -m "not integration"
      2. 모든 테스트 PASS 확인
    Expected Result: 0 failures
    Failure Indicators: FAILED, ERROR 키워드
    Evidence: .sisyphus/evidence/task-1-tuner-test.txt
  ```

  **Commit**: YES
  - Message: `feat(backend): extract model name resolver utility`
  - Files: `backend/services/model_resolver.py`, `backend/services/auto_tuner.py`
  - Pre-commit: `python3 -m pytest tests/test_tuner.py -x -q -m "not integration"`

- [x] 2. 벤치마크 모델별 그룹핑 API + GPU 효율 계산

  **What to do**:
  - `backend/routers/benchmark.py`에 `GET /by-model` 엔드포인트 추가
  - 저장된 벤치마크를 `config.model` 기준으로 그룹핑하여 반환
  - 각 벤치마크에 `gpu_efficiency` 필드 추가 계산: `tps.mean / gpu_utilization_avg` (gpu_utilization_avg == 0이면 None)
  - 응답 형태: `{"models": {"model-a": [Benchmark+gpu_efficiency, ...], "model-b": [...]}}`

  **Must NOT do**:
  - 기존 `/list`, `/save`, `/{id}`, `DELETE` 엔드포인트 변경
  - 데이터베이스 도입

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: 단일 라우터 파일에 엔드포인트 1개 추가. 간단한 그룹핑 로직.
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Tasks 1, 3)
  - **Blocks**: Tasks 5, 6
  - **Blocked By**: None

  **References**:

  **Pattern References**:
  - `backend/routers/benchmark.py:16-19` — 기존 `list_benchmarks()` 패턴. 동일한 `benchmark_storage` 사용
  - `backend/routers/benchmark.py:22-28` — `save_benchmark()` 패턴. 라우터 데코레이터 스타일

  **API/Type References**:
  - `backend/models/load_test.py:123-129` — `Benchmark` 모델. config.model로 그룹핑 키 접근
  - `backend/models/load_test.py:54-68` — `LoadTestResult`. tps.mean, gpu_utilization_avg 필드

  **WHY Each Reference Matters**:
  - `benchmark.py` 기존 패턴: 동일한 `benchmark_storage`에서 읽어 그룹핑. 일관된 스타일
  - `LoadTestResult`: GPU 효율 계산에 필요한 필드 위치

  **Acceptance Criteria**:
  - [x] `GET /api/benchmark/by-model` 엔드포인트 동작
  - [x] 벤치마크가 모델명 기준으로 그룹핑됨
  - [x] 각 항목에 `gpu_efficiency` 필드 포함 (gpu_util=0이면 null)

  **QA Scenarios**:

  ```
  Scenario: 벤치마크 저장 후 모델별 그룹핑 조회
    Tool: Bash (curl)
    Preconditions: Backend 서버 실행 중 (localhost:8000)
    Steps:
      1. curl -X POST http://localhost:8000/api/benchmark/save -H "Content-Type: application/json" -d '{"name":"test-A","config":{"endpoint":"http://fake:8080","model":"model-A","total_requests":10,"concurrency":1},"result":{"tps":{"mean":100,"total":200},"gpu_utilization_avg":50}}'
      2. curl -X POST http://localhost:8000/api/benchmark/save -H "Content-Type: application/json" -d '{"name":"test-B","config":{"endpoint":"http://fake:8080","model":"model-B","total_requests":10,"concurrency":1},"result":{"tps":{"mean":150,"total":300},"gpu_utilization_avg":60}}'
      3. curl -s http://localhost:8000/api/benchmark/by-model | python3 -m json.tool
      4. 응답에 "model-A"와 "model-B" 키 존재 확인
      5. model-A 항목의 gpu_efficiency가 2.0 (100/50) 확인
    Expected Result: JSON에 두 모델 그룹 존재, gpu_efficiency 계산 정확
    Failure Indicators: 404, 500, 키 누락, gpu_efficiency 오류
    Evidence: .sisyphus/evidence/task-2-by-model-api.txt

  Scenario: GPU 사용률 0일 때 gpu_efficiency null
    Tool: Bash (curl)
    Preconditions: Backend 서버 실행 중
    Steps:
      1. curl -X POST http://localhost:8000/api/benchmark/save -H "Content-Type: application/json" -d '{"name":"no-gpu","config":{"model":"model-C"},"result":{"tps":{"mean":50},"gpu_utilization_avg":0}}'
      2. curl -s http://localhost:8000/api/benchmark/by-model | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['models']['model-C'][0].get('gpu_efficiency'))"
      3. 출력이 "None" 또는 "null"인지 확인
    Expected Result: gpu_efficiency가 null/None
    Failure Indicators: ZeroDivisionError, 숫자 출력
    Evidence: .sisyphus/evidence/task-2-gpu-zero.txt
  ```

  **Commit**: YES
  - Message: `feat(api): add model-grouped benchmark endpoint with GPU efficiency`
  - Files: `backend/routers/benchmark.py`
  - Pre-commit: `python3 -m pytest tests/test_benchmark.py -x -q -m "not integration"`

- [x] 3. 프론트엔드 mock 데이터 보강 (config.model + gpu_efficiency)

  **What to do**:
  - `frontend/src/mockData.js`의 기존 `mockBenchmarks()` 수정
  - 각 mock 벤치마크에 `config` 객체 추가 (현재 누락): `config: { model: "모델명", endpoint: "..." }`
  - 각 결과에 `gpu_utilization_avg` 필드 추가
  - 3개 mock 항목에 서로 다른 모델명 부여 (예: "Qwen2.5-3B", "Llama-3.1-8B", "Mistral-7B")

  **Must NOT do**:
  - 기존 `mockBenchmarks()` 반환 구조 파괴 (기존 필드 유지하며 추가만)
  - 새 mock 함수 추가 (기존 함수 보강만)

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: 단일 파일, mock 데이터에 필드 추가만.
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Tasks 1, 2)
  - **Blocks**: Tasks 5, 6
  - **Blocked By**: None

  **References**:

  **Pattern References**:
  - `frontend/src/mockData.js:19-26` — 기존 `mockBenchmarks()`. 현재 config 필드 없음, result에 gpu_utilization_avg 없음

  **API/Type References**:
  - `backend/models/load_test.py:123-129` — `Benchmark` 모델 (id, name, timestamp, config, result)
  - `backend/models/load_test.py:14-24` — `LoadTestConfig` (endpoint, model, ...)
  - `backend/models/load_test.py:54-68` — `LoadTestResult` (gpu_utilization_avg)

  **WHY Each Reference Matters**:
  - `mockBenchmarks()`: BenchmarkPage에서 이 구조를 직접 사용. config 추가 시 기존 필드 깨지면 안 됨
  - Benchmark/LoadTestResult: mock이 실제 API 구조와 일치해야 UI가 정확히 동작

  **Acceptance Criteria**:
  - [x] `mockBenchmarks()` 반환 항목에 `config.model` 존재
  - [x] `mockBenchmarks()` 반환 항목에 `result.gpu_utilization_avg` 존재
  - [x] 기존 BenchmarkPage mock 모드 정상 동작 (깨지지 않음)

  **QA Scenarios**:

  ```
  Scenario: 기존 mockBenchmarks에 config.model 추가 확인
    Tool: Bash
    Preconditions: frontend/ 디렉토리
    Steps:
      1. node -e "const m = await import('./src/mockData.js'); const b = m.mockBenchmarks(); console.log(b[0].config?.model, b[0].result?.gpu_utilization_avg !== undefined)"
      2. 모델명 문자열 + "true" 출력 확인
    Expected Result: "Qwen2.5-3B true" 또는 유사 출력
    Failure Indicators: "undefined" 출력
    Evidence: .sisyphus/evidence/task-3-mock-config.txt
  ```

  **Commit**: YES (groups with Task 5)
  - Message: `feat(frontend): add model name and GPU efficiency to benchmark UI`
  - Files: `frontend/src/mockData.js`

- [x] 4. 부하 테스트 시작 시 모델명 자동 해석 적용

  **What to do**:
  - `backend/routers/load_test.py`의 `start_load_test()` 수정
  - `config.model == "auto"`일 때, `resolve_model_name(config.endpoint)` 호출
  - 해석된 모델명으로 config.model 업데이트 후 엔진에 전달
  - 이력(_test_history)에도 해석된 모델명 저장 보장
  - `from services.model_resolver import resolve_model_name` import 추가

  **Must NOT do**:
  - model이 "auto"가 아닌 경우 해석 시도하지 않음
  - SSE 스트림 로직 변경
  - load_engine.py 내부 수정

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: 기존 라우터에 3-5줄 추가.
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 (with Task 5)
  - **Blocks**: Task 6
  - **Blocked By**: Task 1

  **References**:

  **Pattern References**:
  - `backend/routers/load_test.py:62-100` — `start_load_test()` 함수. config 수신 후 엔진 실행 흐름
  - `backend/services/auto_tuner.py:277-291` — 해석 후 LoadTestConfig에 반영하는 패턴

  **API/Type References**:
  - `backend/services/model_resolver.py` (Task 1에서 생성) — `resolve_model_name(endpoint, fallback)` 시그니처

  **WHY Each Reference Matters**:
  - `start_load_test()`: 해석 로직 삽입 위치 (config 수신 후, run_test() 전)
  - `auto_tuner.py`: 동일 패턴 선례. model_name 해석 → config 반영

  **Acceptance Criteria**:
  - [x] model "auto"로 테스트 시작 시 /v1/models 호출됨
  - [x] 이력에 해석된 실제 모델명 저장됨
  - [x] model 직접 입력 시 해석 스킵

  **QA Scenarios**:

  ```
  Scenario: model "auto"일 때 fallback 동작 확인
    Tool: Bash (curl + python3)
    Preconditions: Backend 서버 실행 중
    Steps:
      1. curl -X POST http://localhost:8000/api/load_test/start -H "Content-Type: application/json" -d '{"endpoint":"http://nonexistent:8080","model":"auto","total_requests":1,"concurrency":1}'
      2. sleep 15
      3. curl -s http://localhost:8000/api/load_test/history?limit=1 | python3 -m json.tool
      4. history의 config.model 필드 확인 (해석 실패 → "auto" 유지)
    Expected Result: config.model 존재 (해석 성공 시 실제 모델명, 실패 시 "auto")
    Failure Indicators: config.model 누락, 500 에러
    Evidence: .sisyphus/evidence/task-4-auto-resolve.txt

  Scenario: model 직접 입력 시 해석 스킵
    Tool: Bash (curl)
    Preconditions: Backend 서버 실행 중
    Steps:
      1. curl -X POST http://localhost:8000/api/load_test/start -H "Content-Type: application/json" -d '{"endpoint":"http://nonexistent:8080","model":"my-custom-model","total_requests":1,"concurrency":1}'
      2. sleep 15
      3. curl -s http://localhost:8000/api/load_test/history?limit=1 | python3 -c "import sys,json; d=json.load(sys.stdin); print(d[0]['config']['model'])"
      4. "my-custom-model" 그대로 출력 확인
    Expected Result: "my-custom-model" 출력
    Failure Indicators: 다른 모델명 출력
    Evidence: .sisyphus/evidence/task-4-manual-model.txt
  ```

  **Commit**: YES
  - Message: `feat(backend): auto-resolve model name on load test start`
  - Files: `backend/routers/load_test.py`
  - Pre-commit: `python3 -m pytest tests/test_load_test.py -x -q -m "not integration"`

- [x] 5. BenchmarkPage 모델명 + GPU 효율 컬럼 추가

  **What to do**:
  - `frontend/src/pages/BenchmarkPage.jsx` 수정
  - **테이블 변경**:
    - 헤더에 "Model" 컬럼 추가 (Name과 Date 사이)
    - 헤더에 "GPU Eff." 컬럼 추가 (RPS 뒤)
    - 각 행에 `b.config?.model || "—"` 표시
    - 각 행에 GPU 효율 표시: `b.result?.gpu_utilization_avg > 0 ? (b.result?.tps?.mean / b.result?.gpu_utilization_avg).toFixed(1) : "—"`
    - colSpan 업데이트 (6 → 8)
  - **비교 차트 변경**:
    - compareData에 `gpuEff` 필드 추가
    - 기존 2개 차트(TPS, P99) 옆에 "GPU 효율 비교" BarChart 1개 추가
    - `grid-2` → `grid-3` 또는 3개 차트를 유연하게 배치

  **Must NOT do**:
  - 기존 TPS, P99 비교 차트 제거/변경
  - 새 UI 라이브러리 추가
  - 컴포넌트 파일 분리 (BenchmarkPage 내에서 해결)

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: 단일 파일. 테이블 컬럼 2개 추가 + BarChart 1개 추가.
  - **Skills**: [`playwright`]
    - `playwright`: QA 시나리오에서 UI 렌더링 확인

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 (with Task 4)
  - **Blocks**: Task 6
  - **Blocked By**: Tasks 2, 3

  **References**:

  **Pattern References**:
  - `frontend/src/pages/BenchmarkPage.jsx:67-91` — 기존 테이블 구조. `<th>`, `<td>` 패턴
  - `frontend/src/pages/BenchmarkPage.jsx:40-48` — `compareData` 계산 로직. 여기에 gpuEff 추가
  - `frontend/src/pages/BenchmarkPage.jsx:94-124` — 비교 차트 영역. BarChart 패턴 복제하여 GPU 효율 차트 추가

  **API/Type References**:
  - `backend/models/load_test.py:54-68` — `LoadTestResult.gpu_utilization_avg`, `tps.mean`

  **Component References**:
  - `frontend/src/constants.js:4-15` — COLORS. GPU 효율 차트에 `COLORS.green` 또는 `COLORS.purple` 사용

  **WHY Each Reference Matters**:
  - BenchmarkPage 테이블: 기존 패턴에 컬럼 삽입. 스타일 일관성 필수
  - compareData: GPU 효율 필드를 동일 패턴으로 추가해야 차트에서 사용 가능
  - BarChart 패턴: 기존 TPS/P99 차트와 동일한 구조로 3번째 차트 추가

  **Acceptance Criteria**:
  - [x] 벤치마크 테이블에 "Model", "GPU Eff." 컬럼 표시
  - [x] config.model 없는 경우 "—", gpu_utilization_avg=0인 경우 "—"
  - [x] 2개 이상 선택 시 GPU 효율 비교 BarChart 표시
  - [x] Mock 모드에서 정상 동작

  **QA Scenarios**:

  ```
  Scenario: 벤치마크 테이블에 Model + GPU Eff. 컬럼 확인
    Tool: Playwright
    Preconditions: 프론트엔드 dev 서버 실행, Mock Data ON
    Steps:
      1. page.goto("http://localhost:5173")
      2. page.click("button.nav-btn:has-text('벤치마크 비교')")
      3. page.locator("th:has-text('Model')").isVisible() 확인
      4. page.locator("th:has-text('GPU Eff.')").isVisible() 확인
      5. 첫 번째 행의 Model 셀에 모델명 존재 확인
      6. 스크린샷 캡처
    Expected Result: "Model", "GPU Eff." 헤더 존재, 행에 값 표시
    Failure Indicators: 헤더 없음, 빈 셀
    Evidence: .sisyphus/evidence/task-5-benchmark-columns.png

  Scenario: 비교 차트에 GPU 효율 차트 추가 확인
    Tool: Playwright
    Preconditions: Mock Data ON, 벤치마크 탭
    Steps:
      1. 첫 번째와 두 번째 벤치마크 체크박스 클릭
      2. page.locator(".recharts-responsive-container").count() >= 3 확인
      3. "GPU" 텍스트 포함 라벨 존재 확인
      4. 스크린샷 캡처
    Expected Result: 3개 이상 차트 (TPS, P99, GPU Eff.)
    Failure Indicators: 차트 2개만 표시
    Evidence: .sisyphus/evidence/task-5-gpu-chart.png
  ```

  **Commit**: YES (groups with Task 3)
  - Message: `feat(frontend): add model name and GPU efficiency to benchmark UI`
  - Files: `frontend/src/pages/BenchmarkPage.jsx`

- [x] 6. 백엔드 + 프론트엔드 테스트

  **What to do**:
  - **백엔드** `backend/tests/test_model_resolver.py` 신규 생성:
    - `test_resolve_model_name_success`: httpx 모킹으로 정상 해석 확인
    - `test_resolve_model_name_fallback`: 연결 실패 시 fallback 반환
    - `test_resolve_model_name_empty_data`: 빈 data 배열 시 fallback 반환
  - **백엔드** `backend/tests/test_benchmark.py` 확장:
    - `test_by_model_endpoint_empty`: 벤치마크 없을 때 빈 응답
    - `test_by_model_grouping`: 다른 모델 저장 후 그룹핑 확인
    - `test_by_model_gpu_efficiency`: GPU 효율 계산 정확성
    - `test_by_model_gpu_zero`: GPU=0일 때 null 반환
  - **프론트엔드** `frontend/src/pages/BenchmarkPage.test.jsx` 신규/확장:
    - `test_model_column_exists`: Model 컬럼 헤더 존재
    - `test_gpu_eff_column_exists`: GPU Eff. 컬럼 헤더 존재
  - 기존 테스트 패턴 준수 (conftest.py 픽스처, @testing-library/react)

  **Must NOT do**:
  - 기존 테스트 수정/삭제
  - 통합 테스트(integration marker) 추가

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
    - Reason: 백엔드 + 프론트엔드 모두 테스트. httpx 모킹, TestClient, @testing-library/react.
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Wave 3 (sequential — 모든 구현 완료 후)
  - **Blocks**: F1-F4
  - **Blocked By**: Tasks 4, 5

  **References**:

  **Pattern References**:
  - `backend/tests/conftest.py` — TestClient 설정 패턴
  - `backend/tests/test_benchmark.py` — 기존 벤치마크 테스트 패턴
  - `backend/tests/test_tuner.py` — httpx 모킹 패턴
  - `frontend/src/` 내 기존 `*.test.jsx` — 컴포넌트 테스트 패턴

  **API/Type References**:
  - `backend/services/model_resolver.py` (Task 1) — 테스트 대상
  - `backend/routers/benchmark.py` `GET /by-model` (Task 2) — 테스트 대상
  - `frontend/src/pages/BenchmarkPage.jsx` (Task 5) — 테스트 대상

  **WHY Each Reference Matters**:
  - `conftest.py`: TestClient 패턴 일관성
  - 기존 테스트: 프로젝트 테스트 스타일(assert, mock) 준수

  **Acceptance Criteria**:
  - [x] `python3 -m pytest tests/ -x -q -m "not integration"` — 전체 PASS
  - [x] `cd frontend && npx vitest run` — 전체 PASS
  - [x] model_resolver 테스트 3+ PASS
  - [x] benchmark by-model 테스트 4+ PASS

  **QA Scenarios**:

  ```
  Scenario: 전체 백엔드 테스트 통과
    Tool: Bash
    Preconditions: backend/ 디렉토리
    Steps:
      1. python3 -m pytest tests/ -x -q -m "not integration" --tb=short
      2. 출력에 "failed" 없음 확인
    Expected Result: 0 failures, all passed
    Failure Indicators: "FAILED", "ERROR"
    Evidence: .sisyphus/evidence/task-6-backend-tests.txt

  Scenario: 전체 프론트엔드 테스트 통과
    Tool: Bash
    Preconditions: frontend/ 디렉토리
    Steps:
      1. npx vitest run --reporter=verbose
      2. 출력에 "fail" 없음 확인
    Expected Result: 0 failures, all passed
    Failure Indicators: "FAIL", "Error"
    Evidence: .sisyphus/evidence/task-6-frontend-tests.txt
  ```

  **Commit**: YES
  - Message: `test: add model resolver and benchmark tests`
  - Files: `backend/tests/test_model_resolver.py`, `backend/tests/test_benchmark.py`, `frontend/src/pages/BenchmarkPage.test.jsx`
  - Pre-commit: `python3 -m pytest tests/ -x -q -m "not integration" && cd ../frontend && npx vitest run`

---

## Final Verification Wave

> 4 review agents run in PARALLEL. ALL must APPROVE. Rejection → fix → re-run.

- [x] F1. **Plan Compliance Audit** — `oracle`
  Read the plan end-to-end. For each "Must Have": verify implementation exists (read file, curl endpoint, run command). For each "Must NOT Have": search codebase for forbidden patterns — reject with file:line if found. Check evidence files exist in .sisyphus/evidence/. Compare deliverables against plan.
  Output: `Must Have [N/N] | Must NOT Have [N/N] | Tasks [N/N] | VERDICT: APPROVE/REJECT`

- [x] F2. **Code Quality Review** — `unspecified-high`
  Run linter + `python3 -m pytest tests/ -x -q -m "not integration"` + `cd frontend && npx vitest run`. Review all changed files for: empty catches, console.log in prod, commented-out code, unused imports. Check AI slop: excessive comments, over-abstraction.
  Output: `Build [PASS/FAIL] | Lint [PASS/FAIL] | Tests [N pass/N fail] | Files [N clean/N issues] | VERDICT`

- [x] F3. **Real Manual QA** — `unspecified-high` (+ `playwright` skill)
  Start from clean state. Execute EVERY QA scenario from EVERY task — follow exact steps, capture evidence. Test cross-task integration (load test with auto model → benchmark saved with resolved name → benchmark table shows it). Test edge case: GPU util = 0 → "—" display. Save to `.sisyphus/evidence/final-qa/`.
  Output: `Scenarios [N/N pass] | Integration [N/N] | Edge Cases [N tested] | VERDICT`

- [x] F4. **Scope Fidelity Check** — `deep`
  For each task: read "What to do", read actual diff. Verify 1:1 — everything in spec was built, nothing beyond spec was built. Check "Must NOT do" compliance. **특히 확인**: 새로운 페이지/탭이 추가되지 않았는지 (폐기된 5번째 탭). Flag unaccounted changes.
  Output: `Tasks [N/N compliant] | Contamination [CLEAN/N issues] | Unaccounted [CLEAN/N files] | VERDICT`

---

## Commit Strategy

| After Task(s) | Commit Message | Files |
|---------------|----------------|-------|
| 1 | `feat(backend): extract model name resolver utility` | `backend/services/model_resolver.py`, `backend/services/auto_tuner.py` |
| 2 | `feat(api): add model-grouped benchmark endpoint with GPU efficiency` | `backend/routers/benchmark.py` |
| 3, 5 | `feat(frontend): add model name and GPU efficiency to benchmark UI` | `frontend/src/mockData.js`, `frontend/src/pages/BenchmarkPage.jsx` |
| 4 | `feat(backend): auto-resolve model name on load test start` | `backend/routers/load_test.py` |
| 6 | `test: add model resolver and benchmark tests` | `backend/tests/test_model_resolver.py`, `backend/tests/test_benchmark.py`, `frontend/src/pages/BenchmarkPage.test.jsx` |

---

## Success Criteria

### Verification Commands
```bash
# Backend tests
cd backend && python3 -m pytest tests/ -x -q -m "not integration"  # Expected: all pass

# Frontend tests
cd frontend && npx vitest run  # Expected: all pass

# API check — model-grouped benchmarks
curl -s http://localhost:8000/api/benchmark/by-model | python3 -m json.tool  # Expected: grouped JSON

# Frontend build
cd frontend && npm run build  # Expected: 0 errors
```

### Final Checklist
- [x] model "auto" 입력 시 실제 모델명 해석 확인
- [x] 벤치마크 테이블에 모델명 + GPU 효율 컬럼 표시
- [x] GPU 사용률 0일 때 GPU 효율 "—" 표시
- [x] 벤치마크 비교 차트에 GPU 효율 차트 포함
- [x] Mock 데이터 모드 정상 동작
- [x] 새 탭/페이지 없음 확인 (폐기됨)
- [x] 모든 테스트 통과
