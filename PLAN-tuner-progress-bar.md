# Plan: Add Progress Display to Tuner START Button

## Context

**User Request Summary:** Add a visual progress bar to the Auto Tuner's START TUNING button in `TunerConfigForm.jsx` to show trial completion percentage and phase information in real-time.

**Current State Analysis:**
- `TunerPage.jsx` manages state: `status.trials_completed`, `config.n_trials`, `currentPhase`, and `isRunning`
- `TunerConfigForm.jsx` receives these as props and displays `{trialsCompleted} / {config.n_trials} trials` as plain text
- SSE stream provides real-time updates via `currentPhase` object with `{trial_id, phase}` structure
- Existing CSS has `.progress-bar` and `.progress-fill` classes ready for use
- Phase labels are defined in `PHASE_LABELS` constant

**What's Missing:**
- No visual progress bar component (only text count exists)
- No percentage calculation or display
- Progress not prominently visible during long tuning sessions

## Task Dependency Graph

| Task | Depends On | Reason |
|------|------------|--------|
| Task 1: Write unit tests | None | TDD approach - tests first |
| Task 2: Create ProgressBar component | Task 1 | Component implements tested interface |
| Task 3: Integrate into TunerConfigForm | Task 2 | Uses the new component |
| Task 4: Add CSS styles | Task 2 | Styles the component |
| Task 5: Integration test | Task 3, Task 4 | Validates full integration |

## Parallel Execution Graph

```
Wave 1 (Start immediately):
└── Task 1: Write unit tests for ProgressBar component (no dependencies)

Wave 2 (After Wave 1 completes):
├── Task 2: Create TunerProgressBar component (depends: Task 1)
└── Task 4: Add CSS styles for progress bar (can start in parallel, only CSS)

Wave 3 (After Task 2 completes):
└── Task 3: Integrate TunerProgressBar into TunerConfigForm (depends: Task 2)

Wave 4 (After Wave 3 completes):
└── Task 5: Integration testing and edge case validation (depends: Task 3, Task 4)

Critical Path: Task 1 → Task 2 → Task 3 → Task 5
Estimated Parallel Speedup: ~20% (Task 4 parallel with Task 2)
```

## Tasks

### Task 1: Write Unit Tests for TunerProgressBar Component

**Description:** Create comprehensive unit tests following TDD approach for the new `TunerProgressBar` component before implementation.

**Delegation Recommendation:**
- Category: `quick` - Straightforward test file creation with known patterns
- Skills: [`frontend-ui-ux`] - For understanding component testing patterns

**Skills Evaluation:**
- ✅ INCLUDED `frontend-ui-ux`: React component testing knowledge
- ❌ OMITTED `git-master`: No git operations in this task
- ❌ OMITTED `playwright`: Unit tests, not E2E browser tests
- ❌ OMITTED `dev-browser`: No browser automation needed

**Depends On:** None

**Acceptance Criteria:**
- [ ] Test file created at `frontend/src/components/__tests__/TunerProgressBar.test.jsx`
- [ ] Tests cover: idle state (0%), running state with progress, completed state (100%)
- [ ] Tests cover: phase label display when `currentPhase` is provided
- [ ] Tests cover: edge cases (n_trials=0, negative values)
- [ ] Tests initially fail (red phase of TDD)

**Test Cases to Implement:**
```javascript
// Test cases specification
1. renders nothing when not running and no trials completed
2. renders progress bar with correct percentage when running
3. displays phase label when currentPhase is provided
4. shows 100% and "COMPLETED" style when all trials done
5. handles edge case: n_trials = 0 (prevent division by zero)
6. handles edge case: trialsCompleted > n_trials
7. updates percentage smoothly on prop changes
```

---

### Task 2: Create TunerProgressBar Component

**Description:** Implement the `TunerProgressBar` React component that displays visual progress of tuning trials.

**Delegation Recommendation:**
- Category: `visual-engineering` - UI component with visual/animation aspects
- Skills: [`frontend-ui-ux`] - For creating polished UI component

**Skills Evaluation:**
- ✅ INCLUDED `frontend-ui-ux`: Essential for creating proper React component with good UX
- ❌ OMITTED `git-master`: No git operations
- ❌ OMITTED `playwright`: Implementation, not testing
- ❌ OMITTED `dev-browser`: No browser automation

**Depends On:** Task 1 (tests must exist first)

**Acceptance Criteria:**
- [ ] Component file created at `frontend/src/components/TunerProgressBar.jsx`
- [ ] Props: `isRunning`, `trialsCompleted`, `totalTrials`, `currentPhase`
- [ ] Calculates percentage: `Math.min(100, Math.round((trialsCompleted / totalTrials) * 100))`
- [ ] Displays: progress bar fill, percentage text, phase label (when running)
- [ ] Uses existing CSS classes: `.progress-bar`, `.progress-fill`
- [ ] All unit tests from Task 1 pass (green phase)
- [ ] Handles division by zero gracefully

**Component Interface:**
```jsx
<TunerProgressBar
  isRunning={boolean}           // Whether tuning is in progress
  trialsCompleted={number}      // Number of completed trials
  totalTrials={number}          // Total trials (config.n_trials)
  currentPhase={object|null}    // {trial_id, phase} from SSE
/>
```

**Implementation Details:**
```jsx
// Key logic
const percentage = totalTrials > 0 
  ? Math.min(100, Math.round((trialsCompleted / totalTrials) * 100))
  : 0;

const phaseLabel = currentPhase 
  ? `Trial ${currentPhase.trial_id + 1}: ${PHASE_LABELS[currentPhase.phase] || currentPhase.phase}`
  : null;
```

---

### Task 3: Integrate TunerProgressBar into TunerConfigForm

**Description:** Add the `TunerProgressBar` component to `TunerConfigForm.jsx`, replacing/augmenting the existing text-only trial count display.

**Delegation Recommendation:**
- Category: `quick` - Simple component integration with clear requirements
- Skills: [`frontend-ui-ux`] - For proper component placement and UX

**Skills Evaluation:**
- ✅ INCLUDED `frontend-ui-ux`: Needed for proper UI integration
- ❌ OMITTED `git-master`: No git operations
- ❌ OMITTED `playwright`: Not E2E testing
- ❌ OMITTED `dev-browser`: No browser automation

**Depends On:** Task 2

**Acceptance Criteria:**
- [ ] Import `TunerProgressBar` in `TunerConfigForm.jsx`
- [ ] Add component below action buttons, replacing `.tuner-trials-count` when running
- [ ] Pass correct props from existing component state
- [ ] Keep existing `.tuner-phase-indicator` for detailed phase info
- [ ] Progress bar visible during tuning, hidden when idle
- [ ] No breaking changes to existing functionality

**Integration Point (in TunerConfigForm.jsx):**
```jsx
// After tuner-config-actions div, before advanced toggle
{(isRunning || trialsCompleted > 0) && (
  <TunerProgressBar
    isRunning={isRunning}
    trialsCompleted={trialsCompleted}
    totalTrials={config.n_trials}
    currentPhase={currentPhase}
  />
)}
```

---

### Task 4: Add CSS Styles for TunerProgressBar

**Description:** Add/extend CSS styles in `index.css` for the tuner progress bar component.

**Delegation Recommendation:**
- Category: `visual-engineering` - Pure CSS/styling task
- Skills: [`frontend-ui-ux`] - For consistent visual design

**Skills Evaluation:**
- ✅ INCLUDED `frontend-ui-ux`: Essential for visual styling consistency
- ❌ OMITTED `git-master`: No git operations
- ❌ OMITTED `playwright`: Not browser testing
- ❌ OMITTED `dev-browser`: No browser automation

**Depends On:** Task 2 (needs to know component structure)

**Acceptance Criteria:**
- [ ] New CSS classes added to `frontend/src/index.css`
- [ ] Consistent with existing design system (CSS variables)
- [ ] Progress bar has smooth transition animation
- [ ] Percentage text is readable and well-positioned
- [ ] Completed state has distinct visual style
- [ ] Mobile responsive

**CSS Classes to Add:**
```css
.tuner-progress-container { ... }
.tuner-progress-header { ... }
.tuner-progress-pct { ... }
.tuner-progress-bar { ... }      /* extend existing .progress-bar */
.tuner-progress-fill { ... }     /* extend existing .progress-fill */
.tuner-progress-fill--completed { ... }
.tuner-progress-phase { ... }
```

---

### Task 5: Integration Testing and Edge Case Validation

**Description:** Validate the complete integration works correctly, including SSE updates, edge cases, and visual appearance.

**Delegation Recommendation:**
- Category: `unspecified-low` - Testing and validation task
- Skills: [`playwright`, `frontend-ui-ux`] - For E2E browser testing

**Skills Evaluation:**
- ✅ INCLUDED `playwright`: For E2E browser verification
- ✅ INCLUDED `frontend-ui-ux`: For visual validation
- ❌ OMITTED `git-master`: No git operations in testing
- ❌ OMITTED `dev-browser`: Using playwright for browser automation

**Depends On:** Task 3, Task 4

**Acceptance Criteria:**
- [ ] All unit tests pass: `npm test -- --testPathPattern=TunerProgressBar`
- [ ] Visual verification in browser with mock data enabled
- [ ] Progress bar updates in real-time during actual tuning (if cluster available)
- [ ] Edge cases verified:
  - Idle state: no progress bar shown (or minimal indicator)
  - 0 trials completed: shows 0%
  - Partial completion: shows correct percentage
  - 100% completion: shows completed state
  - n_trials = 0: no crash, graceful handling
- [ ] No console errors or warnings
- [ ] Accessibility: progress bar has aria attributes

**Manual Testing Checklist:**
```bash
# 1. Run frontend with mock data
cd frontend && npm run dev

# 2. Navigate to Tuner tab
# 3. Toggle mock data ON
# 4. Click Start Tuning
# 5. Verify progress bar appears and animates
# 6. Verify percentage updates
# 7. Verify phase label shows current activity
```

---

## Commit Strategy

Following atomic commit principles with clear, self-contained changes:

```
Commit 1: test(frontend): add unit tests for TunerProgressBar component
  - Add frontend/src/components/__tests__/TunerProgressBar.test.jsx
  - Tests for all states and edge cases

Commit 2: feat(frontend): add TunerProgressBar component
  - Add frontend/src/components/TunerProgressBar.jsx
  - Visual progress indicator for tuning trials

Commit 3: style(frontend): add CSS for tuner progress bar
  - Update frontend/src/index.css with progress bar styles
  - Smooth animations and completed state styling

Commit 4: feat(frontend): integrate progress bar into TunerConfigForm
  - Update frontend/src/components/TunerConfigForm.jsx
  - Add TunerProgressBar component with props

Commit 5: test(frontend): add integration tests for tuner progress
  - Verify E2E flow with progress bar updates
```

## Success Criteria

1. **Functional:** Progress bar displays and updates correctly during tuning
2. **Visual:** Consistent with existing design system, smooth animations
3. **Robust:** Handles all edge cases without errors
4. **Tested:** Unit tests and integration tests pass
5. **Accessible:** Proper ARIA attributes for screen readers
6. **Maintainable:** Clean code following existing patterns

---

## TODO List (ADD THESE)

> CALLER: Add these TODOs using TodoWrite/TaskCreate and execute by wave.

### Wave 1 (Start Immediately - No Dependencies)

- [x] **1. Write unit tests for TunerProgressBar component**
  - What: Create `frontend/src/components/__tests__/TunerProgressBar.test.jsx` with tests for:
    - Idle state (no render or minimal)
    - Running state with various percentages
    - Completed state (100%)
    - Phase label display
    - Edge cases (n_trials=0, overflow)
  - Depends: None
  - Blocks: Task 2
  - Category: `quick`
  - Skills: [`frontend-ui-ux`]
  - QA: `cd frontend && npm test -- --testPathPattern=TunerProgressBar` (tests should fail initially - TDD red phase)

### Wave 2 (After Wave 1 Completes)

- [x] **2. Create TunerProgressBar component**
  - What: Create `frontend/src/components/TunerProgressBar.jsx` with:
    - Props: `isRunning`, `trialsCompleted`, `totalTrials`, `currentPhase`
    - Percentage calculation with bounds checking
    - Phase label lookup using existing PHASE_LABELS
    - Conditional rendering based on state
  - Depends: 1
  - Blocks: 3, 5
  - Category: `visual-engineering`
  - Skills: [`frontend-ui-ux`]
  - QA: `cd frontend && npm test -- --testPathPattern=TunerProgressBar` (all tests should pass - TDD green phase)

- [x] **4. Add CSS styles for progress bar**
  - What: Add to `frontend/src/index.css`:
    - `.tuner-progress-container` - wrapper styling
    - `.tuner-progress-header` - flex row with percentage
    - `.tuner-progress-bar` - bar container (extend existing)
    - `.tuner-progress-fill` - animated fill (extend existing)
    - `.tuner-progress-fill--completed` - green completed state
  - Depends: None (can reference existing patterns)
  - Blocks: 5
  - Category: `visual-engineering`
  - Skills: [`frontend-ui-ux`]
  - QA: Visual inspection - styles should match existing design system (amber/cyan gradient)

### Wave 3 (After Wave 2 Completes)

- [x] **3. Integrate TunerProgressBar into TunerConfigForm**
  - What: In `frontend/src/components/TunerConfigForm.jsx`:
    - Import TunerProgressBar component
    - Add component after `.tuner-config-actions` div
    - Pass props: `isRunning`, `trialsCompleted={trialsCompleted}`, `totalTrials={config.n_trials}`, `currentPhase`
    - Show when running OR when trials > 0 (for completed state)
  - Depends: 2
  - Blocks: 5
  - Category: `quick`
  - Skills: [`frontend-ui-ux`]
  - QA: `cd frontend && npm run dev` then visually verify in Tuner tab

### Wave 4 (After Wave 3 Completes)

- [x] **5. Integration testing and validation**
  - What: 
    - Run all unit tests
    - Manual visual testing with mock data
    - Verify SSE updates work (if cluster available)
    - Check console for errors
    - Verify accessibility (aria-valuenow, aria-valuemax)
  - Depends: 2, 3, 4
  - Blocks: None (final task)
  - Category: `unspecified-low`
  - Skills: [`playwright`, `frontend-ui-ux`]
  - QA: 
    - `cd frontend && npm test` (all tests pass)
    - `cd frontend && npm run dev` (no console errors)
    - Toggle mock data, run tuning, verify progress updates

## Execution Instructions

1. **Wave 1**: Fire Task 1
   ```
   task(category="quick", load_skills=["frontend-ui-ux"], prompt="Task 1: Create unit tests for TunerProgressBar component in frontend/src/components/__tests__/TunerProgressBar.test.jsx...")
   ```

2. **Wave 2**: After Wave 1 completes, fire Tasks 2 and 4 IN PARALLEL
   ```
   task(category="visual-engineering", load_skills=["frontend-ui-ux"], prompt="Task 2: Create TunerProgressBar component...")
   task(category="visual-engineering", load_skills=["frontend-ui-ux"], prompt="Task 4: Add CSS styles for tuner progress bar...")
   ```

3. **Wave 3**: After Task 2 completes, fire Task 3
   ```
   task(category="quick", load_skills=["frontend-ui-ux"], prompt="Task 3: Integrate TunerProgressBar into TunerConfigForm...")
   ```

4. **Wave 4**: After Tasks 3 and 4 complete, fire Task 5
   ```
   task(category="unspecified-low", load_skills=["playwright", "frontend-ui-ux"], prompt="Task 5: Integration testing and validation...")
   ```

5. **Final QA**: Verify all tasks pass their QA criteria
   - All tests pass
   - No console errors
   - Progress bar visually correct
   - Real-time updates working

6. **Commits**: Execute atomic commits as specified in Commit Strategy
