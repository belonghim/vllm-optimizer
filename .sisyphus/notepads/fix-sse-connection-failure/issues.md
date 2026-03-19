# Issues — fix-sse-connection-failure

## [2026-03-15] Session Start

### Known Issues
- T1 and T2 both write to backend/tests/test_load_test.py → potential file conflict if parallel
  → Resolution: each task appends to the file (never overwrites), Task 4 verifies both sets coexist
- event_generator() is a closure inside stream_load_test_results() → harder to unit test directly
  → Resolution: T2 agent must either extract it as module-level helper OR test via asyncio queue manipulation
