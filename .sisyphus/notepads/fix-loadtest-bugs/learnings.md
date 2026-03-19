Learning note: Implementing total_requested in LoadTest
- Always verify changes with unit tests that target internal state (not only API endpoints).
- When adding a new field used for metrics, propagate in initializations and in the stats aggregation.
- Keep tests isolated: construct LoadTestEngine and LoadTestState directly for unit tests.
- Ensure to preserve existing API signatures and avoid changing public interfaces.
- Verification: run pytest backend/tests/ -m "not integration" to confirm all tests pass.
