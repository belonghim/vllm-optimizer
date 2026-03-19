# Learnings — tuner-pod-restart-and-ui

## [2026-03-15] Baseline
- 단위 테스트 베이스라인: 103 passed, 8 deselected, 44 warnings

## Architecture facts (from code inspection)
- auto_tuner.py line 34: K8S_DEPLOYMENT = os.getenv("K8S_DEPLOYMENT_NAME", "vllm-deployment")
- _wait_for_ready: name=K8S_DEPLOYMENT (line 90, 101, 116)
- _apply_params: name = K8S_DEPLOYMENT (line 513) — IS 패치 실패 시 except에서 logger.error 후 계속 진행 → return {"success": True} (line 536)
- _rollback_to_snapshot: name=K8S_DEPLOYMENT (line 571)
- tuner.py:272: os.getenv("K8S_DEPLOYMENT_NAME", "vllm-deployment")
- routers/__init__.py: load_test, metrics, benchmark, tuner만 export — vllm_config 추가 필요
- main.py:138-145: /api/config — vllm_model_name에 K8S_DEPLOYMENT_NAME 사용 (버그!)
- VLLM_IS_NAME = os.getenv("VLLM_DEPLOYMENT_NAME") or "llm-ov" (plan spec)
- IS 패치 실패 처리: except 블록에서 return {"success": False, "error": str(e)} 반환
- vllm_config.py ALLOWED_CONFIG_KEYS: MAX_NUM_SEQS, GPU_MEMORY_UTILIZATION, MAX_MODEL_LEN, MAX_NUM_BATCHED_TOKENS, BLOCK_SIZE, SWAP_SPACE, ENABLE_CHUNKED_PREFILL, ENABLE_ENFORCE_EAGER

## Key env vars
- K8S_DEPLOYMENT_NAME = "llm-ov-predictor" (Deployment 이름, metrics용)
- VLLM_DEPLOYMENT_NAME = "llm-ov" (InferenceService 이름, 02-config.yaml에서 envFrom으로 주입)
- VLLM_MODEL = "Qwen2.5-Coder-3B-Instruct-int4-ov" (모델명)

## [2026-03-15] T2 - /api/vllm-config GET/PATCH 완료
- vllm_config.py 신규 생성: 8개 ALLOWED_CONFIG_KEYS 허용, 무효키→422, 튜너실행중→409
- auto_tuner.py와 동일한 asyncio.to_thread() 패턴으로 동기 K8s API 호출
- basepyright `reportAttributeAccessIssue` on `cm.data` - pre-existing pattern (kubernetes stub 없음), auto_tuner.py line 478에도 동일
- main.py는 다른 태스크에서 이미 수정됨(services.model_resolver import 추가) → 반드시 re-read 후 수정
- 단위 테스트 103 passed baseline 유지 확인

## [2026-03-15] T4 - tuner/config test additions
- `test_tuner.py`: import `VLLM_IS_NAME`, assert the IS patch and rollback helpers use the IS name, add failure handling + rollback coverage, plus `/api/config` validations
- Added `backend/tests/test_vllm_config.py` with GET/PATCH success, invalid key, and tuner-running 409 cases including isolated_client/auto_tuner patching
- pytest backend/tests/ (-x -q -m "not integration") executed — 111 passed, 8 deselected, 52 warnings; captured tail in `.sisyphus/evidence/task-4-pytest.txt`

## [2026-03-15] T7 - pod restart regression
- Added `backend/tests/integration/performance/test_pod_restart.py` to confirm tuner trial applications restart the vLLM pod via UID comparison and to cover `/api/vllm-config` patch flows while respecting the backup_restore_vllm_config fixture; evidence stored in `.sisyphus/evidence/task-7-e2e-test.txt`.
- Non-integration pytest backend/tests/ (-x -q -m "not integration") output: `111 passed, 10 deselected, 52 warnings in 40.71s` (tail captured per instructions).
