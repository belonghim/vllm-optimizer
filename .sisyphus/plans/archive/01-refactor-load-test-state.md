# Work Plan: Refactor Load Test State Management

**Phase:** 2 (Code Simplification)
**Goal:** Refactor the load test functionality to centralize state management within the `LoadTestEngine` and simplify the `load_test` router.

---

## 1. Justification

The current implementation in `backend/routers/load_test.py` uses global variables (`_active_test_task`, `_current_config`) to manage the state of a running load test. This logic is redundant because the `LoadTestEngine` is already a stateful singleton.

This refactoring will move all state management into the `LoadTestEngine`, making the router a stateless pass-through layer. This improves separation of concerns, simplifies the code, and makes the system more robust and easier to test.

---

## 2. Task Breakdown

### Task 1: Enhance `LoadTestEngine` in `backend/services/load_engine.py`

We will add methods to the `LoadTestEngine` to allow it to manage its own execution lifecycle.

#### 1.1. Add new attributes to `__init__`
- `self._active_task: Optional[asyncio.Task] = None`
- `self._current_config: Optional[LoadTestConfig] = None`

#### 1.2. Create `start()` method
- This method will replace the `run_test` logic from the router.
- It will create a background task for `self.run(config)`.
- It will store the task in `self._active_task`.
- It will return a unique `test_id`.

#### 1.3. Modify `stop()` method
- Add logic to cancel `self._active_task` if it's running.

#### 1.4. Create `get_status()` method
- This method will inspect the engine's internal state (`self._state`, `self._active_task`, `self._current_config`) and return a status dictionary, similar to the current `/status` endpoint response.

### Task 2: Simplify `load_test.py` Router

We will remove all state management from the router and make it call the new `LoadTestEngine` methods directly.

#### 2.1. Remove Global State
- Delete the `_active_test_task` and `_current_config` global variables.

#### 2.2. Refactor `/start` endpoint
- Remove the `run_test` inner function.
- Change the implementation to a single call to `load_engine.start(config)`.

#### 2.3. Refactor `/stop` endpoint
- Simplify the implementation to a single call to `load_engine.stop()`.
- The `test_id` argument might become optional or be handled by the engine.

#### 2.4. Refactor `/status` endpoint
- Change the implementation to a single call to `load_engine.get_status()`.

---

## 3. Execution Plan

This plan will be executed by applying a series of `edit` operations to the two files. I will perform the changes to `load_engine.py` first, and then to `load_test.py`.

### Step 3.1: Modify `backend/services/load_engine.py`
*(Detailed edit operations will be generated in the next step)*

### Step 3.2: Modify `backend/routers/load_test.py`
*(Detailed edit operations will be generated in the next step)*

---

This concludes the planning phase for this refactoring. I will now proceed with generating the code modifications.

## 4. TODO List

### Task 1: Enhance `LoadTestEngine` completed.
- [x] **Task 1.1**: Add `_active_task` and `_current_config` to `LoadTestEngine.__init__`
- [x] **Task 1.2**: Create `start(config)` method in `LoadTestEngine`
- [x] **Task 1.3**: Update `stop()` method to cancel `_active_task`
- [x] **Task 1.4**: Create `get_status()` method in `LoadTestEngine`

### Task 2: Simplify `load_test.py` Router completed.
- [x] **Task 2.1**: Remove global state variables from `load_test.py`
- [x] **Task 2.2**: Refactor `/start` endpoint to use `load_engine.start()`
- [x] **Task 2.3**: Refactor `/stop` endpoint to use `load_engine.stop()`
- [x] **Task 2.4**: Refactor `/status` endpoint to use `load_engine.get_status()`
- [x] **Task 1.1**: Add `_active_task` and `_current_config` to `LoadTestEngine.__init__`
- [x] **Task 1.2**: Create `start(config)` method in `LoadTestEngine`
- [x] **Task 1.3**: Update `stop()` method to cancel `_active_task`
- [x] **Task 1.4**: Create `get_status()` method in `LoadTestEngine`
- [ ] **Task 1.2**: Create `start(config)` method in `LoadTestEngine`
- [ ] **Task 1.3**: Update `stop()` method to cancel `_active_task`
- [ ] **Task 1.4**: Create `get_status()` method in `LoadTestEngine`

### Task 2: Simplify `load_test.py` Router
- [ ] **Task 2.1**: Remove global state variables from `load_test.py`
- [ ] **Task 2.2**: Refactor `/start` endpoint to use `load_engine.start()`
- [ ] **Task 2.3**: Refactor `/stop` endpoint to use `load_engine.stop()`
- [ ] **Task 2.4**: Refactor `/status` endpoint to use `load_engine.get_status()`
### Task 3: Simplify `main.py` Router inclusion completed.
- [x] **Task 3.1**: Remove placeholder routers and redundant imports from `main.py`
- [x] **Task 3.2**: Directly include real routers in `main.py`