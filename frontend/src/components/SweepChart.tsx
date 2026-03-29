import React from 'react';
import {
  ComposedChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ReferenceLine, ResponsiveContainer, DotProps
} from 'recharts';
import { useThemeColors } from '../contexts/ThemeContext';

export interface SweepStepResult {
  step: number;
  rps: number;
  stats: {
    latency: { p99: number; mean: number };
    tps: { mean: number };
    success: number;
    failed: number;
    total: number;
    rps_actual: number;
  };
  saturated: boolean;
  saturation_reason: string | null;
}

interface SweepChartProps {
  steps: SweepStepResult[];
  saturationRps?: number | null;
}

interface TooltipEntry {
  name: string;
  value: number;
  color: string;
  dataKey: string;
}

interface CustomTooltipProps {
  active?: boolean;
  payload?: TooltipEntry[];
  label?: string;
}

const CustomTooltip: React.FC<CustomTooltipProps> = ({ active, payload, label }) => {
  const { TOOLTIP_STYLE } = useThemeColors();
  if (active && payload && payload.length) {
    return (
      <div className="chart-tooltip" style={TOOLTIP_STYLE}>
        <p className="chart-tooltip-label">{`RPS: ${label}`}</p>
        {payload.map((pld) => (
          <p key={pld.dataKey} style={{ color: pld.color, margin: 0, fontSize: '11px' }}>
            {`${pld.name}: ${Number(pld.value).toFixed(2)}`}
          </p>
        ))}
      </div>
    );
  }
  return null;
};

interface CustomizedDotProps extends DotProps {
  payload?: Record<string, unknown>;
  value?: number;
  stroke?: string;
  saturated?: boolean;
}

const CustomizedDot: React.FC<CustomizedDotProps> = (props) => {
    const { cx, cy, stroke, payload, value, saturated } = props;
    const { COLORS } = useThemeColors();

    if (saturated) {
        return (
            <svg x={cx! - 5} y={cy! - 5} width={10} height={10} fill={COLORS.red} viewBox="0 0 1024 1024">
                <path d="M512 0C229.2 0 0 229.2 0 512s229.2 512 512 512 512-229.2 512-512S794.8 0 512 0z m0 960C264.7 960 64 759.3 64 512S264.7 64 512 64s448 200.7 448 448-200.7 448-448 448z" />
                <path d="M512 448c-35.3 0-64 28.7-64 64s28.7 64 64 64 64-28.7 64-64-28.7-64-64-64z" />
            </svg>
        );
    }

    return <circle cx={cx} cy={cy} r={3} stroke={stroke} fill="#fff" />;
};


const SweepChart: React.FC<SweepChartProps> = ({ steps, saturationRps }) => {
  const { COLORS } = useThemeColors();

  const chartData = steps.map(step => ({
    rps: step.rps,
    throughput: step.stats.tps.mean,
    p99_latency: step.stats.latency.p99 * 1000,
    saturated: step.saturated,
  }));

  return (
    <div className="panel" data-testid="sweep-chart">
      <div className="section-title">Sweep Visualization</div>
      <div
        style={{
          width: '100%',
          height: '30vh',
          minHeight: '220px',
          maxHeight: '420px',
        }}
      >
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart
            data={chartData}
            margin={{
              top: 5, right: 30, left: 20, bottom: 5,
            }}
          >
            <CartesianGrid strokeDasharray="3 3" stroke={COLORS.border} />
            <XAxis dataKey="rps" type="number" domain={['dataMin', 'dataMax']} tick={{ fontSize: 9, fill: COLORS.muted }} label={{ value: 'Target RPS', position: 'insideBottom', offset: -5, fill: COLORS.muted, fontSize: 10 }} />
            <YAxis yAxisId="left" stroke={COLORS.cyan} tick={{ fontSize: 9, fill: COLORS.cyan }} label={{ value: 'Throughput (TPS)', angle: -90, position: 'insideLeft', fill: COLORS.cyan, fontSize: 10 }} />
            <YAxis yAxisId="right" orientation="right" stroke={COLORS.accent} tick={{ fontSize: 9, fill: COLORS.accent }} label={{ value: 'P99 Latency (ms)', angle: 90, position: 'insideRight', fill: COLORS.accent, fontSize: 10 }} />
            <Tooltip content={<CustomTooltip />} />
            <Legend wrapperStyle={{ fontSize: '12px' }} />
            <Line yAxisId="left" type="monotone" dataKey="throughput" stroke={COLORS.cyan} name="Throughput" dot={(props) => <CustomizedDot {...props} saturated={props.payload.saturated} />} />
            <Line yAxisId="right" type="monotone" dataKey="p99_latency" stroke={COLORS.accent} name="P99 Latency" dot={(props) => <CustomizedDot {...props} saturated={props.payload.saturated} />} />
            {saturationRps != null && (
              <ReferenceLine
                x={saturationRps}
                yAxisId="left"
                stroke={COLORS.red}
                strokeDasharray="3 3"
                label={{ value: 'Saturation', position: 'top', fill: COLORS.red, fontSize: 10 }}
              />
            )}
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
};

export default SweepChart;
