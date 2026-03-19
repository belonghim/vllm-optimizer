## Task 9 — SQLite Study Persistence + Warm-start (COMPLETED)

### Changes Made
- `backend/services/auto_tuner.py`: Replaced `optuna.create_study()` with branched logic:
  - `OPTUNA_STORAGE_URL` set → `asyncio.to_thread(RDBStorage, url, engine_kwargs={"connect_args": {"check_same_thread": False}})` + `create_study(load_if_exists=True)`; warm-start via `enqueue_trial()` if `best_trials` non-empty
  - `OPTUNA_STORAGE_URL` unset → plain in-memory `create_study()`
- `backend/routers/tuner.py`: Fixed pre-existing IndentationErrors (lines 5-9, 189) that blocked test collection
- `backend/tests/test_tuner.py`: Added `test_start_uses_inmemory_when_no_storage_url` and `test_warmstart_enqueues_previous_best`; fixed `StopIteration` → `(StopIteration, RuntimeError)` catch (Python 3.7+ converts StopIteration in coroutines to RuntimeError)

### Commits
- `cd59364` — auto_tuner.py SQLite code was already committed here (T8 overlap)
- `00cab69 feat(tuner): SQLite study persistence and warm-start` — finalized test fixes

### Evidence
- Import OK: `.sisyphus/evidence/task-9-inmemory.txt`
- Tests: 32 passed, 0 failed — `.sisyphus/evidence/task-9-tests.txt`
