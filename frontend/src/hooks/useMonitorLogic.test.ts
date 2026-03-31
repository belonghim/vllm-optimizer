import { vi, describe, it, expect, beforeEach, afterEach } from "vitest";
import { renderHook, act, waitFor } from "@testing-library/react";
import { useMonitorLogic } from "./useMonitorLogic";
import { authFetch } from "../utils/authFetch";

vi.mock("../contexts/MockDataContext", () => ({
  useMockData: () => ({ isMockEnabled: false }),
}));

const MOCK_TARGETS = vi.hoisted(() => [
  { namespace: "test-ns", inferenceService: "test-is", isDefault: true },
]);

vi.mock("../contexts/ClusterConfigContext", () => ({
  useClusterConfig: () => ({
    targets: MOCK_TARGETS,
    crType: "inferenceservice",
  }),
}));

vi.mock("../contexts/ThemeContext", () => ({
  useThemeColors: () => ({ COLORS: ["#ff0000"] }),
}));

vi.mock("../utils/authFetch", () => ({
  authFetch: vi.fn(),
}));

vi.mock("../utils/gapFill", () => ({
  buildGapFill: (data: unknown[]) => data,
}));

vi.mock("../components/Toast", () => ({
  showSlaViolation: vi.fn(),
}));

vi.mock("../components/MonitorChartGrid", () => ({
  buildChartLinesMap: () => ({}),
  loadChartConfig: () => ({ order: [], hidden: [] }),
  saveChartConfig: vi.fn(),
}));

vi.mock("../mockData", () => ({
  mockMetrics: () => ({}),
  mockHistory: () => [],
}));

function makeSuccessResponse() {
  return Promise.resolve({
    ok: true,
    json: async () => ({
      results: {
        "test-ns/test-is": {
          status: "ready",
          data: { tps: 10, latency_p99: 100 },
          history: [],
          hasMonitoringLabel: true,
        },
      },
    }),
  } as unknown as Response);
}

function setupDefaultFetch() {
  vi.mocked(authFetch).mockImplementation((url: string) => {
    if (url.includes("/sla/profiles")) {
      return Promise.resolve({ ok: true, json: async () => [] } as unknown as Response);
    }
    if (url.includes("/metrics/batch")) {
      return makeSuccessResponse();
    }
    return Promise.resolve({ ok: true, json: async () => ({}) } as unknown as Response);
  });
}

beforeEach(() => {
  setupDefaultFetch();
});

afterEach(() => {
  vi.clearAllMocks();
});

describe("useMonitorLogic", () => {
  it("starts with initialized=false and no error when isActive=false", () => {
    const { result } = renderHook(() => useMonitorLogic(false));

    expect(result.current.initialized).toBe(false);
    expect(result.current.error).toBeNull();
  });

  it("sets initialized=true after successful batch fetch when isActive=true", async () => {
    const { result } = renderHook(() => useMonitorLogic(true));

    await waitFor(() => {
      expect(result.current.initialized).toBe(true);
    });
    expect(result.current.error).toBeNull();
  });

  it("sets error when batch metrics fetch returns non-ok response", async () => {
    vi.mocked(authFetch).mockImplementation((url: string) => {
      if (url.includes("/sla/profiles")) {
        return Promise.resolve({ ok: true, json: async () => [] } as unknown as Response);
      }
      return Promise.resolve({
        ok: false,
        status: 500,
        json: async () => ({}),
      } as unknown as Response);
    });

    const { result } = renderHook(() => useMonitorLogic(true));

    await waitFor(() => {
      expect(result.current.error).not.toBeNull();
    });
    expect(result.current.error).toContain("Batch HTTP 500");
  });

  it("hideChart appends the chart id to hiddenCharts", () => {
    const { result } = renderHook(() => useMonitorLogic(false));

    act(() => {
      result.current.hideChart("tps");
    });

    expect(result.current.hiddenCharts).toContain("tps");
  });

  it("showChart removes chart id from hiddenCharts", () => {
    const { result } = renderHook(() => useMonitorLogic(false));

    act(() => {
      result.current.hideChart("latency");
    });
    expect(result.current.hiddenCharts).toContain("latency");

    act(() => {
      result.current.showChart("latency");
    });
    expect(result.current.hiddenCharts).not.toContain("latency");
  });
});
