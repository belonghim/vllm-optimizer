import React from 'react';
import { useThemeColors } from '../contexts/ThemeContext';
import {
  LineChart, Line,
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, ReferenceLine,
} from 'recharts';

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
      <p className="chart-tooltip-label" style={{ margin: 0, marginBottom: '4px', fontWeight: 'bold' }}>{label}</p>
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
}

function Chart({ data, lines, title, height = 180, onHide, threshold }: ChartProps) {
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
          <button className="chart-hide-btn" onClick={onHide} title="차트 숨기기">×</button>
        )}
      </div>
      <ResponsiveContainer width="100%" height={height}>
        <LineChart data={data} margin={{ top: 4, right: 8, bottom: 0, left: -16 }}>
          <CartesianGrid strokeDasharray="3 3" stroke={COLORS.border} />
          <XAxis dataKey="t" tick={{ fontSize: 9, fill: COLORS.muted }} tickFormatter={d => d} />
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
