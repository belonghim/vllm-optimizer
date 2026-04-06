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
| + Add Button | Opens the inline add form. Disabled when max targets reached |

#### Target Table

All targets (both InferenceService and LLMInferenceService) are displayed in a **single unified table**.

#### Target Table Columns

| Column | Header | Data Displayed |
|--------|--------|----------------|
| 1 | Target | InferenceService name + namespace. Shows ★ for default (first row), ⚠️ warning if namespace lacks monitoring label |
| 2 | Type | `KServe` for InferenceService, `LLMIS` badge for LLMInferenceService |
| 3 | TPS | Tokens per second (`fmt(data.tps, 0)`) |
| 4 | RPS | Requests per second (`fmt(data.rps, 1)`) |
| 5 | TTFT m/p99 | Time to First Token mean / p99 in ms |
| 6 | Lat m/p99 | Latency mean / p99 in ms |
| 7 | KV% | KV cache usage percentage |
| 8 | KV Hit% | KV cache hit rate percentage |
| 9 | GPU% | GPU utilization percentage |
| 10 | GPU Mem | GPU memory used / total in GB |
| 11 | Run | Number of running requests |
| 12 | Wait | Number of waiting requests |
| 13 | Pods | Ready pods / total pods. Includes expand button (▶/▼) when pods > 1 |
| 14 | Actions | "Set Default" button + "×" delete button (hidden for first row) |

#### Special Indicators

| Indicator | Condition | Meaning |
|-----------|-----------|---------|
| ★ (star) | First row (index 0) | This is the default monitoring target |
| LLMIS badge | `target.crType === "llminferenceservice"` (Type column) | Target is an LLMInferenceService (not standard KServe) |
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

## Related Hooks

| Module | File | Role |
|--------|------|------|
| useMonitorLogic | `hooks/useMonitorLogic.ts` | Alternative hook-based monitor logic (not used by MonitorPage, which has inline logic) |

## Error States & Edge Cases

### 타겟이 없는 상태

Monitor 페이지에 진입했을 때 타겟이 하나도 등록되어 있지 않으면:
- MultiTargetSelector 영역에 빈 테이블 대신 "Monitoring Targets (0/Max)" 제목과 "+ Add" 버튼만 표시
- "+ Add" 버튼을 클릭하여 타겟을 추가해야 메트릭 수집이 시작됨
- 타겟이 없으면 메트릭 폴링이 수행되지 않음

### Thanos 연결 실패

`METRICS_SOURCE=thanos` 환경 변수로 Thanos Querier를 사용하는 경우:
- Thanos Querier에 연결할 수 없거나 인증 실패 시 응답의 `collector_version`이 "unknown"으로 반환
- 모든 메트릭 값이 0이거나 null로 표시됨
- 这种 상태에서는 GPU%, GPU Mem 등 메트릭이 모두 "-"로 표시됨
- ErrorAlert에 Thanos 연결 오류 메시지가 표시될 수 있음

### Direct 모드에서 Pod IP 없음

`METRICS_SOURCE=direct` 모드에서 메트릭을 수집하는 경우:
- Pod IP를 가져올 수 없는 타겟 (예: Pod이 아직 Running 상태가 아닌 경우) 해당 타겟의 메트릭이 빈값으로 표시
- Pods 컬럼에 해당 타겟이 "0/0" 또는 "—"로 표시됨
- 해당 타겟의 모든 메트릭(tps, latency, gpu 등)이 "—" 대시로 표시됨

### namespace에 모니터링 레이블 누락

 target의 namespace에 `openshift.io/cluster-monitoring=true` 레이블이 없는 경우:
- 해당 타겟 행에 ⚠️ 경고 아이콘이 표시됨
- Thanos 기반 메트릭 수집이 불가능하므로 메트릭이 0 또는 "-"로 표시됨
- 이 경고는 MultiTargetSelector의 "Type" 컬럼 근처에 표시됨 |
