# AGENTS.md — vLLM Optimizer (OpenShift Deployment)
Upon completion, proceed to git push.

---

## Architecture

- **Backend**: FastAPI (Python) port `8000` · **Frontend**: React + nginx port `8080`
- **Storage**: SQLite + PVC · **Monitoring**: Thanos Querier
- **Design**: Compact 2-Pod. No microservice splits. Closed-loop: Measure → Analyze → Optimize → Apply → Re-measure.
- **Dual CR**: Both KServe `InferenceService` and `LLMInferenceService` (LLMIS) via `CRAdapter` (`backend/services/cr_adapter.py`). All components must support both.

---

## Environment Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `VLLM_NAMESPACE` | LLM inference namespace | `vllm-lab-dev` |
| `VLLM_CR_TYPE` | CR type | `inferenceservice` \| `llminferenceservice` |
| `PROMETHEUS_URL` | Thanos Querier URL | `https://thanos-querier.openshift-monitoring.svc:9091` |
| `K8S_DEPLOYMENT_NAME` | LLM Deployment name (KServe: `{name}-predictor`) | `llm-ov-predictor` |
| `VLLM_DEPLOYMENT_NAME` | InferenceService name (not Deployment!) | `llm-ov` |
| `VLLM_ENDPOINT` | LLM inference endpoint | `http://llm-ov-predictor.vllm-lab-dev.svc:8080` |
| `VLLM_MODEL` | Model name | `OpenVINO/Phi-4-mini-instruct-int4-ov` |
| `LOAD_ENGINE_TIMEOUT` | Load test timeout (default: 120s) | `120` |
| `STORAGE_PATH` | SQLite path | `/data/app.db` |

---

## Code Rules

### Backend (FastAPI)
- `async/await` for all I/O
- Singleton: `from services.shared import metrics_collector` — never instantiate directly
- Imports: bare (`from services.xxx`), no `backend.` prefix
- K8s sync client: wrap with `asyncio.to_thread()`
- Thanos: `httpx.AsyncClient(verify=False)` (self-signed certs)
- `model="auto"` prohibited — use `/v1/models` dynamic resolution
- **Dual CR**: always use `CRAdapter` — never access CR fields directly (e.g. `spec.predictor.model.args`). Methods: `read_args()`, `build_args_patch()`, `read_resources()`, `resolve_model_name(spec, fallback_name)`. Unit tests must validate both CR types.

### Frontend (React)
- `/api/*` proxied by nginx — use absolute paths
- SSE via `EventSource`; global config via `useClusterConfig()` from `ClusterConfigContext`
- Resource edit key: `resources.{tier}.{key}` (e.g. `resources.limits.cpu`)

### OpenShift YAML
- Use OpenShift `apiVersion` (`route.openshift.io/v1`, etc.)
- All Deployments: `resources.requests/limits`, liveness/readiness probes
- Security: `runAsNonRoot: true`, `allowPrivilegeEscalation: false`, `capabilities.drop: ["ALL"]`

### Linting
- **Python**: Ruff (E, F, I, UP, B, SIM), line length 120, `ruff format`
- **TypeScript**: ESLint + Prettier, strict mode
- **Test markers**: `integration` (cluster required), `performance`, `slow` — excluded by default

---

## Dual CR Reference

| | InferenceService (KServe) | LLMInferenceService (LLMIS) |
|---|---|---|
| **Namespace** | `vllm-lab-dev` / `vllm-lab-prod` | `llm-d-demo` (managed by llm-d, no direct creation) |
| **Deployment** | `{name}-predictor` | `{name}-kserve` |
| **Pod label** | `app=isvc.{name}-predictor` | `app.kubernetes.io/name={name}` |
| **Endpoint** | `http://{name}-predictor.{ns}.svc:8080` | `http://openshift-ai-inference-openshift-default.openshift-ingress.svc/{ns}/{name}` |
| **Model name** | `--served-model-name` from args | `.spec.model.name` |

- Default: KServe. Switch with `VLLM_CR_TYPE=llminferenceservice`.
- New features must implement both adapters. Unit tests must validate both CR types.

---

## Architecture Notes

- **args PATCH**: `vllm_config` = dict-merge (safe partial). `auto_tuner._apply_params` = full replacement — do not modify.
- **resources**: `ALLOWED_RESOURCE_KEYS = {"cpu", "memory", "nvidia.com/gpu"}`. GPU only in `limits`. Empty string removes key.

---

## Agent Behavioral Rules

- **Tests**: Single-run mode only (e.g. `vitest run`). No parallel test processes.
- **Processes**: Kill all started processes before finishing. Track PID. Non-interactive only.
- **E2E** (auto_tuner / load tests / RBAC / ConfigMap changes): Deploy with `./deploy.sh dev`, verify with `oc` commands, verify Pod replacement. Agent verifies directly — never ask user.
- **Dual CR validation**: Test both `VLLM_CR_TYPE=inferenceservice` and `VLLM_CR_TYPE=llminferenceservice` for CR-specific changes.
- **Playwright**: No snapshot immediately after click/type/navigation. Use `playwright_browser_evaluate` for state, `playwright_browser_console_messages` for errors. One snapshot on initial load only.
