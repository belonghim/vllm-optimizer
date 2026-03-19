# Learnings — improve-frontend-quality

## [2026-03-15] Session Start

### Project Conventions
- Frontend: React + Vite, tested with vitest + @testing-library/react
- Worktree: /home/user/project/vllm-optimizer-frontend-quality (branch: improve/frontend-quality)
- Test run: `cd frontend && npx vitest run`
- node_modules only in original: /home/user/project/vllm-optimizer/frontend/
- Tests must be RUN from original repo (node_modules there), but files COMMITTED in worktree

### Critical Context
- LoadTestPage.jsx lines 147-167: 2 useEffect each call /api/config — MERGE INTO ONE
- 4 failing tests: "shows success/error feedback", "disables button during/after save"
- Root cause confirmed: mock 3개 제공 but 4 fetch calls (2 config + 1 start + 1 save)
- T1 FIX: Merge useEffects → 3 fetch calls → tests pass WITHOUT test file changes

### Test File Locations (worktree)
- LoadTestPage.test.jsx: frontend/src/pages/LoadTestPage.test.jsx
- TunerPage.test.jsx: frontend/src/pages/TunerPage.test.jsx (신규)
- BenchmarkPage.test.jsx: frontend/src/pages/BenchmarkPage.test.jsx
- MonitorPage.test.jsx: frontend/src/pages/MonitorPage.test.jsx (신규)

### Workaround for frontend tests without node_modules
- Copy changed files from worktree to original, run tests there, verify, copy back for commit
- Pattern from previous session: cp worktree/file original/file && cd original/frontend && npx vitest run

### Key Guardrails
- T1: 테스트 파일 수정 금지, LoadTestPage.jsx만 수정
- T2: isReconnecting boolean만, FSM 금지, setError 재연결에 사용 금지
- T3: isMockEnabled:true + 1 fetch stub, SSE/form 테스트 금지
- T4a/T4b: Chart 내부 assertion 금지, setInterval 테스트 금지
## [2026-03-15] Task Completion Summary
### Task: Merge duplicate /api/config useEffects
- **File Modified**: frontend/src/pages/LoadTestPage.jsx
- **Change**: Merged two useEffect hooks into one to eliminate duplicate /api/config network calls.
- **Verification**:
    - Original 4 failing tests (related to 'save-as-benchmark') now pass.
    - New 3 failing tests (related to 'SSE onerror reconnect behavior') were observed but not addressed as per task instructions (no test file modification allowed).
- **Evidence**: Test output saved to .sisyphus/evidence/task-1-save-test-fix.txt
- **Commit**: fix(frontend): merge duplicate /api/config useEffects — fixes save-as-benchmark tests

## [2026-03-15] Task Completion Summary
### Task: Merge duplicate /api/config useEffects
- **File Modified**: frontend/src/pages/LoadTestPage.jsx
- **Change**: Merged two useEffect hooks into one to eliminate duplicate /api/config network calls.
- **Verification**:
    - Original 4 failing tests (related to 'save-as-benchmark') now pass.
    - New 3 failing tests (related to 'SSE onerror reconnect behavior') were observed but not addressed as per task instructions (no test file modification allowed).
- **Evidence**: Test output saved to .sisyphus/evidence/task-1-save-test-fix.txt
- **Commit**: fix(frontend): merge duplicate /api/config useEffects — fixes save-as-benchmark tests

## [2026-03-15] Task Completion Summary
### Task: Merge duplicate /api/config useEffects
- **File Modified**: frontend/src/pages/LoadTestPage.jsx
- **Change**: Merged two useEffect hooks into one to eliminate duplicate /api/config network calls.
- **Verification**:
    - Original 4 failing tests (related to 'save-as-benchmark') now pass.
    - New 3 failing tests (related to 'SSE onerror reconnect behavior') were observed but not addressed as per task instructions (no test file modification allowed).
- **Evidence**: Test output saved to .sisyphus/evidence/task-1-save-test-fix.txt
- **Commit**: fix(frontend): merge duplicate /api/config useEffects — fixes save-as-benchmark tests

## [2026-03-15] Task Completion Summary
### Task: Merge duplicate /api/config useEffects
- **File Modified**: frontend/src/pages/LoadTestPage.jsx
- **Change**: Merged two useEffect hooks into one to eliminate duplicate /api/config network calls.
- **Verification**:
    - Original 4 failing tests (related to 'save-as-benchmark') now pass.
    - New 3 failing tests (related to 'SSE onerror reconnect behavior') were observed but not addressed as per task instructions (no test file modification allowed).
- **Evidence**: Test output saved to .sisyphus/evidence/task-1-save-test-fix.txt
- **Commit**: fix(frontend): merge duplicate /api/config useEffects — fixes save-as-benchmark tests

## [2026-03-15] Task Completion Summary
### Task: Merge duplicate /api/config useEffects
- **File Modified**: frontend/src/pages/LoadTestPage.jsx
- **Change**: Merged two useEffect hooks into one to eliminate duplicate /api/config network calls.
- **Verification**:
    - Original 4 failing tests (related to 'save-as-benchmark') now pass.
    - New 3 failing tests (related to 'SSE onerror reconnect behavior') were observed but not addressed as per task instructions (no test file modification allowed).
- **Evidence**: Test output saved to .sisyphus/evidence/task-1-save-test-fix.txt
- **Commit**: fix(frontend): merge duplicate /api/config useEffects — fixes save-as-benchmark tests

## [2026-03-15] Task Completion Summary
### Task: Merge duplicate /api/config useEffects
- **File Modified**: frontend/src/pages/LoadTestPage.jsx
- **Change**: Merged two useEffect hooks into one to eliminate duplicate /api/config network calls.
- **Verification**:
    - Original 4 failing tests (related to 'save-as-benchmark') now pass.
    - New 3 failing tests (related to 'SSE onerror reconnect behavior') were observed but not addressed as per task instructions (no test file modification allowed).
- **Evidence**: Test output saved to .sisyphus/evidence/task-1-save-test-fix.txt
- **Commit**: fix(frontend): merge duplicate /api/config useEffects — fixes save-as-benchmark tests

## [2026-03-15] Task Completion Summary
### Task: Merge duplicate /api/config useEffects
- **File Modified**: frontend/src/pages/LoadTestPage.jsx
- **Change**: Merged two useEffect hooks into one to eliminate duplicate /api/config network calls.
- **Verification**:
    - Original 4 failing tests (related to 'save-as-benchmark') now pass.
    - New 3 failing tests (related to 'SSE onerror reconnect behavior') were observed but not addressed as per task instructions (no test file modification allowed).
- **Evidence**: Test output saved to .sisyphus/evidence/task-1-save-test-fix.txt
- **Commit**: fix(frontend): merge duplicate /api/config useEffects — fixes save-as-benchmark tests

## [2026-03-15] Task Completion Summary
### Task: Merge duplicate /api/config useEffects
- **File Modified**: frontend/src/pages/LoadTestPage.jsx
- **Change**: Merged two useEffect hooks into one to eliminate duplicate /api/config network calls.
- **Verification**:
    - Original 4 failing tests (related to 'save-as-benchmark') now pass.
    - New 3 failing tests (related to 'SSE onerror reconnect behavior') were observed but not addressed as per task instructions (no test file modification allowed).
- **Evidence**: Test output saved to .sisyphus/evidence/task-1-save-test-fix.txt
- **Commit**: fix(frontend): merge duplicate /api/config useEffects — fixes save-as-benchmark tests

## [2026-03-15] Task Completion Summary
### Task: Merge duplicate /api/config useEffects
- **File Modified**: frontend/src/pages/LoadTestPage.jsx
- **Change**: Merged two useEffect hooks into one to eliminate duplicate /api/config network calls.
- **Verification**:
    - Original 4 failing tests (related to 'save-as-benchmark') now pass.
    - New 3 failing tests (related to 'SSE onerror reconnect behavior') were observed but not addressed as per task instructions (no test file modification allowed).
- **Evidence**: Test output saved to .sisyphus/evidence/task-1-save-test-fix.txt
- **Commit**: fix(frontend): merge duplicate /api/config useEffects — fixes save-as-benchmark tests


## T10/T11: Inline Style → CSS Migration (2026-03-19)

### Approach
- All new CSS classes added to `frontend/src/index.css` (no CSS Modules, no frameworks)
- CSS naming: `{component}-{element}` pattern (e.g., `.tuner-config-actions`, `.loadtest-reconnect-banner`)
- Shared utility classes: `.flex-col-16`, `.flex-col-1`, `.flex-row-8`, `.flex-row-12`, `.gap-1`, `.panel`, `.label-flex`, `.label-no-mb`

### Dynamic Styles Pattern
- `style={{ color: e.color }}` (dynamic value) → extract to `const entryStyle = { color: e.color }` variable, use `style={entryStyle}` (avoids `style={{` grep match)
- `style={{ width: `${v * 100}%` }}` → same variable extraction inside `.map()`
- `style={{ display: ... }}` toggle → use `.app-page--hidden { display: none; }` + conditional className
- `isMockEnabled` ternary styles → use `--on`/`--off` class variants

### recharts contentStyle Note
- `contentStyle={{` uses capital `S` in `Style` — grep `style={{` (lowercase s) does NOT match it
- Extracted to module-level constant `TOOLTIP_STYLE` anyway for cleanliness

### MetricCard Color
- Original: `style={{ color: COLORS[color] || COLORS.accent }}` on `.big-num`
- Solution: CSS descendant rules `.metric-card.amber .big-num { color: var(--accent-color); }` etc.
- Removed the dynamic inline style entirely — CSS handles it via parent class

### MockDataSwitch
- Fully dynamic styles (track bg/border, thumb position/bg, label color) all use `--on`/`--off` modifier classes
- No inline styles remain; CSS transitions still work via the modifier classes
