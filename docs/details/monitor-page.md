# MonitorPage — Detailed Documentation

## Overview

The MonitorPage provides real-time monitoring for vLLM inference services. It displays metrics (TPS, latency, TTFT, KV cache, GPU utilization) for multiple targets simultaneously through interactive charts. The page supports time-range selection, SLA profile integration, and multi-target comparison.

**Source**: `frontend/src/pages/MonitorPage.tsx`

---

## Page Layout (Top → Bottom)

### 1. Top Control Bar

Located at the very top of the page, split into two sections:

#### Left: SLA Profile Selector

| Element | Type | Description |
|---------|------|-------------|
| Label | Text | "SLA PROFILE:" — identifies the selector |
| Dropdown | `<select>` | Lists all saved SLA profiles fetched from `/api/sla/profiles` |
| Default Option | `<option value="">` | "None (disable warning)" — disables SLA threshold warnings |

**Behavior**:
- On mount, fetches SLA profiles via `authFetch('/api/sla/profiles')`
- Selecting a profile enables SLA threshold checking on TPS and P99 latency metrics
- When thresholds are violated, a toast notification appears (debounced at 30-second intervals)
- The selected profile's thresholds are passed to charts as reference lines

#### Right: Time Range Buttons

| Button | Data Points | Time Range | Description |
|--------|-------------|------------|-------------|
| **Live** | 150 | ~5 minutes | Real-time mode, auto-refreshes every 3 seconds |
| **1h** | 360 | 1 hour | Historical view |
| **6h** | 720 | 6 hours | Historical view |
| **24h** | 1000 | 24 hours | Historical view |
| **7d** | 1400 | 7 days | Historical view |

**Behavior**:
- Active button is highlighted with `.active` class
- Clicking a button updates both `timeRangePoints` (number of data points) and `selectedRange` (time range label)
- Uses refs (`timeRangePointsRef`, `selectedRangeRef`) to ensure the polling interval always has the latest values
- In "Live" mode, the API sends `history_points`; in historical modes, it sends `time_range`

---

### 2. Loading State

- While `initialized` is `false` and `targets.length > 0`, a `LoadingSpinner` is displayed
- Once the first data fetch completes, `initialized` becomes `true` and the main content renders

---

### 3. MultiTargetSelector Component

**Source**: `frontend/src/components/MultiTargetSelector.tsx`

This is the central target management component. It displays all monitoring targets in a table with real-time metrics.

#### Header Section

| Element | Description |
|---------|-------------|
| Title | "Monitoring Targets (N/Max)" — shows current count vs. maximum allowed |
| Default Target Dropdown | Button showing the current default target's InferenceService name. Clicking opens a dropdown panel with all targets grouped by type |
| + Add Button | Opens the inline add form. Disabled when max targets reached |

#### Dropdown Panel

When the default target dropdown button is clicked, a panel appears showing:

- **InferenceService (KServe)** section — targets with `crType: "inferenceservice"`
- **LLMInferenceService (LLMIS)** section — targets with `crType: "llminferenceservice"`
- Each section shows a count badge and a table with the same columns as the main view

#### Target Table Columns

| Column | Header | Data Displayed |
|--------|--------|----------------|
| 1 | Target | InferenceService name + namespace. Shows ★ for default, "LLMIS" badge for LLMInferenceService type, ⚠️ warning if namespace lacks monitoring label |
| 2 | TPS | Tokens per second (`fmt(data.tps, 0)`) |
| 3 | RPS | Requests per second (`fmt(data.rps, 1)`) |
| 4 | TTFT m/p99 | Time to First Token mean / p99 in ms |
| 5 | Lat m/p99 | Latency mean / p99 in ms |
| 6 | KV% | KV cache usage percentage |
| 7 | KV Hit% | KV cache hit rate percentage |
| 8 | GPU% | GPU utilization percentage |
| 9 | GPU Mem | GPU memory used / total in GB |
| 10 | Run | Number of running requests |
| 11 | Wait | Number of waiting requests |
| 12 | Pods | Ready pods / total pods. Includes expand button (▶/▼) when pods > 1 |
| 13 | Actions | "Set Default" button + "×" delete button (hidden for default target) |

#### Special Indicators

| Indicator | Condition | Meaning |
|-----------|-----------|---------|
| ★ (star) | `target.isDefault === true` | This is the default monitoring target |
| LLMIS badge | `target.crType === "llminferenceservice"` | Target is an LLMInferenceService (not standard KServe) |
| ⚠️ warning | `hasMonitoringLabel === false` | Namespace lacks `openshift.io/cluster-monitoring=true` label — metrics cannot be collected |
| `...` (dots) | `status === 'collecting'` | Data is being collected, not yet available |
| `—` (dash) | `data === null` | No data available for this metric |

#### Expandable Pod Rows

- When a target has more than 1 pod, an expand button (▶) appears in the Pods column
- Clicking expand fetches per-pod metrics from `/api/metrics/pods` via POST
- The expanded row shows `ExpandablePodRow` with per-pod breakdown, colored with the parent target's color
- Pod data is cached in local state — subsequent collapses/expansions don't re-fetch

#### Add Target Form

When "+ Add" is clicked, an inline form appears:

| Field | Type | Description |
|-------|------|-------------|
| Namespace | Text input | Kubernetes namespace name |
| InferenceService | Text input | InferenceService name |
| CR Type | Select | `inferenceservice` (KServe) or `llminferenceservice` (LLMIS) |
| Confirm | Button | Validates target exists via `/api/metrics/latest`, then adds to config |
| Cancel | Button | Closes the form without adding |

**Validation flow**:
1. User fills in namespace + inference service + CR type
2. Clicks "Confirm"
3. API call to `/api/metrics/latest?namespace=...&is_name=...&cr_type=...`
4. If response is OK → target added via `addTarget()`
5. If response fails → "Target not found" error shown
6. Network error → "Validation error occurred" shown

---

### 4. Error Alert

- `ErrorAlert` component displays any errors from the metrics batch API
- Shown between the MultiTargetSelector and the chart grid
- Class: `error-alert--m08`

---

### 5. MonitorChartGrid Component

**Source**: `frontend/src/components/MonitorChartGrid.tsx`

A responsive 2-column grid of time-series charts.

#### Chart Definitions (9 charts)

| Chart ID | Title | Lines Displayed (Single Target) | Lines Displayed (Multi Target) |
|----------|-------|--------------------------------|-------------------------------|
| `tps` | Throughput (TPS) | TPS (accent color) | One line per target (color-coded) |
| `latency` | Latency (ms) | P99 (red), Latency mean (accent), P99 idle fill (red, dashed) | One line per target (p99) |
| `ttft` | TTFT (ms) | TTFT mean (cyan), TTFT p99 (accent), TTFT idle fill (cyan, dashed) | One line per target (ttft) |
| `kv` | KV Cache Usage (%) | KV Cache % (purple) | One line per target |
| `kv_hit` | KV Cache Hit Rate (%) | KV Hit Rate % (cyan) | One line per target |
| `queue` | Request Queue | Running (green), Waiting (red) | One line per target (running) |
| `rps` | RPS (Requests/sec) | RPS (green) | One line per target |
| `gpu_util` | GPU Utilization (%) | GPU Util % (red) | One line per target |
| `gpu_mem` | GPU Memory (GB) | GPU Mem Used (purple) | One line per target |

#### Chart Controls

- Each chart has a hide button (×) in its header
- Hidden charts appear in a "Hidden charts" bar at the bottom
- Clicking a hidden chart tag restores it
- Chart order and hidden state are persisted in `localStorage` (key: `vllm-optimizer-chart-config`)

#### SLA Threshold Lines

- When an SLA profile is selected, threshold reference lines appear on relevant charts
- TPS chart shows `min_tps` threshold
- Latency chart shows `p95_latency_max_ms` threshold

---

## Data Flow

### Metrics Fetching

1. **Initial fetch**: On mount (when `isActive` and `targets.length > 0`), calls `fetchAllTargets()`
2. **Polling**: Sets up `setInterval` at 3-second intervals
3. **API**: POST to `/api/metrics/batch` with target list and either `history_points` or `time_range`
4. **Abort handling**: Uses `AbortController` — cleanup on unmount or dependency change aborts in-flight requests

### Response Processing

For each target in the batch response:
1. If `status === 'error'` → stores error state
2. If SLA profile selected → checks TPS and P99 latency against thresholds (30s debounce)
3. Maps history data to chart format with gap-filling via `buildGapFill()`
4. Merges all target states into `targetStates` record

### History Merging

- `mergedHistory` useMemo combines all targets' history into a single time-indexed array
- Each timestamp key gets prefixed metric keys: `{targetKey}_{metricKey}`
- In "Live" mode, filters to last 5 minutes only (cutoff: `Date.now()/1000 - 300`)

### Mock Data Mode

- When `isMockEnabled` is true, uses `mockMetrics()` and `mockHistory()` instead of API calls
- No network requests are made

---

## Related Components

| Component | File | Role |
|-----------|------|------|
| MultiTargetSelector | `components/MultiTargetSelector.tsx` | Target management table |
| MonitorChartGrid | `components/MonitorChartGrid.tsx` | Chart grid layout |
| Chart | `components/Chart.tsx` | Individual time-series chart |
| ExpandablePodRow | `components/ExpandablePodRow.tsx` | Per-pod metric breakdown |
| ErrorAlert | `components/ErrorAlert.tsx` | Error message display |
| LoadingSpinner | `components/LoadingSpinner.tsx` | Loading indicator |

## Related Contexts & Hooks

| Module | File | Role |
|--------|------|------|
| ClusterConfigContext | `contexts/ClusterConfigContext.tsx` | Provides `targets`, `crType`, `addTarget`, `removeTarget`, `setDefaultTarget` |
| MockDataContext | `contexts/MockDataContext.tsx` | Provides `isMockEnabled` |
| ThemeContext | `contexts/ThemeContext.tsx` | Provides `COLORS` for chart theming |

## Related Utilities

| Utility | File | Role |
|---------|------|------|
| gapFill | `utils/gapFill.ts` | Fills gaps in time-series data |
| authFetch | `utils/authFetch.ts` | Authenticated HTTP requests |
| format | `utils/format.ts` | Number formatting (`fmt`) |
