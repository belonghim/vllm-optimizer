import React from 'react';
import { useThemeColors } from '../contexts/ThemeContext';
import {
  LineChart, Line,
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, ReferenceLine,
} from 'recharts';

const fmtTooltip = (ts: number) => {
  const date = new Date(ts * 1000);
  const Y = date.getFullYear();
  const M = String(date.getMonth() + 1).padStart(2, '0');
  const D = String(date.getDate()).padStart(2, '0');
  const h = String(date.getHours()).padStart(2, '0');
  const m = String(date.getMinutes()).padStart(2, '0');
  const s = String(date.getSeconds()).padStart(2, '0');
  return `${Y}-${M}-${D} ${h}:${m}:${s}`;
};

type TimeRange = 'Live' | '1h' | '6h' | '24h' | '7d';

const fmtTick = (ts: number, range: TimeRange) => {
  const date = new Date(ts * 1000);
  const d = String(date.getDate()).padStart(2, '0');
  const HH = String(date.getHours()).padStart(2, '0');
  const MM = String(date.getMinutes()).padStart(2, '0');

  if (range === '7d') {
    return `${d}d${HH}h`;
  }
  return `${HH}h${MM}m`;
};

interface ChartLine {
  key: string;
  color: string;
  label: string;
  dash?: boolean;
}

interface TooltipPayloadEntry {
  dataKey: string;
  color: string;
  name: string;
  value: number | null;
}

interface CustomTooltipProps {
  active?: boolean;
  payload?: TooltipPayloadEntry[];
  label?: string;
}

const CustomTooltip = React.memo(function CustomTooltip({ active, payload, label }: CustomTooltipProps) {
  const { TOOLTIP_STYLE } = useThemeColors();
  if (!active || !payload?.length) return null;
  const visible = payload.filter(e => !String(e.dataKey).endsWith('_fill'));
  if (!visible.length) return null;
  return (
    <div className="chart-tooltip" style={TOOLTIP_STYLE}>
      <p className="chart-tooltip-label" style={{ margin: 0, marginBottom: '4px', fontWeight: 'bold' }}>{fmtTooltip(Number(label))}</p>
      {visible.map(e => {
        const entryStyle = { color: e.color, margin: 0, fontSize: '11px' };
        return (
          <p key={e.dataKey} className="chart-tooltip-entry" style={entryStyle}>{e.name}: {e.value != null ? Number(e.value).toFixed(1) : '—'}</p>
        );
      })}
    </div>
  );
});

interface ChartProps {
  data: object[];
  lines: ChartLine[];
  title: string;
  height?: number;
  onHide?: () => void;
  threshold?: number;
  timeRange?: TimeRange;
}

function Chart({ data, lines, title, height = 180, onHide, threshold, timeRange = '1h' }: ChartProps) {
  const { COLORS } = useThemeColors();
  return (
    <div className="chart-container" aria-label={title}>
      <div className="section-title chart-title-row">
        <span style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          {title}
          {threshold != null && (
            <span style={{ fontSize: '9px', color: COLORS.red, opacity: 0.8, fontWeight: 'normal', border: `1px solid ${COLORS.red}`, padding: '0 4px', borderRadius: '2px' }}>
              SLA: {threshold}
            </span>
          )}
        </span>
        {onHide && (
          <button className="chart-hide-btn" onClick={onHide} title="Hide chart" aria-label={`Hide ${title} chart`}>×</button>
        )}
      </div>
      <ResponsiveContainer width="100%" height={height}>
        <LineChart data={data} margin={{ top: 4, right: 8, bottom: 0, left: -16 }}>
          <CartesianGrid strokeDasharray="3 3" stroke={COLORS.border} />
          <XAxis dataKey="t" tick={{ fontSize: 9, fill: COLORS.muted }} tickFormatter={ts => fmtTick(ts, timeRange)} />
          <YAxis tick={{ fontSize: 9, fill: COLORS.muted }} />
          <Tooltip content={<CustomTooltip />} />
          {threshold != null && (
            <ReferenceLine y={threshold} stroke={COLORS.red} strokeDasharray="3 3" label={{ position: 'right', fill: COLORS.red, fontSize: 8, value: 'SLA' }} />
          )}
          {lines.map(l => (
            <Line
              key={l.key}
              type="linear"
              dataKey={l.key}
              stroke={l.color}
              dot={false}
              strokeWidth={l.dash ? 1 : 1.5}
              name={l.label}
              connectNulls={true}
              isAnimationActive={false}
              strokeDasharray={l.dash ? '5 3' : undefined}
              opacity={l.dash ? 0.45 : 1}
              legendType={l.dash ? 'none' : undefined}
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

export default React.memo(Chart);
