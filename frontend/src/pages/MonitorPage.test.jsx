import { render, screen } from "@testing-library/react";
import { vi, describe, it, expect, beforeEach, afterEach } from "vitest";
import MonitorPage from "./MonitorPage";

// vi.mock must be at top level — vitest hoists these
vi.mock("../contexts/MockDataContext", () => ({
  useMockData: () => ({ isMockEnabled: true }),
}));

vi.mock("../contexts/ClusterConfigContext", () => {
  const targets = [{ namespace: "vllm-lab-dev", inferenceService: "llm-ov", isDefault: true }];
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
