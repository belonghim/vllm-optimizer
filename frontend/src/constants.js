// Export constants for use in other components
export const API = "/api";

export const COLORS = {
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

export const font = {
  mono: "'JetBrains Mono', 'Fira Code', monospace",
  display: "'Barlow Condensed', 'Oswald', sans-serif",
};

export const TOOLTIP_STYLE = { background: COLORS.surface, border: `1px solid ${COLORS.border}` };

export const TARGET_COLORS = [COLORS.accent, COLORS.cyan, COLORS.green, COLORS.red, COLORS.purple];

export const METRIC_KEYS = ['tps', 'ttft', 'ttft_fill', 'lat_p99', 'lat_p99_fill', 'kv', 'running', 'waiting', 'rps', 'ttft_p99', 'lat_mean', 'kv_hit', 'gpu_util', 'gpu_mem_used', 'gpu_mem_total'];