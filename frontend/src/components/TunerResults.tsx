import { useMemo } from 'react';
import { fmt } from '../utils/format';
import MetricCard from './MetricCard';
import { downloadJSON, downloadCSV, trialsToCSV } from '../utils/export';
import { ScatterChart, Scatter, CartesianGrid, XAxis, YAxis, Tooltip, ResponsiveContainer, LineChart, Line } from 'recharts';
import { useThemeColors } from '../contexts/ThemeContext';

interface TrialParams {
  [key: string]: unknown;
}

interface Trial {
  id: number;
  tps: number;
  p99_latency: number;
  score: number;
  params: TrialParams;
  status: string;
  is_pareto_optimal?: boolean;
}

interface BestParams {
  tps: number;
  p99_latency: number;
  params?: TrialParams;
}

interface TunerStatus {
  running: boolean;
  trials_completed: number;
  best?: BestParams;
  best_score_history?: number[];
}

interface TunerResultsProps {
  trials: Trial[];
  bestParams: BestParams | undefined;
  status: TunerStatus;
  isRunning: boolean;
  importance: Record<string, number>;
}

export default function TunerResults({ trials, bestParams, status, importance, isRunning: _isRunning }: TunerResultsProps) {
  const { COLORS, TOOLTIP_STYLE } = useThemeColors();
  const TUNER_TOOLTIP_STYLE = useMemo(() => ({ ...TOOLTIP_STYLE, fontSize: 11 }), [TOOLTIP_STYLE]);

  if (!trials) return null;

  const scatterData = trials.map(t => ({
    x: t.tps, y: t.p99_latency, name: `Trial ${t.id}`,
    best: bestParams?.params && JSON.stringify(t.params) === JSON.stringify(bestParams.params),
    pareto_optimal: t.is_pareto_optimal || false,
  }));

  return (
    <>
      {trials.length > 0 && (
      <div className="panel" style={{ marginBottom: '1rem' }}>
          <div className="section-title">Export Results</div>
          <div style={{ display: 'flex', gap: '0.5rem' }}>
            <button
              onClick={() => {
                const timestamp = new Date().getTime();
                downloadJSON(
                  { trials, best: bestParams, importance },
                  `tuning-results-${timestamp}.json`
                );
              }}
              className="btn"
            >
              Export JSON
            </button>
            <button
              onClick={() => {
                const timestamp = new Date().getTime();
                const { headers, rows } = trialsToCSV(trials);
                downloadCSV(headers, rows, `tuning-results-${timestamp}.csv`);
              }}
              className="btn"
            >
              Export CSV
            </button>
          </div>
        </div>
      )}

      {bestParams && (
        <div className="tuner-best-panel">
          <div className="section-title section-title-accent">Best Parameters Found</div>
          <div className="grid-4 tuner-best-metrics-grid">
            <MetricCard label="Best TPS" value={fmt(bestParams.tps, 1)} unit="tok/s" color="amber" />
            <MetricCard label="P99 Latency" value={fmt(bestParams.p99_latency, 0)} unit="ms" color="cyan" />
          </div>
          {bestParams.params && (
            <table className="table">
              <thead><tr><th>Parameter</th><th>Optimal Value</th></tr></thead>
              <tbody>
                {Object.entries(bestParams.params).map(([k, v]) => (
                  <tr key={k}>
                    <td className="td-muted">{k}</td>
                    <td className="td-green">{String(v)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}

      {scatterData.length > 0 && (
        <div className="panel" aria-label="Trial distribution chart (TPS vs P99 Latency)">
          <div className="section-title">Trial Distribution (TPS vs P99 Latency)</div>
          <ResponsiveContainer width="100%" height={240}>
            <ScatterChart margin={{ top: 8, right: 8, bottom: 8, left: -8 }}>
              <CartesianGrid strokeDasharray="3 3" stroke={COLORS.border} />
              <XAxis dataKey="x" name="TPS" tick={{ fontSize: 9, fill: COLORS.muted }} label={{ value: "TPS", position: "insideBottom", fill: COLORS.muted, fontSize: 9 }} />
              <YAxis dataKey="y" name="P99 ms" tick={{ fontSize: 9, fill: COLORS.muted }} />
               <Tooltip contentStyle={TUNER_TOOLTIP_STYLE}
                 formatter={(v: number, n: string) => [fmt(v, 2), n]} />
              <Scatter
                  data={scatterData.filter(d => !d.pareto_optimal)}
                  fill={COLORS.cyan}
                  opacity={0.7}
              />
              <Scatter
                  data={scatterData.filter(d => d.pareto_optimal)}
                  fill={"rgb(var(--success-rgb))"}
                  opacity={1.0}
              />
            </ScatterChart>
          </ResponsiveContainer>
          {scatterData.some(d => d.pareto_optimal) && (
              <div className="tuner-scatter-legend">
                  <span className="tuner-legend-pareto">●</span> Pareto-optimal &nbsp;
                  <span className="tuner-legend-regular">●</span> Regular trial
              </div>
          )}
        </div>
      )}

      {status.best_score_history && status.best_score_history.length > 1 && (
          <div className="panel" aria-label="Best score convergence chart">
              <div className="section-title">Best Score Convergence</div>
              <ResponsiveContainer width="100%" height={180}>
                  <LineChart
                      data={status.best_score_history.map((score, i) => ({ trial: i + 1, score: Number(score).toFixed(2) }))}
                      margin={{ top: 8, right: 8, bottom: 8, left: -8 }}
                  >
                      <CartesianGrid strokeDasharray="3 3" stroke={COLORS.border} />
                      <XAxis dataKey="trial" tick={{ fontSize: 9, fill: COLORS.muted }} />
                      <YAxis tick={{ fontSize: 9, fill: COLORS.muted }} />
                       <Tooltip
                           contentStyle={TUNER_TOOLTIP_STYLE}
                           formatter={(v: string) => [v, "Best Score"]}
                       />
                      <Line type="monotone" dataKey="score" stroke={COLORS.accent} strokeWidth={2} dot={false} />
                  </LineChart>
              </ResponsiveContainer>
          </div>
      )}

      {Object.keys(importance).length > 0 && (
        <div className="panel">
          <div className="section-title">Parameter Importance (FAnova)</div>
          {Object.entries(importance).sort((a, b) => b[1] - a[1]).map(([k, v]) => {
            const fillStyle = { width: `${v * 100}%` };
            return (
              <div key={k} className="tuner-importance-row">
                <div className="tuner-importance-header">
                  <span className="tuner-importance-key">{k}</span>
                  <span className="tuner-importance-val">{fmt(v * 100, 1)}%</span>
                </div>
                <div className="progress-bar">
                  <div className="progress-fill" style={fillStyle} />
                </div>
              </div>
            );
          })}
        </div>
      )}
    </>
  );
}
