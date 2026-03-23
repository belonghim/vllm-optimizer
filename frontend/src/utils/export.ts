interface BenchmarkMetadata {
  model_identifier?: string | null;
  hardware_type?: string | null;
  runtime?: string | null;
  vllm_version?: string | null;
  replica_count?: number | null;
  notes?: string | null;
  extra?: Record<string, string>;
}

interface BenchmarkConfig {
  model?: string;
  [key: string]: unknown;
}

interface BenchmarkResultData {
  tps?: { mean?: number } | null;
  latency?: { p99?: number } | null;
  ttft?: { mean?: number } | null;
  rps_actual?: number;
  gpu_utilization_avg?: number | null;
  metrics_target_matched?: boolean;
}

interface Benchmark {
  id: string | number;
  name: string;
  timestamp: number;
  config?: BenchmarkConfig;
  result: BenchmarkResultData;
  metadata?: BenchmarkMetadata | null;
}

interface Trial {
  id: number;
  tps: number;
  p99_latency: number;
  score: number;
  params: Record<string, unknown>;
  status: string;
  is_pareto_optimal?: boolean;
}

function escapeCsv(value: unknown): string {
  if (value == null) return "";
  const str = String(value);
  if (str.includes(",") || str.includes('"') || str.includes("\n")) {
    return `"${str.replace(/"/g, '""')}"`;
  }
  return str;
}

export function downloadJSON(data: unknown, filename: string): void {
  const jsonStr = JSON.stringify(data, null, 2);
  const blob = new Blob([jsonStr], { type: "application/json" });
  const url = URL.createObjectURL(blob);

  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}

export function downloadCSV(
  headers: string[],
  rows: string[][],
  filename: string
): void {
  const headerRow = headers.map(escapeCsv).join(",");
  const dataRows = rows.map((row) => row.map(escapeCsv).join(",")).join("\n");
  const csv = headerRow + "\n" + dataRows;

  // UTF-8 BOM for Excel to display Korean correctly
  const bomCSV = "\uFEFF" + csv;
  const blob = new Blob([bomCSV], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);

  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}

export function benchmarksToCSV(
  benchmarks: Benchmark[]
): { headers: string[]; rows: string[][] } {
  const headers = [
    "이름",
    "날짜",
    "TPS(mean)",
    "P99 Latency(ms)",
    "TTFT(ms)",
    "RPS",
    "모델",
  ];

  const rows = benchmarks.map((benchmark) => {
    const date = new Date(benchmark.timestamp * 1000).toLocaleString(
      "ko-KR"
    );
    const tpsMean = benchmark.result.tps?.mean ?? "";
    const latencyP99 = benchmark.result.latency?.p99 ?? "";
    const ttftMean = benchmark.result.ttft?.mean ?? "";
    const rpsActual = benchmark.result.rps_actual ?? "";
    const model = benchmark.config?.model ?? "";

    return [
      String(benchmark.name),
      String(date),
      String(tpsMean),
      String(latencyP99),
      String(ttftMean),
      String(rpsActual),
      String(model),
    ];
  });

  return { headers, rows };
}

export function trialsToCSV(
  trials: Trial[]
): { headers: string[]; rows: string[][] } {
  const paramKeys = new Set<string>();
  trials.forEach((trial) => {
    Object.keys(trial.params).forEach((key) => paramKeys.add(key));
  });
  const sortedParamKeys = Array.from(paramKeys).sort();

  const headers = [
    "Trial ID",
    "TPS",
    "P99 Latency(ms)",
    "Score",
    "Status",
    "Pareto",
    ...sortedParamKeys,
  ];

  const rows = trials.map((trial) => {
    const baseRow = [
      String(trial.id),
      String(trial.tps),
      String(trial.p99_latency),
      String(trial.score),
      String(trial.status),
      trial.is_pareto_optimal ? "Y" : "N",
    ];

    const paramValues = sortedParamKeys.map((key) => {
      const value = trial.params[key];
      if (typeof value === "object" && value !== null) {
        return JSON.stringify(value);
      }
      return String(value ?? "");
    });

    return [...baseRow, ...paramValues];
  });

  return { headers, rows };
}
