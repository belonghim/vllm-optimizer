import { COLORS } from '../constants';
import {
  LineChart, Line,
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from 'recharts';

const CustomTooltip = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null;
  const visible = payload.filter(e => !String(e.dataKey).endsWith('_fill'));
  if (!visible.length) return null;
  return (
    <div className="chart-tooltip">
      <p className="chart-tooltip-label">{label}</p>
      {visible.map(e => {
        const entryStyle = { color: e.color };
        return (
          <p key={e.dataKey} className="chart-tooltip-entry" style={entryStyle}>{e.name}: {e.value != null ? Number(e.value).toFixed(1) : '—'}</p>
        );
      })}
    </div>
  );
};

function Chart({ data, lines, title, height = 180, onHide }) {
  return (
    <div className="chart-container" aria-label={title}>
      <div className="section-title" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span>{title}</span>
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

export default Chart;
