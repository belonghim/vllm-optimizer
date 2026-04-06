# SlaPage — Detailed Documentation

## Overview

The SlaPage manages SLA (Service Level Agreement) profiles for monitoring vLLM inference service performance. Users can create, edit, and delete SLA profiles with custom thresholds for availability, latency, error rate, and throughput. The page evaluates selected benchmarks against SLA profiles and visualizes results with interactive bar charts showing pass/fail status against defined thresholds.

**Source**: `frontend/src/pages/SlaPage.tsx`

---

## Page Layout (Top → Bottom)

### 1. Error Alert

| Element | Description |
|---------|-------------|
| ErrorAlert | Displays errors from SLA operations (profile load, save, delete, evaluation). Class: `error-alert--mb8` |

---

### 2. SlaProfileForm Component

**Source**: `frontend/src/components/SlaProfileForm.tsx`

Form for creating and editing SLA profiles.

| Field | Label | Type | Description |
|-------|-------|------|-------------|
| Name | Profile Name | Text input | Unique name for the SLA profile |
| Availability Min | Min Availability (%) | Number input | Minimum availability percentage (e.g., 99.9) |
| P95 Latency Max | Max P95 Latency (ms) | Number input | Maximum P95 latency in milliseconds |
| Error Rate Max | Max Error Rate (%) | Number input | Maximum error rate percentage |
| Min TPS | Min TPS | Number input | Minimum tokens per second |

**Validation**:
- At least one threshold field must be filled
- If all threshold fields are empty, shows error: "At least one threshold must be set"

**Control Buttons**:

| Button | State | Description |
|--------|-------|-------------|
| Create / Save | Enabled when form valid | Creates new profile (POST) or updates existing (PUT) |
| Cancel | Visible when editing | Cancels editing mode, resets form |

**Behavior**:
- In create mode: POST to `/api/sla/profiles`
- In edit mode: PUT to `/api/sla/profiles/{id}`
- On success: resets form, reloads profile list
- On failure: shows error from API response detail (supports both string and array of validation errors)

---

### 3. SlaProfileList Component

**Source**: `frontend/src/components/SlaProfileList.tsx`

Table listing all saved SLA profiles.

| Column | Header | Data |
|--------|--------|------|
| 1 | (radio) | Radio button for profile selection |
| 2 | Name | Profile name |
| 3 | Threshold Summary | Human-readable threshold summary (e.g., "Availability≥99.9% · P95≤200ms") |
| 4 | Actions | Edit button + Delete button |

**Threshold Summary Format**:
- `Availability≥{value}%` — if `availability_min` is set
- `P95 Latency≤{value}ms` — if `p95_latency_max_ms` is set
- `Error Rate≤{value}%` — if `error_rate_max_pct` is set
- `TPS≥{value}` — if `min_tps` is set
- Multiple thresholds joined with ` · ` separator
- If no thresholds: shows "No thresholds set"

**Behavior**:
- Selecting a profile (radio) triggers SLA evaluation against currently selected benchmarks
- Edit button populates the form above with profile data and scrolls to top
- Delete button opens confirmation dialog

**Empty State**:
- When `profiles.length === 0`: "No SLA profiles defined."

---

### 4. Metrics Trend Chart Panel

Shown when a profile is selected (`selectedProfileId !== null`).

#### 4.1 Panel Header

| Element | Description |
|---------|-------------|
| Title | Profile name + " - Metrics Trend" |
| Metric Toggle Buttons | Four buttons to switch chart metric view |

#### 4.2 Metric Toggle Buttons

| Button | Metric ID | Description |
|--------|-----------|-------------|
| P95 Latency | `p95_latency` | Shows P95 latency values with threshold line |
| Availability | `availability` | Shows availability values with threshold line |
| Error Rate | `error_rate` | Shows error rate values with threshold line |
| TPS | `min_tps` | Shows TPS values with threshold line |

**Behavior**:
- Active button is highlighted with cyan background
- Inactive buttons have transparent background with border
- Switching metric updates chart data and threshold line

#### 4.3 Benchmark Selection Prompt

| Condition | Message |
|-----------|---------|
| `selectedIds.length === 0` | "Select benchmarks from the Benchmark page to evaluate against this SLA profile." |

#### 4.4 Bar Chart

**Visualization**:

| Element | Description |
|---------|-------------|
| Chart Type | Recharts BarChart |
| X-axis | Benchmark names |
| Y-axis | Metric values |
| Bars | One bar per benchmark, color-coded using `TARGET_COLORS` |
| Reference Line | Red horizontal line showing SLA threshold |
| Legend | Benchmark names with corresponding colors |

**Chart Dimensions**:
- Width: 100%
- Height: 30vh (min: 220px, max: 420px)

**Threshold Label Format**:
- P95 Latency: `SLA: {value}ms`
- TPS: `SLA: {value} req/s`
- Availability/Error Rate: `SLA: {value}%`

**Empty State**:
- When no evaluation results: "No evaluation results available."

---

### 5. ConfirmDialog Component

**Source**: `frontend/src/components/ConfirmDialog.tsx`

Used for profile deletion confirmation.

| Operation | Title | Message |
|-----------|-------|---------|
| Delete Profile | "Delete SLA Profile" | "Are you sure you want to delete this SLA profile? This action cannot be undone." |

---

## Data Flow

### Profile CRUD

**Load Profiles**:
1. On mount (when `isActive`), calls `loadProfiles()`
2. GET from `/api/sla/profiles`
3. Results stored in `profiles` state

**Create Profile**:
1. Fill form fields
2. Submit → POST to `/api/sla/profiles`
3. Body: `{ name, thresholds: { availability_min, p95_latency_max_ms, error_rate_max_pct, min_tps } }`
4. On success: reset form, reload profiles

**Update Profile**:
1. Click Edit → form populated with profile data
2. Modify fields
3. Submit → PUT to `/api/sla/profiles/{id}`
4. On success: reset form, reload profiles

**Delete Profile**:
1. Click Delete → ConfirmDialog
2. Confirm → DELETE to `/api/sla/profiles/{id}`
3. On success: reload profiles, clear selected profile if deleted

### SLA Evaluation

**Trigger**:
- When a profile is selected AND benchmarks are selected in BenchmarkSelectionContext

**Flow**:
1. POST to `/api/sla/evaluate`
2. Body: `{ profile_id, benchmark_ids: [...] }`
3. Response: `SlaEvaluateResponse` containing:
   - `profile`: The evaluated SLA profile
   - `results`: Array of `SlaEvaluationResult` per benchmark
   - `warnings`: Optional warning messages

**Evaluation Result Structure**:
```
{
  benchmark_id: number,
  benchmark_name: string,
  timestamp: number,
  verdicts: [
    { metric, value, threshold, pass, status: 'pass' | 'fail' | 'insufficient_data' }
  ],
  overall_pass: boolean
}
```

**Auto-re-evaluation**:
- When `selectedIds` changes (from BenchmarkSelectionContext), re-evaluates the currently selected profile

### Chart Data Transformation

1. Takes `currentEval.results` array
2. For each result, finds the verdict matching the selected metric (`chartMetric`)
3. Creates chart data point: `{ name: benchmark_name, value, threshold }`
4. Threshold extracted from any data point for the reference line

---

## Integration with BenchmarkSelectionContext

The SlaPage integrates with `useBenchmarkSelection()` context to:
- Read `selectedIds` — benchmarks selected in the BenchmarkPage
- Automatically re-evaluate SLA profile when selection changes
- Display "Select benchmarks" message when nothing is selected

This creates a cross-page workflow:
1. User selects benchmarks in BenchmarkPage
2. Switches to SLA page
3. Selects an SLA profile
4. Evaluation results appear automatically

---

## Related Components

| Component | File | Role |
|-----------|------|------|
| SlaProfileForm | `components/SlaProfileForm.tsx` | Create/edit SLA profile form |
| SlaProfileList | `components/SlaProfileList.tsx` | Profile list table |
| ConfirmDialog | `components/ConfirmDialog.tsx` | Delete confirmation |
| ErrorAlert | `components/ErrorAlert.tsx` | Error display |
| LoadingSpinner | `components/LoadingSpinner.tsx` | Loading indicator |

## Related Contexts

| Module | File | Role |
|--------|------|------|
| BenchmarkSelectionContext | `contexts/BenchmarkSelectionContext.tsx` | Cross-page benchmark selection state |

## Related Constants

| Constant | File | Role |
|----------|------|------|
| COLORS | `constants/index.ts` | Theme colors for chart |
| TOOLTIP_STYLE | `constants/index.ts` | Chart tooltip styling |
| TARGET_COLORS | `constants/index.ts` | Color palette for benchmarks |
| ERROR_MESSAGES.SLA | `constants/errorMessages.ts` | SLA-specific error messages |

## Error States & Edge Cases

### Threshold 없이 저장 시도

SLA 프로필 저장 시 모든 threshold 필드(Availability, P95 Latency, Error Rate, Min TPS)를 빈 상태로 두고 저장하면:
- 백엔드에서 `SlaThresholds` 모델의 `model_validator`가 이를 거부함
- 422 Unprocessable Entity 에러 반환: "At least one threshold must be set"
- SlaProfileForm에서 "At least one threshold must be set" 에러 메시지가 ErrorAlert에 표시됨
- 최소 하나의 threshold 값을 입력해야 저장이 가능함

### 벤치마크 없이 SLA 평가

SLA 프로필을 선택한 상태에서 BenchmarkPage에서 벤치마크를 선택하지 않은 경우:
- Metrics Trend Chart Panel에 "Select benchmarks from the Benchmark page to evaluate against this SLA profile." 메시지가 표시됨
- 벤치마크가 선택되지 않으면 평가가 수행되지 않음
- Bar Chart 영역에는 "No evaluation results available." 메시지가 표시됨

### 벤치마크 ID 불일치

SLA 평가 요청 시 존재하지 않는 벤치마크 ID를 포함하면:
- 해당 벤치마크는 결과에서 제외됨
- 응답의 `warnings` 배열에 "Benchmark {id} not found (may have been deleted)" 경고 메시지가 포함됨
- 존재하는 벤치마크에 대해서만 평가가 수행됨

### 프로필 삭제 후 재선택

SLA 프로필을 선택한 상태에서 해당 프로필을 삭제하면:
- 선택된 프로필 정보가クリア됨
- Metrics Trend Chart Panel이 더 이상 표시되지 않음
- 사용자가 다른 프로필을 선택하거나 새 프로필을 생성해야 함 |
