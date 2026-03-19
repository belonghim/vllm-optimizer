# Decisions — Full Codebase Cleanup

## Architecture Decisions
- SSE extraction: custom hook `useLoadTestSSE.js` (EventSource refs move into hook)
- Config props: pass `config` object + `onChange(field, value)` (no 12 individual props)
- CSS strategy: extend `index.css` with named classes (NOT CSS Modules)
- Item F merged into Item E (error handling = same CSS problem)
- SECRET_KEY: add warning comment, keep value for dev compatibility

## Exception Type Mapping
- K8s API calls → `kubernetes.client.exceptions.ApiException`
- httpx/HTTP calls → `httpx.HTTPStatusError`, `httpx.ConnectError`, `httpx.TimeoutException`
- JSON parsing → `json.JSONDecodeError`
- asyncio ops → `asyncio.TimeoutError`, `asyncio.CancelledError`
- General I/O → `OSError`
- main.py:73 → excluded (intentionally broad, add "# intentional" comment)

## CSS Naming Convention
- Pattern: `{page}-{element}` (e.g., `.tuner-trial-row`, `.loadtest-config-input`)
- App nav: `.app-nav`, `.app-tab`, `.app-tab-active`, `.app-container`
- Monitor: `.monitor-grid`, `.monitor-refresh-btn`
- Benchmark: `.benchmark-table`, `.benchmark-comparison`
- Chart: `.chart-container`, `.chart-legend`
- MetricCard: `.metric-card-value`, `.metric-card-label`
- MockDataSwitch: `.mock-switch`, `.mock-switch-label`
- ErrorBoundary: `.error-boundary`, `.error-boundary-message`
- ErrorAlert: `.error-alert`
