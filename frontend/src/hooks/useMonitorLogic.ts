import { useState, useEffect, useMemo, useCallback, useRef } from "react";
import { authFetch } from '../utils/authFetch';
import { mockMetrics, mockHistory } from "../mockData";
import { useMockData } from "../contexts/MockDataContext";
import { useClusterConfig } from "../contexts/ClusterConfigContext";
import { API, METRIC_KEYS, CHART_LABELS, MONITOR_POLL_INTERVAL_MS, MONITOR_HISTORY_SLICE, MONITOR_LIVE_CUTOFF_SECS } from "../constants";
import { useThemeColors } from "../contexts/ThemeContext";
import { buildGapFill } from "../utils/gapFill";
import { showSlaViolation } from "../components/Toast";
import {
  buildChartLinesMap, loadChartConfig, saveChartConfig,
  type ChartConfig,
} from "../components/MonitorChartGrid";
import type { SlaProfile, TargetResult, TargetState } from "../types";
import { getTargetKey } from "../utils/targetKey";

export function useMonitorLogic(isActive: boolean) {
  const { isMockEnabled } = useMockData();
  const { targets, crType } = useClusterConfig();
  const { COLORS } = useThemeColors();

  const [targetStates, setTargetStates] = useState<Record<string, TargetState>>({});
  const [error, setError] = useState<string | null>(null);
  const [chartState, setChartState] = useState<ChartConfig>(() => loadChartConfig());
  const [slaProfiles, setSlaProfiles] = useState<SlaProfile[]>([]);
  const [selectedSlaProfileId, setSelectedSlaProfileId] = useState<number | null>(null);
  const [selectedRange, setSelectedRange] = useState<'Live' | '1h' | '6h' | '24h' | '7d'>('Live');
  const [metricsSource, setMetricsSource] = useState<'direct' | 'thanos'>(
    () => (localStorage.getItem('monitor_metrics_source') as 'direct' | 'thanos') || 'direct'
  );
  const [initialized, setInitialized] = useState(false);
  const timeRangePointsRef = useRef(150);
  const selectedRangeRef = useRef('Live');
  const lastViolationTime = useRef<Record<string, number>>({});

  const chartOrder = chartState.order;
  const hiddenCharts = chartState.hidden;

  const selectedSlaProfile = useMemo(() =>
    slaProfiles.find(p => p.id === selectedSlaProfileId),
    [slaProfiles, selectedSlaProfileId]
  );

  const selectedSlaProfileRef = useRef<SlaProfile | undefined>(undefined);
  useEffect(() => {
    selectedSlaProfileRef.current = selectedSlaProfile;
  }, [selectedSlaProfile]);

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
        setError("Failed to load SLA profiles");
      }
    };
    fetchSlaProfiles();
  }, []);

  useEffect(() => {
    localStorage.setItem('monitor_metrics_source', metricsSource);
  }, [metricsSource]);

  const fetchAllTargets = useCallback(async (signal?: AbortSignal) => {
    if (isMockEnabled) {
      const newStates: Record<string, TargetState> = {};
      targets.forEach(target => {
        const key = getTargetKey(target);
        newStates[key] = {
          metrics: { ...mockMetrics() },
          history: buildGapFill(mockHistory().map(h => ({ ...h, t: h.t })), ['ttft', 'lat_p99']).slice(-MONITOR_HISTORY_SLICE),
          status: 'ready',
          error: null,
        };
      });
      setTargetStates(newStates);
      return;
    }

    try {
      const batchTargets = targets.map(t => ({
        namespace: t.namespace,
        inferenceService: t.inferenceService,
        cr_type: t.crType || crType,
      }));

      const res = await authFetch(`${API}/metrics/batch`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(
          selectedRangeRef.current === 'Live'
            ? { targets: batchTargets, history_points: timeRangePointsRef.current, metrics_source: metricsSource }
            : { targets: batchTargets, time_range: selectedRangeRef.current }
        ),
        signal,
      });

      if (signal?.aborted) return;
      if (res.status === 401 || res.status === 403) throw new Error(`Auth error: ${res.status}`);
      if (!res.ok) throw new Error(`Batch HTTP ${res.status}`);

      let batchData: { results?: Record<string, TargetResult> };
      try {
        batchData = await res.json();
      } catch {
        throw new Error('Failed to parse metrics response as JSON');
      }

      if (!batchData.results) throw new Error('Invalid metrics response: missing results');

      const newStates: Record<string, TargetState> = {};
      const now = Date.now();
      const DEBOUNCE_MS = 30_000;

      const checkViolation = (
        metric: string, value: number | null | undefined,
        threshold: number | null | undefined,
        violationFn: (v: number, t: number) => boolean,
      ) => {
        if (value === null || value === undefined || threshold === null || threshold === undefined) return;
        if (!violationFn(value, threshold)) return;
        const last = lastViolationTime.current[metric] || 0;
        if (now - last < DEBOUNCE_MS) return;
        lastViolationTime.current[metric] = now;
        showSlaViolation(metric, value, threshold);
      };

      Object.entries(batchData.results).forEach(([key, result]) => {
        if (result.status === 'error') {
          newStates[key] = {
            status: 'error',
            error: result.error,
            data: null,
            history: [],
            crExists: (result as any).crExists ?? null,
          };
          return;
        }
        if (selectedSlaProfileRef.current && result.data) {
          const { thresholds } = selectedSlaProfileRef.current;
          const { data } = result;
          checkViolation(`${key} ${CHART_LABELS.e2eLatency.violation}`, data.latency_p99, thresholds.p95_latency_max_ms, (v, t) => v > t);
        }
        const mapped = (result.history || []).map((m) => ({
          t: m.timestamp,
          tps: m.tps, ttft: m.ttft_mean, lat_p99: m.latency_p99,
          kv: m.kv_cache, running: m.running, waiting: m.waiting,
          rps: m.rps, ttft_p99: m.ttft_p99, lat_mean: m.latency_mean,
          kv_hit: m.kv_hit_rate, gpu_util: m.gpu_util,
          gpu_mem_used: m.gpu_mem_used, gpu_mem_total: m.gpu_mem_total,
          tpot_mean: m.tpot_mean, tpot_p99: m.tpot_p99,
          queue_time_mean: m.queue_time_mean, queue_time_p99: m.queue_time_p99,
        }));
        const history = buildGapFill(mapped, ['ttft', 'lat_p99', 'ttft_p99', 'lat_mean', 'tpot_mean', 'tpot_p99', 'queue_time_mean', 'queue_time_p99']);
        newStates[key] = {
          data: result.data || null,
          history,
          status: result.status || 'ready',
          hasMonitoringLabel: result.hasMonitoringLabel,
          crExists: (result as any).crExists ?? null,
          error: null,
        };
      });

      setTargetStates(prev => ({ ...prev, ...newStates }));
      setError(null);
    } catch (err) {
      if (err instanceof Error && err.name === 'AbortError') return;
      setError(`Query failed: ${(err as Error).message}`);
    }
  }, [targets, isMockEnabled, crType, metricsSource]);

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
        const key = getTargetKey(t);
        initialStates[key] = prev[key] || { status: 'collecting' };
      });
      return { ...prev, ...initialStates };
    });
    const controller = new AbortController();
    (async () => {
      await fetchAllTargets(controller.signal);
      if (!controller.signal.aborted) setInitialized(true);
    })();
    const id = setInterval(() => fetchAllTargets(controller.signal), MONITOR_POLL_INTERVAL_MS);
    return () => { controller.abort(); clearInterval(id); };
  }, [isActive, targets, fetchAllTargets]);

  const mergedHistory = useMemo(() => {
    const timeMap: Record<string, Record<string, unknown>> = {};
    Object.entries(targetStates).forEach(([targetKey, state]) => {
      if (!state.history) return;
      state.history.forEach(h => {
        const t = String(h.t);
        if (!timeMap[t]) timeMap[t] = { t };
        METRIC_KEYS.forEach(mk => { timeMap[t][`${targetKey}_${mk}`] = h[mk]; });
      });
    });
    const sorted = Object.values(timeMap).sort((a, b) => Number(a.t) - Number(b.t));
    if (selectedRange === 'Live') {
      const cutoff = Date.now() / 1000 - MONITOR_LIVE_CUTOFF_SECS;
      return sorted.filter(p => Number(p.t) >= cutoff);
    }
    return sorted;
  }, [targetStates, selectedRange]);

  const targetStatuses = useMemo(() => {
    const s: Record<string, { status: string; hasMonitoringLabel: boolean }> = {};
    Object.entries(targetStates).forEach(([key, state]) => {
      s[key] = { status: state.status || 'collecting', hasMonitoringLabel: state.hasMonitoringLabel !== false };
    });
    return s;
  }, [targetStates]);

  const defaultKey = useMemo(() => {
    const dt = targets[0];
    return dt ? getTargetKey(dt) : null;
  }, [targets]);

  const chartLinesMap = useMemo(
    () => buildChartLinesMap(targets, defaultKey, COLORS),
    [targets, defaultKey, COLORS],
  );

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
    if (id === 'e2e_latency') return thresholds.p95_latency_max_ms || undefined;
    return undefined;
  };

  return {
    initialized, error, targets, slaProfiles, selectedSlaProfileId, setSelectedSlaProfileId,
    chartOrder, hiddenCharts, mergedHistory, targetStatuses, targetStates, chartLinesMap,
    hideChart, showChart, getSlaThreshold,
    selectedRange, setSelectedRange, timeRangePointsRef, selectedRangeRef,
    metricsSource, setMetricsSource,
  };
}
