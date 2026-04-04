# BenchmarkPage — Detailed Documentation

## Overview

The BenchmarkPage manages saved benchmark results from load tests and tuning sessions. It provides a table view for browsing, comparing, exporting, and deleting benchmarks. Users can select multiple benchmarks for comparison, edit metadata, and import results from external GuideLLM runs.

**Source**: `frontend/src/pages/BenchmarkPage.tsx`

---

## Page Layout (Top → Bottom)

### 1. Error Alert

| Element | Description |
|---------|-------------|
| ErrorAlert | Displays any errors from benchmark operations (fetch, delete, import, metadata save). Class: `error-alert--mb8` |

---

### 2. Loading State

- While `loading === true` and `benchmarks.length === 0`, a `LoadingSpinner` is displayed
- Once data is loaded (even if empty), the main content renders

---

### 3. BenchmarkTable Component

**Source**: `frontend/src/components/BenchmarkTable.tsx`

The main content area displaying all saved benchmarks.

#### 3.1 Action Bar

| Button | State | Description |
|--------|-------|-------------|
| Export JSON | Disabled when no benchmarks | Exports all (or selected) benchmarks as JSON file |
| Export CSV | Disabled when no benchmarks | Exports all (or selected) benchmarks as CSV file |
| Import GuideLLM Results | Disabled while importing | Opens file picker for `.json` GuideLLM result files |
| Delete Selected | Disabled when nothing selected | Bulk deletes selected benchmarks with confirmation |

**Import Flow**:
1. Click "Import GuideLLM Results"
2. File picker opens (accepts `.json` files only)
3. Selected file uploaded via POST to `/api/benchmark/import` as `FormData`
4. On success: shows alert with imported count, refreshes benchmark list
5. On failure: shows error message from API response

#### 3.2 Benchmark Table Columns

| Column | Header | Data Displayed |
|--------|--------|----------------|
| 1 | (checkbox) | Checkbox for multi-select. Clicking toggles selection |
| 2 | Name | Benchmark name. Shows "GuideLLM" badge if `metadata.source === "guidellm"` |
| 3 | Model ID | `metadata.model_identifier` or "—" |
| 4 | Config Model | `config.model` or "—" (muted text) |
| 5 | Date | Formatted timestamp (`toLocaleString()`) |
| 6 | TPS | `result.tps.mean` formatted to 1 decimal |
| 7 | P99 ms | `result.latency.p99 × 1000` formatted to 0 decimals |
| 8 | RPS | `result.rps_actual` formatted to 1 decimal |
| 9 | GPU Eff. | GPU efficiency display or "N/A" if mismatch |
| 10 | Delete | ✕ icon button for single benchmark deletion |

#### 3.3 Row Interactions

| Interaction | Behavior |
|-------------|----------|
| Click row (not checkbox) | Toggles expand/collapse for metadata details |
| Click checkbox | Toggles selection for comparison/bulk operations |
| Click ✕ delete | Opens confirmation dialog, then deletes benchmark |

#### 3.4 Expanded Row (Metadata Detail)

When a row is expanded, a detail panel shows:

| Field | Data |
|-------|------|
| Model ID | `metadata.model_identifier` |
| Hardware | `metadata.hardware_type` |
| Runtime | `metadata.runtime` |
| vLLM Version | `metadata.vllm_version` |
| Replicas | `metadata.replica_count` |
| Notes | `metadata.notes` (full-width) |
| Extra Info | `metadata.extra` key-value pairs as tags (full-width) |

**Expanded Row Actions**:

| Button | Description |
|--------|-------------|
| Edit | Opens BenchmarkMetadataModal for editing metadata |
| ▶ Rerun | Triggers `onRerun` callback with the benchmark's config (navigates to LoadTestPage with pre-filled config) |

#### 3.5 Empty State

When `benchmarks.length === 0`:
- Shows: "Saved load test results will appear here."

---

### 4. BenchmarkMetadataModal Component

**Source**: `frontend/src/components/BenchmarkMetadataModal.tsx`

Modal dialog for editing benchmark metadata.

| Field | Type | Description |
|-------|------|-------------|
| Model Identifier | Text input | Model name/identifier |
| Hardware Type | Text input | Hardware description |
| Runtime | Text input | Runtime environment |
| vLLM Version | Text input | vLLM version string |
| Replica Count | Number input | Number of replicas |
| Notes | Textarea | Free-form notes |
| Extra Info | Key-value pairs | Additional custom metadata fields |

**Behavior**:
- Opens when "Edit" button is clicked in expanded row
- Saves via PATCH to `/api/benchmark/{id}/metadata`
- On success: updates local state, closes modal
- On failure: shows error alert

---

### 5. BenchmarkCompareCharts Component

**Source**: `frontend/src/components/BenchmarkCompareCharts.tsx`

| Condition | Description |
|-----------|-------------|
| `selected.length >= 2` | Comparison chart appears below the table |

**Visualization**:
- Compares selected benchmarks across 3 metrics (TPS, P99 Latency, GPU Efficiency)
- Uses `calcGpuEfficiency()` to compute GPU efficiency for each benchmark
- GPU Efficiency chart only shows benchmarks where `metricsTargetMatched` is true
- Color-codes each benchmark using `TARGET_COLORS`

**Data transformation**:
```
BenchmarkItem → {
  name: string,
  tps: number,
  ttft: number (ms),
  p99: number (ms),
  rps: number,
  gpuEff: number,
  metricsTargetMatched: boolean
}
```

**Rendered charts** (3 total):
- TPS Comparison (BarChart)
- P99 Latency Comparison (BarChart)
- GPU Efficiency Comparison (BarChart, filtered to `metricsTargetMatched` only)

**Rendered charts** (3 total):
- TPS Comparison (BarChart)
- P99 Latency Comparison (BarChart)
- GPU Efficiency Comparison (BarChart, filtered to `metricsTargetMatched` only)

---

### 6. ConfirmDialog Component

**Source**: `frontend/src/components/ConfirmDialog.tsx`

Used for destructive operations:

| Operation | Title | Message |
|-----------|-------|---------|
| Single Delete | "Delete Benchmark" | "Delete benchmark '{name}'?" |
| Bulk Delete | "Delete Benchmarks" | "Delete {N} benchmark(s)?" |

---

## Data Flow

### Fetching Benchmarks

1. On mount (when `isActive`), calls `fetchBenchmarks()`
2. GET from `/api/benchmark/list`
3. Results stored in `benchmarks` state
4. Uses `AbortController` for cleanup on unmount

### Deleting Benchmarks

**Single Delete**:
1. Click ✕ button → opens ConfirmDialog
2. Confirm → DELETE to `/api/benchmark/{id}`
3. On success: removes from selection/expansion, refreshes list
4. On failure: shows error alert

**Bulk Delete**:
1. Select multiple benchmarks → click "Delete Selected"
2. ConfirmDialog shows count
3. Confirm → Sequential DELETE requests to `/api/benchmark/{id}`
4. On success: clears selection, refreshes list

### Exporting

**JSON Export**:
- Selected benchmarks if any selected, otherwise all
- Uses `downloadJSON()` utility
- Filename: `benchmarks-{timestamp}.json`

**CSV Export**:
- Selected benchmarks if any selected, otherwise all
- Uses `benchmarksToCSV()` → `downloadCSV()` utilities
- Filename: `benchmarks-{timestamp}.csv`

### Importing

1. File selected via hidden `<input type="file" accept=".json">`
2. POST to `/api/benchmark/import` with `FormData` containing file
3. Response includes `imported_count`
4. On success: alerts count, refreshes list
5. On failure: shows error from API response detail

### Metadata Editing

1. Click "Edit" in expanded row → opens BenchmarkMetadataModal
2. User edits fields
3. PATCH to `/api/benchmark/{id}/metadata` with updated metadata
4. On success: updates local state, closes modal

### Rerun

1. Click "▶ Rerun" in expanded row
2. Calls `onRerun(config)` callback
3. Parent (LoadTestPage) receives config and pre-fills the load test form

### Mock Data Mode

- When `isMockEnabled` is true, uses `mockBenchmarks()` instead of API calls
- All operations (delete, save metadata) work on local state only

---

## Related Components

| Component | File | Role |
|-----------|------|------|
| BenchmarkTable | `components/BenchmarkTable.tsx` | Main benchmark list table |
| BenchmarkMetadataModal | `components/BenchmarkMetadataModal.tsx` | Metadata editing modal |
| BenchmarkCompareCharts | `components/BenchmarkCompareCharts.tsx` | Multi-benchmark comparison |
| ConfirmDialog | `components/ConfirmDialog.tsx` | Confirmation dialogs |
| ErrorAlert | `components/ErrorAlert.tsx` | Error display |
| LoadingSpinner | `components/LoadingSpinner.tsx` | Loading indicator |

## Related Contexts

| Module | File | Role |
|--------|------|------|
| BenchmarkSelectionContext | `contexts/BenchmarkSelectionContext.tsx` | Multi-select state management |
| MockDataContext | `contexts/MockDataContext.tsx` | Mock data toggle |

## Related Utilities

| Utility | File | Role |
|---------|------|------|
| authFetch | `utils/authFetch.ts` | Authenticated HTTP requests |
| export | `utils/export.ts` | JSON/CSV download, CSV conversion |
| metrics | `utils/metrics.ts` | GPU efficiency calculation |
| mockData | `mockData.ts` | Mock benchmark data generation |
