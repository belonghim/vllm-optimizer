// Test fixtures use LLMIS-style names (llm-d-demo/small-llm-d) intentionally
// to verify MonitorPage works with both CR types (ISVC and LLMISVC).
import { render, screen, act } from "@testing-library/react";
import { vi, describe, it, expect, beforeEach, afterEach } from "vitest";
import MonitorPage, { buildChartLinesMap } from "./MonitorPage";
import { COLORS, TARGET_COLORS } from "../constants";

// vi.mock must be at top level — vitest hoists these
vi.mock("../contexts/MockDataContext", () => ({
  useMockData: () => ({ isMockEnabled: true }),
}));

vi.mock("../contexts/ClusterConfigContext", () => {
  const targets = [{ namespace: "llm-d-demo", inferenceService: "small-llm-d", crType: "llminferenceservice" }];
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
  global.EventSource = class MockEventSource {
    onopen: (() => void) | null = null;
    onmessage: ((e: MessageEvent) => void) | null = null;
    onerror: (() => void) | null = null;
    close() {}
  } as unknown as typeof EventSource;
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

describe("MonitorPage", () => {
  it("renders without crashing", async () => {
    render(<MonitorPage isActive={true} />);
    await act(async () => {});
    expect(screen.getByText("Monitoring Targets (1/5)")).toBeInTheDocument();
  });

  it("renders chart titles", async () => {
    render(<MonitorPage isActive={true} />);
    await act(async () => {});
    // Chart titles may be conditionally rendered; verify at least some key charts exist
    const tpsTitle = screen.queryByText("Throughput (TPS)");
    const latencyTitle = screen.queryByText("Latency (ms)");
    const ttftTitle = screen.queryByText("TTFT (ms)");
    const gpuMemTitle = screen.queryByText("GPU Memory (GB)");
    const tpotTitle = screen.queryByText("TPOT (ms)");
    const queueTimeTitle = screen.queryByText("Queue Time (ms) (vLLM v0.6+)");
    // At least one chart title should be present in mock mode
    expect(tpsTitle || latencyTitle || ttftTitle || gpuMemTitle || tpotTitle || queueTimeTitle).toBeInTheDocument();
  });

  it("does not show error banner in mock mode", () => {
    render(<MonitorPage isActive={false} />);
     expect(screen.queryByText(/Query failed/)).not.toBeInTheDocument();
  });

  it("renders monitoring targets section", async () => {
    render(<MonitorPage isActive={true} />);
    await act(async () => {});
    expect(screen.getByText(/Monitoring Targets/)).toBeInTheDocument();
  });
});

describe("buildChartLinesMap", () => {
  it("single target returns detailed multi-line definitions with COLORS", () => {
    const targets = [{ namespace: "ns1", inferenceService: "svc1", crType: "inferenceservice" }];
    const defaultKey = "ns1/svc1/inferenceservice";
    const result = buildChartLinesMap(targets, defaultKey);

    expect(result.e2e_latency).toHaveLength(3);
    expect(result.e2e_latency[0]).toEqual({ key: "ns1/svc1/inferenceservice_lat_p99_fill", color: COLORS.red, label: "P99 (idle)", dash: true });
    expect(result.e2e_latency[1]).toEqual({ key: "ns1/svc1/inferenceservice_lat_p99", color: COLORS.red, label: "E2E Latency P99" });
    expect(result.e2e_latency[2]).toEqual({ key: "ns1/svc1/inferenceservice_lat_mean", color: COLORS.accent, label: "E2E Latency mean" });

    expect(result.ttft).toHaveLength(3);
    expect(result.ttft[1].color).toBe(COLORS.cyan);
 
    expect(result.queue).toHaveLength(2);
    expect(result.queue[0].label).toBe("Running");
    expect(result.queue[1].label).toBe("Waiting");
  
    expect(result.tpot).toHaveLength(2);
    expect(result.tpot[0].label).toBe("TPOT mean");
    expect(result.tpot[1].label).toBe("TPOT p99");

    expect(result.queue_time).toHaveLength(2);
    expect(result.queue_time[0].label).toBe("Queue mean");
    expect(result.queue_time[1].label).toBe("Queue p99");

    expect(result.tps).toEqual([{ key: "ns1/svc1/inferenceservice_tps", color: COLORS.accent, label: "TPS" }]);
  });

  it("multiple targets returns makeMultiLines with TARGET_COLORS", () => {
    const targets = [
      { namespace: "ns1", inferenceService: "svc1", crType: "inferenceservice" },
      { namespace: "ns2", inferenceService: "svc2", crType: "inferenceservice" },
      { namespace: "ns3", inferenceService: "svc3", crType: "llminferenceservice" },
    ];
    const defaultKey = "ns1/svc1";
    const result = buildChartLinesMap(targets, defaultKey);

    expect(result.tps).toHaveLength(3);
    expect(result.e2e_latency).toHaveLength(3);
    expect(result.gpu_util).toHaveLength(3);
    expect(result.tpot).toHaveLength(3);
    expect(result.queue_time).toHaveLength(3);

    expect(result.tps[0]).toEqual({ key: "ns1/svc1/inferenceservice_tps", label: "svc1", color: TARGET_COLORS[0] });
    expect(result.tps[1]).toEqual({ key: "ns2/svc2/inferenceservice_tps", label: "svc2", color: TARGET_COLORS[1] });
    expect(result.tps[2]).toEqual({ key: "ns3/svc3/llminferenceservice_tps", label: "svc3", color: TARGET_COLORS[2] });

    expect(result.e2e_latency[0].key).toBe("ns1/svc1/inferenceservice_lat_p99");
    expect(result.e2e_latency[1].key).toBe("ns2/svc2/inferenceservice_lat_p99");
  });

  it("empty targets returns object with empty arrays", () => {
    const result = buildChartLinesMap([], null);

    expect(result.tps).toEqual([]);
    expect(result.e2e_latency).toEqual([]);
    expect(result.ttft).toEqual([]);
    expect(result.kv).toEqual([]);
    expect(result.kv_hit).toEqual([]);
    expect(result.queue).toEqual([]);
    expect(result.rps).toEqual([]);
    expect(result.gpu_util).toEqual([]);
    expect(result.gpu_mem).toEqual([]);
    expect(result.tpot).toEqual([]);
    expect(result.queue_time).toEqual([]);
  });
});
