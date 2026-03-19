# Learnings — fix-sse-connection-failure

## [2026-03-15] Session Start: ses_30f1549a8ffeX2n5NkKi21kQRk

### Project Conventions
- Backend: FastAPI (Python), bare imports (`from services.xxx`, no `backend.` prefix)
- Frontend: React + Vite, tested with vitest + @testing-library/react
- Worktree: /home/user/project/vllm-optimizer-sse-fix (branch: fix/sse-connection-failure)
- Test run: `cd backend && python3 -m pytest tests/ -x -q -m "not integration"`
- Frontend test: `cd frontend && npx vitest run`
- asyncio_mode = "auto" in pyproject.toml → async tests work without @pytest.mark.asyncio

### Critical Context
- load_engine.py uses pub/sub with asyncio.Queue — singleton `load_engine` in services/shared.py
- New SSE tests MUST bypass conftest's `_reload_app` stub (which stubs out `LoadTestEngine.run`)
- Pattern to bypass: instantiate `LoadTestEngine()` directly (like test_compute_stats_includes_total_requested)
- asyncio.gather(return_exceptions=True) in lines 200-213 causes silent exception drop AND zero broadcast
- event_generator() never self-terminates → subscriber leak after completed event

### Key Files
- backend/services/load_engine.py:166-213 — task creation loop + gather() (fix target)
- backend/routers/load_test.py:159-182 — event_generator() (fix target)
- frontend/src/pages/LoadTestPage.jsx:60-95 — EventSource setup + onerror (fix target)
- backend/tests/test_load_test.py — test file for T1 and T2 additions
- frontend/src/pages/LoadTestPage.test.jsx — test file for T3 additions

### Guardrails (MUST NOT violate)
- DO NOT modify single_request() or asyncio.wait(timeout=0) in creation loop
- DO NOT change /api/load_test/stream URL
- DO NOT change {"type":"completed","data":...} event schema
- DO NOT modify conftest.py _reload_app stub
- DO NOT add polling fallback or Redis

## [2026-03-15] Session Complete

### 완료 결과
- T1: asyncio.gather() → as_completed() 교체, 9f472ba 커밋
- T2: 15초 heartbeat + break-on-complete + SSE 헤더, 009e27c 커밋
- T3: readyState 체크 + retryCountRef(max 3) + bare catch, 05db9ae + 1235967 커밋
- 신규 테스트 9개 추가 (백엔드 5, 프론트엔드 4)
- Final Wave: F1 APPROVE, F2 APPROVE, F3 APPROVE, F4 APPROVE

### 워크플로우 학습
- 서브에이전트가 worktree 대신 main 브랜치에 작업하는 경향 있음 → Atlas가 직접 복사+커밋
- "single task only" 지시문이 multi-step 지시를 거부함 → 서브에이전트 없이 Atlas 직접 구현
- frontend node_modules가 worktree에 없음 → 원본 레포에서 테스트 실행 후 복사

### 남은 known issue (scope 밖)
- frontend Save as Benchmark 테스트 4개 기존 실패 (useEffect config fetch 2회 vs mock 1회)
