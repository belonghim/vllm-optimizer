# vLLM Optimizer — Page Documentation

Detailed documentation for each page in the vLLM Optimizer frontend application.

## Pages

| Page | Description | Documentation |
|------|-------------|---------------|
| **Monitor** | Real-time monitoring of vLLM inference services with multi-target support, time-series charts, and SLA threshold alerts | [monitor-page.md](./monitor-page.md) |
| **Tuner** | Automated hyperparameter tuning using Bayesian optimization with real-time SSE progress, parameter importance analysis, and auto-benchmark | [tuner-page.md](./tuner-page.md) |
| **Load Test** | Load testing with Normal mode (single config) and Sweep mode (RPS saturation detection), real-time results, and benchmark saving | [loadtest-page.md](./loadtest-page.md) |
| **Benchmark** | Management of saved benchmark results with comparison charts, metadata editing, bulk operations, and GuideLLM import | [benchmark-page.md](./benchmark-page.md) |
| **SLA** | SLA profile management with threshold definition, benchmark evaluation, and metrics trend visualization | [sla-page.md](./sla-page.md) |

Reference: [api-spec.md](./api-spec.md) — full REST API specification (schemas, contracts, error codes).

## Common Components

| Component | Used In | Purpose |
|-----------|---------|---------|
| TargetSelector | Tuner, LoadTest | Dropdown for selecting InferenceService targets |
| MultiTargetSelector | Monitor | Multi-target management table with real-time metrics |
| Chart | Monitor, LoadTest | Time-series line chart (Recharts) |
| MetricCard | Tuner, LoadTest | Single metric display card |
| ErrorAlert | All pages | Error/warning message banner |
| LoadingSpinner | All pages | Loading state indicator |
| ConfirmDialog | Benchmark, SLA | Confirmation dialog for destructive actions |

## Cross-Page Workflows

### Load Test → Benchmark → SLA Evaluation

1. **LoadTestPage**: Run a load test → Save result as benchmark
2. **BenchmarkPage**: View saved benchmarks → Select multiple for comparison
3. **SlaPage**: Selected benchmarks automatically evaluated against SLA profiles

### Tuner → Benchmark

1. **TunerPage**: Run hyperparameter tuning → Enable auto-benchmark
2. Best result automatically saved as benchmark
3. "Go to Benchmark" button appears for quick navigation

### Monitor + SLA Integration

1. **MonitorPage**: Select an SLA profile from dropdown
2. Real-time metrics checked against SLA thresholds
3. Toast notifications on threshold violations (30s debounce)

## Architecture

- **Framework**: React + TypeScript
- **State Management**: React Context (ClusterConfigContext, BenchmarkSelectionContext, ThemeContext)
- **Charts**: Recharts
- **Real-time**: Server-Sent Events (SSE)
- **API**: Authenticated fetch via `authFetch` utility

## API Reference

정확한 API 스키마는 `docs/details/api-spec.md`(정본) 또는 FastAPI 서버의 `/docs` (Swagger UI) / `/openapi.json`을 참조하세요.

## Related

- [architecture.md](../architecture.md) — system architecture
- [deployment.md](../deployment.md) — build & deploy
- [integration_test_guide.md](../integration_test_guide.md) — in-cluster test recipe
- [monitoring_runbook.md](../monitoring_runbook.md) · [troubleshooting.md](../troubleshooting.md) · [user-guide.md](../user-guide.md)
