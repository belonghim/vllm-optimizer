import { useState, useEffect } from "react";
import { API, COLORS } from "../constants";
import { mockBenchmarks } from "../mockData";
import { BarChart, Bar, CartesianGrid, XAxis, YAxis, Tooltip, ResponsiveContainer } from "recharts";

const fmt = (n, d = 1) => (n == null ? "—" : Number(n).toFixed(d));

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

export default BenchmarkPage;
