# Learnings — fix-latency-display

## [2026-03-08] Session ses_331da1df6ffe9OOwk9YtYrLpbc

### Project Context
- Worktree: /home/user/project/vllm-optimizer-fix-latency
- Branch: fix/latency-display
- Recharts actual installed version: 2.15.4 (package.json ^2.10.3 → lock resolves to 2.15.4)

### Root Cause Analysis
- fix-latency-graph-gaps (커밋 c243609) IS correctly applied. Backend: 0→null, Chart: connectNulls=true
- Screenshot evidence: P99≈5ms, TTFT≈2.5ms VALID data present, yet SHORT REGULAR GAPS appear
- Root cause 1: isAnimationActive defaults to true → 2s polling re-render triggers animation → visual gap
- Root cause 2: type="monotone" (cubic spline) near null values is unstable
- Root cause 3: Intermittent null points where connectNulls can't bridge (adjacent nulls)

### Key Conventions
- Frontend test: `cd frontend && npx vitest run` (not npm test directly)
- Build: `cd frontend && npm run build`
- Vitest pattern from existing tests: describe/it/expect
- Frontend import style: relative paths (../utils/, ../components/)
- mockData.js fields: { t, tps, ttft, lat_p99, kv, running, waiting }
- MonitorPage history mapping: ttft: m.ttft_mean, lat_p99: m.latency_p99

### Guardrails (NEVER violate)
- DO NOT modify backend/ files
- DO NOT modify mockHistory() (mock mode uses it)
- DO NOT apply gap-fill to TPS, KV, running, waiting charts
- DO NOT change the lines prop shape (only add optional dash field)
- DO NOT modify MetricCard.jsx component itself
- Tooltip filter: keys ending in _fill → hide from tooltip
- Fill series in Chart.jsx: legendType="none" + custom Tooltip content
