# AGENTS.md — vLLM Optimizer (OpenShift Deployment)

## Quick Commands

```bash
# Backend deps (first time)
python3 -m venv .venv && .venv/bin/pip install -r backend/requirements.txt ruff
# Frontend deps (first time)
(cd frontend && npm ci)

# Verification gate — run before finishing any change
./scripts/check.sh          # full: tests (incl. slow) + lint + type + build
./scripts/check.sh --smoke  # fast core-feature contracts (~4s)

# Deploy
./deploy.sh dev             # build + deploy to vllm-optimizer-dev
```

---

## Architecture

- **Backend**: FastAPI (Python) port `8000` · **Frontend**: React + nginx port `8080`
- **Storage**: SQLite + PVC · **Monitoring**: Thanos Querier
- **Design**: Compact 2-Pod. No microservice splits. Closed-loop: Measure → Analyze → Optimize → Apply → Re-measure.
- **Dual CR**: Both KServe `InferenceService` and `LLMInferenceService` (LLMIS) via `CRAdapter` (`backend/services/cr_adapter.py`). All components must support both.

### Key Files

| Area | Files |
|---|---|
| Dual CR | `backend/services/cr_adapter.py` |
| Metric collection | `backend/services/multi_target_collector.py` (+ `metric_math.py`) |
| Storage | `backend/services/storage.py` (+ `storage_schema.py`) |
| Auto-tuner | `backend/services/auto_tuner.py` (facade) · `tuner_logic.py` · `k8s_operator.py` · `event_broadcaster.py` |
| Model analysis | `backend/services/model_analysis.py` (pure config.json math) · `model_config_reader.py` (pod exec I/O + measured KV from pod `/metrics`) · `GET /api/tuner/model-analysis` |
| Analyst LLM | `backend/services/llm_assistant.py` — separate model via `ANALYST_ENDPOINT` (dev: `llm-ov`); narrates computed facts only |
| Routers | `backend/routers/*.py` — mounted under `/api/<name>` in `backend/main.py` |
| Frontend config | `frontend/src/contexts/ClusterConfigContext.tsx` (+ `useConfigMapTargets`, `useResolvedModelName`) |
| Frontend SSE | `frontend/src/utils/reconnectingEventSource.ts` |
| Docs | `docs/details/README.md` (page index) · `docs/architecture.md` · `docs/integration_test_guide.md` (in-pod pytest recipe) · Changelog: `CHANGELOG.md` (append per round; older rounds in `docs/CHANGELOG-archive.md`) |

---

## Environment Variables

Canonical definitions: `backend/.env.example` (local) and `openshift/base/02-config.yaml` (deployed).

| Variable | Description | Default |
|---|---|---|
| `VLLM_NAMESPACE` | vLLM workload namespace | `vllm-lab-dev` |
| `VLLM_CR_TYPE` | CR type: `inferenceservice` \| `llminferenceservice` | `inferenceservice` |
| `VLLM_DEPLOYMENT_NAME` | InferenceService name (not the Deployment; `{name}-predictor` is normalized to `{name}`) | `llm-ov-predictor` → `llm-ov` |
| `VLLM_ENDPOINT` | Inference endpoint | `http://llm-ov-predictor.vllm-lab-dev.svc.cluster.local` |
| `PROMETHEUS_URL` | Thanos Querier base URL | `https://thanos-querier.openshift-monitoring.svc.cluster.local:9091` |
| `STORAGE_PATH` | SQLite DB path | `/data/app.db` |
| `LOAD_ENGINE_TIMEOUT` | Load-test timeout (seconds) | `120` |
| `OPTUNA_STORAGE_URL` | Optuna RDB storage (unset → in-memory) | unset |
| `LOG_LEVEL` / `LOG_FORMAT` | Logging level / `json` or `text` | `INFO` / `text` |
| `CA_BUNDLE` | CA bundle path for TLS verify (`""` → all httpx clients `verify=False`) | `""` |
| `ANALYST_ENDPOINT` | Analyst LLM (separate small model, e.g. llm-ov). `""` disables it; skipped during tuning if equal to the tuning endpoint | `""` (dev overlay: llm-ov) |

Advanced/optional: `ANALYST_MODEL`(resolved via `/v1/models`), `ANALYST_TIMEOUT`(120), `LOAD_ENGINE_SHORT_TIMEOUT`(5), `MODEL_RESOLVE_TIMEOUT`(10), `SELF_METRICS_URL`, `STORAGE_CAPACITY_BYTES`, `POD_NAMESPACE`.
Integration tests only: `VLLM_MODEL`. Legacy/optional: `K8S_DEPLOYMENT_NAME`.

---

## Code Rules

### Backend (FastAPI)
- `async/await` for all I/O
- Singletons: `from services.shared import multi_target_collector, storage, runtime_config` — never instantiate directly
- Imports: bare (`from services.xxx`), no `backend.` prefix
- K8s sync client: wrap with `asyncio.to_thread()`
- Thanos: `httpx.AsyncClient(verify=False)` (self-signed certs)
- `model="auto"` is only a *default placeholder* — always resolve via `/v1/models` (`model_resolver.resolve_model_name()`); never send `"auto"` to vLLM
- **Dual CR**: always use `CRAdapter` — never access CR fields directly (e.g. `spec.predictor.model.args`). Methods: `read_args()`, `build_args_patch()`, `apply_args_to_cr()`, `restore_cr_from_snapshot()`, `read_resources()`, `resolve_model_name(spec, fallback_name)`, `pod_label_selector()`. Unit tests must validate both CR types.

### Frontend (React)
- `/api/*` proxied by nginx — use absolute paths (or the `API` constant from `src/constants`)
- SSE via `EventSource` (shared reconnect helper: `src/utils/reconnectingEventSource.ts`); global config via `useClusterConfig()`
- Resource edit key: `resources.{tier}.{key}` (e.g. `resources.limits.cpu`)
- Prettier is the formatter: `npm run format` / `npm run format:check`

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
| **API** | `serving.kserve.io/v1beta1` · `inferenceservices` | `serving.kserve.io/v1alpha1` · `llminferenceservices` |
| **Namespace** | from target/config (`VLLM_NAMESPACE`) | from target/config (no hardcoded default) |
| **Deployment** | `{name}-predictor` | `{name}-kserve` |
| **Pod label selector** | `serving.kserve.io/inferenceservice={name}` | `app.kubernetes.io/name={name},kserve.io/component=workload` |
| **Endpoint** | `http://{name}-predictor.{ns}.svc.cluster.local` (port 80) | `https://{name}-kserve-workload-svc.{ns}.svc.cluster.local:8000` (per-LLMIS workload Service; gateway-independent) |
| **Args location** | `spec.predictor.model.args` | `spec.template.containers[main].env` → `VLLM_ADDITIONAL_ARGS` |
| **Model name** | `--served-model-name` from args | `.spec.model.name` |
| **Metric prefix** | `vllm:` | `kserve_vllm:` |

- Default: KServe. Switch with `VLLM_CR_TYPE=llminferenceservice`.
- New features must implement both adapters. Unit tests must validate both CR types (`backend/tests/test_smoke.py::test_dual_cr_adapter_contract` is the fast check).

---

## Architecture Notes

- **args PATCH**: `vllm_config` = dict-merge (safe partial). `auto_tuner._apply_params` = full replacement — do not modify.
- **resources**: `ALLOWED_RESOURCE_KEYS = {"cpu", "memory", "nvidia.com/gpu"}`. GPU only in `limits`. Empty string removes key.
- **metrics_source** is **per target** (`direct` | `thanos`), not an environment variable. New targets default to `direct`.
- **Default target**: selected from ConfigMap (`DEFAULT_ISVC_*` / `DEFAULT_LLMISVC_*`) or explicit target; there is no hardcoded frontend/backend default registration.
- **Version**: single value `1.0.0` in `backend/main.py` (`APP_VERSION`), `frontend/package.json`, and `openshift/overlays/prod/kustomization.yaml` (image tags + `app.kubernetes.io/version` label) — bump together.
- **K8s labels**: `app.kubernetes.io/name=vllm-optimizer` · `instance=vllm-optimizer-{env}` · `component` per resource (`backend`/`frontend`/`monitoring`). Selectors stay on the plain `app:` label — do not point selectors at `app.kubernetes.io/*`.

---

## Agent Behavioral Rules

- **Git**: Upon completion, proceed to `git push`.
- **Tests**: Single-run mode only (e.g. `vitest run`). No parallel test processes.
- **Verification gate**: `./scripts/check.sh` or `--smoke` (fast core-feature contracts). Run before finishing any change.
- **Processes**: Kill all started processes before finishing. Track PID. Non-interactive only.
- **E2E** (auto_tuner / load tests / RBAC / ConfigMap changes): Deploy with `./deploy.sh dev`, verify with `oc` commands, verify Pod replacement. Agent verifies directly — never ask user.
- **Dual CR validation**: Test both `VLLM_CR_TYPE=inferenceservice` and `VLLM_CR_TYPE=llminferenceservice` for CR-specific changes.
- **Playwright**: No snapshot immediately after click/type/navigation. Use `playwright_browser_evaluate` for state, `playwright_browser_console_messages` for errors. One snapshot on initial load only.
