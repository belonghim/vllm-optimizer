interface GpuEfficiencyResult {
  value: number | null;
  display: string;
  mismatch: boolean;
}

interface LoadTestResultInput {
  metrics_target_matched?: boolean;
  gpu_utilization_avg?: number | null;
  tps?: { mean?: number | null } | null;
}

/**
 * Calculates GPU efficiency (TPS per GPU utilization %).
 * @param result - Load test result object
 * @returns GPU efficiency metrics
 */
export function calcGpuEfficiency(result: LoadTestResultInput | null | undefined): GpuEfficiencyResult {
  if (result?.metrics_target_matched === false) {
    return { value: null, display: 'N/A', mismatch: true };
  }
  if (!result?.gpu_utilization_avg || result.gpu_utilization_avg <= 0) {
    return { value: null, display: '—', mismatch: false };
  }
  const eff = result.tps!.mean! / result.gpu_utilization_avg;
  return { value: eff, display: eff.toFixed(1), mismatch: false };
}
