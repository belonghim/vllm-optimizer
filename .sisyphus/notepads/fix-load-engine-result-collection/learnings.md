Plan: fix-load-engine-result-collection

## [2026-03-14] Task 1 결과: TDD RED phase 불발 — Python 3.14 asyncio 동작 차이

### 핵심 발견
- Python 3.14.2에서 asyncio.wait(timeout=0)이 예상보다 더 적극적으로 태스크를 수집함
- asyncio.sleep(0) mock 사용 시 5개 테스트 모두 PASSED (FAIL 예상이었음)
- Bug 1 (sleep 중 완료된 태스크 필터링)은 Python 3.14에서 재현 안 됨
- 버그는 구 Python 버전 + 실제 네트워크 레이턴시(latency > interval) 조합에서 재현됨
- 예: rps=10 (interval=0.1s), latency=0.135s → 태스크가 다음 루프 반복 후에 완료

### 결정
- 테스트 파일 그대로 유지 (올바른 동작 회귀 방지용으로 가치 있음)
- 버그 수정 진행 (Python 호환성, Bug 3 카운터, 코드 명확성)

## [2026-03-14] Setup

### pyproject.toml Key Settings
- pythonpath = ["backend"] → bare imports 작동
- asyncio_mode = "auto" → @pytest.mark.asyncio 불필요
- --strict-markers 적용

### httpx Mock Pattern (검증됨)
- patch("httpx.AsyncClient", return_value=mock_client) 사용
- mock_client.__aenter__ = AsyncMock(return_value=mock_client)
- asyncio.sleep(0) in mock_post → 이벤트 루프 yield 강제 (Python 3.14에서는 효과 미미)

### Task 2 주의사항
- processed_tasks: set[asyncio.Task] 변수를 tasks=[] 직후에 선언
- run() 메서드 내부만 수정 (다른 메서드 금지)
- _state_lock 아래에서만 state 변경
