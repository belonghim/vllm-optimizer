import { useState, useEffect, useRef, useCallback } from "react";
import {
  LineChart, Line, AreaChart, Area, BarChart, Bar,
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend,
  ScatterChart, Scatter, ReferenceLine,
} from "recharts";

// ──────────────────────────────────────────────
// DESIGN: Industrial / Terminal aesthetic
// 색상: 어두운 배경 + 형광 앰버/시안 강조색
// 폰트: JetBrains Mono (코드) + Barlow Condensed (헤더)
// ──────────────────────────────────────────────

const API = "http://localhost:8000/api";

const COLORS = {
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

// ── 인라인 스타일 ──
const font = {
  mono: "'JetBrains Mono', 'Fira Code', monospace",
  display: "'Barlow Condensed', 'Oswald', sans-serif",
};


// ── 유틸 함수 ──
const fmt = (n, d = 1) => (n == null ? "—" : Number(n).toFixed(d));
const fmtTime = (ts) => new Date(ts * 1000).toLocaleTimeString("ko-KR", { hour12: false });

// ── 컴포넌트 ──

function MetricCard({ label, value, unit, color = "amber", delta }) {
  return (
    <div className={`metric-card ${color}`}>
      <div className="label">{label}</div>
      <div className="big-num" style={{ color: COLORS[color] || COLORS.accent }}>
        {value ?? "—"}
      </div>
      <div className="big-unit">{unit}</div>
      {delta != null && (
        <div style={{ fontSize: 10, color: delta >= 0 ? COLORS.green : COLORS.red, marginTop: 4 }}>
          {delta >= 0 ? "▲" : "▼"} {Math.abs(delta).toFixed(1)}%
        </div>
      )}
    </div>
  );
}

function Chart({ data, lines, title, height = 180 }) {
  return (
    <div style={{ background: COLORS.surface, border: `1px solid ${COLORS.border}`, padding: 16 }}>
      <div className="section-title">{title}</div>
      <ResponsiveContainer width="100%" height={height}>
        <LineChart data={data} margin={{ top: 4, right: 8, bottom: 0, left: -16 }}>
          <CartesianGrid strokeDasharray="3 3" stroke={COLORS.border} />
          <XAxis dataKey="t" tick={{ fontSize: 9, fill: COLORS.muted }} tickFormatter={d => d} />
          <YAxis tick={{ fontSize: 9, fill: COLORS.muted }} />
          <Tooltip
            contentStyle={{ background: COLORS.surface, border: `1px solid ${COLORS.border}`, fontSize: 11 }}
            labelStyle={{ color: COLORS.muted }}
          />
          {lines.map(l => (
            <Line key={l.key} type="monotone" dataKey={l.key} stroke={l.color}
              dot={false} strokeWidth={1.5} name={l.label} />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

// ──────────────────────────
// PAGE: Dashboard (모니터링)
// ──────────────────────────
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

      {/* 차트 */}
      <div className="grid-2" style={{ gap: 1 }}>
        <Chart data={history} title="Throughput (TPS)" lines={[
          { key: "tps", color: COLORS.accent, label: "TPS" },
        ]} />
        <Chart data={history} title="Latency (ms)" lines={[
          { key: "ttft", color: COLORS.cyan, label: "TTFT" },
          { key: "lat_p99", color: COLORS.red, label: "P99" },
        ]} />
      </div>

      <div className="grid-2" style={{ gap: 1 }}>
        <Chart data={history} title="KV Cache Usage (%)" lines={[
          { key: "kv", color: COLORS.purple, label: "KV Cache %" },
        ]} />
        <Chart data={history} title="Request Queue" lines={[
          { key: "running", color: COLORS.green, label: "Running" },
          { key: "waiting", color: COLORS.red, label: "Waiting" },
        ]} />
      </div>
    </div>
  );
}

// ──────────────────────────
// PAGE: Load Test
// ──────────────────────────
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
          {[
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

// ──────────────────────────
// PAGE: Benchmark
// ──────────────────────────
function BenchmarkPage() {
  const [benchmarks, setBenchmarks] = useState([]);
  const [selected, setSelected] = useState([]);

  useEffect(() => {
    fetch(`${API}/benchmark/list`)
      .then(r => r.json())
      .then(setBenchmarks)
      .catch(() => setBenchmarks(mockBenchmarks()));
  }, []);

  const toggle = (id) => setSelected(s =>
    s.includes(id) ? s.filter(x => x !== id) : [...s, id]
  );

  const compareData = benchmarks
    .filter(b => selected.includes(b.id))
    .map(b => ({
      name: b.name,
      tps: b.result?.tps?.mean || 0,
      ttft: (b.result?.ttft?.mean || 0) * 1000,
      p99: (b.result?.latency?.p99 || 0) * 1000,
      rps: b.result?.rps_actual || 0,
    }));

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <div style={{ background: COLORS.surface, border: `1px solid ${COLORS.border}`, padding: 20 }}>
        <div className="section-title">저장된 벤치마크</div>
        <table className="table">
          <thead>
            <tr><th></th><th>Name</th><th>Date</th><th>TPS</th><th>P99 ms</th><th>RPS</th></tr>
          </thead>
          <tbody>
            {benchmarks.map(b => (
              <tr key={b.id} onClick={() => toggle(b.id)}
                style={{ cursor: "pointer", background: selected.includes(b.id) ? "rgba(245,166,35,0.05)" : "" }}>
                <td>
                  <input type="checkbox" checked={selected.includes(b.id)} readOnly />
                </td>
                <td style={{ color: COLORS.text }}>{b.name}</td>
                <td style={{ color: COLORS.muted }}>{new Date(b.timestamp * 1000).toLocaleDateString()}</td>
                <td style={{ color: COLORS.accent }}>{fmt(b.result?.tps?.mean, 1)}</td>
                <td style={{ color: COLORS.red }}>{fmt((b.result?.latency?.p99 || 0) * 1000, 0)}</td>
                <td>{fmt(b.result?.rps_actual, 1)}</td>
              </tr>
            ))}
            {benchmarks.length === 0 && (
              <tr><td colSpan={6} style={{ color: COLORS.muted, textAlign: "center", padding: 32 }}>
                부하 테스트 결과를 저장하면 여기 나타납니다.
              </td></tr>
            )}
          </tbody>
        </table>
      </div>

      {compareData.length >= 2 && (
        <div style={{ background: COLORS.surface, border: `1px solid ${COLORS.border}`, padding: 20 }}>
          <div className="section-title">비교 차트</div>
          <div className="grid-2" style={{ gap: 1 }}>
            <div>
              <div className="label">TPS 비교</div>
              <ResponsiveContainer width="100%" height={200}>
                <BarChart data={compareData}>
                  <CartesianGrid strokeDasharray="3 3" stroke={COLORS.border} />
                  <XAxis dataKey="name" tick={{ fontSize: 9, fill: COLORS.muted }} />
                  <YAxis tick={{ fontSize: 9, fill: COLORS.muted }} />
                  <Tooltip contentStyle={{ background: COLORS.surface, border: `1px solid ${COLORS.border}` }} />
                  <Bar dataKey="tps" fill={COLORS.accent} name="TPS" />
                </BarChart>
              </ResponsiveContainer>
            </div>
            <div>
              <div className="label">P99 Latency 비교 (ms)</div>
              <ResponsiveContainer width="100%" height={200}>
                <BarChart data={compareData}>
                  <CartesianGrid strokeDasharray="3 3" stroke={COLORS.border} />
                  <XAxis dataKey="name" tick={{ fontSize: 9, fill: COLORS.muted }} />
                  <YAxis tick={{ fontSize: 9, fill: COLORS.muted }} />
                  <Tooltip contentStyle={{ background: COLORS.surface, border: `1px solid ${COLORS.border}` }} />
                  <Bar dataKey="p99" fill={COLORS.red} name="P99 ms" />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ──────────────────────────
// PAGE: Auto Tuner
// ──────────────────────────
function TunerPage() {
  const [status, setStatus] = useState({ running: false, trials_completed: 0 });
  const [trials, setTrials] = useState([]);
  const [importance, setImportance] = useState({});
  const [config, setConfig] = useState({
    objective: "balanced",
    n_trials: 20,
    vllm_endpoint: "http://localhost:8000",
    max_num_seqs_min: 64, max_num_seqs_max: 512,
    gpu_memory_min: 0.80, gpu_memory_max: 0.95,
  });

  const fetchStatus = useCallback(async () => {
    try {
      const [s, t, imp] = await Promise.all([
        fetch(`${API}/tuner/status`).then(r => r.json()),
        fetch(`${API}/tuner/trials`).then(r => r.json()),
        fetch(`${API}/tuner/importance`).then(r => r.json()),
      ]);
      setStatus(s); setTrials(t); setImportance(imp);
    } catch { setTrials(mockTrials()); }
  }, []);

  useEffect(() => {
    fetchStatus();
    const id = setInterval(fetchStatus, 3000);
    return () => clearInterval(id);
  }, [fetchStatus]);

  const start = async () => {
    await fetch(`${API}/tuner/start`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(config),
    });
    fetchStatus();
  };

  const stop = async () => {
    await fetch(`${API}/tuner/stop`, { method: "POST" });
    fetchStatus();
  };

  const applyBest = async () => {
    await fetch(`${API}/tuner/apply-best`, { method: "POST" });
    alert("최적 파라미터를 Kubernetes ConfigMap에 적용했습니다.");
  };

  const scatterData = trials.map(t => ({
    x: t.tps, y: t.p99_latency, name: `Trial ${t.id}`,
    best: status.best?.params && JSON.stringify(t.params) === JSON.stringify(status.best.params),
  }));

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      {/* 설정 */}
      <div style={{ background: COLORS.surface, border: `1px solid ${COLORS.border}`, padding: 20 }}>
        <div className="section-title">Bayesian Optimization 설정</div>
        <div className="grid-form" style={{ gap: 12 }}>
          <div>
            <label className="label">최적화 목표</label>
            <select className="input" value={config.objective}
              onChange={e => setConfig(c => ({ ...c, objective: e.target.value }))}>
              <option value="tps">최대 처리량 (TPS)</option>
              <option value="latency">최소 레이턴시</option>
              <option value="balanced">균형 (TPS / Latency)</option>
            </select>
          </div>
          <div>
            <label className="label">Trial 수</label>
            <input className="input" type="number" value={config.n_trials}
              onChange={e => setConfig(c => ({ ...c, n_trials: +e.target.value }))} />
          </div>
          <div>
            <label className="label">max_num_seqs 범위</label>
            <div style={{ display: "flex", gap: 8 }}>
              <input className="input" type="number" placeholder="Min" value={config.max_num_seqs_min}
                onChange={e => setConfig(c => ({ ...c, max_num_seqs_min: +e.target.value }))} />
              <input className="input" type="number" placeholder="Max" value={config.max_num_seqs_max}
                onChange={e => setConfig(c => ({ ...c, max_num_seqs_max: +e.target.value }))} />
            </div>
          </div>
          <div>
            <label className="label">GPU Memory Util 범위</label>
            <div style={{ display: "flex", gap: 8 }}>
              <input className="input" type="number" step="0.01" placeholder="Min" value={config.gpu_memory_min}
                onChange={e => setConfig(c => ({ ...c, gpu_memory_min: +e.target.value }))} />
              <input className="input" type="number" step="0.01" placeholder="Max" value={config.gpu_memory_max}
                onChange={e => setConfig(c => ({ ...c, gpu_memory_max: +e.target.value }))} />
            </div>
          </div>
        </div>

        <div style={{ display: "flex", gap: 8, marginTop: 16, alignItems: "center" }}>
          <button className="btn btn-primary" onClick={start} disabled={status.running}>
            ▶ Start Tuning
          </button>
          <button className="btn btn-danger" onClick={stop} disabled={!status.running}>
            ■ Stop
          </button>
          {status.best && (
            <button className="btn btn-green" onClick={applyBest}>
              ✓ Apply Best Params
            </button>
          )}
          <span className={`tag tag-${status.running ? "running" : "idle"}`}>
            {status.running ? "TUNING..." : "IDLE"}
          </span>
          <span style={{ fontSize: 11, color: COLORS.muted }}>
            {status.trials_completed} / {config.n_trials} trials
          </span>
        </div>
      </div>

      {/* 최적 파라미터 */}
      {status.best && (
        <div style={{ background: COLORS.surface, border: `1px solid ${COLORS.accent}`, padding: 20 }}>
          <div className="section-title" style={{ color: COLORS.accent }}>최적 파라미터 발견</div>
          <div className="grid-4" style={{ gap: 1, marginBottom: 16 }}>
            <MetricCard label="Best TPS" value={fmt(status.best.tps, 1)} unit="tok/s" color="amber" />
            <MetricCard label="P99 Latency" value={fmt(status.best.p99_latency, 0)} unit="ms" color="cyan" />
          </div>
          {status.best.params && (
            <table className="table">
              <thead><tr><th>Parameter</th><th>Optimal Value</th></tr></thead>
              <tbody>
                {Object.entries(status.best.params).map(([k, v]) => (
                  <tr key={k}>
                    <td style={{ color: COLORS.muted }}>{k}</td>
                    <td style={{ color: COLORS.green }}>{String(v)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}

      {/* Scatter: TPS vs Latency */}
      {scatterData.length > 0 && (
        <div style={{ background: COLORS.surface, border: `1px solid ${COLORS.border}`, padding: 20 }}>
          <div className="section-title">Trial 분포 (TPS vs P99 Latency)</div>
          <ResponsiveContainer width="100%" height={240}>
            <ScatterChart margin={{ top: 8, right: 8, bottom: 8, left: -8 }}>
              <CartesianGrid strokeDasharray="3 3" stroke={COLORS.border} />
              <XAxis dataKey="x" name="TPS" tick={{ fontSize: 9, fill: COLORS.muted }} label={{ value: "TPS", position: "insideBottom", fill: COLORS.muted, fontSize: 9 }} />
              <YAxis dataKey="y" name="P99 ms" tick={{ fontSize: 9, fill: COLORS.muted }} />
              <Tooltip contentStyle={{ background: COLORS.surface, border: `1px solid ${COLORS.border}`, fontSize: 11 }}
                formatter={(v, n) => [fmt(v, 2), n]} />
              <Scatter data={scatterData} fill={COLORS.cyan} opacity={0.7} />
            </ScatterChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* 파라미터 중요도 */}
      {Object.keys(importance).length > 0 && (
        <div style={{ background: COLORS.surface, border: `1px solid ${COLORS.border}`, padding: 20 }}>
          <div className="section-title">파라미터 중요도 (FAnova)</div>
          {Object.entries(importance).sort((a, b) => b[1] - a[1]).map(([k, v]) => (
            <div key={k} style={{ marginBottom: 8 }}>
              <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 3 }}>
                <span style={{ fontSize: 11, color: COLORS.text }}>{k}</span>
                <span style={{ fontSize: 11, color: COLORS.accent }}>{fmt(v * 100, 1)}%</span>
              </div>
              <div className="progress-bar">
                <div className="progress-fill" style={{ width: `${v * 100}%` }} />
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ── Mock 데이터 (백엔드 없을 때) ──
const mockMetrics = () => ({
  tps: 245 + Math.random() * 50,
  ttft_mean: 85 + Math.random() * 30,
  latency_p99: 420 + Math.random() * 80,
  kv_cache: 67 + Math.random() * 10,
  running: Math.floor(15 + Math.random() * 10),
  waiting: Math.floor(Math.random() * 5),
  gpu_mem_used: 18.4, gpu_mem_total: 24,
  pods: 3, pods_ready: 3,
});

const mockHistory = () => Array.from({ length: 60 }, (_, i) => ({
  t: `${String(Math.floor(i / 4)).padStart(2, "0")}:${String((i % 4) * 15).padStart(2, "0")}`,
  tps: 220 + Math.random() * 80, ttft: 80 + Math.random() * 40,
  lat_p99: 380 + Math.random() * 120, kv: 60 + Math.random() * 20,
  running: 10 + Math.random() * 15, waiting: Math.random() * 8,
}));

const mockBenchmarks = () => [
  { id: 1, name: "Baseline (default)", timestamp: Date.now() / 1000 - 86400,
    result: { tps: { mean: 180 }, latency: { p99: 0.52 }, rps_actual: 12, ttft: { mean: 0.095 } }},
  { id: 2, name: "max_num_seqs=256", timestamp: Date.now() / 1000 - 3600,
    result: { tps: { mean: 247 }, latency: { p99: 0.41 }, rps_actual: 18, ttft: { mean: 0.078 } }},
  { id: 3, name: "chunked_prefill=on", timestamp: Date.now() / 1000 - 1800,
    result: { tps: { mean: 265 }, latency: { p99: 0.38 }, rps_actual: 20, ttft: { mean: 0.072 } }},
];

const mockTrials = () => Array.from({ length: 12 }, (_, i) => ({
  id: i, tps: 150 + Math.random() * 150, p99_latency: 300 + Math.random() * 400,
  score: Math.random() * 100,
  params: { max_num_seqs: [64,128,256,512][i%4], gpu_memory_utilization: 0.8 + Math.random() * 0.15 },
  status: "completed",
}));

const simulateLoadTest = (config, setProgress, setResult, setStatus, setLatencyData) => {
  let done = 0;
  const id = setInterval(() => {
    done += Math.floor(Math.random() * 8) + 2;
    if (done >= config.total_requests) done = config.total_requests;
    setProgress(Math.round((done / config.total_requests) * 100));
    setLatencyData(prev => [...prev.slice(-60), {
      t: prev.length, lat: 350 + Math.random() * 150, tps: 200 + Math.random() * 80
    }]);
    setResult({
      total: done, success: done - Math.floor(done * 0.005), failed: Math.floor(done * 0.005),
      rps_actual: 12 + Math.random() * 4,
      latency: { mean: 0.35, p50: 0.30, p95: 0.45, p99: 0.52, min: 0.10, max: 0.80 },
      ttft: { mean: 0.085, p95: 0.120 },
      tps: { mean: 238, total: 1480 },
    });
    if (done >= config.total_requests) { setStatus("completed"); clearInterval(id); }
  }, 200);
};

// ──────────────────────────
// APP ROOT
// ──────────────────────────
const PAGES = [
  { id: "monitor", label: "실시간 모니터링", Component: MonitorPage },
  { id: "loadtest", label: "부하 테스트", Component: LoadTestPage },
  { id: "benchmark", label: "벤치마크 비교", Component: BenchmarkPage },
  { id: "tuner", label: "자동 파라미터 튜닝", Component: TunerPage },
];

export default function App() {
  const [page, setPage] = useState("monitor");
  const ActivePage = PAGES.find(p => p.id === page)?.Component ?? MonitorPage;

  return (
    <>
      <div className="scanline" />

      {/* HEADER */}
      <header style={{
        background: COLORS.surface, borderBottom: `1px solid ${COLORS.border}`,
        padding: "0 24px", display: "flex", alignItems: "center",
        gap: 0, position: "sticky", top: 0, zIndex: 100,
      }}>
        <div style={{ marginRight: 32, padding: "14px 0" }}>
          <div style={{ fontFamily: font.display, fontWeight: 700, fontSize: 15, letterSpacing: "0.2em", color: COLORS.accent }}>
            vLLM<span style={{ color: COLORS.text }}>·OPT</span>
          </div>
          <div style={{ fontSize: 8, letterSpacing: "0.15em", color: COLORS.muted, textTransform: "uppercase" }}>
            Kubernetes Performance Suite
          </div>
        </div>

        <nav style={{ display: "flex", flex: 1 }}>
          {PAGES.map(p => (
            <button key={p.id} className={`nav-btn ${page === p.id ? "active" : ""}`}
              onClick={() => setPage(p.id)}>
              {p.label}
            </button>
          ))}
        </nav>

        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <div style={{ width: 6, height: 6, borderRadius: "50%", background: COLORS.green, boxShadow: `0 0 8px ${COLORS.green}` }} />
          <span style={{ fontSize: 10, color: COLORS.muted, letterSpacing: "0.1em" }}>CONNECTED</span>
        </div>
      </header>

      {/* MAIN */}
      <main style={{ padding: 1, minHeight: "calc(100vh - 57px)", background: COLORS.bg }}>
        <ActivePage />
      </main>
    </>
  );
}
