import { useState, useEffect, useMemo, useCallback, useRef } from "react";
import { authFetch } from '../utils/authFetch';
import { mockMetrics, mockHistory } from "../mockData";
import { useMockData } from "../contexts/MockDataContext";
import { useClusterConfig } from "../contexts/ClusterConfigContext";
import { API, METRIC_KEYS } from "../constants";
import { useThemeColors } from "../contexts/ThemeContext";
import ErrorAlert from "../components/ErrorAlert";
import MultiTargetSelector from "../components/MultiTargetSelector";
import { buildGapFill } from "../utils/gapFill";
import { showSlaViolation } from "../components/Toast";
import MonitorChartGrid, {
  buildChartLinesMap, loadChartConfig, saveChartConfig,
  type ChartConfig,
} from "../components/MonitorChartGrid";
import MonitorMetricCards from "../components/MonitorMetricCards";

// Re-export for backwards compatibility (tests import from this module)
export { buildChartLinesMap } from "../components/MonitorChartGrid";

interface SlaThresholds {
  availability_min: number | null;
  p95_latency_max_ms: number | null;
  error_rate_max_pct: number | null;
  min_tps: number | null;
}

interface SlaProfile {
  id: number;
  name: string;
  thresholds: SlaThresholds;
}

interface ChartLine {
  key: string;
  color: string;
  label: string;
  dash?: boolean;
}

type ChartLinesMap = Record<string, ChartLine[]>;

const fmtTime = (ts: number) => new Date(ts * 1000).toLocaleTimeString("ko-KR", { hour12: false });

export function buildChartLinesMap(targets: ClusterTarget[], defaultKey: string | null, COLORS: typeof DARK_COLORS = DARK_COLORS): ChartLinesMap {
  const makeMultiLines = (metricKey: string) =>
    targets.map((t, i) => ({
      key: `${t.namespace}/${t.inferenceService}_${metricKey}`,
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
    rps:      makeMultiLines('rps'),
    gpu_util: makeMultiLines('gpu_util'),
    gpu_mem:  makeMultiLines('gpu_mem_used'),
  };
}

interface ChartDefinition {
  id: string;
  title: string;
}

const CHART_DEFINITIONS: ChartDefinition[] = [
  { id: 'tps',      title: 'Throughput (TPS)' },
  { id: 'latency',  title: 'Latency (ms)' },
  { id: 'ttft',     title: 'TTFT (ms)' },
  { id: 'kv',       title: 'KV Cache Usage (%)' },
  { id: 'kv_hit',   title: 'KV Cache Hit Rate (%)' },
  { id: 'queue',    title: 'Request Queue' },
  { id: 'rps',      title: 'RPS (Requests/sec)' },
  { id: 'gpu_util', title: 'GPU Utilization (%)' },
  { id: 'gpu_mem',  title: 'GPU Memory (GB)' },
];

const LS_KEY = 'vllm-optimizer-chart-config';
const DEFAULT_ORDER = CHART_DEFINITIONS.map(c => c.id);

interface ChartConfig {
  order: string[];
  hidden: string[];
}

function loadChartConfig(): ChartConfig {
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

function saveChartConfig(order: string[], hidden: string[]) {
  try {
    localStorage.setItem(LS_KEY, JSON.stringify({ order, hidden }));
  } catch (e) {
    console.error('Failed to save chart configuration to localStorage', e);
  }
}

interface HistoryPoint {
  timestamp: number;
  tps?: number;
  ttft_mean?: number;
  latency_p99?: number;
  kv_cache?: number;
  running?: number;
  waiting?: number;
  rps?: number;
  ttft_p99?: number;
  latency_mean?: number;
  kv_hit_rate?: number;
  gpu_util?: number;
  gpu_mem_used?: number;
  gpu_mem_total?: number;
}

interface TargetResultData {
  tps?: number | null;
  latency_p99?: number | null;
  latency_mean?: number | null;
  ttft_mean?: number | null;
  ttft_p99?: number | null;
  kv_cache?: number | null;
  kv_hit_rate?: number | null;
  running?: number | null;
  waiting?: number | null;
  rps?: number | null;
  gpu_util?: number | null;
  gpu_mem_used?: number | null;
  gpu_mem_total?: number | null;
  error_rate?: number | null;
  availability?: number | null;
}

interface TargetResult {
  status: string;
  error?: string;
  data?: TargetResultData | null;
  history?: HistoryPoint[];
  hasMonitoringLabel?: boolean;
}

interface TargetState {
  status?: string;
  data?: TargetResultData | null;
  metrics?: TargetResultData | null;
  history?: Record<string, unknown>[];
  hasMonitoringLabel?: boolean;
  error?: string | null;
}

interface MonitorPageProps {
  isActive: boolean;
}

const TIME_RANGES = [
  { label: '1h',  points: 360 },
  { label: '6h',  points: 720 },
  { label: '24h', points: 1000 },
  { label: '7d',  points: 1400 },
];

function MonitorPage({ isActive }: MonitorPageProps) {
  const { isMockEnabled } = useMockData();
  const { targets, crType } = useClusterConfig();
  const { COLORS } = useThemeColors();
  const [targetStates, setTargetStates] = useState<Record<string, TargetState>>({});
  const [error, setError] = useState<string | null>(null);
  const [chartState, setChartState] = useState<ChartConfig>(() => loadChartConfig());
  const [slaProfiles, setSlaProfiles] = useState<SlaProfile[]>([]);
  const [selectedSlaProfileId, setSelectedSlaProfileId] = useState<number | null>(null);
  const [timeRangePoints, setTimeRangePoints] = useState(60);
  const [selectedRange, setSelectedRange] = useState('1h');
  const timeRangePointsRef = useRef(60);
  const selectedRangeRef = useRef('1h');
  const lastViolationTime = useRef<Record<string, number>>({});

  const chartOrder = chartState.order;
  const hiddenCharts = chartState.hidden;

  const selectedSlaProfile = useMemo(() => 
    slaProfiles.find(p => p.id === selectedSlaProfileId),
    [slaProfiles, selectedSlaProfileId]
  );

  useEffect(() => {
    const fetchSlaProfiles = async () => {
      try {
        const res = await authFetch(`${API}/sla/profiles`);
        if (res.ok) {
          const data = await res.json();
          setSlaProfiles(data);
        }
      } catch (err) {
        console.error("Failed to load SLA profiles", err);
      }
    };
    fetchSlaProfiles();
  }, []);

  const fetchAllTargets = useCallback(async (signal?: AbortSignal) => {
    if (isMockEnabled) {
      const newStates: Record<string, TargetState> = {};
      targets.forEach(target => {
        const key = `${target.namespace}/${target.inferenceService}`;
        newStates[key] = {
          metrics: { ...mockMetrics() },
          history: buildGapFill(mockHistory().map(h => ({ ...h, t: h.t })), ['ttft', 'lat_p99']).slice(-450),
          status: 'ready',
          error: null
        };
      });
      setTargetStates(newStates);
      return;
    }

    try {
      const batchTargets = targets.map(t => ({
        namespace: t.namespace,
        inferenceService: t.inferenceService,
        cr_type: t.crType || crType
      }));

      const res = await authFetch(`${API}/metrics/batch`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(
          ['6h', '24h', '7d'].includes(selectedRangeRef.current)
            ? { targets: batchTargets, time_range: selectedRangeRef.current }
            : { targets: batchTargets, history_points: timeRangePointsRef.current }
        ),
        signal,
      });

      if (signal?.aborted) return;
      if (!res.ok) throw new Error(`Batch HTTP ${res.status}`);
      const batchData = await res.json();

      const newStates: Record<string, TargetState> = {};
      const now = Date.now();
      const DEBOUNCE_MS = 30_000;

      const checkViolation = (metric: string, value: number | null | undefined, threshold: number | null | undefined, violationFn: (v: number, t: number) => boolean) => {
        if (value === null || value === undefined || threshold === null || threshold === undefined) return;
        if (!violationFn(value, threshold)) return;
        
        const last = lastViolationTime.current[metric] || 0;
        if (now - last < DEBOUNCE_MS) return;
        
        lastViolationTime.current[metric] = now;
        showSlaViolation(metric, value, threshold);
      };

      Object.entries(batchData.results as Record<string, TargetResult>).forEach(([key, result]) => {
        if (result.status === 'error') {
          newStates[key] = { status: 'error', error: result.error, data: null, history: [] };
          return;
        }

        if (selectedSlaProfile && result.data) {
          const { thresholds } = selectedSlaProfile;
          const { data } = result;
          checkViolation(`${key} TPS`, data.tps, thresholds.min_tps, (v, t) => v < t);
          checkViolation(`${key} Latency`, data.latency_p99, thresholds.p95_latency_max_ms, (v, t) => v > t);
        }

        const mapped = (result.history || []).map((m) => ({
          t: fmtTime(m.timestamp),
          tps: m.tps, ttft: m.ttft_mean, lat_p99: m.latency_p99,
          kv: m.kv_cache, running: m.running, waiting: m.waiting,
          rps: m.rps, ttft_p99: m.ttft_p99, lat_mean: m.latency_mean,
          kv_hit: m.kv_hit_rate, gpu_util: m.gpu_util,
          gpu_mem_used: m.gpu_mem_used, gpu_mem_total: m.gpu_mem_total,
        }));
        const history = buildGapFill(mapped, ['ttft', 'lat_p99', 'ttft_p99', 'lat_mean']);

        newStates[key] = {
          data: result.data || null,
          history,
          status: result.status || 'ready',
          hasMonitoringLabel: result.hasMonitoringLabel,
          error: null
        };
      });

      setTargetStates(prev => ({ ...prev, ...newStates }));
      setError(null);
    } catch (err) {
      if (err instanceof Error && err.name === 'AbortError') return;
      setError(`Query failed: ${(err as Error).message}`);
    }
  }, [targets, isMockEnabled, crType, selectedSlaProfile]);

  useEffect(() => {
    if (!isActive) return;
    if (targets.length === 0) {
      setTargetStates({});
      return;
    }

    setTargetStates(prev => {
      const initialStates: Record<string, TargetState> = {};
      targets.forEach(t => {
        const key = `${t.namespace}/${t.inferenceService}`;
        initialStates[key] = prev[key] || { status: 'collecting' };
      });
      return { ...prev, ...initialStates };
    });

    const controller = new AbortController();
    fetchAllTargets(controller.signal);
    const id = setInterval(() => fetchAllTargets(controller.signal), 3000);
    return () => { controller.abort(); clearInterval(id); };
  }, [isActive, targets, isMockEnabled, fetchAllTargets]);

  const mergedHistory = useMemo(() => {
    const timeMap: Record<string, Record<string, unknown>> = {};
    Object.entries(targetStates).forEach(([targetKey, state]) => {
      if (!state.history) return;
      state.history.forEach(h => {
        const t = h.t as string;
        if (!timeMap[t]) timeMap[t] = { t };
        METRIC_KEYS.forEach(mk => {
          timeMap[t][`${targetKey}_${mk}`] = h[mk];
        });
      });
    });
    return Object.values(timeMap).sort((a, b) => (a.t as string).localeCompare(b.t as string));
  }, [targetStates]);

  // hasMonitoringLabel: null/undefined = not yet checked (no warning), false = no label (show warning), true = has label (no warning)
  // using !== false so null/undefined does not show a warning
  const targetStatuses = useMemo(() => {
    const s: Record<string, { status: string; hasMonitoringLabel: boolean }> = {};
    Object.entries(targetStates).forEach(([key, state]) => {
      s[key] = {
        status: state.status || 'collecting',
        hasMonitoringLabel: state.hasMonitoringLabel !== false
      };
    });
    return s;
  }, [targetStates]);

  const defaultKey = useMemo(() => {
    const dt = targets.find(t => t.isDefault) || targets[0];
    return dt ? `${dt.namespace}/${dt.inferenceService}` : null;
  }, [targets]);

  const chartLinesMap = useMemo(() => buildChartLinesMap(targets, defaultKey, COLORS), [targets, defaultKey, COLORS]);

  const hideChart = useCallback((id: string) => {
    const newHidden = [...hiddenCharts, id];
    setChartState(prev => ({ ...prev, hidden: newHidden }));
    saveChartConfig(chartOrder, newHidden);
  }, [hiddenCharts, chartOrder]);

  const showChart = useCallback((id: string) => {
    const newOrder = [...chartOrder.filter(x => x !== id), id];
    const newHidden = hiddenCharts.filter(x => x !== id);
    setChartState(prev => ({ ...prev, order: newOrder, hidden: newHidden }));
    saveChartConfig(newOrder, newHidden);
  }, [chartOrder, hiddenCharts]);

  const getSlaThreshold = (id: string) => {
    if (!selectedSlaProfile) return undefined;
    const { thresholds } = selectedSlaProfile;
    if (id === 'tps') return thresholds.min_tps || undefined;
    if (id === 'latency') return thresholds.p95_latency_max_ms || undefined;
    // error_rate is not in current chart definitions, skip
    return undefined;
  };

  return (
    <div className="flex-col-1">
      <div className="panel flex-row-12" style={{ padding: '12px 20px', borderBottom: 'none', marginBottom: '-1px', justifyContent: 'space-between' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <span className="label label-no-mb">SLA PROFILE:</span>
          <select 
            className="input" 
            style={{ width: '200px', padding: '4px 8px' }}
            value={selectedSlaProfileId || ''}
            onChange={(e) => setSelectedSlaProfileId(e.target.value ? Number(e.target.value) : null)}
          >
            <option value="">None (disable warning)</option>
            {slaProfiles.map(p => (
              <option key={p.id} value={p.id}>{p.name}</option>
            ))}
          </select>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
          {TIME_RANGES.map(r => (
            <button
              key={r.label}
              data-testid="time-range-btn"
              aria-label={`Show last ${r.label}`}
              className={`btn btn-sm${selectedRange === r.label ? ' active' : ''}`}
              onClick={() => { setTimeRangePoints(r.points); setSelectedRange(r.label); timeRangePointsRef.current = r.points; selectedRangeRef.current = r.label; }}
            >
              {r.label}
            </button>
          ))}
        </div>
      </div>
      <MultiTargetSelector 
        targetStatuses={targetStatuses} 
        targetStates={targetStates} 
      />
      <ErrorAlert message={error} className="error-alert--m08" />
      
      <div className="grid-2 gap-1">
        {chartOrder
          .filter(id => !hiddenCharts.includes(id))
          .map(id => {
            const def = CHART_DEFINITIONS.find(c => c.id === id);
            if (!def) return null;
            return (
              <div key={id} aria-label={def.title}>
                <Chart
                  data={mergedHistory}
                  title={def.title}
                  lines={chartLinesMap[id] || []}
                  onHide={() => hideChart(id)}
                  threshold={getSlaThreshold(id)}
                />
              </div>
            );
          })
        }
      </div>
      {hiddenCharts.length > 0 && (
        <div className="hidden-charts-bar">
          <span className="hidden-charts-bar-label">Hidden charts:</span>
          {hiddenCharts.map(id => {
            const def = CHART_DEFINITIONS.find(c => c.id === id);
            if (!def) return null;
            return (
              <button
                key={id}
                className="hidden-chart-tag"
                onClick={() => showChart(id)}
                title="Click to restore"
              >
                {def.title}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
export default MonitorPage;

