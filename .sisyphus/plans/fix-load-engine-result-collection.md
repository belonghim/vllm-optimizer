# Fix: Load Engine 결과 수집 버그 수정

## TL;DR

> **Quick Summary**: `load_engine.py`의 `run()` 메서드에서 `asyncio.wait` 필터 버그로 인해 부하 테스트 결과의 ~90%가 유실되는 문제를 수정한다. `processed_tasks` 셋 기반 추적으로 모든 태스크 결과를 빠짐없이 수집하도록 변경.
> 
> **Deliverables**:
> - `backend/services/load_engine.py` — `run()` 메서드 결과 수집 로직 수정
> - `backend/tests/test_load_engine_run.py` — 5개 비동기 단위 테스트 (회귀 방지)
> 
> **Estimated Effort**: Quick
> **Parallel Execution**: NO — 엄격한 TDD 순서 필요 (RED → GREEN → VERIFY)
> **Critical Path**: Task 1 (테스트 작성) → Task 2 (버그 수정) → Task 3 (검증 + 커밋)

---

## Context

### Original Request
부하 테스트에서 Total Requests=200을 설정했으나 실제 수집된 결과가 18개뿐이고 나머지 182개가 유실되는 문제 수정 요청.

### Interview Summary
**Key Discussions**:
- 스크린샷 분석: Total Requests=200, Success=18, Failed=0, Success Rate=100%, COMPLETED 상태
- RPS=10, Concurrency=20, Latency~135ms 설정에서 재현

**Research Findings**:
- `load_engine.py` 172번 라인: `asyncio.wait([t for t in tasks if not t.done()], timeout=0)` — sleep 중 완료된 태스크를 필터링하여 결과 유실
- 최종 gather (199번 라인)에서도 동일한 필터 적용 → 이중 유실
- 기존 테스트는 `run()` 메서드를 stub으로 대체하여 이 버그를 감지하지 못함

### Metis Review
**Identified Gaps** (addressed):
- Bug 3: 최종 gather에서 `completed_requests`/`failed_requests` 카운터 미증가 → 수정에 포함
- Bug 4: `asyncio.wait([])` ValueError 위험 → `asyncio.wait` 제거로 해결
- Bug 5: `_compute_stats()`의 `success`/`failed` 소스 불일치 → **별도 이슈로 분리 (이번 범위 외)**
- 테스트 파일 분리 필요 → `test_load_engine_run.py` 신규 생성
- `pytest-mock` 미설치 → `unittest.mock` 사용

---

## Work Objectives

### Core Objective
`LoadTestEngine.run()`이 생성한 모든 태스크의 결과를 빠짐없이 수집하도록 결과 수집 로직을 수정한다.

### Concrete Deliverables
- `backend/services/load_engine.py` — `run()` 메서드 내 결과 수집 로직 수정 (약 30줄 변경)
- `backend/tests/test_load_engine_run.py` — 5개 비동기 단위 테스트

### Definition of Done
- [x] `python3 -m pytest backend/tests/test_load_engine_run.py -v` → 5 passed
- [x] `python3 -m pytest backend/tests/ -v -m "not integration"` → all passed, 0 errors

### Must Have
- 모든 태스크 결과 수집: `len(state.results) == config.total_requests`
- 카운터 정합성: `state.completed_requests + state.failed_requests == config.total_requests`
- 중복 수집 방지: `len({r.req_id for r in state.results}) == config.total_requests`
- `asyncio.wait([])` ValueError 방지
- 기존 7개 테스트 무변경 통과

### Must NOT Have (Guardrails)
- `_compute_stats()` 수정 금지 — Bug 5는 별도 이슈
- `stop()` 동작 변경 금지
- 개별 `single_request` 태스크 취소 로직 추가 금지
- `run()` 반환 타입/키 변경 금지
- SSE broadcast 포맷 변경 금지
- `_state_lock` 사용 패턴 변경 금지
- `pytest-mock` 의존성 추가 금지 — `unittest.mock` 사용
- `isolated_client` 픽스처 사용 금지 (새 테스트에서)
- retry 로직 추가 금지
- `single_request`를 클래스 메서드로 리팩토링 금지
- 진행 broadcast를 최종 gather 루프에 추가 금지

---

## Verification Strategy (MANDATORY)

> **ZERO HUMAN INTERVENTION** — ALL verification is agent-executed. No exceptions.

### Test Decision
- **Infrastructure exists**: YES
- **Automated tests**: YES (TDD — RED → GREEN → REFACTOR)
- **Framework**: pytest + pytest-asyncio
- **Import style**: bare import (`from services.load_engine import ...`)
- **Mock strategy**: `unittest.mock.patch` + `AsyncMock` (stdlib only)

### QA Policy
Every task MUST include agent-executed QA scenarios.
Evidence saved to `.sisyphus/evidence/task-{N}-{scenario-slug}.{ext}`.

- **Unit tests**: Bash — `python3 -m pytest` 명령 실행 + 출력 검증
- **Code quality**: `lsp_diagnostics` — 타입 에러 확인

---

## Execution Strategy

### Parallel Execution Waves

```
Wave 1 (Start Immediately):
└── Task 1: 실패하는 비동기 단위 테스트 작성 [ultrabrain]

Wave 2 (After Wave 1):
└── Task 2: load_engine.py run() 메서드 버그 수정 [ultrabrain]

Wave 3 (After Wave 2):
└── Task 3: 전체 테스트 스위트 검증 + 원자적 커밋 [quick + git-master]

Wave FINAL (After ALL tasks):
├── Task F1: Plan compliance audit [oracle]
├── Task F2: Code quality review [unspecified-high]
├── Task F3: Real manual QA [unspecified-high]
└── Task F4: Scope fidelity check [deep]

Critical Path: Task 1 → Task 2 → Task 3 → F1-F4
Parallel Speedup: N/A (strict TDD sequence)
Max Concurrent: 1 (Waves 1-3), 4 (Final Wave)
```

### Dependency Matrix

| Task | Blocked By | Blocks |
|------|-----------|--------|
| 1    | —         | 2, 3   |
| 2    | 1         | 3      |
| 3    | 2         | F1-F4  |
| F1-F4| 3         | —      |

### Agent Dispatch Summary

- **Wave 1**: 1 task — T1 → `ultrabrain`
- **Wave 2**: 1 task — T2 → `ultrabrain`
- **Wave 3**: 1 task — T3 → `quick` + `git-master`
- **FINAL**: 4 tasks — F1 → `oracle`, F2 → `unspecified-high`, F3 → `unspecified-high`, F4 → `deep`

---

## TODOs

---

- [x] 1. 실패하는 비동기 단위 테스트 작성 (TDD RED phase)

  **What to do**:
  - `backend/tests/test_load_engine_run.py` 신규 생성
  - `unittest.mock.patch` + `AsyncMock`로 `httpx.AsyncClient` 모킹
  - 비스트리밍 경로 (`stream=False`) 모킹: `client.post` → `{"usage": {"completion_tokens": 10}}`
  - 아래 5개 비동기 테스트 작성:
    1. `test_run_collects_all_results_when_tasks_complete_during_sleep` — config: total_requests=20, rps=5, concurrency=20, stream=False. 인스턴트 응답 모킹. assert: `len(state.results) == 20`, `state.completed_requests == 20`, `len({r.req_id for r in state.results}) == 20`, `final_stats["total"] == 20`
    2. `test_run_counter_matches_result_count` — config: total_requests=10, rps=0 (unlimited), stream=False. assert: `state.completed_requests + state.failed_requests == 10`
    3. `test_run_no_valueerror_when_all_tasks_done_instantly` — config: total_requests=5, rps=0, stream=False. assert: `run()` 완료 without ValueError
    4. `test_run_failed_requests_counted_correctly` — 짝수 req_id에서 예외 발생하는 모킹. config: total_requests=10, rps=0, stream=False. assert: `state.failed_requests == 5`, `len(state.results) == 10`
    5. `test_run_no_duplicate_results` — config: total_requests=15, rps=10, concurrency=15, stream=False. assert: `len(req_ids) == len(set(req_ids))`
  - 모든 새 테스트가 **FAIL** (not ERROR) 상태인지 확인
  - 기존 7개 테스트가 여전히 PASS인지 확인

  **Must NOT do**:
  - `isolated_client` 픽스처 사용 금지
  - `pytest-mock` 사용 금지
  - `time.sleep()` 사용 금지 — 결정론적, 빠른 테스트 유지 (<1s)
  - 기존 테스트 파일 수정 금지

  **Recommended Agent Profile**:
  - **Category**: `ultrabrain`
    - Reason: 비동기 동시성 버그 재현 테스트 — asyncio 이벤트 루프 시맨틱, mock context manager 프로토콜 정확히 이해 필요
  - **Skills**: []
  - **Skills Evaluated but Omitted**:
    - `playwright`: 브라우저 테스트 아님
    - `git-master`: 이 단계에서 git 작업 없음

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Wave 1 (단독)
  - **Blocks**: Task 2, Task 3
  - **Blocked By**: None

  **References**:

  **Pattern References** (existing code to follow):
  - `backend/tests/test_load_test.py:103-139` — `test_compute_stats_includes_total_requested`: `LoadTestEngine` 직접 인스턴스화 + `_state` 설정 패턴. 새 테스트도 이 패턴 따라서 엔진 직접 테스트
  - `backend/tests/conftest.py:20-21` — `sys.path.insert(0, ...)` 패턴: 새 테스트 파일에서도 동일한 path 설정 필요
  - `backend/tests/conftest.py:208-211` — `_stub_run` 패턴: **이것과 다르게** 실제 `run()` 메서드를 호출해야 함 (stub하지 않음)

  **API/Type References** (contracts to implement against):
  - `backend/models/load_test.py:14-24` — `LoadTestConfig`: 테스트 config 생성 시 사용. `stream=False` 설정 필수
  - `backend/models/load_test.py:27-35` — `RequestResult`: `req_id`, `success`, `latency`, `error` 필드 확인
  - `backend/services/load_engine.py:26-32` — `LoadTestState`: `results`, `completed_requests`, `failed_requests` 필드

  **Implementation References** (bug reproduction target):
  - `backend/services/load_engine.py:90-232` — `run()` 메서드 전체: 이 메서드를 실제로 호출하여 버그 재현
  - `backend/services/load_engine.py:110-161` — `single_request()` 내부 함수: httpx 모킹 시 이 호출 경로 이해 필요
  - `backend/services/load_engine.py:163-194` — 요청 생성 루프: 버그가 있는 `asyncio.wait` 호출 위치

  **External References**:
  - `unittest.mock.AsyncMock` 공식 문서: httpx async context manager 모킹에 필요
  - `pytest-asyncio` 사용법: `@pytest.mark.asyncio` 데코레이터로 비동기 테스트 실행

  **WHY Each Reference Matters**:
  - `test_load_test.py:103-139`: 엔진 직접 테스트의 기존 패턴 확인 — 이 스타일로 작성
  - `conftest.py:20-21`: path 설정이 없으면 bare import 실패
  - `LoadTestConfig`: `stream=False` 설정 안 하면 스트리밍 모킹이 필요해져서 복잡도 증가
  - `run()` 메서드: 실제 호출해서 버그를 재현해야 하므로 전체 흐름 이해 필수
  - `single_request()`: httpx 모킹 지점이 여기 → `httpx.AsyncClient` 패치 위치 결정

  **Acceptance Criteria**:

  - [x] `backend/tests/test_load_engine_run.py` 파일 존재
  - [x] `python3 -m pytest backend/tests/test_load_engine_run.py --collect-only` → 5개 이상 테스트 수집
  - [x] `python3 -m pytest backend/tests/test_load_engine_run.py -v` → 5개 FAILED (ERROR 아님)
  - [x] `python3 -m pytest backend/tests/test_load_test.py -v` → 기존 7개 모두 passed

  **QA Scenarios (MANDATORY)**:

  ```
  Scenario: 새 테스트 파일이 pytest에 의해 수집됨
    Tool: Bash
    Preconditions: backend/tests/test_load_engine_run.py 작성 완료
    Steps:
      1. python3 -m pytest backend/tests/test_load_engine_run.py --collect-only 실행
      2. 출력에서 "test_run_collects_all_results", "test_run_counter_matches", "test_run_no_valueerror", "test_run_failed_requests", "test_run_no_duplicate" 문자열 확인
    Expected Result: 5개 이상 테스트가 수집되어 출력에 표시됨
    Failure Indicators: "no tests ran", "ERROR", "ModuleNotFoundError"
    Evidence: .sisyphus/evidence/task-1-test-collection.txt

  Scenario: 새 테스트가 FAIL 상태 (RED phase 확인)
    Tool: Bash
    Preconditions: 동일
    Steps:
      1. python3 -m pytest backend/tests/test_load_engine_run.py -v 2>&1 실행
      2. 출력에서 "FAILED" 횟수 확인 (5개 이상)
      3. "ERROR" 가 아닌 "FAILED" 인지 확인 (테스트가 실행은 되되 assertion 실패)
    Expected Result: 5개 테스트 모두 FAILED (assertion error)
    Failure Indicators: "ERROR" (import error, fixture error 등), "PASSED" (버그 없이 통과)
    Evidence: .sisyphus/evidence/task-1-test-red-phase.txt

  Scenario: 기존 테스트 무영향 확인
    Tool: Bash
    Preconditions: 동일
    Steps:
      1. python3 -m pytest backend/tests/test_load_test.py -v 실행
      2. 출력에서 "passed" 확인
    Expected Result: 7 passed, 0 failed, 0 errors
    Failure Indicators: "FAILED", "ERROR"
    Evidence: .sisyphus/evidence/task-1-existing-tests.txt
  ```

  **Commit**: NO (Task 3에서 일괄 커밋)

---

- [x] 2. load_engine.py run() 메서드 버그 수정 (TDD GREEN phase)

  **What to do**:
  - `backend/services/load_engine.py`의 `run()` 메서드만 수정
  - **변경 1**: `tasks = []` (100번 라인) 뒤에 `processed_tasks: set[asyncio.Task] = set()` 추가
  - **변경 2**: 171~191번 라인 (`asyncio.wait` 블록 + 내부 for 루프)을 다음으로 교체:
    ```python
    # 완료된 태스크 처리 — sleep 중 완료된 태스크 포함
    for t in [t for t in tasks if t.done() and t not in processed_tasks]:
        processed_tasks.add(t)
        result = await t
        async with self._state_lock:
            self._state.results.append(result)
            if result.success:
                self._state.completed_requests += 1
            else:
                self._state.failed_requests += 1
        stats = self._compute_stats()
        await self._broadcast({"type": "progress", "data": stats})
    ```
  - **변경 3**: 196~205번 라인 (최종 gather 섹션)을 다음으로 교체:
    ```python
    # 남은 태스크 완료 대기 (미처리 태스크만)
    remaining_tasks = [t for t in tasks if t not in processed_tasks]
    if remaining_tasks:
        remaining_results = await asyncio.gather(*remaining_tasks, return_exceptions=True)
        for result in remaining_results:
            if isinstance(result, RequestResult):
                async with self._state_lock:
                    self._state.results.append(result)
                    if result.success:
                        self._state.completed_requests += 1
                    else:
                        self._state.failed_requests += 1
    ```
  - 수정 후 모든 새 테스트 5개 PASS + 기존 7개 PASS 확인

  **Must NOT do**:
  - `_compute_stats()` 수정 금지
  - `stop()` 동작 변경 금지
  - `run()` 반환 타입/키 변경 금지
  - broadcast 포맷 변경 금지
  - `_state_lock` 패턴 변경 금지
  - `run()` 외부의 메서드 수정 금지

  **Recommended Agent Profile**:
  - **Category**: `ultrabrain`
    - Reason: asyncio 시맨틱 정확성이 핵심 — 잘못된 수정은 데이터 유실/중복/데드락 유발 가능
  - **Skills**: []
  - **Skills Evaluated but Omitted**:
    - `playwright`: 브라우저 작업 아님
    - `git-master`: 이 단계에서 커밋하지 않음

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Wave 2 (단독)
  - **Blocks**: Task 3
  - **Blocked By**: Task 1

  **References**:

  **Implementation References** (수정 대상):
  - `backend/services/load_engine.py:90-232` — `run()` 메서드 전체. 수정은 이 메서드 내부에서만 발생
  - `backend/services/load_engine.py:100` — `tasks = []` 라인: 여기 바로 뒤에 `processed_tasks` 선언
  - `backend/services/load_engine.py:163-194` — 요청 생성 루프: `asyncio.wait` 호출을 `processed_tasks` 기반으로 교체
  - `backend/services/load_engine.py:196-206` — 최종 gather 섹션: 필터 교체 + 카운터 업데이트 추가

  **Type References** (import 필요):
  - `backend/models/load_test.py:27-35` — `RequestResult`: 최종 gather에서 `isinstance` 체크에 사용 (이미 import되어 있음)

  **Context References** (수정 시 주의):
  - `backend/services/load_engine.py:40` — `self._state_lock`: 모든 `_state.results`와 카운터 변경은 이 lock 아래서 수행
  - `backend/services/load_engine.py:64-68` — `_broadcast()`: progress 이벤트 포맷 유지 필수
  - `backend/services/load_engine.py:239-274` — `_compute_stats()`: 이 메서드는 수정하지 않음. results 리스트와 카운터가 정확하면 통계도 정확해짐

  **WHY Each Reference Matters**:
  - `run()` 100번 라인: `processed_tasks` 선언 위치 — `tasks` 바로 뒤여야 함
  - 163-194번 라인: 핵심 버그 위치 — 이 블록 전체를 교체
  - 196-206번 라인: 보조 버그 위치 — 필터 + 카운터 수정
  - `_state_lock`: lock 없이 state 변경 시 경쟁 조건 발생 가능 (asyncio에서는 실제로 안전하지만 패턴 일관성 유지)

  **Acceptance Criteria**:

  - [x] `python3 -m pytest backend/tests/test_load_engine_run.py -v` → 5 passed, 0 failed
  - [x] `python3 -m pytest backend/tests/test_load_test.py -v` → 7 passed, 0 failed
  - [x] `python3 -m pytest backend/tests/ -v -m "not integration"` → all passed
  - [x] `lsp_diagnostics` on `load_engine.py` → 새로운 에러 없음
  - [x] diff가 `run()` 메서드 내부만 변경: `_compute_stats()`, `stop()`, `__init__()` 등 미변경

  **QA Scenarios (MANDATORY)**:

  ```
  Scenario: 모든 새 테스트 PASS (GREEN phase)
    Tool: Bash
    Preconditions: load_engine.py 수정 완료
    Steps:
      1. python3 -m pytest backend/tests/test_load_engine_run.py -v 실행
      2. 출력에서 "5 passed" 확인
      3. "FAILED" 또는 "ERROR" 가 없는지 확인
    Expected Result: 5 passed, 0 failed, 0 errors
    Failure Indicators: "FAILED", "ERROR", 5 미만의 passed
    Evidence: .sisyphus/evidence/task-2-green-phase.txt

  Scenario: 기존 테스트 회귀 없음
    Tool: Bash
    Preconditions: 동일
    Steps:
      1. python3 -m pytest backend/tests/test_load_test.py -v 실행
      2. "7 passed" 확인
    Expected Result: 7 passed, 0 failed
    Failure Indicators: "FAILED", "ERROR"
    Evidence: .sisyphus/evidence/task-2-no-regression.txt

  Scenario: 전체 단위 테스트 스위트 통과
    Tool: Bash
    Preconditions: 동일
    Steps:
      1. python3 -m pytest backend/tests/ -v -m "not integration" 실행
      2. "failed" 가 0인지 확인
    Expected Result: all passed, 0 failed, 0 errors
    Failure Indicators: 임의의 "FAILED" 또는 "ERROR"
    Evidence: .sisyphus/evidence/task-2-full-suite.txt

  Scenario: 타입 에러 없음
    Tool: lsp_diagnostics
    Preconditions: 동일
    Steps:
      1. lsp_diagnostics(filePath="backend/services/load_engine.py", severity="error")
      2. 새로운 에러가 없는지 확인
    Expected Result: 0개 에러 (또는 기존과 동일)
    Failure Indicators: 새로운 에러 메시지
    Evidence: .sisyphus/evidence/task-2-diagnostics.txt
  ```

  **Commit**: NO (Task 3에서 일괄 커밋)

---

- [x] 3. 전체 테스트 스위트 검증 + 원자적 커밋

  **What to do**:
  - `python3 -m pytest backend/tests/ -v -m "not integration"` 실행하여 전체 통과 확인
  - 아래 2개 파일만 포함하는 원자적 커밋 생성:
    - `backend/services/load_engine.py`
    - `backend/tests/test_load_engine_run.py`
  - 커밋 메시지:
    ```
    fix(load_engine): collect all task results regardless of completion timing
    
    Tasks completed during asyncio.sleep(interval) had .done()=True and were
    filtered out of both the collection loop and the final asyncio.gather,
    causing ~90% of results to be silently dropped when rps>0.
    
    Replace filter-based task selection with a processed_tasks set that tracks
    which tasks have been collected. Also fixes missing counter updates in the
    final gather section and eliminates potential ValueError from asyncio.wait([]).
    ```
  - 커밋 후 diff가 정확히 2개 파일만 포함하는지 확인

  **Must NOT do**:
  - 다른 파일 커밋에 포함 금지
  - `--amend` 사용 금지
  - `push` 금지 (사용자가 명시적으로 요청하지 않는 한)

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: pytest 실행 + git commit은 단순 기계적 작업
  - **Skills**: [`git-master`]
    - `git-master`: 원자적 커밋 생성 전문
  - **Skills Evaluated but Omitted**:
    - `playwright`: 해당 없음
    - `frontend-ui-ux`: 해당 없음

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Wave 3 (단독)
  - **Blocks**: F1-F4
  - **Blocked By**: Task 2

  **References**:

  **Verification References**:
  - `pyproject.toml` — pytest markers 설정: `-m "not integration"` 마커 확인
  - `backend/tests/` — 전체 테스트 디렉토리: 모든 test_*.py 파일이 통과해야 함

  **WHY Each Reference Matters**:
  - `pyproject.toml`: 올바른 pytest 마커 사용 확인
  - `backend/tests/`: 전체 스위트 범위 확인

  **Acceptance Criteria**:

  - [x] `python3 -m pytest backend/tests/ -v -m "not integration"` → all passed
  - [x] `git log --oneline -1` → `fix(load_engine): collect all task results regardless of completion timing`
  - [x] `git diff HEAD~1 --name-only` → 정확히 2개 파일만 출력

  **QA Scenarios (MANDATORY)**:

  ```
  Scenario: 커밋 범위 검증
    Tool: Bash
    Preconditions: git commit 완료
    Steps:
      1. git diff HEAD~1 --name-only 실행
      2. 출력이 정확히 "backend/services/load_engine.py"와 "backend/tests/test_load_engine_run.py" 2줄인지 확인
    Expected Result: 2개 파일만 변경됨
    Failure Indicators: 3개 이상 파일, 또는 예상 외 파일 포함
    Evidence: .sisyphus/evidence/task-3-commit-scope.txt

  Scenario: 커밋 메시지 형식 확인
    Tool: Bash
    Preconditions: 동일
    Steps:
      1. git log --oneline -1 실행
      2. "fix(load_engine):" 접두사 확인
    Expected Result: 커밋 메시지가 conventional commit 형식
    Failure Indicators: 접두사 누락, 다른 형식
    Evidence: .sisyphus/evidence/task-3-commit-message.txt
  ```

  **Commit**: YES
  - Message: `fix(load_engine): collect all task results regardless of completion timing`
  - Files: `backend/services/load_engine.py`, `backend/tests/test_load_engine_run.py`
  - Pre-commit: `python3 -m pytest backend/tests/ -v -m "not integration"`

---

## Final Verification Wave (MANDATORY — after ALL implementation tasks)

> 4 review agents run in PARALLEL. ALL must APPROVE. Rejection → fix → re-run.

- [x] F1. **Plan Compliance Audit** — `oracle`
  Read the plan end-to-end. For each "Must Have": verify implementation exists (read file, run command). For each "Must NOT Have": search codebase for forbidden patterns — reject with file:line if found. Check evidence files exist in `.sisyphus/evidence/`. Compare deliverables against plan.
  Output: `Must Have [N/N] | Must NOT Have [N/N] | Tasks [N/N] | VERDICT: APPROVE/REJECT`

- [x] F2. **Code Quality Review** — `unspecified-high`
  Run full test suite + lsp_diagnostics. Review `load_engine.py` changes for: `as any`/type:ignore, empty catches, print statements, commented-out code, unused imports. Verify the fix doesn't introduce race conditions or duplicate collection. Check no `asyncio.wait` with empty list remains.
  Output: `Tests [PASS/FAIL] | Diagnostics [PASS/FAIL] | Code Review [N issues] | VERDICT`

- [x] F3. **Real Manual QA** — `unspecified-high`
  Start from clean state. Execute EVERY QA scenario from EVERY task — follow exact steps, capture evidence. Test cross-task: run all tests together, not just individually. Verify evidence files exist.
  Output: `Scenarios [N/N pass] | Evidence [N/N] | VERDICT`

- [x] F4. **Scope Fidelity Check** — `deep`
  For each task: read "What to do", read actual diff (`git diff HEAD~1`). Verify 1:1 — everything in spec was built (no missing), nothing beyond spec was built (no creep). Check "Must NOT do" compliance: `_compute_stats()` unchanged, `stop()` unchanged, no new dependencies added. Flag unaccounted changes.
  Output: `Tasks [N/N compliant] | Creep [CLEAN/N issues] | Unaccounted [CLEAN/N files] | VERDICT`

---

## Commit Strategy

| Wave | Commit | Message | Files |
|------|--------|---------|-------|
| 3    | 1개    | `fix(load_engine): collect all task results regardless of completion timing` | `backend/services/load_engine.py`, `backend/tests/test_load_engine_run.py` |

---

## Success Criteria

### Verification Commands
```bash
# 1. 새 테스트 통과
python3 -m pytest backend/tests/test_load_engine_run.py -v
# Expected: 5 passed

# 2. 기존 테스트 회귀 없음
python3 -m pytest backend/tests/test_load_test.py -v
# Expected: 7 passed

# 3. 전체 단위 테스트 스위트 통과
python3 -m pytest backend/tests/ -v -m "not integration"
# Expected: all passed, 0 errors

# 4. 커밋 범위 정확
git diff HEAD~1 --name-only
# Expected: backend/services/load_engine.py
#           backend/tests/test_load_engine_run.py
```

### Final Checklist
- [x] All "Must Have" present: 모든 태스크 결과 수집, 카운터 정합성, 중복 방지
- [x] All "Must NOT Have" absent: _compute_stats 미수정, stop 미변경, broadcast 포맷 유지
- [x] All tests pass: 새 5개 + 기존 7개 + 전체 스위트

---

## Out-of-Scope Follow-ups (별도 이슈로 추적)

| # | 내용 | 이유 |
|---|------|------|
| 1 | Bug 5: `_compute_stats()`의 `success`/`failed` 소스 불일치 통합 | 프론트엔드 소비하는 통계 포맷 변경 → 별도 검토 필요 |
| 2 | `stop()` 호출 시 in-flight 태스크 취소 로직 | 현재 graceful drain 동작 유지 |
| 3 | TTFT=0 / TPS=0 스트리밍 토큰 카운팅 문제 | 별도 버그 — 결과 수집과 무관 |
