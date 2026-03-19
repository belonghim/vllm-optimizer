## Task Completed: T6: LoadTestPage — prompt_template + temperature + 모델명 자동 해석

The requested modifications to `frontend/src/pages/LoadTestPage.jsx` have been successfully implemented.

### Changes Made:
- **Config State Update**: Added `prompt_template: "Hello, how are you?"` and ensured `temperature: 0.7` as default in the `useState` hook for `config`.
- **Model Auto-Resolution**: Integrated a `useEffect` hook to fetch `/api/config` and automatically set the `model` name if `resolved_model_name` is available and not "auto", respecting user-defined values.
- **UI Field Addition**: Added a `textarea` for `prompt_template` and a `number` input for `temperature` to the load test configuration form.

### Verification:
- `grep "prompt_template" frontend/src/pages/LoadTestPage.jsx` confirmed the presence of the prompt template field.
- `grep "temperature" frontend/src/pages/LoadTestPage.jsx` confirmed the presence of the temperature input field.
- `grep "resolved_model_name" frontend/src/pages/LoadTestPage.jsx` confirmed the implementation of the model auto-resolution logic.
- Evidence files have been generated in `.sisyphus/evidence/`.

### Commit Details:
- **File Modified**: `frontend/src/pages/LoadTestPage.jsx`
- **Commit Message**: `feat(frontend): add prompt_template, temperature, model auto-resolve to LoadTestPage`