Backend/requirements.txt: Added upper bounds for 14 dependencies (fastapi, uvicorn, httpx, pydantic, pydantic-settings, kubernetes, optuna, pytest, pytest-asyncio, pytest-cov, python-dotenv, python-dateutil, psutil, prometheus-client) to enforce <major compatibility. Each line now uses the form >=X,<Y. Verified that there are no bare >= without an accompanying upper bound via a follow-up grep (see verification below).
Verification plan:
- Run: grep ">=" backend/requirements.txt | grep -v "<"
- Expected: 0 lines (all dependencies pinned with an upper bound)

Code quality improvement notes:
- Replaced deprecated utcnow() usage with timezone-aware datetime.now(timezone.utc) in two backend routes:
  - backend/routers/metrics.py: import updated to "from datetime import datetime, timezone"; timestamp computed as datetime.now(timezone.utc).timestamp()
  - backend/routers/benchmark.py: import updated to "from datetime import datetime, timezone"; timestamp computed as datetime.now(timezone.utc).timestamp()
- Confirmed import updates and usage changes via patch; all other logic unchanged and timestamp types remain float.
- Verified by grepping for utcnow occurrences: none found in backend/routers/ (and the codebase portion touched).
- Next steps: run unit and integration tests to ensure no regressions and verify /api/metrics endpoints emit expected data.
Appended entries for .gitignore updates:
- .sisyphus/
- coverage/
- .nyc_output/
- htmlcov/
- *.log
- frontend/dist/

## Task 5: except Exception narrowing (2026-03-19)
- Pattern for grep-based verification: `# intentional: xxx` inline on the `except` line (not inside the block)
- `grep -v "# intentional"` filters the whole line, so comment must be on same line as `except Exception`
- Exception mapping applied:
  - File I/O: `except OSError:` (metrics_collector `_load_token`)
  - K8s API calls: `except client.exceptions.ApiException:` / `K8sApiException` (added module-level import to vllm_config.py)
  - asyncio.wait_for timeout: `except asyncio.TimeoutError:` (main.py `/api/config`)
  - K8s config loading (startup/fallback pattern): `# intentional: non-critical`
  - httpx + data parsing mixed try blocks: kept `Exception # intentional: non-critical` (narrowing httpx-only would let KeyError/JSONDecodeError escape)
  - Load test dispatch errors: `# intentional: non-critical` (any exception → RequestResult failure)
- `from kubernetes.client.exceptions import ApiException as K8sApiException` safe at module level even when client init is deferred
- `.sisyphus/` is in .gitignore; use `git add -f` for evidence files
