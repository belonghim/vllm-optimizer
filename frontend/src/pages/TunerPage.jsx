import { useState, useEffect, useCallback } from "react";
import { API, COLORS, font } from "../constants";
import { useMockData } from "../contexts/MockDataContext";
import MetricCard from "../components/MetricCard";
import { mockTrials } from "../mockData";
import { ScatterChart, Scatter, CartesianGrid, XAxis, YAxis, Tooltip, ResponsiveContainer } from "recharts";

const fmt = (n, d = 1) => (n == null ? "—" : Number(n).toFixed(d));

function TunerPage() {
  const { isMockEnabled } = useMockData();
  const [error, setError] = useState(null);
  const [status, setStatus] = useState({ running: false, trials_completed: 0 });
  const [trials, setTrials] = useState([]);
  const [importance, setImportance] = useState({});
  const [config, setConfig] = useState({
    objective: "balanced",
    n_trials: 20,
    vllm_endpoint: "",
    max_num_seqs_min: 64, max_num_seqs_max: 512,
    gpu_memory_min: 0.80, gpu_memory_max: 0.95,
  });

  const fetchStatus = useCallback(async () => {
    if (isMockEnabled) {
      setTrials(mockTrials());
      setError(null);
      return;
    }
    try {
      const [s, t, imp] = await Promise.all([
        fetch(`${API}/tuner/status`).then(r => r.json()),
        fetch(`${API}/tuner/trials`).then(r => r.json()),
        fetch(`${API}/tuner/importance`).then(r => r.json()),
      ]);
      setStatus(s); setTrials(t); setImportance(imp);
      setError(null);
    } catch (err) {
      setError(`튜너 조회 실패: ${err.message}`);
    }
  }, [isMockEnabled]);

  useEffect(() => {
    fetchStatus();
    const id = setInterval(fetchStatus, 3000);
    return () => clearInterval(id);
  }, [fetchStatus]);

  useEffect(() => {
    fetch(`${API}/config`)
      .then(r => r.json())
      .then(data => {
        if (data.vllm_endpoint) {
          setConfig(c => ({ ...c, vllm_endpoint: c.vllm_endpoint || data.vllm_endpoint }));
        }
      })
      .catch(() => {}); // silently fail — user can type manually
  }, []);

  const start = async () => {
    setError(null);
    try {
      const res = await fetch(`${API}/tuner/start`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify(config),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      if (!data.success) {
        setError(data.message || "튜닝 시작 실패");
        return;
      }
      fetchStatus();
    } catch (err) {
      setError(`튜닝 시작 실패: ${err.message}`);
    }
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
      {error && (
        <div style={{
          border: `1px solid ${COLORS.red}`,
          color: COLORS.red,
          padding: "10px 16px",
          fontFamily: "'JetBrains Mono', monospace",
          fontSize: 11,
          marginBottom: 16,
          background: "rgba(255,59,107,0.05)",
        }}>
          ⚠ {error}
        </div>
      )}
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

export default TunerPage;
