import MetricCard from "./MetricCard";

export interface LatestMetrics {
  tps?: number | null;
  latency_p99?: number | null;
  ttft_mean?: number | null;
  kv_cache?: number | null;
  gpu_util?: number | null;
}

interface MonitorMetricCardsProps {
  latestMetrics: LatestMetrics | null | undefined;
  formatValue: (v: number | null | undefined, decimals?: number) => string;
}

function MonitorMetricCards({ latestMetrics, formatValue }: MonitorMetricCardsProps) {
  if (!latestMetrics) return null;
  return (
    <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', padding: '8px 0' }}>
      <MetricCard label="TPS" value={formatValue(latestMetrics.tps, 1)} unit="req/s" color="amber" />
      <MetricCard label="Latency P99" value={formatValue(latestMetrics.latency_p99)} unit="ms" color="red" />
      <MetricCard label="TTFT" value={formatValue(latestMetrics.ttft_mean)} unit="ms" color="cyan" />
      <MetricCard label="KV Cache" value={formatValue(latestMetrics.kv_cache, 1)} unit="%" color="purple" />
      <MetricCard label="GPU Util" value={formatValue(latestMetrics.gpu_util, 1)} unit="%" color="green" />
    </div>
  );
}

export default MonitorMetricCards;
