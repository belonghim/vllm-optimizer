import { useState, useEffect } from "react";
import { mockMetrics, mockHistory, mockBenchmarks, mockTrials, simulateLoadTest } from "../mockData";
import { API, COLORS, font } from "../constants";
import MetricCard from "../components/MetricCard";
import Chart from "../components/Chart";

const fmt = (n, d = 1) => (n == null ? "—" : Number(n).toFixed(d));
const fmtTime = (ts) => new Date(ts * 1000).toLocaleTimeString("ko-KR", { hour12: false });

function MonitorPage() {
  const [metrics, setMetrics] = useState(null);
  const [history, setHistory] = useState([]);
  useEffect(() => {
    const fetchLatest = async () => {
      try {
        const r = await fetch(`${API}/metrics/latest`);
        const d = await r.json();
        setMetrics(d);
      } catch { /* mock */ setMetrics(mockMetrics()); }
    };
    const fetchHistory = async () => {
      try {
        const r = await fetch(`${API}/metrics/history?last_n=60`);
        const d = await r.json();
        setHistory(d.map((m, i) => ({
          t: fmtTime(m.timestamp),
          tps: m.tps, ttft: m.ttft_mean, lat_p99: m.latency_p99,
          kv: m.kv_cache, running: m.running, waiting: m.waiting,
        })));
      } catch {
        setHistory(mockHistory());
      }
    };
    fetchLatest(); fetchHistory();
    const id = setInterval(() => { fetchLatest(); fetchHistory(); }, 2000);
    return () => clearInterval(id);
  }, []);
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 1 }}>
      {/* KPI 행 */}
      <div className="grid-4" style={{ gap: 1 }}>
        <MetricCard label="Tokens / sec" value={fmt(metrics?.tps, 0)} unit="TPS" color="amber" />
        <MetricCard label="TTFT Mean" value={fmt(metrics?.ttft_mean, 0)} unit="ms" color="cyan" />
        <MetricCard label="P99 Latency" value={fmt(metrics?.latency_p99, 0)} unit="ms" color="red" />
        <MetricCard label="KV Cache" value={fmt(metrics?.kv_cache, 1)} unit="%" color="purple" />
      </div>
      <div className="grid-4" style={{ gap: 1 }}>
        <MetricCard label="Running Reqs" value={metrics?.running ?? "—"} unit="requests" color="green" />
        <MetricCard label="Waiting Reqs" value={metrics?.waiting ?? "—"} unit="queue" color="red" />
        <MetricCard label="GPU Memory" value={metrics?.gpu_mem_used ? `${fmt(metrics.gpu_mem_used, 1)} / ${fmt(metrics.gpu_mem_total, 0)}` : "—"} unit="GB" color="amber" />
        <MetricCard label="Pods Ready" value={metrics ? `${metrics.pods_ready} / ${metrics.pods}` : "—"} unit="k8s pods" color="cyan" />
      </div>
      <div className="grid-2" style={{ gap: 1 }}>
        <Chart data={history} title="Throughput (TPS)" lines={[
          { key: "tps", color: COLORS.accent, label: "TPS" },
        ]} />
      </div>
      <div className="grid-2" style={{ gap: 1 }}>
        <Chart data={history} title="Latency (ms)" lines={[
          { key: "ttft", color: COLORS.cyan, label: "TTFT" },
          { key: "lat_p99", color: COLORS.red, label: "P99" },
        ]} />
      </div>
      <div className="grid-2" style={{ gap: 1 }}>
        <Chart data={history} title="KV Cache Usage (%)" lines={[
          { key: "kv", color: COLORS.purple, label: "KV Cache %" },
        ]} />
      </div>
      <div className="grid-2" style={{ gap: 1 }}>
        <Chart data={history} title="Request Queue" lines={[
          { key: "running", color: COLORS.green, label: "Running" },
          { key: "waiting", color: COLORS.red, label: "Waiting" },
        ]} />
      </div>
    </div>
  );
}

export default MonitorPage;
