# Issues — fix-latency-graph-gaps

## 2026-03-08 Session Start

### Known Issue: /latest vs /history inconsistency (intentional, not a bug)
After Task 2, `/latest` returns 0.0 for idle latency, `/history` returns null.
This is by design — _convert_to_snapshot is NOT modified.
Mitigation: Add a comment to _convert_to_snapshot in metrics.py.

### Deque flush time (documented, not fixed)
Existing NaN entries in deque take up to 120s to scroll out after hot-fix deploy.
On restart (normal deploy), deque is empty — no problem.
