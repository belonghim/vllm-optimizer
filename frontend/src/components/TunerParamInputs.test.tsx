import React from "react";
import { render, screen } from "@testing-library/react";
import { vi, describe, it, expect } from "vitest";
import TunerParamInputs from "./TunerParamInputs";
import type { TunerConfig } from "./TunerConfigForm";

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

const baseProps = {
  config: defaultConfig,
  onChange: vi.fn(),
  editedValues: {},
  currentConfig: null,
  handleChange: vi.fn(),
};

describe("TunerParamInputs", () => {
  it("renders without crashing when currentConfig is null", () => {
    render(<TunerParamInputs {...baseProps} />);
    expect(document.body).toBeTruthy();
  });

  it("shows dash placeholders when currentConfig is null", () => {
    render(<TunerParamInputs {...baseProps} />);
    const dashes = screen.getAllByText("—");
    expect(dashes.length).toBeGreaterThan(0);
  });

  it("renders input fields when currentConfig is provided", () => {
    render(
      <TunerParamInputs
        {...baseProps}
        currentConfig={{ max_num_seqs: "256", max_model_len: "4096" }}
      />
    );
    const inputs = screen.getAllByRole("spinbutton");
    expect(inputs.length).toBeGreaterThan(0);
  });

  it("uses editedValues over currentConfig when key exists", () => {
    render(
      <TunerParamInputs
        {...baseProps}
        currentConfig={{ max_num_seqs: "256" }}
        editedValues={{ max_num_seqs: "128" }}
      />
    );
    const input = screen.getByDisplayValue("128");
    expect(input).toBeInTheDocument();
  });
});
