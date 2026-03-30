import { render, screen } from "@testing-library/react";
import { vi, describe, it, expect } from "vitest";
import TunerConfigSection from "./TunerConfigSection";
import type { TunerStatus, TunerConfig, TunerPhase } from "../types";

vi.mock("./TunerStatusPanel", () => ({
  default: (props: Record<string, unknown>) => (
    <div data-testid="tuner-status-panel">
      <span data-testid="status-error">{String(props.error)}</span>
      <span data-testid="status-warning">{String(props.warning)}</span>
      <span data-testid="status-apply">{String(props.applyStatus)}</span>
      <span data-testid="status-interrupted">{String(props.interruptedWarning)}</span>
      <span data-testid="status-auto-benchmark">{String(props.autoBenchmark)}</span>
      <span data-testid="status-benchmark-saved">{String(props.benchmarkSaved)}</span>
    </div>
  ),
}));

vi.mock("./TunerCurrentConfig", () => ({
  default: (props: Record<string, unknown>) => (
    <div data-testid="tuner-current-config">
      <span data-testid="config-is-active">{String(props.isActive)}</span>
      <span data-testid="config-is-running">{String(props.isRunning)}</span>
      <span data-testid="config-has-best">{String(props.hasBest)}</span>
      <span data-testid="config-trials">{String(props.trialsCompleted)}</span>
    </div>
  ),
}));

const defaultStatus: TunerStatus = {
  running: false,
  trials_completed: 0,
};

const defaultConfig: TunerConfig = {
  objective: "throughput",
  evaluation_mode: "single",
  n_trials: 10,
  vllm_endpoint: "http://localhost:8000",
  max_num_seqs_min: 16,
  max_num_seqs_max: 256,
  gpu_memory_min: 0.7,
  gpu_memory_max: 0.95,
  max_model_len_min: 512,
  max_model_len_max: 4096,
  max_num_batched_tokens_min: 256,
  max_num_batched_tokens_max: 8192,
  block_size_options: [16, 32],
  include_swap_space: false,
  swap_space_min: 0,
  swap_space_max: 8,
  eval_concurrency: 10,
  eval_rps: 5,
  eval_requests: 100,
};

const defaultProps = {
  isActive: true,
  status: defaultStatus,
  config: defaultConfig,
  error: null,
  warning: null,
  applyStatus: null,
  interruptedWarning: null,
  autoBenchmark: false,
  benchmarkSaved: false,
  benchmarkSavedId: null,
  currentPhase: null,
  onDismissInterrupted: vi.fn(),
  onAutoBenchmarkChange: vi.fn(),
  onTabChange: undefined,
  onConfigChange: vi.fn(),
  onStart: vi.fn(),
  onStop: vi.fn(),
  onApplyBest: vi.fn(),
  onError: vi.fn(),
  onApplySuccess: vi.fn(),
};

describe("TunerConfigSection", () => {
  it("renders TunerStatusPanel and TunerCurrentConfig", () => {
    render(<TunerConfigSection {...defaultProps} />);
    expect(screen.getByTestId("tuner-status-panel")).toBeInTheDocument();
    expect(screen.getByTestId("tuner-current-config")).toBeInTheDocument();
  });

  it("passes error to TunerStatusPanel", () => {
    render(<TunerConfigSection {...defaultProps} error="Connection failed" />);
    expect(screen.getByTestId("status-error")).toHaveTextContent("Connection failed");
  });

  it("passes null error to TunerStatusPanel", () => {
    render(<TunerConfigSection {...defaultProps} error={null} />);
    expect(screen.getByTestId("status-error")).toHaveTextContent("null");
  });

  it("passes warning to TunerStatusPanel", () => {
    render(<TunerConfigSection {...defaultProps} warning="Low memory" />);
    expect(screen.getByTestId("status-warning")).toHaveTextContent("Low memory");
  });

  it("passes interruptedWarning to TunerStatusPanel", () => {
    render(<TunerConfigSection {...defaultProps} interruptedWarning="Previous run interrupted" />);
    expect(screen.getByTestId("status-interrupted")).toHaveTextContent("Previous run interrupted");
  });

  it("passes applyStatus to TunerStatusPanel", () => {
    render(<TunerConfigSection {...defaultProps} applyStatus="success" />);
    expect(screen.getByTestId("status-apply")).toHaveTextContent("success");
  });

  it("passes autoBenchmark to TunerStatusPanel", () => {
    render(<TunerConfigSection {...defaultProps} autoBenchmark={true} />);
    expect(screen.getByTestId("status-auto-benchmark")).toHaveTextContent("true");
  });

  it("passes benchmarkSaved to TunerStatusPanel", () => {
    render(<TunerConfigSection {...defaultProps} benchmarkSaved={true} benchmarkSavedId={42} />);
    expect(screen.getByTestId("status-benchmark-saved")).toHaveTextContent("true");
  });

  it("passes isActive to TunerCurrentConfig", () => {
    render(<TunerConfigSection {...defaultProps} isActive={false} />);
    expect(screen.getByTestId("config-is-active")).toHaveTextContent("false");
  });

  it("passes running status to TunerCurrentConfig", () => {
    render(<TunerConfigSection {...defaultProps} status={{ ...defaultStatus, running: true }} />);
    expect(screen.getByTestId("config-is-running")).toHaveTextContent("true");
  });

  it("passes hasBest=false when status has no best", () => {
    render(<TunerConfigSection {...defaultProps} />);
    expect(screen.getByTestId("config-has-best")).toHaveTextContent("false");
  });

  it("passes hasBest=true when status has best", () => {
    const statusWithBest: TunerStatus = {
      ...defaultStatus,
      best: { tps: 100, p99_latency: 50 },
    };
    render(<TunerConfigSection {...defaultProps} status={statusWithBest} />);
    expect(screen.getByTestId("config-has-best")).toHaveTextContent("true");
  });

  it("passes trialsCompleted to TunerCurrentConfig", () => {
    render(<TunerConfigSection {...defaultProps} status={{ ...defaultStatus, trials_completed: 5 }} />);
    expect(screen.getByTestId("config-trials")).toHaveTextContent("5");
  });

  it("passes currentPhase to TunerCurrentConfig", () => {
    const phase: TunerPhase = { trial_id: 3, phase: "evaluation" };
    render(<TunerConfigSection {...defaultProps} currentPhase={phase} />);
    expect(screen.getByTestId("tuner-current-config")).toBeInTheDocument();
  });
});
