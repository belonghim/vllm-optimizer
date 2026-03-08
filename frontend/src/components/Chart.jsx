import { COLORS } from '../constants';
import {
  LineChart, Line, AreaChart, Area, BarChart, Bar,
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend,
  ScatterChart, Scatter, ReferenceLine,
} from 'recharts';

function Chart({ data, lines, title, height = 180 }) {
  return (
    <div style={{ background: COLORS.surface, border: `1px solid ${COLORS.border}`, padding: 16 }}>
      <div className="section-title">{title}</div>
      <ResponsiveContainer width="100%" height={height}>
        <LineChart data={data} margin={{ top: 4, right: 8, bottom: 0, left: -16 }}>
          <CartesianGrid strokeDasharray="3 3" stroke={COLORS.border} />
          <XAxis dataKey="t" tick={{ fontSize: 9, fill: COLORS.muted }} tickFormatter={d => d} />
          <YAxis tick={{ fontSize: 9, fill: COLORS.muted }} />
          <Tooltip
            contentStyle={{ background: COLORS.surface, border: `1px solid ${COLORS.border}`, fontSize: 11 }}
            labelStyle={{ color: COLORS.muted }}
          />
           {lines.map(l => (
             <Line key={l.key} type="monotone" dataKey={l.key} stroke={l.color}
               dot={false} strokeWidth={1.5} name={l.label} connectNulls={true} />
           ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

export default Chart;