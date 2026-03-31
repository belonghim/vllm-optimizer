import "@testing-library/jest-dom";
import { render, screen, fireEvent } from "@testing-library/react";
import { vi, describe, it, expect, beforeEach } from "vitest";
import LoadTestParamForm from "./LoadTestParamForm";

const baseConfig = {
  endpoint: "http://localhost:8080",
  model: "test-model",
  total_requests: 100,
  concurrency: 10,
  rps: 0,
  max_tokens: 512,
  prompt_template: "Hello, world!",
  temperature: 0.7,
};

describe("LoadTestParamForm", () => {
  const onChange = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders all param field labels", () => {
    render(<LoadTestParamForm config={baseConfig} onChange={onChange} />);
    expect(screen.getByLabelText("vLLM Endpoint")).toBeInTheDocument();
    expect(screen.getByLabelText("Model")).toBeInTheDocument();
    expect(screen.getByLabelText("Total Requests")).toBeInTheDocument();
    expect(screen.getByLabelText("Concurrency")).toBeInTheDocument();
    expect(screen.getByLabelText("RPS (0=unlimited)")).toBeInTheDocument();
    expect(screen.getByLabelText("Temperature")).toBeInTheDocument();
  });

  it("displays config values in inputs", () => {
    render(<LoadTestParamForm config={baseConfig} onChange={onChange} />);
    const endpointInput = screen.getByLabelText("vLLM Endpoint") as HTMLInputElement;
    expect(endpointInput.value).toBe("http://localhost:8080");
    const temperatureInput = screen.getByLabelText("Temperature") as HTMLInputElement;
    expect(temperatureInput.value).toBe("0.7");
  });

  it("calls onChange with string value on text input change", () => {
    render(<LoadTestParamForm config={baseConfig} onChange={onChange} />);
    const endpointInput = screen.getByLabelText("vLLM Endpoint");
    fireEvent.change(endpointInput, { target: { value: "http://new:8080" } });
    expect(onChange).toHaveBeenCalledWith("endpoint", "http://new:8080");
  });

  it("calls onChange with number value on number input change", () => {
    render(<LoadTestParamForm config={baseConfig} onChange={onChange} />);
    const totalRequestsInput = screen.getByLabelText("Total Requests");
    fireEvent.change(totalRequestsInput, { target: { value: "200" } });
    expect(onChange).toHaveBeenCalledWith("total_requests", 200);
  });

  it("renders Direct Input and Synthetic prompt mode buttons", () => {
    render(
      <LoadTestParamForm
        config={baseConfig}
        onChange={onChange}
        promptMode="static"
        onPromptModeChange={vi.fn()}
      />
    );
    expect(screen.getByText("Direct Input")).toBeInTheDocument();
    expect(screen.getByText("Synthetic")).toBeInTheDocument();
  });

  it("calls onPromptModeChange with 'synthetic' when Synthetic button clicked", () => {
    const onPromptModeChange = vi.fn();
    render(
      <LoadTestParamForm
        config={baseConfig}
        onChange={onChange}
        promptMode="static"
        onPromptModeChange={onPromptModeChange}
      />
    );
    fireEvent.click(screen.getByText("Synthetic"));
    expect(onPromptModeChange).toHaveBeenCalledWith("synthetic");
  });

  it("calls onPromptModeChange with 'static' when Direct Input button clicked", () => {
    const onPromptModeChange = vi.fn();
    render(
      <LoadTestParamForm
        config={baseConfig}
        onChange={onChange}
        promptMode="synthetic"
        onPromptModeChange={onPromptModeChange}
        syntheticConfig={{ distribution: "uniform", min_tokens: 50, max_tokens: 500 }}
      />
    );
    fireEvent.click(screen.getByText("Direct Input"));
    expect(onPromptModeChange).toHaveBeenCalledWith("static");
  });

  it("shows prompt template textarea in static mode", () => {
    render(
      <LoadTestParamForm config={baseConfig} onChange={onChange} promptMode="static" />
    );
    expect(screen.getByLabelText("Prompt template")).toBeInTheDocument();
  });

  it("shows synthetic config fields when promptMode is synthetic", () => {
    render(
      <LoadTestParamForm
        config={baseConfig}
        onChange={onChange}
        promptMode="synthetic"
        syntheticConfig={{ distribution: "uniform", min_tokens: 50, max_tokens: 500 }}
        onSyntheticConfigChange={vi.fn()}
      />
    );
    expect(screen.getByLabelText("Distribution")).toBeInTheDocument();
    expect(screen.getByLabelText("Min Tokens")).toBeInTheDocument();
  });

  it("shows mean/stddev fields when distribution is normal", () => {
    render(
      <LoadTestParamForm
        config={baseConfig}
        onChange={onChange}
        promptMode="synthetic"
        syntheticConfig={{
          distribution: "normal",
          min_tokens: 50,
          max_tokens: 500,
          mean_tokens: 200,
          stddev_tokens: 50,
        }}
        onSyntheticConfigChange={vi.fn()}
      />
    );
    expect(screen.getByLabelText("Mean Tokens")).toBeInTheDocument();
    expect(screen.getByLabelText("Std Dev")).toBeInTheDocument();
  });
});
