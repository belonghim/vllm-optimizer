import { useState, useEffect } from "react";
import { API, COLORS } from "../constants";
import { mockBenchmarks } from "../mockData";
import { BarChart, Bar, CartesianGrid, XAxis, YAxis, Tooltip, ResponsiveContainer } from "recharts";
import { useMockData } from "../contexts/MockDataContext";
import ErrorAlert from "../components/ErrorAlert";

const fmt = (n, d = 1) => (n == null ? "—" : Number(n).toFixed(d));

const TOOLTIP_STYLE = { background: COLORS.surface, border: `1px solid ${COLORS.border}` };

function BenchmarkPage({ isActive }) {
  const [benchmarks, setBenchmarks] = useState([]);
  const [selected, setSelected] = useState([]);
  const [error, setError] = useState(null);
  const { isMockEnabled } = useMockData();

  useEffect(() => {
    if (!isActive) return;

    if (isMockEnabled) {
      setBenchmarks(mockBenchmarks());
      setError(null);
      return;
    }
    fetch(`${API}/benchmark/list`)
      .then(r => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then(data => {
        setBenchmarks(data);
        setError(null);
      })
      .catch(err => {
        setError(`벤치마크 조회 실패: ${err.message}`);
      });
  }, [isMockEnabled, isActive]);

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
      gpuEff: b.result?.metrics_target_matched !== false && b.result?.gpu_utilization_avg > 0
        ? b.result.tps.mean / b.result.gpu_utilization_avg
        : 0,
      metricsTargetMatched: b.result?.metrics_target_matched !== false,
    }));

  return (
    <div className="flex-col-16">
      <ErrorAlert message={error} className="error-alert--mb8" />
      <div className="panel">
        <div className="section-title">저장된 벤치마크</div>
        <table className="table">
          <thead>
            <tr><th></th><th>Name</th><th>Model</th><th>Date</th><th>TPS</th><th>P99 ms</th><th>RPS</th><th>GPU Eff.</th></tr>
          </thead>
          <tbody>
            {benchmarks.map(b => (
              <tr key={b.id} onClick={() => toggle(b.id)}
                className={selected.includes(b.id) ? 'benchmark-row benchmark-row--selected' : 'benchmark-row'}>
                <td>
                  <input type="checkbox" checked={selected.includes(b.id)} readOnly aria-label={`벤치마크 ${b.name} 선택`} />
                </td>
                <td className="td-text">{b.name}</td>
                <td className="td-cyan">{b.config?.model || "—"}</td>
                <td className="td-muted">{new Date(b.timestamp * 1000).toLocaleString()}</td>
                <td className="td-accent">{fmt(b.result?.tps?.mean, 1)}</td>
                <td className="td-red">{fmt((b.result?.latency?.p99 || 0) * 1000, 0)}</td>
                <td>{fmt(b.result?.rps_actual, 1)}</td>
                <td className="td-green">
                  {b.result?.metrics_target_matched === false ? (
                    <span title="GPU metrics mismatch">N/A</span>
                  ) : (
                    b.result?.gpu_utilization_avg > 0
                      ? (b.result.tps.mean / b.result.gpu_utilization_avg).toFixed(1)
                      : "—"
                  )}
                </td>
              </tr>
            ))}
            {benchmarks.length === 0 && (
              <tr><td colSpan={8} className="benchmark-empty">
                부하 테스트 결과를 저장하면 여기 나타납니다.
              </td></tr>
            )}
          </tbody>
        </table>
      </div>

      {compareData.length >= 2 && (
        <div className="panel">
          <div className="section-title">비교 차트</div>
          <div className="benchmark-compare-charts">
            <div>
              <div className="label">TPS 비교</div>
              <ResponsiveContainer width="100%" height={200}>
                <BarChart data={compareData}>
                  <CartesianGrid strokeDasharray="3 3" stroke={COLORS.border} />
                  <XAxis dataKey="name" tick={{ fontSize: 9, fill: COLORS.muted }} />
                  <YAxis tick={{ fontSize: 9, fill: COLORS.muted }} />
                  <Tooltip contentStyle={TOOLTIP_STYLE} />
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
                  <Tooltip contentStyle={TOOLTIP_STYLE} />
                  <Bar dataKey="p99" fill={COLORS.red} name="P99 ms" />
                </BarChart>
              </ResponsiveContainer>
            </div>
            <div>
              <div className="label">GPU 효율 비교 (TPS/GPU%)</div>
              <ResponsiveContainer width="100%" height={200}>
                <BarChart data={compareData.filter(d => d.metricsTargetMatched)}>
                  <CartesianGrid strokeDasharray="3 3" stroke={COLORS.border} />
                  <XAxis dataKey="name" tick={{ fontSize: 9, fill: COLORS.muted }} />
                  <YAxis tick={{ fontSize: 9, fill: COLORS.muted }} />
                  <Tooltip contentStyle={TOOLTIP_STYLE} />
                  <Bar dataKey="gpuEff" fill={COLORS.green} name="GPU Eff." />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
export default BenchmarkPage;
