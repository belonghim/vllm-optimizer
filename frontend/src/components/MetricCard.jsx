import { COLORS } from '../constants';

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

export default MetricCard;