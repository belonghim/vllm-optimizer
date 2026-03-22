/**
 * Calculates GPU efficiency (TPS per GPU utilization %).
 * @param {object|null} result - Load test result object
 * @returns {{ value: number|null, display: string, mismatch: boolean }}
 */
export function calcGpuEfficiency(result) {
  if (result?.metrics_target_matched === false) {
    return { value: null, display: 'N/A', mismatch: true };
  }
  if (!result?.gpu_utilization_avg || result.gpu_utilization_avg <= 0) {
    return { value: null, display: '—', mismatch: false };
  }
  const eff = result.tps.mean / result.gpu_utilization_avg;
  return { value: eff, display: eff.toFixed(1), mismatch: false };
}
