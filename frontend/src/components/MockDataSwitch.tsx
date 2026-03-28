import { useMockData } from "../contexts/MockDataContext";

export default function MockDataSwitch() {
  const { isMockEnabled, toggleMockEnabled } = useMockData();

  return (
    <div
      className="mock-switch-root"
      onClick={toggleMockEnabled}
      role="switch"
      aria-checked={isMockEnabled}
      aria-label="Toggle mock data"
      tabIndex={0}
      onKeyDown={(e) => (e.key === " " || e.key === "Enter") && toggleMockEnabled()}
    >
      <div className={`mock-switch-track ${isMockEnabled ? 'mock-switch-track--on' : 'mock-switch-track--off'}`}>
        <div className={`mock-switch-thumb ${isMockEnabled ? 'mock-switch-thumb--on' : 'mock-switch-thumb--off'}`} />
      </div>
      <span className={`mock-switch-label ${isMockEnabled ? 'mock-switch-label--on' : 'mock-switch-label--off'}`}>
        MOCK
      </span>
    </div>
  );
}
