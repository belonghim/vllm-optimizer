import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import { vi, describe, it, expect, beforeEach, afterEach } from "vitest";
import TunerCurrentConfig from "./TunerCurrentConfig";
import { MockDataProvider } from "../contexts/MockDataContext";
import { ClusterConfigProvider } from "../contexts/ClusterConfigContext";
import type { TunerConfig } from "../types";

vi.mock("./TunerConfigForm", () => ({
  default: ({ config, isRunning }: { config: TunerConfig; isRunning: boolean }) => (
    <div data-testid="tuner-config-form">
      <span data-testid="is-running">{String(isRunning)}</span>
    </div>
  ),
}));

vi.mock("./ConfirmDialog", () => ({
  default: () => null,
}));

const defaultConfig: TunerConfig = {
  objective: "tps",
  evaluation_mode: "single",
  n_trials: 10,
  vllm_endpoint: "http://test:8080",
  max_num_seqs_min: 64,
  max_num_seqs_max: 512,
  gpu_memory_min: 0.7,
  gpu_memory_max: 0.95,
  max_model_len_min: 2048,
  max_model_len_max: 8192,
  max_num_batched_tokens_min: 2048,
  max_num_batched_tokens_max: 8192,
  block_size_options: [16, 32],
  include_swap_space: false,
  swap_space_min: 0,
  swap_space_max: 4,
  eval_concurrency: 4,
  eval_rps: 0,
  eval_requests: 5,
};

const defaultProps = {
  isActive: false,
  isRunning: false,
  config: defaultConfig,
  onChange: vi.fn(),
  onSubmit: vi.fn(),
  onStop: vi.fn(),
  onApplyBest: vi.fn(),
  hasBest: false,
  currentPhase: null,
  trialsCompleted: 0,
  onError: vi.fn(),
  onApplySuccess: vi.fn(),
};

function renderWithProviders(ui: React.ReactElement) {
  return render(
    <MockDataProvider>
      <ClusterConfigProvider>{ui}</ClusterConfigProvider>
    </MockDataProvider>
  );
}

beforeEach(() => {
  vi.spyOn(Storage.prototype, "getItem").mockReturnValue(null);
  vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {});
  vi.spyOn(global, "fetch").mockResolvedValue({
    json: () => Promise.resolve({ vllm_endpoint: "", vllm_namespace: "", vllm_is_name: "" }),
  } as unknown as Response);
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("TunerCurrentConfig", () => {
  it("renders TunerConfigForm", () => {
    renderWithProviders(<TunerCurrentConfig {...defaultProps} />);
    expect(screen.getByTestId("tuner-config-form")).toBeInTheDocument();
  });

  it("passes isRunning=false to TunerConfigForm when not running", () => {
    renderWithProviders(<TunerCurrentConfig {...defaultProps} isRunning={false} />);
    expect(screen.getByTestId("is-running").textContent).toBe("false");
  });

  it("passes isRunning=true to TunerConfigForm when running", () => {
    renderWithProviders(<TunerCurrentConfig {...defaultProps} isRunning={true} />);
    expect(screen.getByTestId("is-running").textContent).toBe("true");
  });

  it("does not fetch vllm-config when isActive is false", async () => {
    const fetchSpy = vi.spyOn(global, "fetch");
    renderWithProviders(<TunerCurrentConfig {...defaultProps} isActive={false} />);
    await waitFor(() => {}, { timeout: 100 });
    // fetch might be called by ClusterConfigProvider, but not for /vllm-config
    const vllmConfigCalls = fetchSpy.mock.calls.filter(
      ([url]) => typeof url === "string" && url.includes("vllm-config")
    );
    expect(vllmConfigCalls.length).toBe(0);
  });
});
