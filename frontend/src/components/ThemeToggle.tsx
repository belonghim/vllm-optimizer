import { useTheme } from "../contexts/ThemeContext";

export default function ThemeToggle() {
  const { theme, toggleTheme } = useTheme();
  const isLight = theme === "light";

  return (
    <div
      className="mock-switch-root"
      onClick={toggleTheme}
      role="switch"
      aria-checked={isLight}
      aria-label="테마 전환"
      tabIndex={0}
      onKeyDown={(e) => (e.key === " " || e.key === "Enter") && toggleTheme()}
    >
      <div className={`mock-switch-track ${isLight ? 'mock-switch-track--on' : 'mock-switch-track--off'}`}>
        <div className={`mock-switch-thumb ${isLight ? 'mock-switch-thumb--on' : 'mock-switch-thumb--off'}`} />
      </div>
      <span className={`mock-switch-label ${isLight ? 'mock-switch-label--on' : 'mock-switch-label--off'}`}>
        {isLight ? "LIGHT" : "DARK"}
      </span>
    </div>
  );
}
