import Chart from "./Chart";
import { TARGET_COLORS, COLORS as DARK_COLORS } from "../constants";
import type { ClusterTarget } from "../types";

export interface ChartLine {
  key: string;
  color: string;
  label: string;
  dash?: boolean;
}

export type ChartLinesMap = Record<string, ChartLine[]>;

export interface ChartDefinition {
  id: string;
  title: string;
}

export const CHART_DEFINITIONS: ChartDefinition[] = [
  { id: 'tps',      title: 'Throughput (TPS)' },
  { id: 'latency',  title: 'Latency (ms)' },
  { id: 'ttft',     title: 'TTFT (ms)' },
  { id: 'kv',       title: 'KV Cache Usage (%)' },
  { id: 'kv_hit',   title: 'KV Cache Hit Rate (%)' },
  { id: 'queue',    title: 'Request Queue' },
  { id: 'swapped',  title: 'Swapped Requests' },
  { id: 'rps',      title: 'RPS (Requests/sec)' },
  { id: 'gpu_util', title: 'GPU Utilization (%)' },
  { id: 'gpu_mem',  title: 'GPU Memory (GB)' },
  { id: 'tpot',       title: 'TPOT (ms)' },
  { id: 'queue_time', title: 'Queue Time (ms) (vLLM v0.6+)' },
];

const LS_KEY = 'vllm-optimizer-chart-config';
export const DEFAULT_ORDER = CHART_DEFINITIONS.map(c => c.id);

export interface ChartConfig {
  order: string[];
  hidden: string[];
}

export function loadChartConfig(): ChartConfig {
  try {
    const raw = localStorage.getItem(LS_KEY);
    if (!raw) return { order: DEFAULT_ORDER, hidden: [] };
    const parsed = JSON.parse(raw);
    const validIds = new Set(DEFAULT_ORDER);
    const order = Array.isArray(parsed.order)
      ? parsed.order.filter((id: string) => validIds.has(id))
      : DEFAULT_ORDER;
    const hidden = Array.isArray(parsed.hidden)
      ? parsed.hidden.filter((id: string) => validIds.has(id))
      : [];
    const inOrder = new Set(order);
    DEFAULT_ORDER.forEach(id => { if (!inOrder.has(id)) order.push(id); });
    return { order, hidden };
  } catch (e) {
    console.error('Failed to load chart configuration from localStorage', e);
    return { order: DEFAULT_ORDER, hidden: [] };
  }
}

export function saveChartConfig(order: string[], hidden: string[]) {
  try {
    localStorage.setItem(LS_KEY, JSON.stringify({ order, hidden }));
  } catch (e) {
    console.error('Failed to save chart configuration to localStorage', e);
  }
}

export function buildChartLinesMap(
  targets: ClusterTarget[],
  defaultKey: string | null,
  COLORS: typeof DARK_COLORS = DARK_COLORS,
): ChartLinesMap {
  const makeMultiLines = (metricKey: string) =>
    targets.map((t, i) => ({
      key: `${t.namespace}/${t.inferenceService}/${t.crType || 'inferenceservice'}_${metricKey}`,
      label: t.inferenceService,
      color: TARGET_COLORS[i % TARGET_COLORS.length],
    }));

  if (targets.length === 1 && defaultKey) {
    return {
      tps:      [{ key: `${defaultKey}_tps`, color: COLORS.accent, label: "TPS" }],
      latency:  [
        { key: `${defaultKey}_lat_p99_fill`, color: COLORS.red, label: "P99 (idle)", dash: true },
        { key: `${defaultKey}_lat_p99`, color: COLORS.red, label: "Latency P99" },
        { key: `${defaultKey}_lat_mean`, color: COLORS.accent, label: "Latency mean" },
      ],
      ttft:     [
        { key: `${defaultKey}_ttft_fill`, color: COLORS.cyan, label: "TTFT (idle)", dash: true },
        { key: `${defaultKey}_ttft`, color: COLORS.cyan, label: "TTFT mean" },
        { key: `${defaultKey}_ttft_p99`, color: COLORS.accent, label: "TTFT p99" },
      ],
      kv:       [{ key: `${defaultKey}_kv`, color: COLORS.purple, label: "KV Cache %" }],
      kv_hit:   [{ key: `${defaultKey}_kv_hit`, color: COLORS.cyan, label: "KV Hit Rate %" }],
      queue:    [
        { key: `${defaultKey}_running`, color: COLORS.green, label: "Running" },
        { key: `${defaultKey}_waiting`, color: COLORS.red, label: "Waiting" },
      ],
      swapped: [{ key: `${defaultKey}_swapped`, color: COLORS.accent, label: "Swapped" }],
      tpot: [
        { key: `${defaultKey}_tpot_mean`, color: COLORS.cyan, label: "TPOT mean" },
        { key: `${defaultKey}_tpot_p99`, color: COLORS.accent, label: "TPOT p99" },
      ],
      queue_time: [
        { key: `${defaultKey}_queue_time_mean`, color: COLORS.green, label: "Queue mean" },
        { key: `${defaultKey}_queue_time_p99`, color: COLORS.accent, label: "Queue p99" },
      ],
      rps:      [{ key: `${defaultKey}_rps`, color: COLORS.green, label: "RPS" }],
      gpu_util: [{ key: `${defaultKey}_gpu_util`, color: COLORS.red, label: "GPU Util %" }],
      gpu_mem:  [{ key: `${defaultKey}_gpu_mem_used`, color: COLORS.purple, label: "GPU Mem Used (GB)" }],
    };
  }

  return {
    tps:      makeMultiLines('tps'),
    latency:  makeMultiLines('lat_p99'),
    ttft:     makeMultiLines('ttft'),
    kv:       makeMultiLines('kv'),
    kv_hit:   makeMultiLines('kv_hit'),
    queue:    makeMultiLines('running'),
    swapped:  makeMultiLines('swapped'),
    rps:      makeMultiLines('rps'),
    gpu_util: makeMultiLines('gpu_util'),
    gpu_mem:  makeMultiLines('gpu_mem_used'),
    tpot:       makeMultiLines('tpot_mean'),
    queue_time: makeMultiLines('queue_time_mean'),
  };
}

interface MonitorChartGridProps {
  visibleCharts: string[];
  hiddenCharts: string[];
  chartData: Record<string, unknown>[];
  chartLinesMap: ChartLinesMap;
  onHideChart: (id: string) => void;
  onShowChart: (id: string) => void;
  getSlaThreshold: (id: string) => number | undefined;
  timeRange: 'Live' | '1h' | '6h' | '24h' | '7d';
}

function MonitorChartGrid({
  visibleCharts,
  hiddenCharts,
  chartData,
  chartLinesMap,
  onHideChart,
  onShowChart,
  getSlaThreshold,
  timeRange,
}: MonitorChartGridProps) {
  return (
    <>
      <div className="grid-2 gap-1">
        {visibleCharts.map(id => {
          const def = CHART_DEFINITIONS.find(c => c.id === id);
          if (!def) return null;
          return (
            <section key={id} aria-label={def.title}>
              <Chart
                data={chartData}
                title={def.title}
                lines={chartLinesMap[id] || []}
                onHide={() => onHideChart(id)}
                threshold={getSlaThreshold(id)}
                timeRange={timeRange}
              />
            </section>
          );
        })}
      </div>
      {hiddenCharts.length > 0 && (
        <div className="hidden-charts-bar">
          <span className="hidden-charts-bar-label">Hidden charts:</span>
          {hiddenCharts.map(id => {
            const def = CHART_DEFINITIONS.find(c => c.id === id);
            if (!def) return null;
            return (
              <button
                type="button"
                key={id}
                className="hidden-chart-tag"
                onClick={() => onShowChart(id)}
                title="Click to restore"
              >
                {def.title}
              </button>
            );
          })}
        </div>
      )}
    </>
  );
}

export default MonitorChartGrid;
