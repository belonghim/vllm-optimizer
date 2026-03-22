import { useState, useEffect, useMemo } from "react";
import { mockMetrics, mockHistory } from "../mockData";
import { useMockData } from "../contexts/MockDataContext";
import { useClusterConfig } from "../contexts/ClusterConfigContext";
import { API, COLORS } from "../constants";
import Chart from "../components/Chart";
import ErrorAlert from "../components/ErrorAlert";
import MultiTargetSelector from "../components/MultiTargetSelector";
import { buildGapFill } from "../utils/gapFill";

const fmtTime = (ts) => new Date(ts * 1000).toLocaleTimeString("ko-KR", { hour12: false });

const TARGET_COLORS = [COLORS.accent, COLORS.cyan, COLORS.green, COLORS.red, COLORS.purple];

const CHART_DEFINITIONS = [
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

function loadChartConfig() {
  try {
    const raw = localStorage.getItem(LS_KEY);
    if (!raw) return { order: DEFAULT_ORDER, hidden: [] };
    const parsed = JSON.parse(raw);
    const validIds = new Set(DEFAULT_ORDER);
    const order = Array.isArray(parsed.order)
      ? parsed.order.filter(id => validIds.has(id))
      : DEFAULT_ORDER;
    const hidden = Array.isArray(parsed.hidden)
      ? parsed.hidden.filter(id => validIds.has(id))
      : [];
    const inOrder = new Set(order);
    DEFAULT_ORDER.forEach(id => { if (!inOrder.has(id)) order.push(id); });
    return { order, hidden };
  } catch {
    return { order: DEFAULT_ORDER, hidden: [] };
  }
}

function saveChartConfig(order, hidden) {
  try {
    localStorage.setItem(LS_KEY, JSON.stringify({ order, hidden }));
  } catch {
    // ignore storage errors
  }
}

function MonitorPage() {
  const { isMockEnabled } = useMockData();
  const { targets } = useClusterConfig();
  const [targetStates, setTargetStates] = useState({});
  const [error, setError] = useState(null);
  const [chartOrder, setChartOrder] = useState(() => loadChartConfig().order);
  const [hiddenCharts, setHiddenCharts] = useState(() => loadChartConfig().hidden);

  useEffect(() => {
    if (targets.length === 0) {
      setTargetStates({});
      return;
    }

    const fetchAllTargets = async () => {
      if (isMockEnabled) {
        const newStates = {};
        targets.forEach(target => {
          const key = `${target.namespace}/${target.inferenceService}`;
          newStates[key] = {
            metrics: mockMetrics(),
            history: buildGapFill(mockHistory().map(h => ({ ...h, t: h.t })), ['ttft', 'lat_p99']),
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
          inferenceService: t.inferenceService
        }));

        const res = await fetch(`${API}/metrics/batch`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ targets: batchTargets })
        });

        if (!res.ok) throw new Error(`Batch HTTP ${res.status}`);
        const batchData = await res.json();

        const newStates = {};
        Object.entries(batchData.results).forEach(([key, result]) => {
          if (result.status === 'error') {
            newStates[key] = { status: 'error', error: result.error, data: null, history: [] };
            return;
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
        setError(`조회 실패: ${err.message}`);
      }
    };

    const initialStates = {};
    targets.forEach(t => {
      const key = `${t.namespace}/${t.inferenceService}`;
      initialStates[key] = targetStates[key] || { status: 'collecting' };
    });
    setTargetStates(prev => ({ ...prev, ...initialStates }));

    fetchAllTargets();
    const id = setInterval(fetchAllTargets, 2000);
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
        timeMap[h.t][`${targetKey}_rps`] = h.rps;
        timeMap[h.t][`${targetKey}_ttft_p99`] = h.ttft_p99;
        timeMap[h.t][`${targetKey}_lat_mean`] = h.lat_mean;
        timeMap[h.t][`${targetKey}_kv_hit`] = h.kv_hit;
        timeMap[h.t][`${targetKey}_gpu_util`] = h.gpu_util;
        timeMap[h.t][`${targetKey}_gpu_mem_used`] = h.gpu_mem_used;
        timeMap[h.t][`${targetKey}_gpu_mem_total`] = h.gpu_mem_total;
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
        { key: `${defaultKey}_lat_p99_fill`, color: COLORS.red, label: "P99 (idle)", dash: true },
        { key: `${defaultKey}_lat_p99`, color: COLORS.red, label: "Latency P99" },
        { key: `${defaultKey}_lat_mean`, color: COLORS.accent, label: "Latency mean" },
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

  const ttftLines = useMemo(() => {
    if (targets.length === 1) {
      return [
        { key: `${defaultKey}_ttft_fill`, color: COLORS.cyan, label: "TTFT (idle)", dash: true },
        { key: `${defaultKey}_ttft`, color: COLORS.cyan, label: "TTFT mean" },
        { key: `${defaultKey}_ttft_p99`, color: COLORS.accent, label: "TTFT p99" },
      ];
    }
    return targets.map((t, i) => ({
      key: `${t.namespace}/${t.inferenceService}_ttft`,
      label: t.inferenceService,
      color: TARGET_COLORS[i % TARGET_COLORS.length]
    }));
  }, [targets, defaultKey]);

  const rpsLines = useMemo(() => {
    if (targets.length === 1) {
      return [{ key: `${defaultKey}_rps`, color: COLORS.green, label: "RPS" }];
    }
    return targets.map((t, i) => ({
      key: `${t.namespace}/${t.inferenceService}_rps`,
      label: t.inferenceService,
      color: TARGET_COLORS[i % TARGET_COLORS.length]
    }));
  }, [targets, defaultKey]);

  const kvHitLines = useMemo(() => {
    if (targets.length === 1) {
      return [{ key: `${defaultKey}_kv_hit`, color: COLORS.cyan, label: "KV Hit Rate %" }];
    }
    return targets.map((t, i) => ({
      key: `${t.namespace}/${t.inferenceService}_kv_hit`,
      label: t.inferenceService,
      color: TARGET_COLORS[i % TARGET_COLORS.length]
    }));
  }, [targets, defaultKey]);

  const gpuUtilLines = useMemo(() => {
    if (targets.length === 1) {
      return [{ key: `${defaultKey}_gpu_util`, color: COLORS.red, label: "GPU Util %" }];
    }
    return targets.map((t, i) => ({
      key: `${t.namespace}/${t.inferenceService}_gpu_util`,
      label: t.inferenceService,
      color: TARGET_COLORS[i % TARGET_COLORS.length]
    }));
  }, [targets, defaultKey]);

  const gpuMemLines = useMemo(() => {
    if (targets.length === 1) {
      return [{ key: `${defaultKey}_gpu_mem_used`, color: COLORS.purple, label: "GPU Mem Used (GB)" }];
    }
    return targets.map((t, i) => ({
      key: `${t.namespace}/${t.inferenceService}_gpu_mem_used`,
      label: t.inferenceService,
      color: TARGET_COLORS[i % TARGET_COLORS.length]
    }));
  }, [targets, defaultKey]);

  const chartLinesMap = {
    tps:      tpsLines,
    latency:  latencyLines,
    ttft:     ttftLines,
    kv:       kvLines,
    kv_hit:   kvHitLines,
    queue:    queueLines,
    rps:      rpsLines,
    gpu_util: gpuUtilLines,
    gpu_mem:  gpuMemLines,
  };

  const hideChart = (id) => {
    const newHidden = [...hiddenCharts, id];
    setHiddenCharts(newHidden);
    saveChartConfig(chartOrder, newHidden);
  };

  const showChart = (id) => {
    const newOrder = [...chartOrder.filter(x => x !== id), id];
    const newHidden = hiddenCharts.filter(x => x !== id);
    setChartOrder(newOrder);
    setHiddenCharts(newHidden);
    saveChartConfig(newOrder, newHidden);
  };

  return (
    <div className="flex-col-1">
      <MultiTargetSelector targetStatuses={targetStatuses} targetStates={targetStates} />
      <ErrorAlert message={error} className="error-alert--m08" />
      
      {chartOrder
        .filter(id => !hiddenCharts.includes(id))
        .map(id => {
          const def = CHART_DEFINITIONS.find(c => c.id === id);
          if (!def) return null;
          return (
            <div key={id} className="grid-2 gap-1" aria-label={def.title}>
              <Chart
                data={mergedHistory}
                title={def.title}
                lines={chartLinesMap[id] || []}
                onHide={() => hideChart(id)}
              />
            </div>
          );
        })
      }
      {hiddenCharts.length > 0 && (
        <div className="hidden-charts-bar">
          <span className="hidden-charts-bar-label">숨긴 차트:</span>
          {hiddenCharts.map(id => {
            const def = CHART_DEFINITIONS.find(c => c.id === id);
            if (!def) return null;
            return (
              <button
                key={id}
                className="hidden-chart-tag"
                onClick={() => showChart(id)}
                title="클릭하여 복원"
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
