# Decisions — enhanced-perf-tests-v2

## [2026-03-07] Task Execution Order

Wave 1+2 (parallel): Tasks 1, 3, 4, 5 simultaneously
Then: Task 2 (after 1), Task 6 (after 1+3+4+5)
Then: Task 7 (after 6)
Then: Tasks 8+9 in parallel (after 7)
Then: Task 10 (after 9)

## [2026-03-07] Expose AutoTuner wait metrics
- `_wait_for_ready` now tracks each readiness poll, the total wait seconds, and per-trial durations.
- Added a `wait_metrics` property that rounds the totals and exposes the history.
- `/api/tuner/status` now returns `wait_metrics` so observability clients can consume the timing data.
