import { useThemeColors } from "../contexts/ThemeContext";
import { TARGET_COLORS } from "../constants";
import { BarChart, Bar, Cell, CartesianGrid, XAxis, YAxis, Tooltip, ResponsiveContainer } from "recharts";

export interface CompareDataItem {
  name: string;
  tps: number;
  ttft: number;
  p99: number;
  rps: number;
  gpuEff: number;
  metricsTargetMatched: boolean;
}

interface BenchmarkCompareChartsProps {
  compareData: CompareDataItem[];
}

export default function BenchmarkCompareCharts({ compareData }: BenchmarkCompareChartsProps) {
  const { COLORS, TOOLTIP_STYLE } = useThemeColors();

  return (
    <div className="panel">
      <div className="section-title">Comparison Charts</div>
      <div className="benchmark-compare-charts">
        <div>
          <div className="label">TPS Comparison</div>
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={compareData}>
              <CartesianGrid strokeDasharray="3 3" stroke={COLORS.border} />
              <XAxis dataKey="name" tick={{ fontSize: 9, fill: COLORS.muted }} />
              <YAxis tick={{ fontSize: 9, fill: COLORS.muted }} />
              <Tooltip contentStyle={TOOLTIP_STYLE} />
              <Bar dataKey="tps" name="TPS">
                {compareData.map((_, index) => (
                  <Cell key={index} fill={TARGET_COLORS[index % TARGET_COLORS.length]} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
        <div>
          <div className="label">P99 Latency Comparison (ms)</div>
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={compareData}>
              <CartesianGrid strokeDasharray="3 3" stroke={COLORS.border} />
              <XAxis dataKey="name" tick={{ fontSize: 9, fill: COLORS.muted }} />
              <YAxis tick={{ fontSize: 9, fill: COLORS.muted }} />
              <Tooltip contentStyle={TOOLTIP_STYLE} />
              <Bar dataKey="p99" name="P99 ms">
                {compareData.map((_, index) => (
                  <Cell key={index} fill={TARGET_COLORS[index % TARGET_COLORS.length]} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
        <div>
          <div className="label">GPU Efficiency Comparison (TPS/GPU%)</div>
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={compareData.filter(d => d.metricsTargetMatched)}>
              <CartesianGrid strokeDasharray="3 3" stroke={COLORS.border} />
              <XAxis dataKey="name" tick={{ fontSize: 9, fill: COLORS.muted }} />
              <YAxis tick={{ fontSize: 9, fill: COLORS.muted }} />
              <Tooltip contentStyle={TOOLTIP_STYLE} />
              <Bar dataKey="gpuEff" name="GPU Eff.">
                {compareData
                  .filter(d => d.metricsTargetMatched)
                  .map((item) => {
                    const index = compareData.indexOf(item);
                    return <Cell key={index} fill={TARGET_COLORS[index % TARGET_COLORS.length]} />;
                  })}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  );
}
