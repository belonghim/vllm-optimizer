# Decisions — auto-tuner-improvement

## [2026-03-14] Session Init

### Architecture Decisions
- Multi-objective: NSGAIISampler + directions=["maximize","minimize"]
- Study 영속성: OPTUNA_STORAGE_URL env var (None=in-memory)
- Warm-start: study.enqueue_trial() (WarmStartSampler 아님)
- MedianPruner: 2-phase evaluation (fast_fraction=0.5)
- Rollback: 메모리 스냅샷 (_cm_snapshot)
- SSE: LoadTestEngine 패턴 복제 (asyncio.Queue + lock)
- SQLite: check_same_thread=False 필수

### API Decisions  
- /importance: multi-obj에서 {} 반환 (RuntimeError 방지)
- /apply-best: best 없으면 "No best trial available" 반환
- /stream: GET endpoint, text/event-stream
- TunerStatusFrontendResponse: best_score_history 추가
- TrialFrontendInfo: is_pareto_optimal, pruned 추가
