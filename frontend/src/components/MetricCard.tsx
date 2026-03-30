import React, { type ReactNode } from "react";

interface MetricCardProps {
  label: string;
  value: ReactNode;
  unit: string;
  color?: string;
  delta?: number | null;
  alert?: boolean;
}

function MetricCard({ label, value, unit, color = "amber", delta, alert }: MetricCardProps) {
  return (
    <div className={`metric-card ${color} ${alert ? 'metric-card--alert' : ''}`}>
      <div className="label">{label}</div>
      <div className="big-num">
        {value ?? "—"}
      </div>
      <div className="big-unit">{unit}</div>
      {delta != null && (
        <div className={`metric-card-delta ${delta >= 0 ? 'metric-card-delta--pos' : 'metric-card-delta--neg'}`}>
          {delta >= 0 ? "▲" : "▼"} {Math.abs(delta).toFixed(1)}%
        </div>
      )}
    </div>
  );
}

export default React.memo(MetricCard);
