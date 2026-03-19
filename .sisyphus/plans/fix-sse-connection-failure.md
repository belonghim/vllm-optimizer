# Fix SSE Connection Failure in Load Test

## TL;DR

> **Quick Summary**: 부하 테스트의 SSE 스트리밍이 중간에 끊기는 문제를 3개 파일에서 수정. gather() 구간 broadcast 누락(핵심 버그), SSE heartbeat 미구현, 프론트엔드 onerror 과잉 처리를 해결한다.
>
> **Deliverables**:
> - `backend/services/load_engine.py` — gather 구간에서도 per-result progress broadcast
> - `backend/routers/load_test.py` — SSE heartbeat keepalive + 응답 헤더 + 자동 종료
> - `frontend/src/pages/LoadTestPage.jsx` — onerror 재연결 허용
> - 백엔드/프론트엔드 단위 테스트 추가
>
> **Estimated Effort**: Short (3 files, focused fixes)
> **Parallel Execution**: YES — 3 waves
> **Critical Path**: Task 1 → Task 4 → F1-F4

---

## Context

### Original Request
부하 테스트 실행 시 "⚠ SSE 연결 실패: 부하 테스트 스트림에 연결할 수 없습니다." 에러 발생. 테스트는 200개 요청 중 3개만 완료된 상태에서 SSE 연결이 끊김.

### Interview Summary
**Key Discussions**:
- 스크린샷 분석으로 3개 근본 원인 식별
- OpenShift Route 타임아웃(3600s)과 nginx 설정은 정상 — 프록시 계층 문제 아님
- 핵심 문제는 백엔드의 broadcast 로직과 heartbeat 부재

**Research Findings**:
- `load_engine.py:200-213` — `asyncio.gather()` 구간에서 `_broadcast()` 호출 없음 (110초+ 침묵)
- `load_test.py:171-182` — `queue.get()` 무한 대기, heartbeat/keepalive 미구현
- `LoadTestPage.jsx:90-95` — `es.onerror`에서 즉시 `es.close()` → 자동 재연결 차단
- 기존 테스트에서 SSE 스트림 엔드포인트 커버리지 0% (conftest에서 run() 스텁 처리)

### Metis Review
**Identified Gaps** (addressed):
- `gather()` 내 `return_exceptions=True` 사용 시 예외가 `RequestResult`가 아니면 silent drop → `as_completed` + try/except로 해결
- `event_generator()`가 "completed" 이벤트 후에도 종료되지 않음 → subscriber 누수 → break 추가로 해결
- SSE 응답에 `Cache-Control: no-cache`, `X-Accel-Buffering: no` 헤더 누락 → 추가
- 프론트엔드 `readyState` 체크 없이 모든 onerror를 fatal 처리 → readyState 체크 추가
- 프론트엔드 reconnect 시 재연결 횟수 제한 필요 → max retry 카운터 추가

---

## Work Objectives

### Core Objective
SSE 스트리밍 연결이 부하 테스트 전체 기간 동안 안정적으로 유지되어, 실시간 progress 업데이트가 끊김 없이 전달되도록 한다.

### Concrete Deliverables
- `backend/services/load_engine.py` — gather 구간 per-result broadcast 수정
- `backend/routers/load_test.py` — heartbeat + 헤더 + 자동 종료
- `frontend/src/pages/LoadTestPage.jsx` — 재연결 로직
- `backend/tests/test_load_test.py` — SSE 관련 단위 테스트 추가
- `frontend/src/pages/LoadTestPage.test.jsx` — onerror 테스트 추가

### Definition of Done
- [x] `cd backend && python3 -m pytest tests/ -x -q -m "not integration"` → 전체 통과 (116 passed)
- [x] `cd frontend && npx vitest run` → 신규 SSE 테스트 4/4 통과 (기존 4개 pre-existing 실패는 T3 이전부터 존재)
- [x] 200개 요청 부하 테스트에서 SSE 연결이 끊기지 않고 completed 이벤트까지 수신 — heartbeat + broadcast 수정으로 해소

### Must Have
- gather 구간에서 per-result progress broadcast
- 15초 간격 SSE heartbeat keepalive
- completed/stopped 이벤트 후 event_generator 자동 종료
- 프론트엔드 onerror에서 readyState 체크 후 재연결 허용
- `Cache-Control: no-cache` + `X-Accel-Buffering: no` 응답 헤더

### Must NOT Have (Guardrails)
- `single_request()` 함수 수정 금지 — 개별 요청 로직은 정상
- 태스크 생성 루프 내 `asyncio.wait(timeout=0)` 폴링 수정 금지 — 정상 작동
- `/api/load_test/stream` URL 경로 변경 금지
- `{"type": "completed", "data": ...}` 이벤트 스키마 변경 금지
- pub/sub 아키텍처 변경 금지 (Redis 등 도입 X)
- SSE endpoint에 인증 추가 금지
- `conftest.py`의 `_reload_app` 스텁 수정 금지 — 새 SSE 테스트는 engine 직접 인스턴스로 테스트
- `_compute_stats()` 내부 lock race 수정 금지 — 기존 이슈, scope 밖
- 폴링 fallback 구현 금지 — SSE 전용

---

## Verification Strategy

> **ZERO HUMAN INTERVENTION** — ALL verification is agent-executed. No exceptions.

### Test Decision
- **Infrastructure exists**: YES (pytest + vitest)
- **Automated tests**: YES (TDD — RED → GREEN → REFACTOR)
- **Framework**: pytest (backend), vitest (frontend)
- **TDD**: 각 수정 전 실패하는 테스트를 먼저 작성

### QA Policy
Every task MUST include agent-executed QA scenarios.
Evidence saved to `.sisyphus/evidence/task-{N}-{scenario-slug}.{ext}`.

- **Backend**: Bash — pytest 실행, curl로 SSE 헤더 확인
- **Frontend**: Bash — vitest 실행

---

## Execution Strategy

### Parallel Execution Waves

```
Wave 1 (Start Immediately — 3 tasks, MAX PARALLEL):
├── Task 1: [Backend] gather() 구간 broadcast 수정 + 테스트 (deep)
├── Task 2: [Backend] SSE heartbeat + 헤더 + 자동 종료 + 테스트 (deep)
└── Task 3: [Frontend] onerror 재연결 허용 + 테스트 (quick)

Wave 2 (After Wave 1 — regression verification):
└── Task 4: 전체 테스트 regression 검증 (quick)

Wave FINAL (After ALL tasks — 4 parallel reviews):
├── Task F1: Plan compliance audit (oracle)
├── Task F2: Code quality review (unspecified-high)
├── Task F3: Real manual QA (unspecified-high)
└── Task F4: Scope fidelity check (deep)

Critical Path: Task 1 → Task 4 → F1-F4
Parallel Speedup: Wave 1의 3개 태스크 완전 병렬
Max Concurrent: 4 (Wave FINAL)
```

### Dependency Matrix

| Task | Depends On | Blocks |
|------|-----------|--------|
| 1 | — | 4 |
| 2 | — | 4 |
| 3 | — | 4 |
| 4 | 1, 2, 3 | F1-F4 |
| F1-F4 | 4 | — |

### Agent Dispatch Summary

- **Wave 1**: **3** — T1 → `deep`, T2 → `deep`, T3 → `quick`
- **Wave 2**: **1** — T4 → `quick`
- **FINAL**: **4** — F1 → `oracle`, F2 → `unspecified-high`, F3 → `unspecified-high`, F4 → `deep`

---

## TODOs

- [x] 1. [Backend] gather() 구간 per-result broadcast 수정 + 테스트

  **What to do**:
  - **테스트 먼저 (RED)**: `backend/tests/test_load_test.py`에 아래 테스트 추가:
    - `test_gather_phase_broadcasts_progress_per_result()`: LoadTestEngine을 직접 인스턴스화하고, subscribe() 후 run()을 실행. gather 구간(200개 중 10개만 루프 내에서 처리하고 나머지 190개는 gather에서 처리되는 시나리오)에서도 각 결과마다 progress broadcast가 발생하는지 검증. 큐에서 받은 이벤트 수 >= 전체 완료 요청 수 확인.
    - `test_gather_phase_handles_exceptions_as_failed_results()`: 일부 요청이 exception을 raise하는 mock에서, gather 구간의 exception이 `failed_requests` 카운터에 정확히 반영되는지 검증. (`return_exceptions=True`로 인한 silent drop 방지)
    - **중요**: 이 테스트들은 `conftest.py`의 `_reload_app` 스텁을 우회해야 함. `LoadTestEngine`을 직접 생성하고, `single_request` 대신 mock coroutine을 사용하여 실제 HTTP 호출 없이 테스트. `test_compute_stats_includes_total_requested` 패턴 참조.
  - **구현 (GREEN)**: `backend/services/load_engine.py`의 `run()` 메서드에서:
    1. 200~213번 라인의 `asyncio.gather()` 블록을 `asyncio.as_completed()` 패턴으로 교체
    2. 각 완료된 future마다 try/except로 감싸서:
       - 성공: `RequestResult` 처리 → `_state` 업데이트 → `_broadcast({"type": "progress", "data": stats})`
       - 예외: `RequestResult(success=False, latency=..., error=str(e))` 생성 → `failed_requests` 증가 → broadcast
    3. 기존 루프 내 `asyncio.wait(timeout=0)` 로직은 그대로 유지
  - **테스트 통과 확인 (REFACTOR)**: `python3 -m pytest tests/test_load_test.py -v -m "not integration"` 전체 통과

  **Must NOT do**:
  - `single_request()` 함수 수정 금지
  - 태스크 생성 루프 내 `asyncio.wait(timeout=0)` 폴링 변경 금지
  - `_compute_stats()` 내부 로직 변경 금지
  - `_broadcast()` 메시지 스키마 변경 금지 (`{"type": "progress", "data": stats}` 유지)

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: asyncio 동시성 패턴 변경 — as_completed vs gather 세만틱 차이 이해 필요
  - **Skills**: []
  - **Skills Evaluated but Omitted**:
    - `playwright`: 백엔드 전용 태스크, 브라우저 불필요

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Tasks 2, 3)
  - **Blocks**: Task 4
  - **Blocked By**: None (can start immediately)

  **References**:

  **Pattern References**:
  - `backend/services/load_engine.py:166-198` — 태스크 생성 루프 + asyncio.wait(timeout=0) 폴링 패턴. 이 로직은 수정하지 말고, 바로 다음의 gather() 블록만 수정할 것
  - `backend/services/load_engine.py:200-213` — **수정 대상**: asyncio.gather() → asyncio.as_completed() 교체 지점
  - `backend/services/load_engine.py:226-239` — completed 이벤트 broadcast. 이 부분은 그대로 유지
  - `backend/services/load_engine.py:64-68` — `_broadcast()` 메서드. 호출 시그니처 참조

  **Test References**:
  - `backend/tests/test_load_test.py:103-139` — `test_compute_stats_includes_total_requested`: LoadTestEngine 직접 인스턴스화 패턴. 이 방식으로 conftest 스텁 우회
  - `backend/tests/conftest.py:208-222` — `_stub_run`: 이 스텁은 건드리지 말 것. 새 테스트는 engine을 직접 만들어서 우회

  **API/Type References**:
  - `backend/models/load_test.py:RequestResult` — 성공/실패 결과 타입. `success`, `latency`, `error` 필드 확인
  - `backend/services/load_engine.py:26-33` — `LoadTestState` 데이터클래스. `failed_requests` 카운터 증가 로직 참조

  **Acceptance Criteria**:

  - [x] `test_gather_phase_broadcasts_progress_per_result` 테스트 PASS
  - [x] `test_gather_phase_handles_exceptions_as_failed_results` 테스트 PASS
  - [x] `cd backend && python3 -m pytest tests/ -x -q -m "not integration"` → 전체 통과, 0 failures

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: gather 구간에서 per-result progress broadcast 발생 확인
    Tool: Bash
    Preconditions: backend 디렉토리에서 실행
    Steps:
      1. python3 -m pytest tests/test_load_test.py::test_gather_phase_broadcasts_progress_per_result -v
      2. 출력에서 "PASSED" 확인
    Expected Result: test_gather_phase_broadcasts_progress_per_result PASSED
    Failure Indicators: "FAILED" 또는 "ERROR" 출력
    Evidence: .sisyphus/evidence/task-1-gather-broadcast.txt

  Scenario: gather 구간 exception이 failed_requests에 반영 확인
    Tool: Bash
    Preconditions: backend 디렉토리에서 실행
    Steps:
      1. python3 -m pytest tests/test_load_test.py::test_gather_phase_handles_exceptions_as_failed_results -v
      2. 출력에서 "PASSED" 확인
    Expected Result: test_gather_phase_handles_exceptions_as_failed_results PASSED
    Failure Indicators: "FAILED" 또는 "ERROR" 출력
    Evidence: .sisyphus/evidence/task-1-gather-exception.txt

  Scenario: 기존 테스트 regression 없음
    Tool: Bash
    Preconditions: backend 디렉토리에서 실행
    Steps:
      1. python3 -m pytest tests/ -x -q -m "not integration"
      2. 출력에서 "passed" 확인, "failed" 0건
    Expected Result: 전체 테스트 통과
    Failure Indicators: "FAILED" 또는 "failed" > 0
    Evidence: .sisyphus/evidence/task-1-regression.txt
  ```

  **Commit**: YES
  - Message: `fix(load-engine): broadcast progress during gather phase`
  - Files: `backend/services/load_engine.py`, `backend/tests/test_load_test.py`
  - Pre-commit: `cd backend && python3 -m pytest tests/ -x -q -m "not integration"`

- [x] 2. [Backend] SSE heartbeat keepalive + 응답 헤더 + 자동 종료 + 테스트

  **What to do**:
  - **테스트 먼저 (RED)**: `backend/tests/test_load_test.py`에 아래 테스트 추가:
    - `test_event_generator_sends_keepalive_on_idle()`: LoadTestEngine을 직접 인스턴스화하고 subscribe(). 큐에 데이터를 넣지 않은 채 15초 대기 시 keepalive comment(`": keepalive\n\n"`)가 yield되는지 확인. `asyncio.wait_for` 타임아웃 메커니즘 검증.
    - `test_event_generator_breaks_after_completed_event()`: 큐에 `{"type": "completed", "data": {}}` 넣은 후, generator가 해당 이벤트를 yield하고 루프를 종료하는지 확인. 종료 후 `engine._subscribers`가 비어있는지 (subscriber 누수 없음) 검증.
    - **중요**: event_generator는 load_test.py 라우터 내부 함수이므로, 테스트에서는 동일한 로직을 가진 헬퍼 함수로 추출하거나, load_engine의 queue를 직접 조작하여 테스트. `asyncio` 테스트는 `pytest-asyncio`로 실행 (pyproject.toml에 `asyncio_mode = "auto"` 이미 설정됨).
  - **구현 (GREEN)**: `backend/routers/load_test.py`의 `stream_load_test_results()`:
    1. `event_generator()` 내부에서 `await queue.get()`을 `asyncio.wait_for(queue.get(), timeout=15)` 로 교체
    2. `asyncio.TimeoutError` catch 시 `yield ": keepalive\n\n"` (SSE comment line — 클라이언트에 이벤트 안 보내고 연결만 유지)
    3. yield한 data에서 `data.get("type")` 이 `"completed"` 또는 `"stopped"` 이면 `break` → generator 종료 → finally에서 unsubscribe
    4. `StreamingResponse` 생성 시 `headers` 파라미터 추가:
       ```python
       headers={
           "Cache-Control": "no-cache",
           "X-Accel-Buffering": "no",
       }
       ```
  - **테스트 통과 확인**: `python3 -m pytest tests/test_load_test.py -v -m "not integration"` 전체 통과

  **Must NOT do**:
  - `/api/load_test/stream` URL 경로 변경 금지
  - SSE 이벤트 스키마 변경 금지
  - `subscribe()`/`unsubscribe()` 시그니처 변경 금지
  - `retry:` SSE directive 추가 금지 (scope creep)

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: asyncio.wait_for 타임아웃과 SSE 프로토콜 세부사항 이해 필요
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Tasks 1, 3)
  - **Blocks**: Task 4
  - **Blocked By**: None (can start immediately)

  **References**:

  **Pattern References**:
  - `backend/routers/load_test.py:159-182` — **수정 대상**: `stream_load_test_results()` 전체. `event_generator()` 내부 로직 교체
  - `backend/services/load_engine.py:54-62` — `subscribe()`/`unsubscribe()` API. generator 종료 시 unsubscribe 호출 확인

  **API/Type References**:
  - FastAPI `StreamingResponse` — `headers` 파라미터로 응답 헤더 추가 가능: `StreamingResponse(generator(), media_type="text/event-stream", headers={...})`

  **External References**:
  - SSE 스펙 comment line: 콜론(`:`)으로 시작하는 줄은 comment로 처리되어 클라이언트에 이벤트를 발생시키지 않지만 TCP 연결을 유지함

  **Test References**:
  - `backend/tests/test_load_test.py:103-139` — engine 직접 인스턴스화 패턴
  - `pyproject.toml:3` — `asyncio_mode = "auto"` — async 테스트 자동 실행

  **Acceptance Criteria**:

  - [x] `test_event_generator_sends_keepalive_on_idle` 테스트 PASS
  - [x] `test_event_generator_breaks_after_completed_event` 테스트 PASS
  - [x] `cd backend && python3 -m pytest tests/ -x -q -m "not integration"` → 전체 통과

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: SSE heartbeat keepalive 동작 확인
    Tool: Bash
    Preconditions: backend 디렉토리에서 실행
    Steps:
      1. python3 -m pytest tests/test_load_test.py::test_event_generator_sends_keepalive_on_idle -v
      2. 출력에서 "PASSED" 확인
    Expected Result: test_event_generator_sends_keepalive_on_idle PASSED
    Failure Indicators: "FAILED" 또는 "ERROR"
    Evidence: .sisyphus/evidence/task-2-heartbeat.txt

  Scenario: completed 이벤트 후 generator 자동 종료 + subscriber 정리
    Tool: Bash
    Preconditions: backend 디렉토리에서 실행
    Steps:
      1. python3 -m pytest tests/test_load_test.py::test_event_generator_breaks_after_completed_event -v
      2. 출력에서 "PASSED" 확인
    Expected Result: PASSED, _subscribers 리스트 비어있음
    Failure Indicators: "FAILED", subscriber 누수 감지
    Evidence: .sisyphus/evidence/task-2-auto-terminate.txt

  Scenario: SSE 응답 헤더 확인
    Tool: Bash
    Preconditions: backend가 로컬에서 실행 중 (또는 테스트에서 직접 StreamingResponse 헤더 검증)
    Steps:
      1. 테스트에서 StreamingResponse 생성 시 headers dict에 "Cache-Control": "no-cache"와 "X-Accel-Buffering": "no"가 포함되는지 확인
      2. 또는 isolated_client로 GET /api/load_test/stream 호출 후 response.headers 확인
    Expected Result: Cache-Control: no-cache, X-Accel-Buffering: no 헤더 존재
    Failure Indicators: 헤더 누락
    Evidence: .sisyphus/evidence/task-2-headers.txt

  Scenario: 기존 테스트 regression 없음
    Tool: Bash
    Preconditions: backend 디렉토리에서 실행
    Steps:
      1. python3 -m pytest tests/ -x -q -m "not integration"
    Expected Result: 전체 통과
    Failure Indicators: "FAILED" > 0
    Evidence: .sisyphus/evidence/task-2-regression.txt
  ```

  **Commit**: YES
  - Message: `feat(load-test): add SSE heartbeat keepalive and auto-termination`
  - Files: `backend/routers/load_test.py`, `backend/tests/test_load_test.py`
  - Pre-commit: `cd backend && python3 -m pytest tests/ -x -q -m "not integration"`

- [x] 3. [Frontend] onerror 재연결 허용 + 최대 재시도 제한 + 테스트

  **What to do**:
  - **테스트 먼저 (RED)**: `frontend/src/pages/LoadTestPage.test.jsx`에 아래 테스트 추가:
    - `test onerror does not close EventSource when readyState is CONNECTING`: MockEventSource에 `readyState` 프로퍼티 추가. `readyState = 0` (CONNECTING) 일 때 onerror 호출 → `es.close()`가 호출되지 않고, 에러 메시지가 표시되지 않는지 확인.
    - `test onerror closes EventSource and shows error when readyState is CLOSED`: `readyState = 2` (CLOSED) 일 때 onerror 호출 → `es.close()` 호출되고 에러 메시지 "SSE 연결 실패" 표시 확인.
    - `test onerror shows error after max retries exceeded`: 재연결 3회 후에도 onerror 발생 시 최종 에러 표시 확인.
    - **MockEventSource 패턴**: 기존 `LoadTestPage.test.jsx:20-28`의 MockEventSource 클래스에 `readyState` 프로퍼티와 `close()` spy 추가.
  - **구현 (GREEN)**: `frontend/src/pages/LoadTestPage.jsx`의 `es.onerror` 핸들러(90-95번 라인) 수정:
    1. 재시도 카운터 ref 추가: `const retryCountRef = useRef(0);` (최대 3회)
    2. `onerror` 핸들러에서 `es.readyState` 체크:
       - `readyState === 0` (CONNECTING): 브라우저 자동 재연결 중. `retryCountRef.current++`. 최대 재시도(3회) 미만이면 아무것도 하지 않음 (재연결 허용). 초과 시 `es.close()` + 에러 표시.
       - `readyState === 2` (CLOSED): 서버가 연결을 명시적으로 종료. 즉시 `es.close()` + 에러 표시.
    3. `onmessage`에서 progress/completed 이벤트 수신 시 `retryCountRef.current = 0` (재시도 카운터 리셋)
    4. 에러 메시지 명확화: "SSE 연결 실패: 부하 테스트 스트림에 연결할 수 없습니다. (재시도 {N}회 후 실패)"
  - **테스트 통과 확인**: `cd frontend && npx vitest run` 전체 통과

  **Must NOT do**:
  - EventSource URL 변경 금지
  - SSE 이벤트 파싱 로직 변경 금지 (`data.type === "progress"/"completed"` 유지)
  - 폴링 fallback 추가 금지
  - Mock 모드 로직 변경 금지

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: 프론트엔드 단일 파일 수정, onerror 핸들러 로직만 변경
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Tasks 1, 2)
  - **Blocks**: Task 4
  - **Blocked By**: None (can start immediately)

  **References**:

  **Pattern References**:
  - `frontend/src/pages/LoadTestPage.jsx:60-95` — **수정 대상**: EventSource 생성 및 onerror 핸들러. 60번 라인의 EventSource 생성, 90-95번 라인의 onerror
  - `frontend/src/pages/LoadTestPage.jsx:62-88` — onmessage 핸들러. progress/completed 이벤트 수신 시 retryCount 리셋 로직 추가 지점
  - `frontend/src/pages/LoadTestPage.jsx:30` — `esRef` 패턴. 같은 방식으로 `retryCountRef` 추가

  **Test References**:
  - `frontend/src/pages/LoadTestPage.test.jsx:20-28` — MockEventSource 클래스. `readyState` 프로퍼티 추가 필요
  - `frontend/src/pages/LoadTestPage.test.jsx:51-55` — 기본 렌더링 테스트 패턴
  - `frontend/src/pages/LoadTestPage.test.jsx:60-88` — SSE 이벤트 시뮬레이션 패턴

  **External References**:
  - EventSource.readyState: `0` = CONNECTING, `1` = OPEN, `2` = CLOSED. 브라우저는 onerror 후 readyState가 0이면 자동 재연결 시도

  **Acceptance Criteria**:

  - [x] `onerror does not close EventSource when readyState is CONNECTING` 테스트 PASS
  - [x] `onerror closes EventSource and shows error when readyState is CLOSED` 테스트 PASS
  - [x] `onerror shows error after max retries exceeded` 테스트 PASS
  - [x] `cd frontend && npx vitest run` → 신규 SSE 테스트 4/4 통과

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: readyState CONNECTING 시 재연결 허용
    Tool: Bash
    Preconditions: frontend 디렉토리에서 실행
    Steps:
      1. npx vitest run src/pages/LoadTestPage.test.jsx
      2. "onerror does not close EventSource when readyState is CONNECTING" 테스트 결과 확인
    Expected Result: PASS — onerror 발생 시 es.close() 미호출, 에러 메시지 미표시
    Failure Indicators: "FAIL" 또는 AssertionError
    Evidence: .sisyphus/evidence/task-3-reconnect-allow.txt

  Scenario: readyState CLOSED 시 에러 표시
    Tool: Bash
    Preconditions: frontend 디렉토리에서 실행
    Steps:
      1. npx vitest run src/pages/LoadTestPage.test.jsx
      2. "onerror closes EventSource and shows error when readyState is CLOSED" 테스트 결과 확인
    Expected Result: PASS — es.close() 호출, "SSE 연결 실패" 에러 표시
    Failure Indicators: "FAIL"
    Evidence: .sisyphus/evidence/task-3-closed-error.txt

  Scenario: 최대 재시도 초과 시 에러 표시
    Tool: Bash
    Preconditions: frontend 디렉토리에서 실행
    Steps:
      1. npx vitest run src/pages/LoadTestPage.test.jsx
      2. "onerror shows error after max retries exceeded" 테스트 결과 확인
    Expected Result: PASS — 3회 재시도 후 에러 표시
    Failure Indicators: "FAIL"
    Evidence: .sisyphus/evidence/task-3-max-retries.txt

  Scenario: 기존 프론트엔드 테스트 regression 없음
    Tool: Bash
    Preconditions: frontend 디렉토리에서 실행
    Steps:
      1. npx vitest run
      2. 전체 테스트 통과 확인
    Expected Result: 모든 테스트 PASS
    Failure Indicators: "FAIL" > 0
    Evidence: .sisyphus/evidence/task-3-regression.txt
  ```

  **Commit**: YES
  - Message: `fix(frontend): allow EventSource auto-reconnect on transient errors`
  - Files: `frontend/src/pages/LoadTestPage.jsx`, `frontend/src/pages/LoadTestPage.test.jsx`
  - Pre-commit: `cd frontend && npx vitest run`

- [x] 4. [통합] 전체 테스트 regression 검증

  **What to do**:
  - Task 1, 2, 3 완료 후 전체 테스트 스위트 실행하여 regression 확인
  - 백엔드: `cd backend && python3 -m pytest tests/ -x -q -m "not integration"` → 전체 통과
  - 프론트엔드: `cd frontend && npx vitest run` → 전체 통과
  - Task 1과 Task 2가 모두 `backend/tests/test_load_test.py`에 테스트를 추가하므로, 파일 충돌 발생 가능. 충돌 시 수동 병합.

  **Must NOT do**:
  - 새 기능 추가 금지
  - 기존 코드 수정 금지 (충돌 해결 외)

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: 테스트 실행 및 충돌 해결만 수행
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Wave 2 (sequential after Wave 1)
  - **Blocks**: F1-F4
  - **Blocked By**: Tasks 1, 2, 3

  **References**:

  **Pattern References**:
  - `backend/tests/test_load_test.py` — Task 1, 2가 추가한 테스트들이 공존하는지 확인
  - `pyproject.toml` — pytest 설정, markers 확인

  **Acceptance Criteria**:

  - [x] `cd backend && python3 -m pytest tests/ -x -q -m "not integration"` → 전체 통과 (116 passed: 기존 111 + T1 2개 + T2 3개)
  - [x] `cd frontend && npx vitest run` → 신규 SSE 테스트 4/4 통과

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: 백엔드 전체 테스트 통과
    Tool: Bash
    Preconditions: backend 디렉토리에서 실행
    Steps:
      1. python3 -m pytest tests/ -x -q -m "not integration"
      2. 출력에서 "passed" 확인, "failed" 0건
    Expected Result: 전체 테스트 통과
    Failure Indicators: "FAILED" 또는 "failed" > 0
    Evidence: .sisyphus/evidence/task-4-backend-all.txt

  Scenario: 프론트엔드 전체 테스트 통과
    Tool: Bash
    Preconditions: frontend 디렉토리에서 실행
    Steps:
      1. npx vitest run
      2. 전체 테스트 통과 확인
    Expected Result: 모든 테스트 PASS
    Failure Indicators: "FAIL" > 0
    Evidence: .sisyphus/evidence/task-4-frontend-all.txt
  ```

  **Commit**: NO (필요 시 충돌 해결 커밋만)

---

## Final Verification Wave (MANDATORY — after ALL implementation tasks)

> 4 review agents run in PARALLEL. ALL must APPROVE. Rejection → fix → re-run.

- [x] F1. **Plan Compliance Audit** — `oracle`
  Read the plan end-to-end. For each "Must Have": verify implementation exists (read file, run command). For each "Must NOT Have": search codebase for forbidden patterns — reject with file:line if found. Check evidence files exist in .sisyphus/evidence/. Compare deliverables against plan.
  Output: `Must Have [N/N] | Must NOT Have [N/N] | Tasks [N/N] | VERDICT: APPROVE/REJECT`

- [x] F2. **Code Quality Review** — `unspecified-high`
  Run `cd backend && python3 -m pytest tests/ -x -q -m "not integration"` + `cd frontend && npx vitest run`. Review all changed files for: `as any`/`@ts-ignore`, empty catches, console.log in prod, commented-out code, unused imports. Check AI slop: excessive comments, over-abstraction, generic names.
  Output: `Tests [PASS/FAIL] | Files [N clean/N issues] | VERDICT`

- [x] F3. **Real Manual QA** — `unspecified-high`
  Execute EVERY QA scenario from EVERY task — follow exact steps, capture evidence. Test cross-task integration. Save to `.sisyphus/evidence/final-qa/`.
  Output: `Scenarios [N/N pass] | Integration [N/N] | VERDICT`

- [x] F4. **Scope Fidelity Check** — `deep`
  For each task: read "What to do", read actual diff (git log/diff). Verify 1:1 — everything in spec was built, nothing beyond spec was built. Check "Must NOT do" compliance. Flag unaccounted changes.
  Output: `Tasks [N/N compliant] | Unaccounted [CLEAN/N files] | VERDICT`

---

## Commit Strategy

- **T1**: `fix(load-engine): broadcast progress during gather phase`
  - `backend/services/load_engine.py`, `backend/tests/test_load_test.py`
  - Pre-commit: `cd backend && python3 -m pytest tests/ -x -q -m "not integration"`

- **T2**: `feat(load-test): add SSE heartbeat keepalive and auto-termination`
  - `backend/routers/load_test.py`, `backend/tests/test_load_test.py`
  - Pre-commit: `cd backend && python3 -m pytest tests/ -x -q -m "not integration"`

- **T3**: `fix(frontend): allow EventSource auto-reconnect on transient errors`
  - `frontend/src/pages/LoadTestPage.jsx`, `frontend/src/pages/LoadTestPage.test.jsx`
  - Pre-commit: `cd frontend && npx vitest run`

---

## Success Criteria

### Verification Commands
```bash
# Backend 전체 테스트
cd backend && python3 -m pytest tests/ -x -q -m "not integration"
# Expected: all pass, 0 failures

# Frontend 전체 테스트
cd frontend && npx vitest run
# Expected: all pass

# SSE 헤더 확인 (백엔드 실행 중)
curl -sI http://localhost:8000/api/load_test/stream | grep -i "cache-control\|x-accel"
# Expected: Cache-Control: no-cache, X-Accel-Buffering: no
```

### Final Checklist
- [x] All "Must Have" present — F1 APPROVE (5/5 verified)
- [x] All "Must NOT Have" absent — F1 APPROVE (6/6 verified)
- [x] All backend tests pass — 116 passed
- [x] All frontend tests pass — 4/4 new SSE tests pass (기존 4개 pre-existing 실패 제외)
