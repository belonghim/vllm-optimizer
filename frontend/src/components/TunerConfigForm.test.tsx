import "@testing-library/jest-dom";
import { render, screen, fireEvent } from "@testing-library/react";
import { vi, describe, it, expect, beforeEach } from "vitest";
import TunerConfigForm from "./TunerConfigForm";

vi.mock("./TunerProgressBar", () => ({ default: () => null }));

const baseConfig = {
  objective: "balanced",
  n_trials: 10,
  vllm_endpoint: "",
  max_num_seqs_min: 1,
  max_num_seqs_max: 256,
  gpu_memory_min: 0.5,
  gpu_memory_max: 0.95,
  max_model_len_min: 256,
  max_model_len_max: 8192,
  max_num_batched_tokens_min: 256,
  max_num_batched_tokens_max: 4096,
  block_size_options: [16],
  include_swap_space: false,
  swap_space_min: 0,
  swap_space_max: 16,
  eval_concurrency: 10,
  eval_rps: 5,
  eval_requests: 100,
};

const baseProps = {
  config: baseConfig,
  onChange: vi.fn(),
  onSubmit: vi.fn(),
  onStop: vi.fn(),
  onApplyBest: vi.fn(),
  isRunning: false,
  hasBest: false,
  currentConfig: null as Record<string, unknown> | null,
  currentPhase: null,
  trialsCompleted: 0,
  storageUri: null,
  onSaveStorageUri: vi.fn(),
};

describe("TunerConfigForm", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders without crashing", () => {
    render(<TunerConfigForm {...baseProps} />);
    expect(screen.getByText("▶ Start Tuning")).toBeInTheDocument();
  });

  it("shows em dash spans when currentConfig is null", () => {
    render(<TunerConfigForm {...baseProps} currentConfig={null} />);
    const dashes = screen.getAllByText("—");
    expect(dashes.length).toBeGreaterThan(0);
  });

  it("shows inputs instead of dashes when currentConfig is provided", () => {
    const currentConfig = {
      max_num_seqs: 64,
      gpu_memory_utilization: 0.9,
      max_model_len: 4096,
      max_num_batched_tokens: 2048,
      block_size: 16,
      swap_space: 0,
      enable_chunked_prefill: true,
      enable_enforce_eager: false,
    };
    render(<TunerConfigForm {...baseProps} currentConfig={currentConfig} />);
    expect(screen.queryAllByText("—")).toHaveLength(7);
  });

   it("Apply Current Values button is disabled when editedValues is empty", () => {
    const currentConfig = {
      max_num_seqs: 64,
      gpu_memory_utilization: 0.9,
      max_model_len: 4096,
      max_num_batched_tokens: 2048,
      block_size: 16,
      swap_space: 0,
    };
    render(
      <TunerConfigForm
        {...baseProps}
        currentConfig={currentConfig}
        onApplyCurrentValues={vi.fn()}
      />
    );
     expect(screen.getByText("Apply Current Values")).toBeDisabled();
  });

   it("Apply Current Values button enables after changing a currentConfig input", () => {
    const currentConfig = {
      max_num_seqs: 64,
      gpu_memory_utilization: 0.9,
      max_model_len: 4096,
      max_num_batched_tokens: 2048,
      block_size: 16,
      swap_space: 0,
    };
    render(
      <TunerConfigForm
        {...baseProps}
        currentConfig={currentConfig}
        onApplyCurrentValues={vi.fn()}
      />
    );
     const btn = screen.getByText("Apply Current Values");
    expect(btn).toBeDisabled();

    // Find the max_num_seqs input (value "64") and change it
    const spinbuttons = screen.getAllByRole("spinbutton") as HTMLInputElement[];
    const maxNumSeqsInput = spinbuttons.find((el) => el.value === "64");
    expect(maxNumSeqsInput).toBeDefined();
    fireEvent.change(maxNumSeqsInput!, { target: { value: "128" } });

    expect(btn).not.toBeDisabled();
  });

   it("does not render Apply Current Values button when onApplyCurrentValues is not provided", () => {
     render(<TunerConfigForm {...baseProps} currentConfig={{ max_num_seqs: 64 }} />);
     expect(screen.queryByText("Apply Current Values")).not.toBeInTheDocument();
  });

  it("resource rows show dash in range column", () => {
    const currentConfig = {
      max_num_seqs: 64,
      gpu_memory_utilization: 0.9,
      max_model_len: 4096,
      max_num_batched_tokens: 2048,
      block_size: 16,
      swap_space: 0,
      enable_chunked_prefill: true,
      enable_enforce_eager: false,
    };
    render(<TunerConfigForm {...baseProps} currentConfig={currentConfig} />);
    // 2 boolean range dashes + 5 resource range dashes = 7
    expect(screen.queryAllByText("—")).toHaveLength(7);
  });

  it("resource inputs show values from currentResources", () => {
    const currentConfig = {
      max_num_seqs: 64,
      gpu_memory_utilization: 0.9,
      max_model_len: 4096,
      max_num_batched_tokens: 2048,
      block_size: 16,
      swap_space: 0,
    };
    const currentResources = {
      requests: { cpu: "4" },
      limits: { memory: "16Gi" },
    };
    render(
      <TunerConfigForm
        {...baseProps}
        currentConfig={currentConfig}
        currentResources={currentResources}
      />
    );
     const cpuReqInput = screen.getByPlaceholderText("e.g. 4, 500m") as HTMLInputElement;
    expect(cpuReqInput.value).toBe("4");
     const memLimInput = screen.getByPlaceholderText("e.g. 16Gi") as HTMLInputElement;
    expect(memLimInput.value).toBe("16Gi");
  });
});
