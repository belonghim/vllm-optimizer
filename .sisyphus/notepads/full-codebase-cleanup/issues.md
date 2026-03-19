# Issues — Full Codebase Cleanup

## Known Edge Cases
- auto_tuner.start() has K8s side effects in strict sequence — extraction must preserve order
- load_engine.run() uses asyncio.wait(FIRST_COMPLETED) — must NOT convert to gather()
- TunerPage has 12-field config state — thread as single config object + onChange
- LoadTestPage uses EventSource refs — these must move into useLoadTestSSE hook
- _evaluate() has warmup BEFORE probe — sequence is critical
- Vitest has no global setup file — tests import jest-dom manually per file
- T13 and T14 both touch 02-config.yaml — run sequentially or merge carefully

## Kustomize Binary
- `./kustomize` binary was missing from repo. Installed v5.8.1 and committed.
- Both dev and prod overlays build successfully with the new binary.

## Count Corrections (from Metis review)
- Exception blocks: ~14 total (not 35+)
  - auto_tuner.py: 9
  - metrics_collector.py: 3
  - load_test.py (router): 1
  - load_engine.py: 1
  - vllm_config.py: 5
  - startup_metrics_shim.py: 3
  - model_resolver.py: 1
  - main.py:73: EXCLUDE (intentional)
  - test files: EXCLUDE
- Type annotations: ~12 functions (not 40+)
- ARIA baseline: only 1 attribute in entire frontend

## Ordering Dependencies
- T7/T8 must complete before T9/T10 (page files change during decomposition)
- T9/T10/T11 must ALL complete before T12 (ARIA targets final DOM structure)
- T13 and T14 both edit 02-config.yaml — coordinate or merge
