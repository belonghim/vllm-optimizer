import { render, screen } from "@testing-library/react";
import { vi, describe, it, expect, beforeEach, afterEach } from "vitest";
import MonitorPage, { buildChartLinesMap } from "./MonitorPage";
import { COLORS, TARGET_COLORS } from "../constants";

// vi.mock must be at top level — vitest hoists these
vi.mock("../contexts/MockDataContext", () => ({
  useMockData: () => ({ isMockEnabled: true }),
}));

vi.mock("../contexts/ClusterConfigContext", () => {
  const targets = [{ namespace: "llm-d-demo", inferenceService: "small-llm-d", isDefault: true }];
  return {
    useClusterConfig: () => ({
      targets,
      maxTargets: 5,
      addTarget: vi.fn(),
      removeTarget: vi.fn(),
    }),
  };
});

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["setInterval", "clearInterval", "setTimeout", "clearTimeout"] });
  global.ResizeObserver = class ResizeObserver {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

describe("MonitorPage", () => {
  it("renders without crashing", () => {
    render(<MonitorPage />);
    expect(screen.getByText("모니터링 대상 (1/5)")).toBeInTheDocument();
  });

  it("renders 9 chart titles", () => {
    render(<MonitorPage />);
    expect(screen.getByText("Throughput (TPS)")).toBeInTheDocument();
    expect(screen.getByText("Latency (ms)")).toBeInTheDocument();
    expect(screen.getByText("TTFT (ms)")).toBeInTheDocument();
    expect(screen.getByText("GPU Memory (GB)")).toBeInTheDocument();
  });

  it("does not show error banner in mock mode", () => {
    render(<MonitorPage />);
    expect(screen.queryByText(/조회 실패/)).not.toBeInTheDocument();
  });

  it("renders table with metric column headers", () => {
    render(<MonitorPage />);
    expect(screen.getByText("TPS")).toBeInTheDocument();
    expect(screen.getByText("RPS")).toBeInTheDocument();
    expect(screen.getByText("GPU%")).toBeInTheDocument();
  });
});

describe("buildChartLinesMap", () => {
  it("single target returns detailed multi-line definitions with COLORS", () => {
    const targets = [{ namespace: "ns1", inferenceService: "svc1", isDefault: true }];
    const defaultKey = "ns1/svc1";
    const result = buildChartLinesMap(targets, defaultKey);

    expect(result.latency).toHaveLength(3);
    expect(result.latency[0]).toEqual({ key: "ns1/svc1_lat_p99_fill", color: COLORS.red, label: "P99 (idle)", dash: true });
    expect(result.latency[1]).toEqual({ key: "ns1/svc1_lat_p99", color: COLORS.red, label: "Latency P99" });
    expect(result.latency[2]).toEqual({ key: "ns1/svc1_lat_mean", color: COLORS.accent, label: "Latency mean" });

    expect(result.ttft).toHaveLength(3);
    expect(result.ttft[1].color).toBe(COLORS.cyan);

    expect(result.queue).toHaveLength(2);
    expect(result.queue[0].label).toBe("Running");
    expect(result.queue[1].label).toBe("Waiting");

    expect(result.tps).toEqual([{ key: "ns1/svc1_tps", color: COLORS.accent, label: "TPS" }]);
  });

  it("multiple targets returns makeMultiLines with TARGET_COLORS", () => {
    const targets = [
      { namespace: "ns1", inferenceService: "svc1" },
      { namespace: "ns2", inferenceService: "svc2" },
      { namespace: "ns3", inferenceService: "svc3" },
    ];
    const defaultKey = "ns1/svc1";
    const result = buildChartLinesMap(targets, defaultKey);

    expect(result.tps).toHaveLength(3);
    expect(result.latency).toHaveLength(3);
    expect(result.gpu_util).toHaveLength(3);

    expect(result.tps[0]).toEqual({ key: "ns1/svc1_tps", label: "svc1", color: TARGET_COLORS[0] });
    expect(result.tps[1]).toEqual({ key: "ns2/svc2_tps", label: "svc2", color: TARGET_COLORS[1] });
    expect(result.tps[2]).toEqual({ key: "ns3/svc3_tps", label: "svc3", color: TARGET_COLORS[2] });

    expect(result.latency[0].key).toBe("ns1/svc1_lat_p99");
    expect(result.latency[1].key).toBe("ns2/svc2_lat_p99");
  });

  it("empty targets returns object with empty arrays", () => {
    const result = buildChartLinesMap([], null);

    expect(result.tps).toEqual([]);
    expect(result.latency).toEqual([]);
    expect(result.ttft).toEqual([]);
    expect(result.kv).toEqual([]);
    expect(result.kv_hit).toEqual([]);
    expect(result.queue).toEqual([]);
    expect(result.rps).toEqual([]);
    expect(result.gpu_util).toEqual([]);
    expect(result.gpu_mem).toEqual([]);
  });
});
