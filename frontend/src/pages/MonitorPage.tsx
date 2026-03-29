import { useState, useEffect, useMemo, useCallback, useRef } from "react";
import { authFetch } from '../utils/authFetch';
import { mockMetrics, mockHistory } from "../mockData";
import { useMockData } from "../contexts/MockDataContext";
import { useClusterConfig } from "../contexts/ClusterConfigContext";
import { API, METRIC_KEYS } from "../constants";
import { useThemeColors } from "../contexts/ThemeContext";
import ErrorAlert from "../components/ErrorAlert";
import LoadingSpinner from "../components/LoadingSpinner";
import MultiTargetSelector from "../components/MultiTargetSelector";
import { buildGapFill } from "../utils/gapFill";
import { showSlaViolation } from "../components/Toast";
import MonitorChartGrid, {
  buildChartLinesMap, loadChartConfig, saveChartConfig,
  type ChartConfig,
} from "../components/MonitorChartGrid";
import type { SlaThresholds, SlaProfile, HistoryPoint, TargetResultData, TargetResult, TargetState } from "../types";

// Re-export for backwards compatibility (tests import from this module)
export { buildChartLinesMap } from "../components/MonitorChartGrid";

const TIME_RANGES = [
  { label: 'Live' as const, points: 60 },
  { label: '1h' as const,  points: 360, timeRange: '1h' },
  { label: '6h' as const,  points: 720, timeRange: '6h' },
  { label: '24h' as const, points: 1000, timeRange: '24h' },
  { label: '7d' as const,  points: 1400, timeRange: '7d' },
];

function MonitorPage({ isActive }: { isActive: boolean }) {
  const { isMockEnabled } = useMockData();
  const { targets, crType } = useClusterConfig();
  const { COLORS } = useThemeColors();
  const [targetStates, setTargetStates] = useState<Record<string, TargetState>>({});
  const [error, setError] = useState<string | null>(null);
  const [chartState, setChartState] = useState<ChartConfig>(() => loadChartConfig());
  const [slaProfiles, setSlaProfiles] = useState<SlaProfile[]>([]);
  const [selectedSlaProfileId, setSelectedSlaProfileId] = useState<number | null>(null);
  const [timeRangePoints, setTimeRangePoints] = useState(60);
  const [selectedRange, setSelectedRange] = useState<'Live' | '1h' | '6h' | '24h' | '7d'>('Live');
  const [initialized, setInitialized] = useState(false);
  const timeRangePointsRef = useRef(60);
  const selectedRangeRef = useRef('Live');
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
           selectedRangeRef.current === 'Live'
             ? { targets: batchTargets, history_points: timeRangePointsRef.current }
             : { targets: batchTargets, time_range: selectedRangeRef.current }
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
          t: m.timestamp,
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
      setInitialized(true);
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
    
    (async () => {
      await fetchAllTargets(controller.signal);
      if (!controller.signal.aborted) {
        setInitialized(true);
      }
    })();
    
    const id = setInterval(() => fetchAllTargets(controller.signal), 3000);
    return () => { controller.abort(); clearInterval(id); };
  }, [isActive, targets, fetchAllTargets]);

  const mergedHistory = useMemo(() => {
    const timeMap: Record<string, Record<string, unknown>> = {};
     Object.entries(targetStates).forEach(([targetKey, state]) => {
       if (!state.history) return;
       state.history.forEach(h => {
         const t = String(h.t);
         if (!timeMap[t]) timeMap[t] = { t };
         METRIC_KEYS.forEach(mk => {
           timeMap[t][`${targetKey}_${mk}`] = h[mk];
         });
       });
     });
    const sorted = Object.values(timeMap).sort((a, b) => Number(a.t) - Number(b.t));
    if (selectedRange === 'Live') {
      const cutoff = Date.now() / 1000 - 300; // keep last 5 minutes (timestamps in seconds)
      return sorted.filter(p => Number(p.t) >= cutoff);
    }
    return sorted;
  }, [targetStates, selectedRange]);

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
              type="button"
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
      {!initialized && targets.length > 0 ? (
        <LoadingSpinner />
      ) : (
        <>
           <MultiTargetSelector
             targetStatuses={targetStatuses}
             targetStates={targetStates}
           />
           <ErrorAlert message={error} className="error-alert--m08" />
           <MonitorChartGrid
            visibleCharts={chartOrder.filter(id => !hiddenCharts.includes(id))}
            hiddenCharts={hiddenCharts}
            chartData={mergedHistory}
            chartLinesMap={chartLinesMap}
            onHideChart={hideChart}
            onShowChart={showChart}
            getSlaThreshold={getSlaThreshold}
            timeRange={selectedRange}
          />
        </>
      )}
    </div>
  );
}
export default MonitorPage;

