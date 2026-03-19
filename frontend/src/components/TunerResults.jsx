import { COLORS } from '../constants';
import MetricCard from './MetricCard';
import { ScatterChart, Scatter, CartesianGrid, XAxis, YAxis, Tooltip, ResponsiveContainer, LineChart, Line } from 'recharts';

const fmt = (n, d = 1) => (n == null ? "—" : Number(n).toFixed(d));

export default function TunerResults({ trials, bestParams, status, isRunning, importance }) {
  const scatterData = trials.map(t => ({
    x: t.tps, y: t.p99_latency, name: `Trial ${t.id}`,
    best: bestParams?.params && JSON.stringify(t.params) === JSON.stringify(bestParams.params),
    pareto_optimal: t.is_pareto_optimal || false,
  }));

  return (
    <>
      {bestParams && (
        <div style={{ background: COLORS.surface, border: `1px solid ${COLORS.accent}`, padding: 20 }}>
          <div className="section-title" style={{ color: COLORS.accent }}>최적 파라미터 발견</div>
          <div className="grid-4" style={{ gap: 1, marginBottom: 16 }}>
            <MetricCard label="Best TPS" value={fmt(bestParams.tps, 1)} unit="tok/s" color="amber" />
            <MetricCard label="P99 Latency" value={fmt(bestParams.p99_latency, 0)} unit="ms" color="cyan" />
          </div>
          {bestParams.params && (
            <table className="table">
              <thead><tr><th>Parameter</th><th>Optimal Value</th></tr></thead>
              <tbody>
                {Object.entries(bestParams.params).map(([k, v]) => (
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
    </>
  );
}
