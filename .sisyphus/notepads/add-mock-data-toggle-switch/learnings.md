# Learnings — add-mock-data-toggle-switch

## 2026-03-06T06:01:43Z — Initial Exploration
- Theme: Industrial / Terminal aesthetic (dark background + fluorescent amber/cyan accents)
- COLORS from `frontend/src/constants.js`:
  - bg: "#0a0b0d", surface: "#111318", border: "#1e2330"
  - accent: "#f5a623" (amber), cyan: "#00d4ff", green: "#00ff87"
  - red: "#ff3b6b", purple: "#b060ff", text: "#c8cfe0", muted: "#4a5578"
- font: { mono: "'JetBrains Mono'...", display: "'Barlow Condensed'..." }
- API base: "http://localhost:8000/api" (from constants.js)

### Current State
- `frontend/src/contexts/` — DOES NOT EXIST yet (must create dir + file)
- App.jsx header right area: `<div style={{ display: "flex", alignItems: "center", gap: 12 }}>`
  - Contains green dot + "CONNECTED" span
  - MockDataSwitch goes to LEFT of the green dot separator
- App.jsx imports mockData but doesn't actually use it (each page imports its own)

### Mock Data Usage Per Page
- MonitorPage.jsx: mockMetrics, mockHistory, mockBenchmarks, mockTrials, simulateLoadTest
- LoadTestPage.jsx: simulateLoadTest
- BenchmarkPage.jsx: mockBenchmarks
- TunerPage.jsx: mockTrials

### Task Execution Order
- Task 1 (Context) MUST run first — blocks all others
- Tasks 2-6 can run in PARALLEL after Task 1
- Final Verification LAST
- Created MockDataContext with toggle state persisted to localStorage and wrapped App in MockDataProvider.

### Implementation Details
- Created `frontend/src/components/MockDataSwitch.jsx` with industrial/terminal aesthetic using COLORS and font constants
- Updated `frontend/src/App.jsx`:
  - Removed unused mockData import
  - Added import for MockDataSwitch
  - Inserted MockDataSwitch component to the left of the green CONNECTED dot
  - Added divider between MockDataSwitch and green dot
- Component includes proper accessibility attributes: role="switch", aria-checked, aria-label, tabIndex, onKeyDown handler
- Styled with dark background, accent border, animated thumb movement
- Verified with linters and formatters

### Verification
- lsp_diagnostics shows no errors on modified files
- Component renders correctly in browser
- Accessibility attributes are correctly set
- No breaking changes to existing functionality

### 2026-03-06TXX:XX:XXZ — Updated MonitorPage.jsx with useMockData toggle and error handling
- Integrated useMockData from MockDataContext to control mock vs real API data
- Added error state and display UI with red border and warning icon
- Cleaned up mock imports to only include mockMetrics and mockHistory
- Preserved mockBenchmarks, mockTrials, simulateLoadTest for other pages

(End of file - updated 2026-03-06)