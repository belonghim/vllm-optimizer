export const API: string = "/api";

interface ColorPalette {
  bg: string;
  surface: string;
  border: string;
  accent: string;
  cyan: string;
  green: string;
  red: string;
  purple: string;
  text: string;
  muted: string;
}

export const COLORS: ColorPalette = {
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

interface FontFamily {
  mono: string;
  display: string;
}

export const font: FontFamily = {
  mono: "'JetBrains Mono', 'Fira Code', monospace",
  display: "'Barlow Condensed', 'Oswald', sans-serif",
};

interface TooltipStyle {
  background: string;
  border: string;
}

export const TOOLTIP_STYLE: TooltipStyle = { background: COLORS.surface, border: `1px solid ${COLORS.border}` };

export const TARGET_COLORS: string[] = [COLORS.accent, COLORS.cyan, COLORS.green, COLORS.red, COLORS.purple];

export const METRIC_KEYS: string[] = ['tps', 'ttft', 'ttft_fill', 'lat_p99', 'lat_p99_fill', 'kv', 'running', 'waiting', 'rps', 'ttft_p99', 'lat_mean', 'kv_hit', 'gpu_util', 'gpu_mem_used', 'gpu_mem_total', 'tpot_mean', 'tpot_p99', 'queue_time_mean', 'queue_time_p99'];

export interface LoadTestPreset {
  name: string;
  description: string;
  total_requests: number;
  concurrency: number;
  rps: number;
  max_tokens: number;
  stream: boolean;
}

export const LOAD_TEST_PRESETS: LoadTestPreset[] = [
  { name: "Quick Smoke", description: "Quick validation (10 requests)", total_requests: 10, concurrency: 2, rps: 5, max_tokens: 64, stream: true },
  { name: "Standard", description: "Standard load (100 requests)", total_requests: 100, concurrency: 10, rps: 20, max_tokens: 128, stream: true },
  { name: "Stress", description: "Stress test (500 requests)", total_requests: 500, concurrency: 50, rps: 50, max_tokens: 128, stream: true },
];

export interface SweepPreset {
  name: string;
  description: string;
  rps_start: number;
  rps_end: number;
  rps_step: number;
  requests_per_step: number;
  concurrency: number;
}

export const SWEEP_PRESETS: SweepPreset[] = [
  { name: "Quick Sweep", description: "Quick saturation point detection", rps_start: 1, rps_end: 20, rps_step: 5, requests_per_step: 10, concurrency: 5 },
  { name: "Full Sweep", description: "Precision saturation point detection", rps_start: 1, rps_end: 50, rps_step: 2, requests_per_step: 30, concurrency: 10 },
];
