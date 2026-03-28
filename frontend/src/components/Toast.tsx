import toast, { Toaster } from "react-hot-toast";

export { Toaster };

export function showSlaViolation(metric: string, value: number, threshold: number): void {
  toast.error(
    `SLA violation: ${metric} = ${value.toFixed(3)} (threshold: ${threshold})`,
    { duration: 5000, id: `sla-${metric}` }
  );
}
