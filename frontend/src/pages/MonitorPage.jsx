import { useState, useEffect, useRef, useMemo } from "react";
import { mockMetrics, mockHistory } from "../mockData";
import { useMockData } from "../contexts/MockDataContext";
import { useClusterConfig } from "../contexts/ClusterConfigContext";
import { API, COLORS } from "../constants";
import MetricCard from "../components/MetricCard";
import Chart from "../components/Chart";
import ErrorAlert from "../components/ErrorAlert";
import MultiTargetSelector from "../components/MultiTargetSelector";
import { buildGapFill } from "../utils/gapFill";

const fmt = (n, d = 1) => (n == null ? "—" : Number(n).toFixed(d));
const fmtTime = (ts) => new Date(ts * 1000).toLocaleTimeString("ko-KR", { hour12: false });

const TARGET_COLORS = [COLORS.accent, COLORS.cyan, COLORS.green, COLORS.red, COLORS.purple];

function MonitorPage() {
  const { isMockEnabled } = useMockData();
  const { targets } = useClusterConfig();
  const [targetStates, setTargetStates] = useState({});
  const [error, setError] = useState(null);

  useEffect(() => {
    if (targets.length === 0) {
      setTargetStates({});
      return;
    }

    const fetchTarget = async (target) => {
      const key = `${target.namespace}/${target.inferenceService}`;
      
      if (isMockEnabled) {
        setTargetStates(prev => ({
          ...prev,
          [key]: {
            metrics: mockMetrics(),
            history: buildGapFill(mockHistory().map(h => ({ ...h, t: h.t })), ['ttft', 'lat_p99']),
            status: 'ready',
            error: null
          }
        }));
        return;
      }

      try {
        const query = `namespace=${target.namespace}&is_name=${target.inferenceService}`;
        const [mRes, hRes] = await Promise.all([
          fetch(`${API}/metrics/latest?${query}`),
          fetch(`${API}/metrics/history?last_n=60&${query}`)
        ]);

        if (!mRes.ok) throw new Error(`Metrics HTTP ${mRes.status}`);
        if (!hRes.ok) throw new Error(`History HTTP ${hRes.status}`);

        const metricsData = await mRes.json();
        const historyData = await hRes.json();

        const mapped = historyData.map((m) => ({
          t: fmtTime(m.timestamp),
          tps: m.tps, ttft: m.ttft_mean, lat_p99: m.latency_p99,
          kv: m.kv_cache, running: m.running, waiting: m.waiting,
        }));
        const history = buildGapFill(mapped, ['ttft', 'lat_p99']);

        const status = metricsData.status || 'ready';
        const data = metricsData.data || null;

        setTargetStates(prev => ({
          ...prev,
          [key]: { data, history, status, hasMonitoringLabel: metricsData.hasMonitoringLabel, error: null }
        }));
        setError(null);
      } catch (err) {
        setTargetStates(prev => ({
          ...prev,
          [key]: { ...prev[key], status: 'error', error: err.message }
        }));
        setError(`조회 실패: ${err.message}`);
      }
    };

    const initialStates = {};
    targets.forEach(t => {
      const key = `${t.namespace}/${t.inferenceService}`;
      initialStates[key] = targetStates[key] || { status: 'collecting' };
    });
    setTargetStates(initialStates);

    targets.forEach(fetchTarget);
    const id = setInterval(() => { targets.forEach(fetchTarget); }, 2000);
    return () => clearInterval(id);
  }, [targets, isMockEnabled]);

  const mergedHistory = useMemo(() => {
    const timeMap = {};
    Object.entries(targetStates).forEach(([targetKey, state]) => {
      if (!state.history) return;
      state.history.forEach(h => {
        if (!timeMap[h.t]) timeMap[h.t] = { t: h.t };
        timeMap[h.t][`${targetKey}_tps`] = h.tps;
        timeMap[h.t][`${targetKey}_ttft`] = h.ttft;
        timeMap[h.t][`${targetKey}_ttft_fill`] = h.ttft_fill;
        timeMap[h.t][`${targetKey}_lat_p99`] = h.lat_p99;
        timeMap[h.t][`${targetKey}_lat_p99_fill`] = h.lat_p99_fill;
        timeMap[h.t][`${targetKey}_kv`] = h.kv;
        timeMap[h.t][`${targetKey}_running`] = h.running;
        timeMap[h.t][`${targetKey}_waiting`] = h.waiting;
      });
    });
    return Object.values(timeMap).sort((a, b) => a.t.localeCompare(b.t));
  }, [targetStates]);

  const targetStatuses = useMemo(() => {
    const s = {};
    Object.entries(targetStates).forEach(([key, state]) => {
      s[key] = {
        status: state.status,
        hasMonitoringLabel: state.hasMonitoringLabel !== false
      };
    });
    return s;
  }, [targetStates]);

  const defaultTarget = targets.find(t => t.isDefault) || targets[0];
  const defaultKey = defaultTarget ? `${defaultTarget.namespace}/${defaultTarget.inferenceService}` : null;
  const defaultState = targetStates[defaultKey] || { status: 'collecting' };
  const data = defaultState.data;

  const tpsLines = useMemo(() => {
    if (targets.length === 1) {
      return [{ key: `${defaultKey}_tps`, color: COLORS.accent, label: "TPS" }];
    }
    return targets.map((t, i) => ({
      key: `${t.namespace}/${t.inferenceService}_tps`,
      label: t.inferenceService,
      color: TARGET_COLORS[i % TARGET_COLORS.length]
    }));
  }, [targets, defaultKey]);

  const latencyLines = useMemo(() => {
    if (targets.length === 1) {
      return [
        { key: `${defaultKey}_ttft_fill`, color: COLORS.cyan, label: "TTFT (idle)", dash: true },
        { key: `${defaultKey}_lat_p99_fill`, color: COLORS.red, label: "P99 (idle)", dash: true },
        { key: `${defaultKey}_ttft`, color: COLORS.cyan, label: "TTFT" },
        { key: `${defaultKey}_lat_p99`, color: COLORS.red, label: "P99" },
      ];
    }
    return targets.map((t, i) => ({
      key: `${t.namespace}/${t.inferenceService}_lat_p99`,
      label: t.inferenceService,
      color: TARGET_COLORS[i % TARGET_COLORS.length]
    }));
  }, [targets, defaultKey]);

  const kvLines = useMemo(() => {
    if (targets.length === 1) {
      return [{ key: `${defaultKey}_kv`, color: COLORS.purple, label: "KV Cache %" }];
    }
    return targets.map((t, i) => ({
      key: `${t.namespace}/${t.inferenceService}_kv`,
      label: t.inferenceService,
      color: TARGET_COLORS[i % TARGET_COLORS.length]
    }));
  }, [targets, defaultKey]);

  const queueLines = useMemo(() => {
    if (targets.length === 1) {
      return [
        { key: `${defaultKey}_running`, color: COLORS.green, label: "Running" },
        { key: `${defaultKey}_waiting`, color: COLORS.red, label: "Waiting" },
      ];
    }
    return targets.map((t, i) => ({
      key: `${t.namespace}/${t.inferenceService}_running`,
      label: t.inferenceService,
      color: TARGET_COLORS[i % TARGET_COLORS.length]
    }));
  }, [targets, defaultKey]);

  return (
    <div className="flex-col-1">
      <MultiTargetSelector targetStatuses={targetStatuses} />
      <ErrorAlert message={error} className="error-alert--m08" />
      
      <div className="grid-4 gap-1">
        <MetricCard label="Tokens / sec" value={defaultState.status === 'collecting' ? "..." : fmt(data?.tps, 0)} unit="TPS" color="amber" />
        <MetricCard label="TTFT Mean" value={defaultState.status === 'collecting' ? "..." : fmt(data?.ttft_mean, 0)} unit="ms" color="cyan" />
        <MetricCard label="P99 Latency" value={defaultState.status === 'collecting' ? "..." : fmt(data?.latency_p99, 0)} unit="ms" color="red" />
        <MetricCard label="KV Cache" value={defaultState.status === 'collecting' ? "..." : fmt(data?.kv_cache, 1)} unit="%" color="purple" />
      </div>
      <div className="grid-4 gap-1">
        <MetricCard label="Running Reqs" value={defaultState.status === 'collecting' ? "..." : (data?.running ?? "—")} unit="requests" color="green" />
        <MetricCard label="Waiting Reqs" value={defaultState.status === 'collecting' ? "..." : (data?.waiting ?? "—")} unit="queue" color="red" />
        <MetricCard label="GPU Memory" value={defaultState.status === 'collecting' ? "..." : (data?.gpu_mem_used ? `${fmt(data.gpu_mem_used, 1)} / ${fmt(data.gpu_mem_total, 0)}` : "—")} unit="GB" color="amber" />
        <MetricCard label="Pods Ready" value={defaultState.status === 'collecting' ? "..." : (data ? `${data.pods_ready} / ${data.pods}` : "—")} unit="k8s pods" color="cyan" />
      </div>

      <div className="grid-2 gap-1">
        <Chart data={mergedHistory} title="Throughput (TPS)" lines={tpsLines} />
      </div>
      <div className="grid-2 gap-1">
        <Chart data={mergedHistory} title="Latency (ms)" lines={latencyLines} />
      </div>
      <div className="grid-2 gap-1">
        <Chart data={mergedHistory} title="KV Cache Usage (%)" lines={kvLines} />
      </div>
      <div className="grid-2 gap-1">
        <Chart data={mergedHistory} title="Request Queue" lines={queueLines} />
      </div>
    </div>
  );
}
export default MonitorPage;
