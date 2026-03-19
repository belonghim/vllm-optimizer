# Learnings — fix-latency-graph-gaps

## 2026-03-08 Session Start

### Root Cause (confirmed via code + Starlette source)
- `histogram_quantile()` on Prometheus returns `"NaN"` string when vLLM is idle
- `float("NaN")` → Python `nan` — no exception, flows silently
- `nan is not None` → True → gets into result dict without being caught
- Starlette `JSONResponse.render()` uses `json.dumps(allow_nan=False)` — HARDCODED
- Any `nan` in history deque → `/api/metrics/history` returns HTTP 500

### Files and Key Locations
- `backend/services/metrics_collector.py:234-246` → `_fetch_prometheus_metric` — **FIXED** ✅ (NaN/Inf filter added)
- `backend/services/metrics_collector.py:344-370` → `get_history_dict` — next: change latency 0→None
- `backend/models/load_test.py:103-120` → `MetricsSnapshot` — next: change 4 latency fields to Optional[float]
- `backend/routers/metrics.py:16-55` → `_convert_to_snapshot` — next: add comment only, NO logic change
- `frontend/src/components/Chart.jsx:22` → `<Line>` — **FIXED** ✅ (connectNulls={true} added)

### Critical Ordering Constraint (Task 2)
MetricsSnapshot Optional[float] change MUST happen BEFORE get_history_dict 0→None change.
Reason: Pydantic v2 raises ValidationError when None is passed to float field.

### Scope Boundaries
- IN: ttft_mean, ttft_p99, latency_mean, latency_p99 → Optional
- OUT: tps, rps, kv_cache, kv_hit_rate, gpu_mem_used, gpu_util, pods (keep as float, 0 is valid)
- OUT: VLLMMetrics dataclass field types (don't change)
- OUT: _convert_to_snapshot logic (comment only)
- OUT: <Area>, <Bar> in Chart.jsx (only <Line>)

### Python Patterns
- `0.0 or None` → None (falsy 활용)
- `500.0 or None` → 500.0 (truthy)
- `math.isnan(value) or math.isinf(value)` — both must be checked
- NaN check MUST be after `float()` call, BEFORE `round()` call

### Test Framework
- Backend: pytest, location `backend/tests/`
- Run: `cd backend && python3 -m pytest tests/ -x -q -m "not integration"`
- conftest.py has fixtures: check before writing mock setups
- Test patterns: use AsyncMock, patch, MagicMock from unittest.mock

### Completed Tasks
- **Task 1**: NaN/Inf filtering in `_fetch_prometheus_metric` ✅
  - Added `import math`
  - Added `if math.isnan(value) or math.isinf(value): return metric_name, None`
  - Added 4 regression tests (NaN, +Inf, -Inf, valid value)
  - All 45 backend tests pass
  - Commit: `fix(metrics): filter NaN/Infinity from Prometheus responses to prevent HTTP 500`
  
- **Task 3**: `connectNulls={true}` in Chart.jsx ✅
  - Added prop to `<Line>` component
  - Verified with grep
  - Included in same commit as Task 1

### Next: Task 2
1. Update `MetricsSnapshot` model: ttft_mean, ttft_p99, latency_mean, latency_p99 → Optional[float]
2. Update `get_history_dict`: latency 0.0 → None (using `or None` pattern)
3. Add comment to `_convert_to_snapshot` about /latest vs /history inconsistency
4. Add tests for Optional serialization and null latency in history
