
### Bug Fixes in LoadTestPage.jsx

- **Issue**: API paths used hyphens (`/load-test/`) while the backend expected underscores (`/load_test/`), leading to 404 errors. The `endpoint` form default was `"http://localhost:8000"` instead of `""`.
- **Resolution**:
    - Changed `endpoint: "http://localhost:8000"` to `endpoint: ""` in `useState`.
    - Replaced all instances of `/load-test/` with `/load_test/` in API calls (`start`, `stream`, `stop`).
    - Added a `useEffect` hook to fetch the default `vllm_endpoint` from `/api/config` on component mount and set it if the `endpoint` is currently empty.
- **Learnings**:
    - Always ensure consistency between frontend and backend API path conventions (hyphens vs. underscores).
    - Utilize a configuration endpoint (`/api/config`) to provide dynamic defaults for frontend components, improving flexibility and reducing hardcoding.
    - Be mindful of `oldString` uniqueness when using the `edit` tool; provide sufficient context to avoid multiple matches.
