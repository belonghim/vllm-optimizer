# Issues — fix-loadtest-bugs

## [2026-03-13] Session ses_31862bddaffer5u1wiAV3Ta9KT

### Known Pre-existing Bugs (OUT OF SCOPE — do NOT fix)
- `asyncio.gather()` block (load_engine.py:197-206): `failed_requests` not updated for remaining tasks
- Race condition: EventSource connected after `completed` event broadcast → SSE stream hangs

### Edge Cases to Handle
- `_compute_stats()` returns `{}` when no results yet → frontend NaN% progress → add `d.total != null` guard
- Frontend `config.model` stays "auto" after start → capture resolved model from POST /start response
