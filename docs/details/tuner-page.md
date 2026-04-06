# TunerPage — Detailed Documentation

## Overview

The TunerPage provides automated hyperparameter tuning for vLLM inference services. It uses Bayesian optimization to find optimal configuration parameters (max_num_seqs, gpu_memory_utilization, max_model_len, etc.) that balance throughput (TPS) and latency (P99). The page supports real-time progress tracking via SSE, parameter importance analysis, and automatic benchmark saving.

**Source**: `frontend/src/pages/TunerPage.tsx`

---

## Page Layout (Top → Bottom)

### 1. Target Selector

| Element | Type | Description |
|---------|------|-------------|
| Label | Text | "Target:" — identifies the selector |
| TargetSelector | Dropdown | Custom dropdown for selecting which InferenceService to tune |

**Behavior**:
- Uses `TargetSelector` component (same as used in LoadTestPage)
- Groups targets by CR type: KServe (isvc) and LLMInferenceService (llmisvc)
- Default target is marked with ★
- Selecting a target overrides the global cluster config target for tuning operations
- If no target is selected, falls back to the global endpoint from ClusterConfigContext

---

### 2. TunerConfigSection Component

**Source**: `frontend/src/components/TunerConfigSection.tsx`

This section contains two sub-components: TunerStatusPanel and TunerCurrentConfig.

#### 2.1 TunerStatusPanel

**Source**: `frontend/src/components/TunerStatusPanel.tsx`

Displays status messages, warnings, and controls at the top of the tuning section.

| Element | Condition | Description |
|---------|-----------|-------------|
| Interrupted Warning | `interruptedWarning !== null` | Warning banner if a previous tuning run was interrupted. Includes dismiss (×) button |
| Error Alert | `error !== null` | Red error banner for tuning errors |
| Warning Alert | `warning !== null` | Yellow warning banner for tuning warnings |
| Success Message | `applyStatus === "success"` | Green message: "Best parameters applied successfully" |
| Success Message | `applyStatus === "apply_current_success"` | Green message: "Current values applied successfully" |
| Auto Benchmark Checkbox | Always visible | Checkbox: "Auto-benchmark after tuning" — when enabled, automatically saves the best result as a benchmark |
| Benchmark Saved Message | `benchmarkSaved === true` | Green message: "Benchmark saved" with optional ID |
| Go to Benchmark Button | `benchmarkSaved && onTabChange` | Button to navigate to the Benchmark page after saving |

#### 2.2 TunerCurrentConfig

Contains the tuning configuration form and control buttons. Also fetches current vLLM config from the API on mount, handles "Apply Current Values" with confirmation dialog, and manages storage URI updates. Also fetches current vLLM config from the API on mount, handles "Apply Current Values" with confirmation dialog, and manages storage URI updates.

**Configuration Fields**:

| Field | Type | Description |
|-------|------|-------------|
| Objective | Select | Optimization objective: "balanced", "maximize_tps", "minimize_latency" |
| Evaluation Mode | Select | "single" (single-point evaluation) or "sweep" (RPS sweep evaluation) |
| N Trials | Number | Number of optimization trials to run |
| Max Num Seqs (min-max) | Number range | Minimum and maximum `max_num_seqs` values to explore |
| GPU Memory (min-max) | Number range | GPU memory utilization range (0.0–1.0) |
| Max Model Len (min-max) | Number range | Maximum model length range in tokens |
| Max Num Batched Tokens (min-max) | Number range | Batched tokens range |
| Block Size Options | Multi-select | Block size options: [8, 16, 32] |
| Include Swap Space | Checkbox | Whether to include swap space in tuning |
| Swap Space (min-max) | Number range | Swap space range in GB |
| Eval Concurrency | Number | Number of concurrent requests for evaluation |
| Eval RPS | Number | Requests per second for evaluation |
| Eval Requests | Number | Total requests per evaluation trial |
| VLLM Endpoint | Text (read-only) | Auto-populated from cluster config or selected target |

**Control Buttons**:

| Button | State | Description |
|--------|-------|-------------|
| ▶ Start Tuning | Enabled when not running | Starts the tuning process with current configuration |
| ■ Stop | Enabled when running | Stops the running tuning process |
| Apply Best | Enabled when `hasBest === true` | Applies the best-found parameters to the running vLLM instance |
| Apply Current | Always enabled | Applies the current form values to the running vLLM instance |

---

### 3. TunerResults Component

**Source**: `frontend/src/components/TunerResults.tsx`

Displays tuning results after trials have been completed.

#### 3.1 Export Results Panel

| Button | Description |
|--------|-------------|
| Export JSON | Downloads all trials, best params, and importance data as JSON file |
| Export CSV | Downloads trials data as CSV file |

Shown only when `trials.length > 0`.

#### 3.2 Best Parameters Panel

Shown when `bestParams` exists.

| Element | Description |
|---------|-------------|
| Best TPS | MetricCard showing optimal tokens-per-second value |
| P99 Latency | MetricCard showing optimal P99 latency in ms |
| Parameters Table | Two-column table: Parameter name → Optimal value |

#### 3.3 Trial Distribution Chart (Scatter Chart)

| Axis | Data |
|------|------|
| X-axis | TPS (tokens per second) |
| Y-axis | P99 Latency (ms) |

**Visual encoding**:
- **Cyan dots** (opacity 0.7): Regular trials
- **Green dots** (opacity 1.0): Pareto-optimal trials
- Legend appears below chart when pareto-optimal trials exist

#### 3.4 Best Score Convergence Chart (Line Chart)

| Axis | Data |
|------|------|
| X-axis | Trial number |
| Y-axis | Best score value |

- Shows how the best score improves over trials
- Only shown when `best_score_history.length > 1`
- Monotone line with accent color, no dots

#### 3.5 Parameter Importance (FAnova)

| Element | Description |
|---------|-------------|
| Parameter name | Name of the hyperparameter |
| Importance bar | Horizontal progress bar showing percentage contribution |
| Percentage | FAnova importance score as percentage |

- Sorted by importance (highest first)
- Only shown when `Object.keys(importance).length > 0`

---

### 4. TunerHistoryPanel Component

**Source**: `frontend/src/components/TunerHistoryPanel.tsx`

Displays historical tuning sessions in a table with columns: Date, Objective, Trials, Best TPS, Best P99, Delete. Users can select up to 2 sessions and click "Compare Selected" to view a side-by-side comparison of best parameters. Sessions can be deleted with confirmation. Fetches sessions from `/api/tuner/sessions` on mount.

---

## Data Flow

### useTunerLogic Hook

**Source**: `frontend/src/hooks/useTunerLogic.ts`

The core business logic for the TunerPage.

#### State Management

| State | Type | Description |
|-------|------|-------------|
| error | string \| null | Current error message |
| warning | string \| null | Current warning message |
| status | TunerStatus | Running state, trials completed, best params, score history |
| trials | TunerTrial[] | Array of completed trials |
| importance | Record<string, number> | FAnova parameter importance scores |
| currentPhase | TunerPhase \| null | Current tuning phase from SSE |
| applyStatus | string \| null | Status of parameter apply operation |
| interruptedWarning | string \| null | Warning about interrupted runs |
| autoBenchmark | boolean | Whether to auto-save benchmark after tuning |
| benchmarkSaved | boolean | Whether benchmark was just saved |
| benchmarkSavedId | number \| null | ID of the saved benchmark |
| initialized | boolean | Whether initial data has been loaded |
| config | TunerConfig | Current tuning configuration |

#### Polling

- Fetches status, trials, and importance every 3 seconds via `Promise.allSettled`
- Endpoints: `/api/tuner/status`, `/api/tuner/trials`, `/api/tuner/importance`
- Graceful degradation: if some endpoints fail, shows partial error message

#### SSE Streaming

- Connects to `/api/tuner/stream` when `status.running === true`
- Event handlers:
  - `phase`: Updates current phase display
  - `tuning_error`: Sets error state
  - `tuning_warning`: Sets warning state
  - `benchmark_saved`: Sets benchmark saved flag and ID
  - `trial_complete`: Refreshes status
  - `tuning_complete`: Refreshes status, clears phase

#### Configuration Auto-Population

- Fetches current vLLM config from `/api/vllm-config` on mount
- Auto-fills form fields with current vLLM values
- User-edited fields are tracked via `userEditedRef` and not overwritten by auto-fetch

#### Start Tuning

- POST to `/api/tuner/start` with full config payload
- Includes `auto_benchmark` flag
- Resolves endpoint from target override or global config
- In "sweep" evaluation mode, generates `sweep_config` with RPS range

#### Stop Tuning

- POST to `/api/tuner/stop`
- Clears current phase and refreshes status

#### Apply Best

- POST to `/api/tuner/apply-best`
- Applies the best-found parameters to the running vLLM instance

---

## Related Components

| Component | File | Role |
|-----------|------|------|
| TargetSelector | `components/TargetSelector.tsx` | Target selection dropdown |
| TunerConfigSection | `components/TunerConfigSection.tsx` | Config + status container |
| TunerStatusPanel | `components/TunerStatusPanel.tsx` | Status messages and controls |
| TunerCurrentConfig | `components/TunerCurrentConfig.tsx` | Config fetcher, apply-current, storage URI editor |
| TunerConfigForm | `components/TunerConfigForm.tsx` | Configuration form with fields and controls |
| TunerResults | `components/TunerResults.tsx` | Results display |
| TunerHistoryPanel | `components/TunerHistoryPanel.tsx` | Historical runs with session comparison |
| ConfirmDialog | `components/ConfirmDialog.tsx` | Confirmation dialog for apply-current action |
| MetricCard | `components/MetricCard.tsx` | Metric display cards |
| ErrorAlert | `components/ErrorAlert.tsx` | Error display |
| LoadingSpinner | `components/LoadingSpinner.tsx` | Loading indicator |

## Related Contexts & Hooks

| Module | File | Role |
|--------|------|------|
| useTunerLogic | `hooks/useTunerLogic.ts` | Core tuning logic |
| useSSE | `hooks/useSSE.ts` | Server-Sent Events connection |
| ClusterConfigContext | `contexts/ClusterConfigContext.tsx` | Global cluster configuration |
| MockDataContext | `contexts/MockDataContext.tsx` | Mock data toggle |

## Error States & Edge Cases

### 튜닝 중 페이지 이탈 후 복귀

튜닝 실행 중(상태: "running")에 사용자가 페이지를 이탈하거나 브라우저를 닫은 후:
- 다시 TunerPage에 진입하면 `/api/status/interrupted` 엔드포인트를 통해 이전에 중단된 튜닝 세션이 있는지 확인
- 발견되면 `interruptedWarning` 상태에 경고 배너 표시: "A previous tuning run was interrupted."
- × 버튼을 클릭하여 해당 경고를 닫을 수 있음
- 이 경고는 TunerStatusPanel 상단에 표시됨

### model="auto" 사용 금지

튜닝 설정에서 Model 필드에 "auto" 값을 입력하면:
- 백엔드 Preflight Check에서 거부됨
- 400 에러 반환: "Preflight check failed: model 'auto' is not allowed"
- auto_tuner는 `/api/v1/models` 엔드포인트를 통해 실제 모델 이름을 동적으로 해결해야 함
- 사용자가 직접 사용 가능한 모델 이름을 입력해야 함 (예: `meta-llama/Llama-3.1-8B-Instruct`)

### 튜닝 중 중복 시작 방지

▶ Start Tuning 버튼 클릭 시:
- 백엔드에서 `auto_tuner.is_running` 상태를 확인함
- 이미 튜닝이 실행 중인 경우 409 에러 반환: "Tuning is already running. Wait for it to complete or stop it first."
- 중복 시작을 방지하기 위해 버튼은 실행 중 비활성화되지 않으나, 백엔드에서 에러를 반환함

### 파라미터 적용 시 튜닝 실행 중

■ Stop 버튼을 클릭하지 않고 Apply Best 또는 Apply Current를 클릭하면:
- 백엔드에서 `auto_tuner.is_running` 상태를 확인함
- 튜닝이 실행 중인 경우 409 에러 반환: "Tuning is in progress. Wait for completion or stop first."
- Apply Best, Apply Current 버튼은 튜닝이 완료된 후에만 사용 가능함 |
