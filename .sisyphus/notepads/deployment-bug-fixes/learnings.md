# Learnings — deployment-bug-fixes

## 2026-03-07 Session ses_33bc2a80affebk4hqb0W6dd7it

### Context
- Worktree: /home/user/project/vllm-optimizer-bugfix
- Branch: deployment-bug-fixes
- Plan: 17 bugs + 1 new endpoint, 12 Tasks across 5 Waves

### Key Findings from Analysis
- Frontend pod serves static JS. All API calls run in user's BROWSER, not in the pod.
- nginx proxy_pass uses service DNS (vllm-optimizer-backend) — only works from inside cluster
- Backend Service port: 8000 (03-backend.yaml:129-131), not 8080
- Root nginx.conf is what Dockerfile actually copies (COPY ../nginx.conf) — but this fails build context
- frontend/nginx.conf has CORS block — must be removed when FastAPI takes over CORS
- metrics_collector.py already uses PROMETHEUS_URL correctly — do NOT touch it except await fix
- TuningConfig uses tuple fields (max_num_seqs_range) not separate min/max — backend must flatten
- 04-frontend.yaml affinity at wrong YAML level (spec vs spec.template.spec)
- SSE requires Connection '' not Connection "upgrade"

### Guardrails (from Metis)
- NEVER: allow_origins=["*"] + allow_credentials=True
- NEVER: modify metrics_collector.py beyond lines 195,246
- NEVER: add test_id state tracking
- NEVER: hardcode cluster URLs in source
- MUST: FastAPI is sole CORS authority after Task 1

### Wave Dependency
Wave1 (infra) → Wave2+Wave3 (backend, parallel) → Wave4 (frontend) → Wave5 (yaml) → Wave6 (verify)
### Bug Fixes for nginx/Dockerfile Configuration

- **Bug #7 & #13 (Dockerfile COPY path & nginx.conf consolidation):**
  - Changed `frontend/Dockerfile:16` from `COPY ../nginx.conf` to `COPY nginx.conf`.
  - Deleted the root `nginx.conf` file, consolidating the configuration to `frontend/nginx.conf` only.
  - **Bug #2 (proxy_pass port):**
  - Changed `frontend/nginx.conf:25` from `proxy_pass http://vllm-optimizer-backend:8080` to `proxy_pass http://vllm-optimizer-backend:8000` to correctly point to the backend port.
- **Bug #16 (nginx CORS block removal):**
  - Removed the entire CORS block (`add_header Access-Control-Allow-Origin` through `return 204;`) from `frontend/nginx.conf`. FastAPI's CORSMiddleware will now be the sole CORS authority.
- **Bug #18 (SSE compatibility for Connection header):**
  - Changed `frontend/nginx.conf:46` from `proxy_set_header Connection "upgrade"` to `proxy_set_header Connection ''` for Server-Sent Events (SSE) compatibility.

All changes were verified using the provided QA commands.

## Bug Fixes for backend/main.py

### Bug #6: Incorrect Environment Variable
- **Issue**: `check_prometheus_health()` function was reading `THANOS_URL` environment variable, but the ConfigMap provides `PROMETHEUS_URL`.
- **Resolution**: Changed `os.getenv("THANOS_URL", ...)` to `os.getenv("PROMETHEUS_URL", ...)`.

### Bug #14: Insecure TLS Verification
- **Issue**: `httpx.AsyncClient` was using `verify=False` for TLS verification, which is insecure.
- **Resolution**: Implemented dynamic CA path checking. The `verify` parameter now uses `_ca_path` if `/var/run/secrets/kubernetes.io/serviceaccount/ca.crt` exists, otherwise it falls back to `False` for local development compatibility.

### Verification
All QA checks passed:
- `THANOS_URL` is no longer directly referenced in `backend/main.py`.
- `PROMETHEUS_URL` is correctly used in `check_prometheus_health()`.
- `verify=False` is no longer directly used in `backend/main.py`.
- `backend/services/metrics_collector.py` remains untouched.

## Bug Fixes for backend/services/metrics_collector.py

### Bug #17: `await resp.json()` on synchronous method
- **Issue**: `await resp.json()` was incorrectly used on `httpx.Response.json()`, which is a synchronous method, leading to `TypeError` and silent metric collection failures.
- **Resolution**: Removed `await` from `resp.json()` on lines 195 and 246.
- **Verification**:
    - `grep -c 'await resp.json'` returned 0.
    - `grep -c 'resp.json()'` returned 2.
    - `wc -l backend/services/metrics_collector.py` showed no change in line count (315 lines).

### Bug #4: Dynamic CORS Configuration

**Issue:** The CORS middleware in `backend/main.py` was hardcoded to allow only localhost origins, preventing dynamic configuration via environment variables.

**Resolution:** Modified `backend/main.py` to read `ALLOWED_ORIGINS` from the environment variable. If `ALLOWED_ORIGINS` is not set or is empty, it falls back to a predefined list of localhost origins. This ensures flexibility for deployment while maintaining security by not using `allow_origins=["*"]` with `allow_credentials=True`.

**QA Checks Performed:**
1. `grep 'ALLOWED_ORIGINS' backend/main.py`: Confirmed `os.getenv("ALLOWED_ORIGINS", "")` is present.
2. `grep -c 'allow_origins=\["\*"\]' backend/main.py`: Confirmed no hardcoded `["*"]` is used.
3. `grep 'localhost:5173' backend/main.py`: Confirmed the fallback localhost origin list is still present.

All checks passed.
