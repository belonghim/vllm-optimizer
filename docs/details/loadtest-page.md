# LoadTestPage — Detailed Documentation

## Overview

The LoadTestPage provides load testing capabilities for vLLM inference services. It supports two modes: **Normal Test** (single-configuration load testing) and **Sweep Test** (automated RPS sweep to find saturation points). Results can be saved as benchmarks for later comparison. The page integrates with the SSE system for real-time progress updates.

**Source**: `frontend/src/pages/LoadTestPage.tsx`

---

## Page Layout (Top → Bottom)

### 1. Mode Tabs

| Tab | Description |
|-----|-------------|
| **Normal Test** | Single-configuration load testing with detailed results |
| **Sweep Test** | Automated RPS sweep to find saturation and optimal throughput |

**Behavior**:
- Active tab is highlighted with `.active` class
- Switching tabs preserves shared endpoint and model values
- Each mode renders a completely different set of components

---

### 2. Target Selector (Normal Mode Only)

| Element | Type | Description |
|---------|------|-------------|
| Label | Text | "TARGET:" |
| TargetSelector | Dropdown | Selects which InferenceService to load test |

**Behavior**:
- Uses the same `TargetSelector` component as TunerPage
- When a target is selected, automatically builds the endpoint URL from the target's namespace, inference service name, and CR type
- Endpoint is constructed via `buildDefaultEndpoint(crType, namespace, inferenceService)`
- If no target is selected, falls back to the global endpoint from ClusterConfigContext
- Model name is resolved via `/api/vllm-config` backend proxy (not direct cluster URL); uses `target.modelName` fast-path if already pre-resolved by ClusterConfigContext

---

### 3. Normal Mode Components

#### 3.1 Presets Bar

| Element | Description |
|---------|-------------|
| Label | "PRESETS:" |
| Preset Buttons | Pre-configured load test profiles from `LOAD_TEST_PRESETS` constant |

**Behavior**:
- Each preset button shows the preset name and has a tooltip with description
- Clicking a preset auto-fills: total_requests, concurrency, rps, max_tokens, stream
- Presets provide quick starting configurations for common testing scenarios

#### 3.2 LoadTestConfig Form

**Source**: `frontend/src/components/LoadTestConfig.tsx`

The main configuration form for normal load testing.

| Field | Type | Description |
|-------|------|-------------|
| Endpoint | Text input | vLLM API endpoint URL |
| Model | Text input | Model identifier (or "auto" for auto-detection) |
| Total Requests | Number | Total number of requests to send |
| Concurrency | Number | Number of concurrent requests |
| RPS | Number | Target requests per second |
| Max Tokens | Number | Maximum tokens in response |
| Prompt Template | Textarea | Custom prompt text for requests |
| Temperature | Number | Sampling temperature (0.0–1.0) |
| Stream | Checkbox | Enable streaming responses |
| Prompt Mode | Toggle | "Static" (single prompt) or "Synthetic" (generated prompts) |

**Synthetic Prompt Configuration** (when Prompt Mode = Synthetic):

| Field | Type | Description |
|-------|------|-------------|
| Distribution | Select | "uniform" or "normal" distribution for token lengths |
| Min Tokens | Number | Minimum tokens in synthetic prompts |
| Max Tokens | Number | Maximum tokens in synthetic prompts |
| Mean Tokens | Number | Mean tokens (for normal distribution) |
| StdDev Tokens | Number | Standard deviation (for normal distribution) |

**Control Buttons**:

| Button | State | Description |
|--------|-------|-------------|
| ▶ Start | Enabled when not running | Starts the load test |
| ■ Stop | Enabled when running | Stops the running load test |
| Status Tag | Dynamic | Shows current status: IDLE, RUNNING, COMPLETED, STOPPED, ERROR |

#### 3.3 SSE Reconnection Banner

| Element | Condition | Description |
|---------|-----------|-------------|
| Reconnecting Banner | `isReconnecting && status === 'running'` | Shows "↺ Reconnecting SSE... (attempt N/3)" |

#### 3.4 Interrupted Warning

| Element | Condition | Description |
|---------|-----------|-------------|
| Warning Banner | `interruptedWarning !== null` | Warns about previously interrupted load test. Includes dismiss (×) button |

#### 3.5 Progress Bar

| Element | Condition | Description |
|---------|-----------|-------------|
| Progress Header | `status === "running"` | Shows "Progress" label and percentage |
| Progress Bar | `status === "running"` | Visual progress fill (width = progress%) |

#### 3.6 Result Metrics (5 MetricCards)

Displayed after test completion.

| Card | Label | Data | Color |
|------|-------|------|-------|
| 1 | Mean TPS | `result.tps.mean` tok/s | Amber |
| 2 | TTFT Mean | `result.ttft.mean × 1000` ms | Cyan |
| 3 | P99 Latency | `result.latency.p99 × 1000` ms | Red |
| 4 | Success Rate | `(result.success / result.total) × 100` % | Green |
| 5 | GPU Eff. | GPU efficiency (tok/s/%) or "N/A" if mismatch | Purple |

#### 3.7 Latency Distribution Table

Detailed latency breakdown table:

| Metric | Data Source |
|--------|-------------|
| Total Requests | `result.total_requested` or `result.total` |
| Success | `result.success` |
| Failed | `result.failed` |
| Actual RPS | `result.rps_actual` |
| Mean Latency | `result.latency.mean × 1000` ms |
| P50 Latency | `result.latency.p50 × 1000` ms |
| P95 Latency | `result.latency.p95 × 1000` ms |
| P99 Latency | `result.latency.p99 × 1000` ms |
| TTFT Mean | `result.ttft.mean × 1000` ms |
| TTFT P95 | `result.ttft.p95 × 1000` ms |
| Total TPS | `result.tps.total` tok/s |
| GPU Efficiency | Calculated efficiency or "N/A" |

#### 3.8 Real-time Latency Chart

| Element | Condition | Description |
|---------|-----------|-------------|
| Chart | `latencyData.length > 0` | Real-time line chart showing latency (red) and TPS (accent) over time |

#### 3.9 Save as Benchmark

| Element | Condition | Description |
|---------|-----------|-------------|
| Save Button | `status === "completed" && !isMockEnabled` | "⬆ Save as Benchmark" — saves result to benchmarks |
| Saved Status | After save | Shows "✓ Saved" or "✗ Save failed" |

**Behavior**:
- Generates name as `{model}-{timestamp}`
- POST to `/api/benchmark/save` with config and result data

---

### 4. Sweep Mode Components

#### 4.1 Sweep Presets Bar

| Element | Description |
|---------|-------------|
| Label | "SWEEP PRESETS:" |
| Preset Buttons | Pre-configured sweep profiles from `SWEEP_PRESETS` constant |

**Behavior**:
- Active preset button is highlighted with primary color
- Clicking auto-fills: rps_start, rps_end, rps_step, requests_per_step, concurrency

#### 4.2 Sweep Test Settings Form

| Field | Type | Description |
|-------|------|-------------|
| Endpoint | Text input | vLLM API endpoint URL |
| Model | Text input | Model identifier |
| RPS Start | Number | Starting requests per second |
| RPS End | Number | Ending requests per second |
| RPS Step | Number | Increment between steps |
| Requests/Step | Number | Number of requests per RPS step |
| Concurrency | Number | Concurrent requests per step |
| Max Tokens | Number | Maximum tokens in response |
| Saturation Error Rate | Number | Error rate threshold for saturation detection |
| Min Stable Steps | Number | Minimum stable steps before stopping |

**Control Buttons**:

| Button | State | Description |
|--------|-------|-------------|
| ▶ Start Sweep | Enabled when not running | Starts the sweep test |
| ■ Stop | Enabled when running | Stops the running sweep |
| Status Tag | Dynamic | Shows current status |

#### 4.3 Sweep Progress

| Element | Condition | Description |
|---------|-----------|-------------|
| Starting Message | `sweepStatus === 'running' && sweepSteps.length === 0` | "Starting Sweep..." |
| Step Progress | `sweepStatus === 'running' && sweepSteps.length > 0` | "Step N+1 In Progress..." |

#### 4.4 Sweep Results Table

| Column | Data |
|--------|------|
| Step | Step number |
| RPS | Requests per second for this step |
| P99 Latency | P99 latency in ms |
| TPS | Mean tokens per second |
| Success % | Success rate percentage |
| Status | "OK" or "Saturated" (with reason tooltip) |

**Visual encoding**:
- Saturated steps have highlighted background (`var(--sweep-step-bg)`)
- "Saturated" text is shown in red

#### 4.5 Sweep Summary Metrics

| Card | Label | Data | Color |
|------|-------|------|-------|
| 1 | Optimal RPS | `sweepResult.optimal_rps` | Green |
| 2 | Saturation RPS | `sweepResult.saturation_point` or "None" | Red |
| 3 | Total Steps | `sweepResult.steps.length` | Cyan |
| 4 | Duration | `sweepResult.total_duration` seconds | Amber |

#### 4.6 Sweep Chart

**Source**: `frontend/src/components/SweepChart.tsx`

Visualizes the sweep results showing the relationship between RPS and latency/throughput.

#### 4.7 Save Sweep Result

| Element | Condition | Description |
|---------|-----------|-------------|
| Save Button | `sweepStatus === 'completed'` | "⬆ Save to Benchmark" |
| POST | Endpoint | `/api/load_test/sweep/save` |

**Note**: Despite the button label "Save to Benchmark", this saves the sweep result to sweep history, not to the benchmark store.

#### 4.8 Sweep Save History

| Column | Data |
|--------|------|
| Optimal RPS | Best RPS found |
| Steps | Number of steps in the sweep |
| Duration | Total duration in seconds |
| Actions | Delete button |

**Behavior**:
- Fetched from `/api/load_test/sweep/history?limit=20` on mount
- Delete via `/api/load_test/sweep/history/{sweepId}` DELETE

---

## Data Flow

### Normal Mode

1. **Config initialization**: Endpoint and model auto-populated from ClusterConfigContext or selected target
2. **Start**: POST to `/api/load_test/start` with config payload (includes `prompt_mode` and `synthetic_config` for synthetic prompts)
3. **SSE connection**: Connects to receive real-time progress updates
4. **Progress updates**: SSE pushes progress percentage and latency data points
5. **Completion**: Result data received, metrics displayed
6. **Save**: Optional POST to `/api/benchmark/save`

### Sweep Mode

1. **Config**: User configures RPS range and step parameters
2. **Start**: POST to `/api/load_test/sweep` with sweep config
3. **SSE connection**: Connects to `/api/load_test/stream`
4. **Step updates**: SSE pushes `sweep_step` events with per-step results
5. **Completion**: SSE pushes `sweep_completed` with full results
6. **Save**: Optional POST to `/api/load_test/sweep/save`

### Interrupted Run Detection

- On mount, checks `/api/status/interrupted` for interrupted load test runs
- If found, shows warning banner with dismiss option

### Mock Data Mode

- When `isMockEnabled` is true, uses `simulateLoadTest()` instead of API calls
- Simulates progress, results, and latency data locally

---

## Related Components

| Component | File | Role |
|-----------|------|------|
| TargetSelector | `components/TargetSelector.tsx` | Target selection dropdown |
| LoadTestNormalMode | `components/LoadTestNormalMode.tsx` | Normal mode container (config, results, chart) |
| LoadTestSweepMode | `components/LoadTestSweepMode.tsx` | Sweep mode container (config, results, chart) |
| LoadTestConfig | `components/LoadTestConfig.tsx` | Configuration form with presets |
| LoadTestParamForm | `components/LoadTestParamForm.tsx` | Parameter input form |
| LoadTestPresetSelector | `components/LoadTestPresetSelector.tsx` | Preset selection |
| MetricCard | `components/MetricCard.tsx` | Metric display cards |
| Chart | `components/Chart.tsx` | Real-time latency chart |
| SweepChart | `components/SweepChart.tsx` | Sweep results visualization |
| ErrorAlert | `components/ErrorAlert.tsx` | Error display |

## Related Contexts & Hooks

| Module | File | Role |
|--------|------|------|
| useLoadTestSSE | `hooks/useLoadTestSSE.ts` | SSE connection for load tests |
| ClusterConfigContext | `contexts/ClusterConfigContext.tsx` | Global cluster configuration |
| MockDataContext | `contexts/MockDataContext.tsx` | Mock data toggle |

## Error States & Edge Cases

### 실행 중 타겟 변경 시도

로드 테스트 실행 중(상태가 "RUNNING"일 때)에는:
- Normal 모드의 TargetSelector가 비활성화됨 (disabled 속성)
- Sweep 모드의 타겟 관련 필드도 비활성화됨
- 이를 변경하려면 먼저 ■ Stop 버튼으로 테스트를 중지해야 함
- 실행 중 타겟 변경을 시도하면 UI层面上에서 막혀있어 별도의 에러 메시지가 나타나지 않음

### 엔드포인트 없이 Start

엔드포인트 필드가 비어있는 상태에서 ▶ Start 또는 ▶ Start Sweep 버튼을 클릭하면:
- 백엔드에서 Preflight Check 실패로 400 에러 반환
- ErrorAlert에 "Preflight check failed" 관련 오류 메시지 표시
- 에러 타입은 `preflight_error`로, 구체적인 이유는 엔드포인트 URL 누락이 원인이 됨

### SSE 연결 끊김 (Reconnection)

SSE 연결이 끊어지는 경우:
- `isReconnecting` 상태가 true로 전환됨
- 페이지 상단에 "↺ Reconnecting SSE... (attempt N/3)" 배너가 표시됨
- 최대 3번까지 재연결을 시도함
- 재연결 실패 시 (또는 3회 모두 실패 시) 테스트 상태가 "stuck"으로 유지되지 않도록 자동 처리됨
- 이 재연결 로직은 `useLoadTestSSE` 후크에서 관리됨

### 인터럽트된 테스트 복구

로드 테스트 실행 중 페이지 이탈(브라우저 닫기, 새로고침 등) 후 다시 진입하면:
- `/api/status/interrupted` 엔드포인트를 통해 이전에 중단된 테스트가 있는지 확인
- 발견되면 `interruptedWarning` 상태에 경고 배너 표시
- 사용자가 × 버튼을 클릭하여 해당 경고를 닫을 수 있음 |
