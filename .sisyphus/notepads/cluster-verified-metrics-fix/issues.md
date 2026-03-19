# Issues — cluster-verified-metrics-fix

## Guardrails (from Metis)
- MUST NOT touch auto_tuner.py async/sync K8s issues (out of scope)
- MUST NOT change endpoint paths, response schemas, or business logic
- MUST NOT modify files beyond the 6+1 listed in plan
- conftest.py MUST be updated or tests will attempt real K8s init after shared.py created

## Out of Scope (Tracked as Follow-Up)
- auto_tuner.py `_wait_for_ready()` awaits sync K8s client → TypeError in real cluster
- auto_tuner.py `_apply_params()` blocks event loop with sync K8s calls
