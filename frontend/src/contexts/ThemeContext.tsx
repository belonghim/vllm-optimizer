import { createContext, useState, useEffect, useMemo, useContext } from "react";
import type { ReactNode } from "react";

const STORAGE_KEY = "vllm-theme";

type Theme = "dark" | "light";

interface ThemeContextValue {
  theme: Theme;
  toggleTheme: () => void;
}

const ThemeContext = createContext<ThemeContextValue>({
  theme: "dark",
  toggleTheme: () => {},
});

interface ThemeProviderProps {
  children: ReactNode;
}

export function ThemeProvider({ children }: ThemeProviderProps) {
  const [theme, setTheme] = useState<Theme>(() => {
    const stored = localStorage.getItem(STORAGE_KEY) as Theme | null;
    if (stored) return stored;
    return window.matchMedia("(prefers-color-scheme: dark)").matches
      ? "dark"
      : "light";
  });

  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, theme);
    document.documentElement.setAttribute("data-theme", theme);
  }, [theme]);

  const toggleTheme = () => setTheme(prev => (prev === "dark" ? "light" : "dark"));

  const value = useMemo(
    () => ({ theme, toggleTheme }),
    [theme]
  );

  return (
    <ThemeContext.Provider value={value}>
      {children}
    </ThemeContext.Provider>
  );
}

export const LIGHT_COLORS = {
  bg: "#ffffff",
  surface: "#f5f6f8",
  border: "#e0e4ea",
  accent: "#f5a623",
  cyan: "#00d4ff",
  green: "#00ff87",
  red: "#ff3b6b",
  purple: "#b060ff",
  text: "#1a1d26",
  muted: "#8892a8",
};

export const DARK_COLORS = {
  bg: "#0a0b0d",
  surface: "#111318",
  border: "#1e2330",
  accent: "#f5a623",
  cyan: "#00d4ff",
  green: "#00ff87",
  red: "#ff3b6b",
  purple: "#b060ff",
  text: "#c8cfe0",
  muted: "#4a5578",
};

export const LIGHT_TOOLTIP = {
  backgroundColor: "#ffffff",
  border: "1px solid #e0e4ea",
  borderRadius: "6px",
  color: "#1a1d26",
  fontSize: 12,
};

export const DARK_TOOLTIP = {
  backgroundColor: "#111318",
  border: "1px solid #1e2330",
  borderRadius: "6px",
  color: "#c8cfe0",
  fontSize: 12,
};

export function useThemeColors() {
  const { theme } = useTheme();
  const isLight = theme === "light";
  return {
    COLORS: isLight ? LIGHT_COLORS : DARK_COLORS,
    TOOLTIP_STYLE: isLight ? LIGHT_TOOLTIP : DARK_TOOLTIP,
  };
}

export function useTheme(): ThemeContextValue {
  return useContext(ThemeContext);
}
