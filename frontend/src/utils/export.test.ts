import { describe, it, expect } from "vitest";
import { benchmarksToCSV, trialsToCSV } from "./export";

const makeBenchmark = (overrides: Record<string, unknown> = {}) => ({
  id: 1,
  name: "bench1",
  timestamp: 1700000000,
  config: { model: "qwen2-5-7b-instruct" },
  result: {
    tps: { mean: 42.5 },
    latency: { p99: 123 },
    ttft: { mean: 55 },
    rps_actual: 10,
  },
  ...overrides,
});

describe("benchmarksToCSV", () => {
  it("returns 7 headers", () => {
    const { headers } = benchmarksToCSV([makeBenchmark()]);
    expect(headers).toHaveLength(7);
  });

  it("returns one row per benchmark", () => {
    const { rows } = benchmarksToCSV([makeBenchmark(), makeBenchmark()]);
    expect(rows).toHaveLength(2);
  });

  it("null tps renders as empty string", () => {
    const bm = makeBenchmark({ result: { tps: null, latency: null, ttft: null, rps_actual: undefined } });
    const { rows } = benchmarksToCSV([bm as never]);
    expect(rows[0][2]).toBe("");
  });

  it("null latency renders as empty string", () => {
    const bm = makeBenchmark({ result: { tps: null, latency: null, ttft: null } });
    const { rows } = benchmarksToCSV([bm as never]);
    expect(rows[0][3]).toBe("");
  });

  it("null ttft renders as empty string", () => {
    const bm = makeBenchmark({ result: { tps: null, latency: null, ttft: null } });
    const { rows } = benchmarksToCSV([bm as never]);
    expect(rows[0][4]).toBe("");
  });
});

const makeTrial = (overrides: Record<string, unknown> = {}) => ({
  id: 1,
  tps: 100,
  p99_latency: 50,
  score: 0.8,
  params: { max_num_seqs: 64, gpu_memory_utilization: 0.9 },
  status: "complete",
  is_pareto_optimal: true,
  ...overrides,
});

describe("trialsToCSV", () => {
  it("includes param key max_num_seqs in headers", () => {
    const { headers } = trialsToCSV([makeTrial()]);
    expect(headers).toContain("max_num_seqs");
  });

  it("includes param key gpu_memory_utilization in headers", () => {
    const { headers } = trialsToCSV([makeTrial()]);
    expect(headers).toContain("gpu_memory_utilization");
  });

  it("converts is_pareto_optimal true to Y", () => {
    const { rows } = trialsToCSV([makeTrial({ is_pareto_optimal: true })]);
    expect(rows[0][5]).toBe("Y");
  });

  it("converts is_pareto_optimal false to N", () => {
    const { rows } = trialsToCSV([makeTrial({ is_pareto_optimal: false })]);
    expect(rows[0][5]).toBe("N");
  });

  it("collects param keys from all trials", () => {
    const t1 = makeTrial({ params: { alpha: 1 } });
    const t2 = makeTrial({ params: { beta: 2 } });
    const { headers } = trialsToCSV([t1, t2]);
    expect(headers).toContain("alpha");
    expect(headers).toContain("beta");
  });
});
