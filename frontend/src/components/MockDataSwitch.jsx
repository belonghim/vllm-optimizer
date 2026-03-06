import { useMockData } from "../contexts/MockDataContext";
import { COLORS, font } from "../constants";

export default function MockDataSwitch() {
  const { isMockEnabled, toggleMockEnabled } = useMockData();

  return (
    <div
      style={{ display: "flex", alignItems: "center", gap: 6, cursor: "pointer" }}
      onClick={toggleMockEnabled}
      role="switch"
      aria-checked={isMockEnabled}
      aria-label="Mock 데이터 사용 전환"
      tabIndex={0}
      onKeyDown={(e) => (e.key === " " || e.key === "Enter") && toggleMockEnabled()}
    >
      {/* Track */}
      <div style={{
        position: "relative",
        width: 32, height: 16,
        borderRadius: 8,
        background: isMockEnabled ? COLORS.accent : COLORS.surface,
        border: `1px solid ${isMockEnabled ? COLORS.accent : COLORS.border}`,
        transition: "background 0.2s, border-color 0.2s",
        boxSizing: "border-box",
      }}>
        {/* Thumb */}
        <div style={{
          position: "absolute",
          top: 2, left: isMockEnabled ? 16 : 2,
          width: 10, height: 10,
          borderRadius: "50%",
          background: isMockEnabled ? COLORS.bg : COLORS.muted,
          boxShadow: isMockEnabled ? `0 0 6px ${COLORS.accent}` : "none",
          transition: "left 0.2s, background 0.2s, box-shadow 0.2s",
        }} />
      </div>
      {/* Label */}
      <span style={{
        fontSize: 9,
        letterSpacing: "0.1em",
        textTransform: "uppercase",
        fontFamily: font.mono,
        color: isMockEnabled ? COLORS.accent : COLORS.muted,
        transition: "color 0.2s",
      }}>
        MOCK
      </span>
    </div>
  );
}