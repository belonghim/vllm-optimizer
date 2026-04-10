import "@testing-library/jest-dom";
import { render, screen, fireEvent } from "@testing-library/react";
import { vi, describe, it, expect, beforeEach } from "vitest";
import TunerResults from "./TunerResults";
import * as exportUtils from "../utils/export";

vi.mock("recharts", () => ({
  ScatterChart: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="scatter-chart">{children}</div>
  ),
  Scatter: () => null,
  CartesianGrid: () => null,
  XAxis: () => null,
  YAxis: () => null,
  Tooltip: () => null,
  ResponsiveContainer: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="responsive-container">{children}</div>
  ),
  LineChart: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="line-chart">{children}</div>
  ),
  Line: () => null,
}));

vi.mock("../utils/export", () => ({
  downloadJSON: vi.fn(),
  downloadCSV: vi.fn(),
  trialsToCSV: vi.fn(() => ({ headers: [], rows: [] })),
}));

const baseStatus = {
  running: false,
  trials_completed: 0,
};

const sampleTrial = {
  id: 1,
  tps: 120.5,
  p99_latency: 450,
  score: 0.85,
  params: { max_num_seqs: 64 },
  status: "complete",
  is_pareto_optimal: false,
};

describe("TunerResults", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders nothing notable when trials is empty and no bestParams", () => {
    render(
      <TunerResults
        trials={[]}
        bestParams={undefined}
        status={baseStatus}
        isRunning={false}
        importance={{}}
      />
    );
    expect(screen.queryByText("Export Results")).not.toBeInTheDocument();
    expect(screen.queryByText("Best Parameters Found")).not.toBeInTheDocument();
  });

  it("shows export buttons when trials exist", () => {
    render(
      <TunerResults
        trials={[sampleTrial]}
        bestParams={undefined}
        status={baseStatus}
        isRunning={false}
        importance={{}}
      />
    );
    expect(screen.getByText("Export Results")).toBeInTheDocument();
    expect(screen.getByText("Export JSON")).toBeInTheDocument();
    expect(screen.getByText("Export CSV")).toBeInTheDocument();
  });

  it("renders best parameters section when bestParams is provided", () => {
    const bestParams = {
      tps: 120.5,
      p99_latency: 450,
      params: { max_num_seqs: 64, gpu_memory_utilization: 0.9 },
    };
    render(
      <TunerResults
        trials={[]}
        bestParams={bestParams}
        status={baseStatus}
        isRunning={false}
        importance={{}}
      />
    );
    expect(screen.getByText("Best Parameters Found")).toBeInTheDocument();
    expect(screen.getByText("Best TPS")).toBeInTheDocument();
    expect(screen.getByText("E2E Latency P99")).toBeInTheDocument();
  });

  it("renders best params table with parameter names and values", () => {
    const bestParams = {
      tps: 100,
      p99_latency: 300,
      params: { max_num_seqs: 64, gpu_memory_utilization: 0.9 },
    };
    render(
      <TunerResults
        trials={[]}
        bestParams={bestParams}
        status={baseStatus}
        isRunning={false}
        importance={{}}
      />
    );
    expect(screen.getByText("max_num_seqs")).toBeInTheDocument();
    expect(screen.getByText("64")).toBeInTheDocument();
    expect(screen.getByText("gpu_memory_utilization")).toBeInTheDocument();
    expect(screen.getByText("0.9")).toBeInTheDocument();
  });

  it("renders parameter importance section when importance is non-empty", () => {
    render(
      <TunerResults
        trials={[]}
        bestParams={undefined}
        status={baseStatus}
        isRunning={false}
        importance={{ max_num_seqs: 0.7, gpu_memory_utilization: 0.3 }}
      />
    );
    expect(screen.getByText("Parameter Importance (FAnova)")).toBeInTheDocument();
    expect(screen.getByText("max_num_seqs")).toBeInTheDocument();
  });

  it("does not render parameter importance when importance is empty", () => {
    render(
      <TunerResults
        trials={[]}
        bestParams={undefined}
        status={baseStatus}
        isRunning={false}
        importance={{}}
      />
    );
    expect(screen.queryByText("Parameter Importance (FAnova)")).not.toBeInTheDocument();
  });

  it("calls downloadJSON when Export JSON is clicked", () => {
    render(
      <TunerResults
        trials={[sampleTrial]}
        bestParams={undefined}
        status={baseStatus}
        isRunning={false}
        importance={{}}
      />
    );
    fireEvent.click(screen.getByText("Export JSON"));
    expect(exportUtils.downloadJSON).toHaveBeenCalled();
  });
});
