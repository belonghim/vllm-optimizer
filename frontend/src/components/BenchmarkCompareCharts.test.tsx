import { render, screen } from "@testing-library/react";
import { vi, describe, it, expect, beforeEach, afterEach } from "vitest";
import BenchmarkCompareCharts from "./BenchmarkCompareCharts";
import type { CompareDataItem } from "./BenchmarkCompareCharts";

function makeItem(name: string, metricsTargetMatched = true): CompareDataItem {
  return { name, tps: 50, ttft: 100, p99: 200, rps: 5, gpuEff: 1.5, metricsTargetMatched };
}

beforeEach(() => {
  global.ResizeObserver = class ResizeObserver {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
});

afterEach(() => {
  vi.clearAllMocks();
});

describe("BenchmarkCompareCharts", () => {
  it("renders all three chart section titles", () => {
    render(<BenchmarkCompareCharts compareData={[makeItem("Run A")]} />);
    expect(screen.getByText("TPS Comparison")).toBeInTheDocument();
    expect(screen.getByText("P99 Latency Comparison (ms)")).toBeInTheDocument();
    expect(screen.getByText("GPU Efficiency Comparison (TPS/GPU%)")).toBeInTheDocument();
  });

  it("renders without crashing when compareData is empty", () => {
    render(<BenchmarkCompareCharts compareData={[]} />);
    expect(screen.getByText("Comparison Charts")).toBeInTheDocument();
    expect(screen.getByText("TPS Comparison")).toBeInTheDocument();
  });

  it("renders with multiple data items", () => {
    const data = [makeItem("Run A"), makeItem("Run B"), makeItem("Run C", false)];
    render(<BenchmarkCompareCharts compareData={data} />);
    expect(screen.getByText("Comparison Charts")).toBeInTheDocument();
    expect(screen.getByText("TPS Comparison")).toBeInTheDocument();
  });
});
