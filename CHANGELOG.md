# Changelog

All notable changes to this project will be documented in this file.

## [2026-10-10] - GPU 실측 검증·튜너 낭비 제거

### Fixed
- **hybrid 모델 OOM 예측이 과도하게 보수적**: 실제 RTX 3060에서 건너뛴 trial 5건 중 3건이 정상 기동했음(`max_num_seqs`×전체 GDN 상태를 KV와 합산한 탓). CUDA 백엔드는 레이어 그룹(`min(full, linear)`층) 단위 블록으로 슬롯당 1블록(Qwen3.5-0.8B: 19.5MB가 아니라 6.5MB)만 필요하고, KV 1시퀀스와 슬롯 블록은 합산이 아니라 각각 풀과 비교됨(262144 토큰 KV + 500 슬롯이 합보다 작은 풀에서 기동 확인). `ModelAnalysis.boot_state_bytes_per_seq`(OpenVINO는 전체 상태 유지)·`kv_cache_oom_risk`가 `max()` 사용. 실측 기동 결과 5건을 회귀 테스트로 고정.
- 튜너 시작 직후(파드 기동 미완료)에는 관측 보정이 없어 표 오버헤드 6.0 GiB로 대부분 건너뛰던 문제는 위 수정 + 준비 후 시작으로 해소 확인.

- **소스 대조로 부팅 진단 규칙 검증**: RHAI vLLM 0.24 이미지의 vLLM/transformers 소스에서 실제 메시지를 확인. `tp_not_divisible`·`quantization_mismatch`·`bf16_unsupported`·`unsupported_architecture`는 정규식이 소스와 일치. `trust_remote_code_required`는 transformers가 실제로는 "contains custom code which must be executed"를 출력해 기존 규칙이 놓치던 것을 수정(vLLM의 "Failed to load the model config"도 인식). `chat_template_missing`은 소스에 없는 문구를 제거하고 실제 문구만 사용(요청 시점 400 오류이며 부팅 로그에는 나오지 않음). 소스 원문을 테스트로 고정.

### Changed
- **예측/학습 스킵은 trial 예산을 소모하지 않음**: 파드 재시작 없이 건너뛴 trial은 `n_trials`에 포함하지 않고 계속 샘플링(상한 `n_trials × 5`회, 초과 시 경고). `trials_completed`도 스킵 제외. 이전에는 6회 요청 중 5회가 스킵되어 실질 1회만 평가됨.
- `llm-ov`: cpu 4 / memory 8Gi 고정(requests=limits), `--max-num-batched-tokens=512` 추가. serving1/2의 InferenceService·LLMInferenceService는 `serving.kserve.io/stop` 어노테이션으로 중지.

### Added
- 진단 규칙: `quantization_not_applicable`(`Cannot find the config file for awq`), `world_size_exceeds_gpus`, `chat_template_path_missing`; `--enable-auto-tool-choice requires --tool-call-parser`를 `tool_choice_flags_missing`으로 인식.

### Verification
- 실제 GPU(RHAI vLLM 0.24 CUDA, Qwen3.5-0.8B, serving3) 기동 실패 로그 12종으로 진단 규칙 검증 — `gpu_memory_busy`, `max_model_len_exceeds_model`, `batched_tokens_below_model_len`, `kv_cache_too_small`(추정값 54944 일치), `no_kv_memory`, `mamba_blocks_exceeded`, `cuda_oom`, 위 신규 3종 등(픽스처 `tests/fixtures/vllm_cuda_boot/`). 1 GPU 환경이라 `tp_not_divisible`, 그리고 `trust_remote_code`·`unsupported_architecture`·`chat_template_missing`·`bf16_unsupported`는 재현하지 못해 미검증.
- GPU 타깃(serving3/qwen-gpu)에서 튜너 end-to-end 실행: 6 trial 중 4건 정상 평가, 예측 스킵 2건(`max_num_seqs` 576@util 0.57은 실제로도 `Mamba cache blocks (382)`로 기동 실패).

## [2026-10-09] - 진단 피드백·실패 트라이얼 기록·오버헤드 보정

### Added
- **실패 트라이얼 기록**: 기동 실패/평가 실패/예측 스킵 트라이얼을 `failure`(`reason`, 진단 최대 3건)와 함께 저장·`/api/tuner/trials`로 노출(`tuner_trials.failure_json`, ALTER 마이그레이션).
- **진단 → 탐색 상한 학습**: `mamba_blocks_exceeded`/`kv_cache_too_small`/`max_model_len_exceeds_model`의 수치를 `TuningConfig.learned_limits`에 누적, 이후 같은 `gpu_memory_utilization` 이하에서 상한을 넘는 trial은 파드 재시작 없이 `learned_limit`으로 건너뜀.
- **학습 상한 영속화**: 학습한 상한을 `tuner_learned_limits`(target 키별, 7일 TTL)에 저장하고 다음 튜닝 시작 시 자동 적용(시작 시 `tuning_warning`으로 안내). `DELETE /api/tuner/learned-limits`로 현재 타깃의 학습분 초기화.
- **오버헤드 관측 보정**: 순수 full-attention 모델이 기동 중이면 `overhead = budget×util − weights − 관측 KV 풀`로 역산해 용량표와 튜너 OOM 예측에 사용(`memory_budget.overhead_source`: `table`/`observed`). hybrid/sliding 모델은 풀 토큰 수가 단일 토큰 크기의 배수가 아니라 보정하지 않음.

- **오버헤드 보정 확장(hybrid/sliding 포함)**: 파드 로그 앞부분의 `Available KV cache memory: X GiB`(GPU당)로 `overhead = budget×util − weights − X×GPU수`를 역산 — 토큰 수 기반 보정이 불가능한 hybrid/sliding-window 모델도 보정. 실제 RTX 3060 + Qwen3.5-0.8B(`openshift/vllm-dependency/gpu-test`의 `qwen-gpu`, serving3)에서 표 오버헤드 6.0 → 관측 ≈1.9–2.1 GiB, 8192 컨텍스트 동시성 예측 17 → 59(vLLM 보고 56, `estimate_ratio` 1.05). `observed.available_kv_gib` 추가, `estimate_ratio`는 보정 후 기준으로 계산.

### Removed
- 참조가 없는 코드 정리(vulture/knip 근거): `AutoTuner._params_to_args/_update_pareto_front/_handle_trial_result`, `CRAdapter.snapshot_args/build_rollback_patch`(+테스트; `restore_cr_from_snapshot`으로 대체됨), `RuntimeConfig.apply_default_llmisvc`, `Storage.count_trials`, `K8sOperator.get_pod_logs/get_model_name`, 미사용 e2e `MockFactory.ts`, 미사용 devDependency `@vitest/coverage-v8`·`eslint-config-prettier`.

### Tooling
- `scripts/smoke-ui.sh [dev|prod]`: `oc port-forward`로 oauth-proxy를 우회해 배포된 프론트엔드에 Playwright 스모크(`frontend/tests/e2e-live/`, `playwright.live.config.ts`)를 실행하고 종료 시 포워딩 정리. 기동 진단 카드(실제 API)와 실패/건너뜀 트라이얼 표(모킹된 `/api/tuner/trials`) 및 콘솔 에러를 확인.

### Changed
- 기동 실패 시 롤백 전에 로그를 먼저 읽음(롤백이 실패한 파드를 건강한 파드로 교체하기 때문). `AutoTuner._explain_failure` → `_on_trial_failure`(진단·학습·기록·UI 이벤트).
- 평가 실패 트라이얼이 이제 trials 목록에 `failed`로 포함됨(이전엔 누락).

### Verification
- 신규 단위 테스트: 학습 상한 규칙, 학습 상한으로 인한 스킵(재시작 없음), 기동 실패 시 로그→롤백 순서·기록·학습, 오버헤드 보정(두 CR 타입).
- GPU 경로(보정·TP 오버헤드)는 dev 클러스터에 GPU 타깃이 없어 단위 테스트로만 검증. 진단 규칙 중 `kv_cache_too_small`·`max_model_len_exceeds_model`은 dev(vLLM 0.30 OpenVINO) 실제 기동 실패 로그로 검증(픽스처 `tests/fixtures/vllm030_openvino_kv_too_small.log`; 무관한 INFO 줄에 매칭되던 evidence 수정). `batched_tokens_below_model_len`·quantization·tool-parser 규칙은 실제 로그 미검증(재현 불가/이미지 풀 지연).

## [2026-10-09] - 기동 실패 진단·Mamba 블록 상한

### Added
- **부트 로그 진단(`services/boot_diagnosis.py`)**: vLLM/transformers 에러 문구를 결정론적으로 매칭해 원인·조치·로그 속 수치(Mamba 블록 수, 추정 최대 길이, 유도 max_model_len)를 반환. Mamba 블록 초과, KV 부족, 메모리 없음, GPU 점유, CUDA OOM, max_model_len/batched_tokens 충돌, 양자화 불일치, trust-remote-code, 미지원 아키텍처, chat template, tool parser, TP 분할, bf16 미지원, OOMKilled/CrashLoopBackOff/ImagePull 포함.
- **`GET /api/tuner/boot-diagnosis`**: 대상 CR(두 타입 모두)의 최신 파드 컨테이너 상태 + 로그(재시작 시 previous) + 진단 목록.
- **Mamba 블록 상한**: 관측된 `num_gpu_blocks`가 있으면 hybrid 모델의 `suggested_search_space.max_num_seqs_max`를 이 값으로 제한하고 `--max-num-seqs` 초과 시 경고 노트(근거: vLLM `max_num_seqs > kv_cache_config.num_blocks`이면 full CUDA graph 기동 실패).

### Changed
- `K8sOperator`의 파드 로그 읽기: 모델 컨테이너 명시, 최신 파드 선택, 재시작 시 previous 로그 사용, 컨테이너 상태 요약(`read_boot_report`). 트라이얼 기동 실패 시 분석가 LLM이 꺼져 있어도 `tuning_failure_explanation`에 `diagnoses`와 진단 요약을 전송.

### Not implemented
- GDN 페이지 크기·KV 그룹 패딩의 정확한 수치 계산: 상류 소스에서 `MambaStateShapeCalculator`/`verify_and_update_config` 본문과 `SlidingWindowSpec.max_memory_usage_bytes`를 검증하지 못해 추정 공식은 넣지 않음(측정값 우선 정책 유지).

## [2026-10-09] - 모델 분석 확장: 기능 인자 추천·컨텍스트 상한 유도·오버헤드 반영

### Added
- **서빙 인자 추천(`services/serving_advisor.py`)**: 가이드(config.json → vLLM 인자 도출)의 규칙을 결정론적으로 구현. chat template 시그니처(`tool_xml`/`tool_json`/`harmony`/`gemma4_tool`/`think`)로 `--tool-call-parser`·`--reasoning-parser`·`--enable-auto-tool-choice`, 템플릿 부재 시 `--chat-template`, `--kv-cache-dtype=fp8`, hybrid `--enable-prefix-caching`, MTP `--speculative-config`, 멀티모달(`--language-model-only`·`--limit-mm-per-prompt`·`--mm-encoder-tp-mode=data`·Gemma4 `--attention-backend`), `auto_map` 시 `--trust-remote-code`, 양자화 체크포인트의 `--quantization`/`--dtype` 지정 경고. 대상 CR의 현재 args(`static + tuning`)와 비교해 present/missing/mismatch 상태와 붙여넣기용 `add_args` 제공. InferenceService·LLMIS 모두 동일 경로(`CRAdapter`).
- **모델 산출물 읽기**: pod exec로 `generation_config.json`·`tokenizer_config.json`·`chat_template.jinja`·`*.py` 목록 추가 수집(파일당 4 MiB 상한). 기본 샘플링, 사용자 정의 코드 누락 등 노트에 사용.
- **컨텍스트 상한 유도**: config 컨텍스트 키 최솟값, tokenizer `model_max_length`, YaRN `original×factor`(llama3/longrope/su/default는 제외)로 `context_limit` 계산. `--max-model-len` 초과 시 경고 노트.
- **`GET /api/tuner/model-analysis`**: 응답에 `advice`, `model.context_limit` 등 신규 필드, `runtime.max_num_batched_tokens`, `memory_budget.overhead_gib` 추가.
- **프런트엔드**: 모델 분석 패널에 "Serving arguments" 섹션(추천 표·노트·복사 가능한 `add_args`)과 신규 팩트 행.
- 분석가 LLM 팩트에 필수 기능 인자 누락/불일치 요약 추가(숫자는 계산값만 서술).

### Changed
- **용량 추정**: sliding-window 예약을 `window-1+max_num_batched_tokens`로, GPU 타깃에 TP별 보수적 오버헤드(GPU당 6/10/16/24 GiB)를 차감. 더 이상 "이론적 상한"이 아니라 계획용 추정치(실측 `observed` 우선).
- **`utilization` 기본값**: 쿼리 미지정 시 대상 CR의 `--gpu-memory-utilization`, 없으면 0.9.

### Changed (tuner)
- **튜너 OOM 예측/탐색 범위에 오버헤드 반영**: `TuningConfig.memory_overhead_gib`(= 분석의 `memory_budget.overhead_gib`)를 `kv_cache_oom_risk`의 가용 KV에서 차감하고, sliding window 예약을 trial의 `max_num_batched_tokens`로 계산(`window-1+batched`). `gpu_memory_utilization` 하한도 `(weights×1.1 + overhead)/budget`로 상향해 부팅 불가능한 trial을 사전에 건너뜀.

### Verification
- `backend/tests/test_serving_advisor.py`(신규) + `test_model_analysis.py`: 아티팩트 파싱, 템플릿 시그니처, 컨텍스트 상한, 오버헤드, 규칙별 추천, 두 CR 타입의 엔드포인트 `advice`/`utilization` 폴백 검증.

### Not implemented
- GDN 페이지 크기·KV 그룹 패딩의 정확한 계산, Mamba 블록 기반 `--max-num-seqs` 상한의 수치 계산(vLLM 내부 값 필요), 기동 로그 진단.

## [2026-10-04] - 군더더기 제거·튜너 수정·RBAC 환경 분리 및 검증 라운드

### Removed
- **TLS 정책 단일화**: `services/tls.py`의 `internal_verify`/`external_verify`(certifi + service-ca 결합 컨텍스트)를 `tls_verify()` 하나로 통합 — `CA_BUNDLE` 미설정 시 모든 httpx 클라이언트 `verify=False`(폐쇄망 자체서명: Thanos·LLMIS workload Service·MaaS 게이트웨이). 이로써 MaaS 게이트웨이도 CA 마운트 없이 호출됨. `certifi` 직접 의존 제거.
- **백엔드 HPA(`vllm-optimizer-backend-hpa`, 단일 레플리카라 무의미), 두 PDB(`vllm-optimizer-backend-pdb`/`-frontend-pdb`, 단일 레플리카), prod 백엔드 replicas=2 패치**(`5d033ed`). 프런트엔드 HPA는 유지. dev 클러스터의 잔재 삭제(`oc apply`는 prune 안 함); prod에는 잔재 없음.
- **vLLM 알림 정리**(`91acf12`): `vllm.performance`·`vllm.availability` 그룹과 `OptimizerBackendHighErrorRate` 알림, 오버레이 PrometheusRule 패치 2개, 가짜 runbook URL 제거. `vllm-lab-*`의 의존성 알림은 `vllm:`/`kserve_vllm:` 이중 접두사로 통합.
- **죽은 스크립트/도구**(`709b1c9`): `scripts/run_performance_tests.sh`, `scripts/collect_baseline.sh`, `backend/tests/integration/performance/utils/`, `performance_baseline` 픽스처, 문서 §4, deploy.sh 죽은 변수 및 dev 기본 네임스페이스 `vllm-lab-dev`로 수정.

### Fixed
- **튜너 study 재사용 prune**: 세션마다 이전 Optuna study를 재사용해 `MedianPruner`가 새 세션 trial을 prune하던 문제 → 세션 시작 시 동일 이름 study 삭제(`df7b424`, 단위 테스트 `test_setup_study_fresh_study_per_session`).
- **튜너 OOM skip 기록 누락**: KV OOM 예측으로 건너뛴 trial이 trial 목록에 기록되지 않던 문제 → `status="skipped"`, `pruned=true`로 기록, best 선택에는 영향 없음(`c392125`, 테스트 `test_oom_skipped_trial_recorded_with_skipped_status`).
- **로드 테스트 stop 500**: `POST /api/load_test/stop`을 `test_id` 없이 호출하면 `StopResponse.test_id: str` 때문에 500(ResponseValidationError) → `str | None = None`(`be20de9`, 회귀 테스트 추가). UI Stop 버튼이 항상 콘솔 500을 내던 문제 해소.
- **K8s RBAC 환경 분리**: 클러스터 범위 ClusterRoleBinding 3개(`vllm-optimizer-monitoring-view`/`auth-delegator`/`target-operator`)가 dev·prod에서 같은 이름이라 prod 배포가 dev 서브젝트를 덮어써 dev 백엔드가 `vllm-lab-dev`의 InferenceService를 못 읽던(403→500) 문제 → 오버레이별 `-dev`/`-prod` 이름(`e96fc09`). 기존 무접미 바인딩 3개는 클러스터에서 삭제(총 6개). 교훈: 클러스터 범위 객체는 오버레이마다 고유 이름이 필요하고 `oc apply`는 prune하지 않는다.

### Verification
- **인-파드 통합 테스트**: 이전 라운드 13 passed / 3 skipped(정당한 과부하 skip) / 1 failed(튜너 버그) → 위 2건 수정 후 `test_auto_tuner_completes_with_results` 단독 재실행 PASSED(`best.tps=21.4`, trials 2건: 완료 1 + skipped 1). 이후 전체 스위트(`/app/tests/integration/`, 17 tests, `-k`/`--deselect` 없음) 재실행 → 15 passed / 2 skipped / 0 failed(1138.78s), `test_auto_tuner_completes_with_results` 포함 통과. 2 skipped는 일시적 과부하 skip(`skip_if_overloaded`)으로 해당 2건만 따로 재실행 시 2 passed. 테스트 후 llm-ov args를 overlay 기준으로 복원, Ready=True.
- **SSE 터미널 재생**: `completed` 1회 후 EOF, `stopped` 1회 후 EOF.
- **LLMIS HTTPS 워크로드 서비스 경로**: 모델 `qwen`, success=2/failed=0, SSL 오류 없음, `CA_BUNDLE` 불필요.
- **UI QA(Playwright, 번들 Chromium)**: LoadTest 완료 흐름(0→90%→COMPLETED+결과표)·Stop 흐름(RUNNING→STOPPED, Start 재활성화) 모두 정상, 수정 후 콘솔 오류 0건·bad response 0건. oauth-proxy 때문에 프런트 파드 nginx `:8080` port-forward로 접근.
- **`./scripts/check.sh`** exit 0 (ALL CHECKS PASSED): backend 782 passed, frontend 446 passed (57 files), ruff·타입·빌드 통과.
- **정리 후 dev**: 백엔드 HPA/PDB 0건(프런트 HPA만), optimizer 알림 룰에 워크로드 알림 0건, `vllm-performance-alerts` 적용됨. GPU 테스트 ISVC `qwen-gpu`(serving3) 삭제(매니페스트 `openshift/vllm-dependency/gpu-test/`는 유지).
- **prod**: `vllm-optimizer-prod` 네임스페이스 신규 생성 후 배포 — 백엔드 1/1·프런트 Running 0 재시작, `instance=vllm-optimizer-prod`·`version=1.0.0`, HPA는 프런트만, PDB 0건. 서버 dry-run은 대상 네임스페이스 부재로 실패(매니페스트 결함 아님; 클라이언트 렌더 22개 리소스 OK).

### Known blockers
- **MaaS 게이트웨이 경유 부하 테스트**: 사용자 제공 API 키로 `serving1/qwen`·`serving2/lfm` 각각 4/4 성공(스트리밍, c=1, max_tokens=8). 자체서명 CA 문제는 TLS 정책 단일화(`verify=False`)로 해소.
- **prod 의존성 단계**: `vllm-lab-prod` 네임스페이스 부재로 `openshift/vllm-dependency/prod` 적용이 `namespaces "vllm-lab-prod" not found`로 실패(optimizer 배포는 정상 유지). 해당 네임스페이스를 만들 때까지 prod 모니터링 라벨 패치 단계는 미실행.
- Red Hat 2B modelcar 미러 pull 실패로 0.8B 대체 사용 중(이전 라운드부터).

## [2026-10-04] - 요청되지 않은 SQLite 백업 CronJob 제거

### Removed
- **`vllm-optimizer-sqlite-backup` CronJob + `vllm-optimizer-pod-exec` Role/`vllm-optimizer-backup-exec` RoleBinding + `backend/scripts/backup_sqlite.py`(+테스트)**: 요청 없이 추가됐던 기능(`eb927ed`). 같은 PVC에 백업을 써서 PVC 장애 대비가 되지 않았고, `registry.redhat.io/openshift4/ose-cli:latest`를 직접 pull해 폐쇄망에서 매번 `ImagePullBackOff` — 실제로 백업이 한 번도 생성되지 않았다(`/data/backup` 없음). 백엔드 SA의 네임스페이스 `pods/exec` 권한도 함께 사라짐.
- dev 클러스터에 남아 있던 CronJob·Job·Role·RoleBinding 삭제(`oc apply`는 prune하지 않음). prod에는 없음.

### Verification
- dev/prod `oc kustomize` 렌더 OK(26 objects, backup 참조 0), `./scripts/check.sh --smoke` OK.

## [2026-10-04] - SSE 터미널 재생·TLS 컨텍스트 현대화·이미지 내 스모크

### Fixed
- **SSE 늦은 구독 이벤트 유실**: `/api/load_test/stream`이 구독 이후 이벤트만 전달해 완료 후 재연결한 클라이언트가 keepalive만 받고 멈추던 문제. 엔진이 마지막 터미널 이벤트(`completed`/`stopped`/`error`/`sweep_completed`)를 기록하고 늦은 구독자에게 즉시 재생 후 스트림을 종료한다. 새 실행 시작 시(`/start`, `/sweep`, `run()`, `run_sweep()`) 이전 이벤트는 초기화. `stop()`은 실행 중일 때 `stopped` 이벤트를 브로드캐스트.
- **프런트**: `useLoadTestSSE`가 `stopped` 이벤트를 처리(상태 표시 후 연결 종료) — 서버 주도 정지와 재접속 루프 방지.

### Changed
- **TLS 검증 컨텍스트화**: `CA_BUNDLE`을 httpx `verify=<str>`(deprecated)로 넘기던 것을 `services/tls.py`의 `internal_verify()`/`external_verify()`가 `ssl.create_default_context(cafile=...)`로 생성하도록 통합. `main.py`·`shared.py` 공용, `main._external_verify` 제거(httpx 0.28+ deprecation 해소, 향후 버전 대비).

### Fixed (tests)
- **이미지 내부 스모크 실행 가능**: conftest가 `backend.*` 모듈을 무조건 import해 `/app`(이미지 레이아웃)에서 `ModuleNotFoundError: backend`로 전부 실패하던 문제 — 리포 경로/이미지 경로 어느 쪽이든 동작하는 optional import/패치로 전환. `podman run -w /app … pytest tests/test_smoke.py` 10 passed.
- 통합 테스트(SSE·스윕) 구독 순서를 "시작 후 구독"으로 복원 — 터미널 재생 덕분에 완료를 놓치지 않는다. `test_pod_restart`의 CA 경로 문자열(httpx deprecation) 제거.

### Verification
- `./scripts/check.sh` exit 0 (ALL CHECKS PASSED): backend 784 passed, frontend 446 passed (57 files).
- 이미지 빌드 후 in-image `pip check` OK · `app.version=1.0.0` · 스모크 10 passed.
- 통합 테스트는 클러스터 API 다운(EOF)으로 이번 라운드 미실행 — 복구 시 재검증 예정.

## [2026-10-04] - 메타데이터 정리: 의존성·버전·K8s 라벨·문서 컨텍스트

### Changed
- **백엔드 의존성 정리**: 미사용 `pydantic-settings`·`psutil`·`python-dateutil`·`python-dotenv`·`pytest-cov` 제거(코드 import 0회 — dateutil/dotenv는 kubernetes·uvicorn[standard] 전이 의존이라 즉시 설치도 불변), 빈 `## Rate Limiting` 헤더 삭제. `python-multipart`(UploadFile)·`pytest`/`pytest-asyncio`(인-파드 테스트)는 유지.
- **버전 단일화 1.0.0**: `backend/main.py` 0.1.0 → `APP_VERSION = "1.0.0"`(FastAPI 메타데이터·루트 응답 공용). 프런트 `package.json`, Dockerfile LABEL, prod 이미지 태그/버전 라벨과 일치.
- **K8s 라벨 체계 정상화**: overlay가 `app.kubernetes.io/name`에 환경명(-dev/-prod), `component`에 development/production을 넣던 것을 권장 체계로 교체 — `name=vllm-optimizer`(공통·base), `instance=vllm-optimizer-{env}`, `component=backend|frontend|monitoring|backup`(리소스별), `version`(overlay), `managed-by=kustomize`. pod template까지 전파(`includeTemplates`), **셀렉터는 전부 불변**(dev/prod 렌더 전/후 셀렉터 다이제스트 33건씩 동일).
- **prod DNS 검색 도메인**: backend·frontend pod의 `dnsConfig.searches[0]`가 dev 네임스페이스를 가리키던 것을 `vllm-optimizer-prod.svc.cluster.local`로 교체.

### Fixed (docs)
- CHANGELOG 1,156줄 → 최근 10개 라운드(280줄) 유지, 이전 라운드(2026-03~09)는 `docs/CHANGELOG-archive.md`(884줄)로 분리 — 에이전트가 매 세션 읽는 컨텍스트 축소.
- `docs/details/README.md`: 렌더링 불가한 위키링크(`[[page]]`) → 실제 상대 링크, api-spec·관련 문서 링크 보강.
- `docs/monitoring_runbook.md`: stale `[[AGENTS]]`·`.sisyphus/plans` 참조 제거.
- `01-namespace-rbac.yaml`의 "session artifacts" 스테일 주석 제거.

### Removed
- 추적 중이던 `.omo/run-continuation/*.json` 3건 untrack(.gitignore 대상), 루트 `.dockerignore`(빌드 컨텍스트가 `backend/`·`frontend/`라 미사용) 삭제.

### Verification
- `oc kustomize` dev/prod 렌더 OK, 셀렉터 불변 검증 완료(pod template 라벨은 표준 체계로 갱신됨 — 다음 `deploy.sh` 때 재시작 반영).
- 백엔드 이미지 `podman build` OK + in-image `pip check` OK + `app.version = 1.0.0` 확인.
- `./scripts/check.sh` exit 0 (ALL CHECKS PASSED): backend 780 passed, frontend 445 passed (57 files).

## [2026-10-03] - 실측 KV 용량·클러스터 전역 RBAC·LLMIS/GPU 실증·통합 테스트 복구

### Added
- **vLLM 실측 KV 용량** (`observed`): 대상 파드 `/metrics`의 `vllm:cache_config_info`(또는 `kserve_vllm:` / 구버전 `num_gpu_blocks×block_size`)를 읽어 `kv_cache_size_tokens`, `max_concurrency`, `block_size`, prefix caching을 분석 응답에 포함. 용량표에 `observed_max_seqs` 열, 이론 추정 대비 `estimate_ratio` 표시, 탐색 범위는 실측값 우선. 파드 `list`만 필요(exec 불필요).
- **ClusterRole/ClusterRoleBinding `vllm-optimizer-target-operator`**: 타깃 네임스페이스별 Role/RoleBinding(`vllm-rbac.yaml`, `llmis-rbac/`, `dcgm-rbac/`) 제거 — 새 네임스페이스에 RBAC 추가 불필요. `pods/log`(실패 로그), `namespaces get`(모니터링 라벨) 포함, 미사용 `deployments`/`services` 권한 제거.
- **GPU 테스트 타깃** `openshift/vllm-dependency/gpu-test/`: serving3에 Red Hat vLLM CUDA runtime + modelcar(0.8B) ISVC.

### Changed
- **튜너 타깃 고정**: `/api/tuner/start`의 `vllm_namespace`/`vllm_is_name`/`vllm_cr_type`를 `K8sOperator`에 반영 — 해당 CR만 읽고 trial args를 적용(delete+recreate). 기본값은 runtime-config. `apply-best` 응답 `deployment_name`도 실제 타깃(`ns/name`) 표기. (프런트는 이미 전송 중이었으나 백엔드가 무시해 기본 타깃이 수정되던 문제)
- **Optuna study 분리**: study 이름을 `objective + 타깃 + 탐색공간 해시`로 스코프 — 다른 모델/범위 trial과 충돌(CategoricalDistribution 오류·웜스타트 누수) 제거.
- **`block_size` 기본 옵션** `[8,16,32]` → `[16,32]`: CUDA FlashAttention이 16의 배수만 허용.
- **추론 트래픽 TLS**: `CA_BUNDLE` 미설정 시 certifi + OpenShift `service-ca.crt` 결합 컨텍스트(`_external_verify`) — LLMIS workload Service의 self-signed 인증서 검증.
- **LLMIS 기본 엔드포인트**: `https://{name}-kserve-workload-svc.{ns}.svc.cluster.local:8000` (게이트웨이 무관·검증됨).
- **메트릭 소스**: 새 타깃은 `metrics_source` 미지정 시 `direct`로 등록(+`/pods`, `/pods/history`가 요청의 source 전달) — `/latest`가 영구 `collecting`이던 문제 수정.
- `check.sh` full 게이트에 slow 테스트 포함(방치 방지).

### Fixed (tests)
- 통합 테스트 복구: `/api/metrics/latest` 타깃 지정 계약 반영(cluster_health·metrics_collection·direct_scrape), async 마커/픽스처 명시(`@pytest.mark.asyncio`, `pytest_asyncio.fixture`)로 이미지(설정 없는 strict 모드)에서 실행 가능, `oc` 부재 시 args 백업 픽스처 no-op, `skip_if_overloaded` 실동작화, `test_thanos_path_still_works`를 실제 `metrics_source=thanos` 배치 검증으로 교체.
- SSE 통합 테스트(부하·스윕): 스트림 구독을 테스트 시작 **전**으로 이동 — 시작 후 늦게 구독하면 완료 이벤트를 놓치고 keepalive만 받아 영구 대기하던 문제.
- conftest autouse mock이 integration 마커 테스트까지 가로채던 문제(모델명 resolve, preflight) 수정.

### Verification
- `./scripts/check.sh` exit 0 (backend 780, frontend 445).
- 인-클러스터 통합 테스트 **17/17 통과**(복구 전에는 다수 실패·행): cluster_health(3), metrics_collection(2), direct_scrape(3), itl(2), load_test(1), sse(1), sweep(2), auto_tuner(1), pod_restart(2).
- GPU `serving3/qwen-gpu`(vLLM 0.24 CUDA): KV 459,614 tokens·56.1× @8,192, estimate/measured 1.36(이론 상한), 튜너 2 trial 완료(tps 266.6→329.5, best 적용).
- LLMIS `serving1/qwen`(0.8B OpenVINO): 분석·실측 257,536 tokens(31.4× @8,192), 부하 테스트 8/8 성공(workload Service 직접, TLS 검증).
- 테스트 후 llm-ov args는 overlay 기준으로 복원(Ready 확인).

## [2026-10-03] - 정리: 죽은 max-targets 경로·stale 테스트·prefix caching·배포 순서

### Removed
- **도달 불가능한 max-targets 경로**: `register_target()`은 MAX_TARGETS 제거(`24b0fa0`) 이후 항상 성공하므로 반환값을 없애고, `/api/metrics/latest`의 409, `/batch`·`/pods`·`/pods/history`의 `max_targets_reached` 분기, OpenAPI 409 선언, api-spec 409 기술을 삭제. `/latest`는 400(타깃 누락)을 문서화.
- **프런트 `maxTargets`**: 헤더가 `(N/Infinity)`로 표시되고, 예전 localStorage에 숫자(예: 5)가 남아 있으면 백엔드엔 제한이 없는데 UI만 Add를 막던 잔재 제거 → `Monitoring Targets (N)`.

### Fixed (tests)
- slow 마커 테스트 18건이 조용히 실패 중이던 문제(기본 게이트에서 제외): 리팩터로 옮겨진 `_fetch_query_range` import 경로, 제거된 기본 타깃 대신 의존성 override로 NaN history 검증, `get_metrics` 목에 `metrics_source` 인자, FastAPI 0.142 라우트 래퍼 대응(`conftest.get_route_handler_globals`/`iter_api_routes`), `_evaluate` 목에 `broadcaster` 인자, discover 응답 계약(이름 배열) 반영. `pytest -m "slow and not integration"` 156/156.

### Changed
- **llm-ov**: dev overlay가 args 배열을 통째로 교체하면서 빠져 있던 `--enable-prefix-caching`을 base와 일치시킴. OpenVINO hybrid(GDN)에서 Mamba cache mode `align`으로 기동, KV 용량 불변(8K 기준 69.62×), 같은 시스템 프롬프트 재요청 2.3s→1.2s, prefix hit 32/68.
- **deploy.sh**: 이미지 digest 비교/롤아웃을 kustomize 적용·ConfigMap 해시 동기화 뒤로 이동 — 이미지와 설정이 함께 바뀌어도 파드가 한 번만 재시작(`imagePullPolicy: Always` 전제).
- 문서: architecture.md 메트릭 흐름(Monitor는 `/batch`), monitor-page.md 헤더/Add 버튼 설명, 테스트 픽스처의 `:8080` 엔드포인트 정리.

### Verification
- `./scripts/check.sh` exit 0 (backend 612, frontend 444), slow 156 passed.
- `deploy.sh dev`: 백엔드 ReplicaSet 1개만 생성(단일 재시작), `/api/metrics/latest` 무파라미터 400·타깃 지정 200, `/batch` 정상. Playwright: 헤더 `Monitoring Targets (1)`, Add 활성, 4xx/5xx·콘솔 오류 0건.

## [2026-10-03] - 후속 수정: 세션 하트비트·기본 엔드포인트·배포 반영·llm-ov 샘플링 고정

E2E에서 남은 콘솔 오류와 배포 반영 문제를 수정.

### Fixed
- **세션 하트비트 400**: `useSessionKeepAlive`가 명시 타깃 전용이 된 `/api/metrics/latest`를 파라미터 없이 호출(4분마다 콘솔 오류) → 경량 인증 엔드포인트 `GET /api/status/ping` 추가 후 사용. 커밋 `24b0fa0`의 "no default target" 계약은 유지.
- **KServe ISVC 기본 엔드포인트 `:8080`**: predictor Service는 80 포트(클러스터에서 `llm-ov-predictor`/`gemma-predictor` = 80 확인). 백엔드·프런트 기본값, ConfigMap(base/dev/prod), `.env.example`, 통합 테스트 기본값, 문서(AGENTS.md 포함) 수정. prod overlay의 `https://…:8080` → `http://…`(80).
- **배포 시 ConfigMap 변경이 파드에 반영되지 않던 문제**: `deploy.sh`가 이미지 롤아웃 → kustomize 적용 순서라 env(`VLLM_ENDPOINT` 등)가 갱신되지 않음. 적용 후 ConfigMap 해시가 달라진 경우에만 백엔드를 재시작하는 `sync_configmap_rollout` 추가.
- **콘솔 CSP 오류**: CSP(`font-src 'self'`)가 이미 차단하는 Google Fonts `@import` 제거(폐쇄망에서 로드 불가, 배포 화면은 폴백 폰트로 렌더링 중이었음).
- api-spec: `/api/metrics/latest` 파라미터를 명시 필수(누락 시 400)로 정정, stale slow 테스트를 계약에 맞게 수정.
- 분석 LLM 프롬프트: 파라미터·환경변수 이름 창작 금지 명시.

### Changed
- **llm-ov**: `--max-num-batched-tokens=2048` 제거, `--override-generation-config={"temperature":0}` 추가(분석 LLM 겸용, 결정적 출력). vLLM 0.30.0 런타임에 플래그 존재 확인.

### Verification
- `./scripts/check.sh` exit 0 (backend 612, frontend 444), `--smoke` OK.
- 클러스터: llm-ov 새 옵션으로 Ready(3/3)·`/v1/models` 정상. 백엔드 env·`/api/config` = 포트 없는 엔드포인트, `resolved_model_name=OpenVINO/Qwen3.5-2B-int4-ov`, `GET /api/status/ping` 200. Playwright: 페이지 로드 시 `/api/status/ping` 200, 콘솔 오류 0건. `deploy.sh dev` 재실행에서 ConfigMap 변경 시에만 롤아웃되는 것 확인.

## [2026-10-03] - 모델 분석·분석 LLM 분리·실측 보강, 불필요 기능 제거

목표: RHOAI 테스트 클러스터에서 모델별 vLLM 인자를 정하는 벤치·튜닝 도구로 범위를 좁힘.

### Added
- **결정적 모델 분석** (`services/model_analysis.py`, `GET /api/tuner/model-analysis`): 대상 파드의 `/mnt/models/config.json`을 읽어 KV bytes/token, 용량표(컨텍스트별 최대 동시 시퀀스), 튜너 탐색 범위 제안을 계산. `text_config` 중첩, 명시적 `head_dim`/`global_head_dim`, `layer_types`(full/sliding/linear), KV-shared 레이어(Gemma 4), GDN 고정 상태(Qwen3.5), MLA, MoE, `--kv-cache-dtype`, OpenVINO 양자화 반영. GPU 대상은 장당 메모리 입력, CPU(OpenVINO) 대상은 파드 메모리를 예산으로 사용. Tuner 페이지에 Model Analysis 패널(용량표, "Apply to search space").
- **분석 LLM 분리** (`ANALYST_ENDPOINT`, dev overlay: `llm-ov`): 웜스타트 제안·실패 설명·리포트가 튜닝 대상 대신 별도 소형 모델을 호출. 미설정 시 비활성, 튜닝 대상과 같으면 튜닝 중 호출 생략. `POST /api/tuner/model-analysis/explain`은 계산된 수치만 서술.
- **부하 테스트/스윕 API key** (`api_key`): MaaS 등 게이트웨이 경로에 `Authorization: Bearer` 전송. 응답·이력·벤치마크에 저장되지 않음.
- **스윕 knee 판정** (`knee_rps`): 오류율 임계 이내 단계 중 토큰 처리량/평균 지연(Kleinrock power) 최대 지점. 요약 카드와 차트 "Knee" 라인.
- `CRAdapter.model_container_name()` (isvc `kserve-container`, LLMIS `main`), `extract_arg_value()`.

### Changed
- KV OOM 사전 필터: `max_num_seqs × max_model_len` 전체 할당(과도하게 보수적) → vLLM 기동 조건(최대 길이 시퀀스 1개가 KV 예산에 들어가는지)으로 변경, 가중치 차감.
- 튜너의 `max_model_len` 상한 clamp를 현재 서빙 값이 아니라 모델 `max_position_embeddings`로 변경.
- 기존 파서가 `text_config` 모델(Gemma 4, Qwen3.5 등)에서 레이어·헤드를 읽지 못하고 `head_dim`을 `hidden/heads`로만 계산하던 문제 해소. 가중치 크기는 단일 파일 대신 safetensors/bin/gguf 합계.

### Removed
- Mock 데이터 모드(`MockDataContext`, `MockDataSwitch`, `mockData.ts`) — 실측 도구에서 가상 데이터와 혼동 위험. 관련 테스트는 MSW 픽스처로 전환.
- slowapi 레이트 리미터 — 내부 단일 사용자 도구이며 중복 시작은 409로 이미 방지.

### Fixed (배포)
- vLLM 네임스페이스 Role에 `pods/exec`(모델 분석의 config.json 읽기)와 InferenceService/LLMIS `create`/`delete` 추가 — 튜너가 delete+recreate로 trial을 적용하는데 권한이 없어 클러스터에서 403으로 실패하던 문제.
- llm-ov(분석 LLM): `--max-num-seqs=256`에서 OpenVINO가 4 GiB KV 공간에 GDN 상태를 슬롯마다 예약해 KV 블록 0개로 기동 실패 → 32. served-model-name을 `OpenVINO/Qwen3.5-2B-int4-ov`로 정정.
- OpenVINO 대상은 KV 예산을 `VLLM_OPENVINO_KVCACHE_SPACE`(기본 4 GiB, u8, 가중치 별도)로 계산하고, OOM 사전 필터가 linear-attention 상태를 `max_num_seqs` 슬롯 수만큼 반영.

### Verification
- `./scripts/check.sh` → exit 0 (backend 611 passed, frontend 444 passed).
- `deploy.sh dev` 후 인-클러스터: llm-ov(ISVC) 모델 분석(용량 61 seqs@8K, vLLM 자체 보고 69.6×), 분석 LLM 설명, API key 부하 테스트(키가 응답·SQLite에 없음), 스윕 knee, 튜너 2 trial(파드 교체·best 적용). LLMIS(qwen)·ISVC(gemma) config.json 분석은 kubeconfig 드라이버로 확인. 브라우저(Playwright)로 Model Analysis 패널·탐색 범위 적용·API key 입력 확인.

## [2026-10-03] - 잔여 결함 2차 수정

**Status**: Completed (로컬 검증 + 서버측 dry-run 검증, 인-클러스터 E2E는 `deploy.sh dev` 후 확인 필요)

1차 점검에서 남겨둔 항목과 테스트 인프라 결함을 수정.

### Fixed (vLLM config PATCH)
- **LLMIS args 패치 시 `containers`/`env` 배열이 통째로 교체되어 형제 env(HF_HOME 등)와 `resources`가 삭제되던 문제** 수정 — 라이브 CR을 읽어 name 기준으로 병합한 배열로 확장. `oc patch --dry-run=server`로 보존 확인.
- PATCH가 `namespace`/`is_name`/`cr_type` 쿼리 파라미터를 무시하고 기본 타겟만 수정하던 문제 수정 (프런트는 이미 전달 중이었음).
- 리소스 빈 문자열이 무시되어 키 삭제가 불가능하던 문제 수정 — merge patch null로 변환. `requests.nvidia.com/gpu`는 422로 거부.
- `cr_type`을 `Literal`로 검증 (GET/PATCH).

### Fixed (Backend)
- `rps_actual`이 실패 요청까지 포함하던 문제 → 성공 요청 수 기준 (guidellm parser와 일치).
- targets 저장/불러오기: `metrics_source` 기본값이 수집기가 거부하는 `"prometheus"`이던 문제 → `"direct"` + `Literal` 검증. 프런트가 `inferenceService`/`crType`을 보내 저장이 422, 불러오기가 undefined로 매핑되던 계약 불일치 수정.
- SQLite 백업이 `app.db`만 백업하던 문제 → 기본적으로 `app.db` + `optuna.db`(튜닝 이력) 백업, 소스별 보존 개수 적용, 없는 DB는 건너뛰되 전부 없으면 실패.

### Fixed (Test infrastructure)
- FastAPI 0.142의 `_IncludedRouter` 래퍼 때문에 `app.routes` 직접 순회로는 라우트를 찾지 못해 vllm-config 테스트 24건이 조용히 skip되던 문제 수정 (`conftest.iter_api_routes` 도입, auto-tuner preflight 스캔 포함).
- 테스트가 존재하지 않는 `_get_vllm_is_name`을 패치하던 stale 키 수정.

### Fixed (Frontend)
- SSE: `connect()`가 이전 핸들을 dispose하지 않아 실행마다 스트림이 누적되고, `disconnect()`/완료 시 재연결 타이머가 살아남던 문제 수정 (`dispose` 사용).
- 모니터: 타겟 제거 시 `targetStates`가 정리되지 않아 stale 차트/메모리 누수 발생 → 현재 타겟 키로 prune.
- ConfigMap 초기 동기화가 같은 CR 타입의 수동 타겟을 모두 삭제하던 문제 수정 (configmap 소스만 교체, 중복 방지).
- `resolvedModelName`이 전역 `/api/config` 값을 사용하던 문제 → 기본 타겟의 `/api/vllm-config` 조회 결과 사용.
- 백엔드가 제공한 `vllm_endpoint`를 프런트가 계산값으로 덮어쓰던 문제 수정.
- 숫자 입력란을 비우면 0으로 강제 변환되던 문제 수정 (`parseNumberInput`, 4개 컴포넌트).
- 프로덕션 빌드에서 mock 모드가 localStorage에 영속되던 문제 수정.
- SLA 프로필 전환 경합(늦게 도착한 이전 응답이 최신 결과를 덮어씀) 및 중복 평가 요청 수정.
- 튜너: endpoint 폴링 변경 시 사용자 편집이 초기화되던 문제 수정.
- nginx: `client_max_body_size 50m` (백엔드 50MB import와 일치), `location ^~ /api/`로 정적 regex location의 shadow 방지.

### Verification
- `./scripts/check.sh` → exit 0 (backend 597 passed, frontend 452 passed).
- 라이브 `oc patch --dry-run=server`로 LLMIS args+resources 병합 결과 검증.

---

## [2026-10-03] - 실무 기능 점검 및 결함 수정

**Status**: Completed (로컬 검증 완료, 인-클러스터 E2E는 `deploy.sh dev` 후 확인 필요)

실제 클러스터(KServe ISVC / LLMIS)에 대해 부하 테스트·메트릭·튜너·알림 경로를 점검하고 확인된 결함만 최소 수정.

### Fixed (Load test)
- HTTP 4xx/5xx 응답을 성공으로 집계하던 문제 수정 (completions/chat 모두 `HTTP {status}` 실패 처리).
- `tps.total`이 마지막 요청 값이던 문제 → 누적 출력 토큰 / 경과 시간으로 계산.
- 중지(STOPPED)된 테스트가 COMPLETED로 덮어써지던 문제 및 이력이 두 번 저장되던 문제 수정 (라우터 백그라운드 실행은 `persist=False`).
- `/status`의 `test_id` 누락, 동시 시작 경합(`_start_lock`) 수정.
- `cr_type`을 `Literal`로 검증(잘못된 값 거부), `/api/metrics/latest`·`/pods`가 기본 `cr_type`을 일관되게 사용.

### Fixed (Auto-tuner)
- latency/balanced 목표에서 Optuna direction을 minimize로 바꾸면서 점수 부호가 이미 반전되어 있어 최적화 방향이 뒤집히던 문제 수정 (항상 maximize). sla_tps 위반 점수도 부호 일관화.
  - ⚠️ 이전 방향(minimize)으로 영속화된 `vllm-tuner-latency`/`vllm-tuner-balanced` study는 로드 실패 시 in-memory로 폴백(경고 브로드캐스트).
- 최적 파라미터 적용 실패 또는 서비스 미준비 시 `auto_benchmark`를 건너뛰고 `tuning_warning` 전송.
- 삭제 대기 타임아웃/취소 시 CR이 사라진 채 남던 문제 → 스냅샷으로 복원 (`_wait_for_deletion` 기본 180s).
- `cr_adapter`: `--max-num-seqs 128`처럼 공백 구분 인자에서 값 토큰이 정적 인자로 남아 vLLM에 전달되던 문제 수정 (`strip_tuning_args`, `args_list_to_config_dict` 공백 형식 지원).

### Fixed (Alerts / Frontend / Deploy)
- 알림 임계값: 동작하지 않던 `max_ttft_ms` 대신 실제 수집되는 TTFT/E2E/TPOT/Queue 지표에 매핑.
- LLMIS 기본 엔드포인트를 `https://openshift-ai-inference-openshift-default.openshift-ingress.svc/{ns}/{name}`로 수정 (frontend `endpointUtils`).
- backend Deployment `strategy: Recreate` (RWO PVC + SQLite 동시 마운트 방지).

### Known (pre-existing, not changed)
- `backend/tests/test_tuner.py` slow 마커 테스트 중 mock이 `broadcaster` 인자를 받지 않는 5건 및 SSE 2건은 변경 이전부터 실패.

### Verification
- `./scripts/check.sh` → exit 0 (backend 558 passed, frontend 435 passed, ruff/tsc/eslint/prettier OK), `oc kustomize openshift/base` OK.

---

## [2026-09-30] - 배포/빌드 메타데이터 정리

**Status**: Completed

`oc kustomize`로 dev/prod/vllm-dependency 오버레이를 검증하며 미사용 배포 메타데이터와 깨진 스크립트를 정리.

### Removed (OpenShift)
- `vllm-optimizer-config`에서 코드가 읽지 않는 키 제거: `APP_ENV`, `METRICS_INTERVAL_SEC`, `PROMETHEUS_USE_TLS`/`PROMETHEUS_TOKEN_PATH`/`PROMETHEUS_CA_PATH` (코드는 SA 토큰 경로를 하드코딩하고 `verify=False` 사용).
- 미사용 `vllm-optimizer-secret`(`VLLM_API_KEY`, `SECRET_KEY`)과 backend `secretRef` 제거. (`oc apply`는 prune하지 않으므로 기존 클러스터의 Secret은 잔존 — 필요 시 수동 삭제.)
- dev 오버레이의 `APP_ENV` replace 패치 제거.

### Fixed
- **`scripts/collect_baseline.sh`**: `namespace`/`is_name` 없이 `/api/metrics/latest`를 호출해 400을 받던 문제 수정 — 타겟 파라미터(`VLLM_*`, 기본 `vllm-lab-dev`/`llm-ov`)를 전달하고 응답 `data`에서 스냅샷 필드(`rps`/`latency_mean`/`latency_p99`/`tps`/`gpu_util`)를 읽도록 수정. 문서에 사용법 반영.
- **`backend/Dockerfile`**: 중복 `COPY requirements.txt` 제거, `HEALTHCHECK` 공백 정리.
- **`frontend/Dockerfile`**: `npm install` → `npm ci` (lockfile 재현성).

### Added
- **`backend/.dockerignore`**, **`frontend/.dockerignore`**: `deploy.sh`는 각 하위 디렉터리를 빌드 컨텍스트로 사용하는데 루트 `.dockerignore`만 있어 적용되지 않았음. frontend는 `node_modules`가 이미지로 복사되던 문제 해결. `backend/tests/`는 인-파드 테스트 실행(`docs/integration_test_guide.md`) 때문에 의도적으로 유지.
- **`openshift/base/kustomization.yaml`**: `06-backup-cronjob.yaml`(일 02:00 SQLite 백업 CronJob + `pods/exec` Role/RoleBinding)을 resources에 등록. 작성(eb927ed)만 되고 kustomization에 포함된 적이 없어 **한 번도 배포되지 않던** 누락 수정. ⚠️ 다음 `deploy.sh dev` 시 CronJob/RBAC E2E 검증 필요.

### Verification
- `oc kustomize` 4개 오버레이(dev/prod × optimizer/vllm-dependency) 빌드 OK — diff는 의도한 제거만 포함.
- `./scripts/check.sh` → **ALL CHECKS PASSED**, `--smoke` OK, `bash -n` 통과.

---

## [2026-09-30] - 메타데이터 정합화 + Prettier 강제

**Status**: Completed

AGENTS.md·설정·문서 메타데이터를 실제 코드 기준으로 정합화하고, 선언만 되어 있던 Prettier를 실제로 강제.

### Changed
- **`AGENTS.md`**: Quick Commands/Key Files 추가, env 테이블을 실제 `os.getenv` 기준으로 정정(canonical: `backend/.env.example`, `openshift/base/02-config.yaml`), singleton 이름 `multi_target_collector`로 수정, Dual CR 표를 `CRAdapter` 구현 기준으로 정정(API 버전·pod label selector·LLMIS https 엔드포인트·args 위치), `git push` 규칙을 Behavioral Rules로 이동.
- **`backend/.env.example`**: 실제 사용 변수 기준으로 재작성(미사용 `K8S_NAMESPACE`/`APP_*`/stale Prometheus 기본값 제거).
- **`pyproject.toml`**: `testpaths` 추가로 저장소 루트에서 bare `pytest` 동작, ruff per-file-ignores를 `backend/tests/**`로 확장.
- **`.gitignore`**: 중복 섹션 정리, `.env.example` 추적 유지(`.env.*` + negation), `.codegraph`/`.ruff_cache` 추가, blanket `*.png` 제거.
- **`frontend/package.json`**: `private`, `engines`, `format:check` 추가. `@types/react(-dom)`을 React 18 런타임에 정렬(React 19 타입과 불일치 해소; `BenchmarkTable` ref 타입을 cross-version `MutableRefObject`로 수정).
- **`docs/`**: 제거된 `METRICS_SOURCE` env → per-target `metrics_source`로 정정, `MetricsCollector`/pod label/`K8S_DEPLOYMENT_NAME` 설명 최신화, runbook 예시를 현재 기본값으로 갱신, frontmatter 정리.
- **Prettier**: `prettier --write src/` 1회 정규화(124 files) 후 `scripts/check.sh`에 `format:check` 단계 추가.

### Verification
- `./scripts/check.sh` → **ALL CHECKS PASSED** (backend 545 passed / ruff clean; frontend 435 passed / tsc / eslint / prettier / build).

---

## [2026-09-30] - 최소 검증 게이트 + 핵심 기능 smoke tier

**Status**: Completed

"최소 사이즈로 기능을 검증"하기 위한 단일 명령 게이트와 빠른 smoke tier를 추가.

### Added
- **`scripts/check.sh`**: 단일 명령 검증 게이트. 기본은 full(smoke + backend pytest/ruff + frontend vitest/tsc/eslint/build), `--smoke`는 핵심 계약만 빠르게 검증(새 도구/CI 의존 없음).
- **`backend/tests/test_smoke.py`**: 핵심 기능 HTTP 계약 9개 — health, config, metrics(latest/batch), load test status, benchmark 저장/목록/삭제, SLA 프로필 라이프사이클, tuner status, targets 저장/로드 + **dual-CR adapter 계약**(KServe `spec.predictor.model.args` vs LLMIS `spec.template...VLLM_ADDITIONAL_ARGS`, 메트릭 prefix/잡 분리). 약 0.9초.
- **`frontend` `npm run test:smoke`**: 핵심 페이지 6개(App/LoadTest/Monitor/Tuner/SLA/Benchmark) 54 테스트, 약 2초.

### Fixed
- **`backend/tests/conftest.py`**: `routers.sla`/`routers.targets`/`routers.alerts`가 `_MODULES_TO_CLEAR`에서 누락되어 스테일 `storage` 바인딩을 유지하던 격리 버그 수정. 스텁 `register_target`/`get_metrics`에 `metrics_source` 파라미터 반영.

### Docs
- `AGENTS.md` 검증 게이트 규칙 추가, `docs/architecture.md` Quick Start에 게이트 사용법 추가.

### Verification
- `./scripts/check.sh --smoke` → **4.3s** (backend smoke 9 passed + frontend smoke 54 passed).
- `./scripts/check.sh` → **ALL CHECKS PASSED** (backend 545 passed / ruff clean; frontend 435 passed / tsc 0 / eslint 0 / build 성공).

---

## [2026-09-29] - 코드베이스 재정비: 테스트 그린 복구 + 최적화

**Status**: Completed

장기 미점검 후 전체 검토. `24b0fa0`(default target 자동등록 제거) 리팩터 이후 방치된 백엔드/프론트엔드 테스트 불일치를 전면 복구하고, 코드 품질·번들·모듈 구조를 최적화.

### Fixed (Backend)
- **`backend/tests/test_tuner.py`**: `auto_tuner`에서 이동한 `get_k8s_namespace`/`get_vllm_is_name` import를 `k8s_operator`로 수정 — 기본 `pytest` 수집 실패(전체 중단) 해소.
- **stale 테스트 복구**: `_register_default_target`/`_get_default_target` 제거 반영(`test_direct_scrape`, `test_metrics_collector`), `auto_tuner.k8s_config` → `k8s_operator.k8s_config` 패치(`test_auto_tuner`), `/api/metrics/latest`의 namespace+is_name 계약 반영(`test_chaos`), `_DummyTrial.set_user_attr` 추가, conftest 스텁 `get_cr_exists` 추가.
- **`backend/services/multi_target_collector.py`**: `gpu_utilization_pct` 집계를 `sum` → `avg`로 복원 (`8dfe8c7` 회귀; 백분율 합산은 100% 초과 가능).
- **ruff 13건 + 포맷 정리**: import 정렬, 미사용 변수, `B904`, `SIM108` 등.

### Removed
- **`backend/services/config_watcher.py` + `test_config_watcher.py`**: `main.py` 미배선 + `_WATCHED_FIELDS = ()` 상태의 dead code 삭제 (기능 은퇴).
- **`debug_routes.py`** (루트 잔재), **`test_guidellm_parser.py`**의 중복·미완성 `test_ms_to_seconds_conversion` 삭제.

### Changed (Backend)
- **env 헬퍼 중복 제거**: `_get_k8s_namespace`/`_get_vllm_is_name`을 `k8s_operator.py` 단일 정의로 통합, `vllm_config.py`는 import 사용.
- **`backend/routers/status.py`**: async 내 블로킹 `os.path.exists` → `asyncio.to_thread`.
- **대형 파일 분해**: `metric_math.py`(히스토그램·rate 순수 계산)와 `storage_schema.py`(DDL) 추출, 기존 메서드는 위임(delegator)으로 유지.

### Fixed (Frontend)
- **`BenchmarkItem` import 경로** 수정(`pages/BenchmarkPage` → `types`) — `tsc` 2 errors 해소.
- **stale 테스트 복구**: `ClusterConfigContext` 15건(ConfigMap/default target 계약), `MultiTargetSelector` 2건(빈 상태·에러 문구) — 현 구현 기준으로 정렬.
- **타입 안전성/일관성**: `any` 캐스트 제거(`useTunerLogic`의 `toTunerConfig` 검증 매핑, `TargetResult.crExists` 타입 추가), `/api/...` 하드코딩 → `${API}`, fetch `AbortController` cleanup(`useMonitorLogic`/`TunerHistoryPanel`/`useSweepHistory`), `useLoadTestSSE` 타이머 cleanup.

### Changed (Frontend)
- **recharts 지연 로딩**: 차트 컴포넌트를 `React.lazy` + `Suspense`로 분리 — 초기 엔트리 청크에서 recharts 제거(엔트리 gzip 57 kB, `generateCategoricalChart` gzip 103 kB는 lazy chunk).
- **`ClusterConfigContext.tsx` 556 → 357줄**: `useConfigMapTargets`, `useResolvedModelName`, `clusterConfigShared`로 추출(공개 API·동작 불변).
- **SSE 재연결 로직 공용화**: `utils/reconnectingEventSource.ts` 신설 — `useSSE` 77→40줄, `useLoadTestSSE` 137→110줄.

### Verification
- Backend: **536 passed, 0 failed**, 24 skipped, 172 deselected (`not integration and not slow`); `ruff check`/`ruff format --check` clean.
- Frontend: **435 passed, 0 failed**; `tsc --noEmit` 0 errors; `eslint` 0 errors / 0 warnings; production build 성공.

---


---

이전 라운드(2026-03 ~ 2026-09) 기록은 [docs/CHANGELOG-archive.md](docs/CHANGELOG-archive.md)에 있습니다.
