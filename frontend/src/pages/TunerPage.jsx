import { useState, useEffect, useCallback } from "react";
import { API, COLORS } from "../constants";
import { useMockData } from "../contexts/MockDataContext";
import MetricCard from "../components/MetricCard";
import { mockTrials } from "../mockData";
import { ScatterChart, Scatter, CartesianGrid, XAxis, YAxis, Tooltip, ResponsiveContainer, LineChart, Line } from "recharts";

const fmt = (n, d = 1) => (n == null ? "—" : Number(n).toFixed(d));

const PHASE_LABELS = {
  applying_config: "ConfigMap 업데이트 중...",
  restarting: "InferenceService 재시작 중...",
  waiting_ready: "Pod Ready 대기 중...",
  warmup: "Warmup 요청 전송 중...",
  evaluating: "성능 평가 중...",
};

function TunerPage() {
  const { isMockEnabled } = useMockData();
  const [error, setError] = useState(null);
  const [status, setStatus] = useState({ running: false, trials_completed: 0 });
  const [trials, setTrials] = useState([]);
  const [importance, setImportance] = useState({});
  const [currentPhase, setCurrentPhase] = useState(null);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [currentConfig, setCurrentConfig] = useState(null);
  const [config, setConfig] = useState({
    objective: "balanced",
    n_trials: 20,
    vllm_endpoint: "",
    max_num_seqs_min: 64, max_num_seqs_max: 512,
    gpu_memory_min: 0.80, gpu_memory_max: 0.95,
    max_model_len_min: 2048, max_model_len_max: 8192,
    max_num_batched_tokens_min: 256, max_num_batched_tokens_max: 2048,
    block_size_options: [8, 16, 32],
    include_swap_space: false,
    swap_space_min: 1.0, swap_space_max: 8.0,
    eval_concurrency: 32,
    eval_rps: 20,
    eval_requests: 200,
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
    if (!status.running || isMockEnabled) return;
    const es = new EventSource(`${API}/tuner/stream`);
    es.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.type === "phase") {
          setCurrentPhase(data.data);
        }
        if (data.type === "trial_complete" || data.type === "tuning_complete") {
          setCurrentPhase(null);
          fetchStatus();
        }
      } catch (e) {
        console.warn("SSE parse error:", e);
      }
    };
    es.onerror = () => { es.close(); };
    return () => { es.close(); };
  }, [status.running, isMockEnabled, fetchStatus]);

  useEffect(() => {
    if (isMockEnabled) return;
    fetch(`${API}/vllm-config`)
      .then(r => r.json())
      .then(data => { if (data.success) setCurrentConfig(data.data); })
      .catch(() => {});
  }, [isMockEnabled]);

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
    setCurrentPhase(null);
    fetchStatus();
  };

  const applyBest = async () => {
    try {
      const res = await fetch(`${API}/tuner/apply-best`, { method: "POST" });
      const data = await res.json();
      if (data && data.success) {
        alert("최적 파라미터를 Kubernetes ConfigMap에 적용했습니다.");
      } else {
        alert(`파라미터 적용 실패: ${data?.message || "Unknown error"}`);
      }
    } catch (err) {
      alert(`파라미터 적용 실패: ${err.message}`);
    }
  };

  const scatterData = trials.map(t => ({
    x: t.tps, y: t.p99_latency, name: `Trial ${t.id}`,
    best: status.best?.params && JSON.stringify(t.params) === JSON.stringify(status.best.params),
    pareto_optimal: t.is_pareto_optimal || false,
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
              <option value="pareto">Pareto (TPS + Latency)</option>
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

        <div style={{ marginTop: 8 }}>
          <button
            className="btn"
            onClick={() => setShowAdvanced(v => !v)}
            style={{ fontSize: 11, padding: "4px 12px", background: "none", border: `1px solid ${COLORS.border}`, color: COLORS.muted, cursor: "pointer" }}
          >
            고급 설정 {showAdvanced ? "▲" : "▼"}
          </button>
        </div>

        {showAdvanced && (
          <div style={{ background: COLORS.surface, border: `1px solid ${COLORS.border}`, padding: 16, marginTop: 8 }}>
            {currentConfig && (
              <div style={{ background: "rgba(0,0,0,0.2)", border: `1px solid ${COLORS.border}`, padding: 12, marginBottom: 16, fontSize: 11 }}>
                <div style={{ color: COLORS.muted, marginBottom: 6, fontFamily: "'JetBrains Mono', monospace" }}>현재 vLLM 설정 (ConfigMap)</div>
                <div style={{ display: "flex", flexWrap: "wrap", gap: "4px 16px" }}>
                  {Object.entries(currentConfig).map(([k, v]) => (
                    <span key={k} style={{ fontFamily: "'JetBrains Mono', monospace", color: COLORS.text, fontSize: 11 }}>
                      {k}: <span style={{ color: COLORS.accent }}>{String(v) || "(비어있음)"}</span>
                    </span>
                  ))}
                </div>
              </div>
            )}
            <div className="grid-form" style={{ gap: 12 }}>
              <div>
                <label className="label">max_model_len 범위</label>
                <div style={{ display: "flex", gap: 8 }}>
                  <input className="input" type="number" placeholder="Min" value={config.max_model_len_min}
                    onChange={e => setConfig(c => ({ ...c, max_model_len_min: +e.target.value }))} />
                  <input className="input" type="number" placeholder="Max" value={config.max_model_len_max}
                    onChange={e => setConfig(c => ({ ...c, max_model_len_max: +e.target.value }))} />
                </div>
              </div>
              <div>
                <label className="label">max_num_batched_tokens 범위</label>
                <div style={{ display: "flex", gap: 8 }}>
                  <input className="input" type="number" placeholder="Min" value={config.max_num_batched_tokens_min}
                    onChange={e => setConfig(c => ({ ...c, max_num_batched_tokens_min: +e.target.value }))} />
                  <input className="input" type="number" placeholder="Max" value={config.max_num_batched_tokens_max}
                    onChange={e => setConfig(c => ({ ...c, max_num_batched_tokens_max: +e.target.value }))} />
                </div>
              </div>
              <div>
                <label className="label">block_size 옵션</label>
                <div style={{ display: "flex", gap: 12 }}>
                  {[8, 16, 32].map(size => (
                    <label key={size} style={{ display: "flex", alignItems: "center", gap: 4, fontSize: 12, color: COLORS.text, cursor: "pointer" }}>
                      <input type="checkbox"
                        checked={config.block_size_options.includes(size)}
                        onChange={e => {
                          setConfig(c => ({
                            ...c,
                            block_size_options: e.target.checked
                              ? [...c.block_size_options, size].sort((a, b) => a - b)
                              : c.block_size_options.filter(s => s !== size)
                          }));
                        }}
                      />
                      {size}
                    </label>
                  ))}
                </div>
              </div>
              <div>
                <label className="label" style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <input type="checkbox"
                    checked={config.include_swap_space}
                    onChange={e => setConfig(c => ({ ...c, include_swap_space: e.target.checked }))}
                  />
                  swap_space 포함
                </label>
                {config.include_swap_space && (
                  <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
                    <input className="input" type="number" step="0.5" placeholder="Min GB" value={config.swap_space_min}
                      onChange={e => setConfig(c => ({ ...c, swap_space_min: +e.target.value }))} />
                    <input className="input" type="number" step="0.5" placeholder="Max GB" value={config.swap_space_max}
                      onChange={e => setConfig(c => ({ ...c, swap_space_max: +e.target.value }))} />
                  </div>
                )}
              </div>
              <div>
                <label className="label">평가 요청 수</label>
                <input className="input" type="number" value={config.eval_requests}
                  onChange={e => setConfig(c => ({ ...c, eval_requests: +e.target.value }))} />
              </div>
              <div>
                <label className="label">평가 동시 요청</label>
                <input className="input" type="number" value={config.eval_concurrency}
                  onChange={e => setConfig(c => ({ ...c, eval_concurrency: +e.target.value }))} />
              </div>
              <div>
                <label className="label">평가 RPS</label>
                <input className="input" type="number" value={config.eval_rps}
                  onChange={e => setConfig(c => ({ ...c, eval_rps: +e.target.value }))} />
              </div>
            </div>
          </div>
        )}

        {status.running && currentPhase && (
          <div style={{
            marginTop: 12,
            padding: "8px 16px",
            background: "rgba(0,163,255,0.08)",
            border: `1px solid ${COLORS.accent}`,
            fontSize: 12,
            fontFamily: "'JetBrains Mono', monospace",
            color: COLORS.accent,
          }}>
            Trial {(currentPhase.trial_id ?? 0) + 1}: {PHASE_LABELS[currentPhase.phase] || currentPhase.phase}
          </div>
        )}
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
              {/* Regular trials */}
              <Scatter
                  data={scatterData.filter(d => !d.pareto_optimal)}
                  fill={COLORS.cyan}
                  opacity={0.7}
              />
              {/* Pareto-optimal trials — highlighted */}
              <Scatter
                  data={scatterData.filter(d => d.pareto_optimal)}
                  fill={"#4caf50"}
                  opacity={1.0}
              />
            </ScatterChart>
          </ResponsiveContainer>
          {scatterData.some(d => d.pareto_optimal) && (
              <div style={{ fontSize: 10, color: COLORS.muted, marginTop: 4 }}>
                  <span style={{ color: "#4caf50" }}>●</span> Pareto-optimal &nbsp;
                  <span style={{ color: COLORS.cyan }}>●</span> Regular trial
              </div>
          )}
        </div>
      )}

      {/* Convergence Chart */}
      {status.best_score_history && status.best_score_history.length > 1 && (
          <div style={{ background: COLORS.surface, border: `1px solid ${COLORS.border}`, padding: 20 }}>
              <div className="section-title">최적 점수 수렴</div>
              <ResponsiveContainer width="100%" height={180}>
                  <LineChart
                      data={status.best_score_history.map((score, i) => ({ trial: i + 1, score: Number(score).toFixed(2) }))}
                      margin={{ top: 8, right: 8, bottom: 8, left: -8 }}
                  >
                      <CartesianGrid strokeDasharray="3 3" stroke={COLORS.border} />
                      <XAxis dataKey="trial" tick={{ fontSize: 9, fill: COLORS.muted }} />
                      <YAxis tick={{ fontSize: 9, fill: COLORS.muted }} />
                      <Tooltip
                          contentStyle={{ background: COLORS.surface, border: `1px solid ${COLORS.border}`, fontSize: 11 }}
                          formatter={(v) => [v, "Best Score"]}
                      />
                      <Line type="monotone" dataKey="score" stroke={COLORS.accent} strokeWidth={2} dot={false} />
                  </LineChart>
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
