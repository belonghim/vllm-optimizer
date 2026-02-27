import { useState } from "react";
import { API, COLORS, font } from "../constants";
import MetricCard from "../components/MetricCard";
import Chart from "../components/Chart";
import { simulateLoadTest } from "../mockData";

const fmt = (n, d = 1) => (n == null ? "—" : Number(n).toFixed(d));

function LoadTestPage() {
  const [config, setConfig] = useState({
    endpoint: "http://localhost:8000",
    model: "auto",
    total_requests: 200,
    concurrency: 20,
    rps: 10,
    max_tokens: 256,
    temperature: 0.7,
    stream: true,
  });
  const [status, setStatus] = useState("idle");
  const [result, setResult] = useState(null);
  const [progress, setProgress] = useState(0);
  const [latencyData, setLatencyData] = useState([]);

  const start = async () => {
    setStatus("running"); setResult(null); setLatencyData([]); setProgress(0);

    try {
      await fetch(`${API}/load-test/start`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify(config),
      });

      const es = new EventSource(`${API}/load-test/stream`);
      es.onmessage = (e) => {
        const data = JSON.parse(e.data);
        if (data.type === "progress" && data.data) {
          const d = data.data;
          setProgress(Math.round((d.total / config.total_requests) * 100));
          setLatencyData(prev => [...prev.slice(-60), {
            t: prev.length, lat: d.latency?.mean * 1000 | 0, tps: d.tps?.mean | 0
          }]);
          setResult(d);
        }
        if (data.type === "completed") {
          setStatus("completed"); es.close();
          setResult(data.data);
        }
      };
      es.onerror = () => { setStatus("failed"); es.close(); };
    } catch {
      // 모의 실행
      simulateLoadTest(config, setProgress, setResult, setStatus, setLatencyData);
    }
  };

  const stop = async () => {
    await fetch(`${API}/load-test/stop`, { method: "POST" });
    setStatus("stopped");
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      {/* 설정 */}
      <div style={{ background: COLORS.surface, border: `1px solid ${COLORS.border}`, padding: 20 }}>
        <div className="section-title">부하 테스트 설정</div>
        <div className="grid-form" style={{ gap: 12 }}>
          {
            [
              ["vLLM Endpoint", "endpoint", "text"],
              ["Model Name", "model", "text"],
              ["Total Requests", "total_requests", "number"],
              ["Concurrency", "concurrency", "number"],
              ["RPS (0=unlimited)", "rps", "number"],
              ["Max Tokens", "max_tokens", "number"],
            ].map(([label, key, type]) => (
              <div key={key}>
                <label className="label">{label}</label>
                <input className="input" type={type} value={config[key]}
                  onChange={e => setConfig(c => ({ ...c, [key]: type === "number" ? +e.target.value : e.target.value }))} />
              </div>
            ))}
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 16 }}>
          <input type="checkbox" id="stream" checked={config.stream}
            onChange={e => setConfig(c => ({ ...c, stream: e.target.checked }))} />
          <label htmlFor="stream" className="label" style={{ marginBottom: 0 }}>
            Streaming Mode (TTFT 측정 활성화)
          </label>
        </div>

        <div style={{ display: "flex", gap: 8, marginTop: 16 }}>
          <button className="btn btn-primary" onClick={start} disabled={status === "running"}>
            ▶ Run Load Test
          </button>
          <button className="btn btn-danger" onClick={stop} disabled={status !== "running"}>
            ■ Stop
          </button>
          <span className={`tag tag-${status}`}>{status.toUpperCase()}</span>
        </div>
      </div>

      {/* 진행률 */}
      {status === "running" && (
        <div style={{ background: COLORS.surface, border: `1px solid ${COLORS.border}`, padding: 20 }}>
          <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 8 }}>
            <span className="label">진행률</span>
            <span style={{ fontSize: 11, color: COLORS.accent }}>{progress}%</span>
          </div>
          <div className="progress-bar">
            <div className="progress-fill" style={{ width: `${progress}%` }} />
          </div>
        </div>
      )}

      {/* 결과 */}
      {result && (
        <>
          <div className="grid-4" style={{ gap: 1 }}>
            <MetricCard label="Mean TPS" value={fmt(result.tps?.mean, 1)} unit="tok/s" color="amber" />
            <MetricCard label="TTFT Mean" value={fmt((result.ttft?.mean || 0) * 1000, 0)} unit="ms" color="cyan" />
            <MetricCard label="P99 Latency" value={fmt((result.latency?.p99 || 0) * 1000, 0)} unit="ms" color="red" />
            <MetricCard label="Success Rate"
              value={result.total ? fmt((result.success / result.total) * 100, 1) : "—"}
              unit="%" color="green" />
          </div>

          <div style={{ background: COLORS.surface, border: `1px solid ${COLORS.border}`, padding: 20 }}>
            <div className="section-title">Latency Distribution</div>
            <table className="table">
              <thead>
                <tr>
                  <th>Metric</th><th>Value</th>
                </tr>
              </thead>
              <tbody>
                {[
                  ["Total Requests", result.total],
                  ["Success", result.success],
                  ["Failed", result.failed],
                  ["Actual RPS", fmt(result.rps_actual, 2)],
                  ["Mean Latency", `${fmt((result.latency?.mean || 0) * 1000, 0)} ms`],
                  ["P50 Latency", `${fmt((result.latency?.p50 || 0) * 1000, 0)} ms`],
                  ["P95 Latency", `${fmt((result.latency?.p95 || 0) * 1000, 0)} ms`],
                  ["P99 Latency", `${fmt((result.latency?.p99 || 0) * 1000, 0)} ms`],
                  ["TTFT Mean", `${fmt((result.ttft?.mean || 0) * 1000, 0)} ms`],
                  ["TTFT P95", `${fmt((result.ttft?.p95 || 0) * 1000, 0)} ms`],
                  ["Total TPS", `${fmt(result.tps?.total, 1)} tok/s`],
                ].map(([k, v]) => (
                  <tr key={k}>
                    <td style={{ color: COLORS.muted }}>{k}</td>
                    <td style={{ color: COLORS.accent, fontFamily: font.mono }}>{v}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {latencyData.length > 0 && (
            <Chart data={latencyData} title="실시간 레이턴시 (ms)" height={160} lines={[
              { key: "lat", color: COLORS.red, label: "Latency ms" },
              { key: "tps", color: COLORS.accent, label: "TPS" },
            ]} />
          )}
        </>
      )}
    </div>
  );
}

export default LoadTestPage;
