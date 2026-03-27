import toast, { Toaster } from "react-hot-toast";

export { Toaster };

export function showSlaViolation(metric: string, value: number, threshold: number): void {
  toast.error(
    `SLA 위반: ${metric} = ${value.toFixed(3)} (임계값: ${threshold})`,
    { duration: 5000, id: `sla-${metric}` }
  );
}
