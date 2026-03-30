import React from "react";
import { render, screen } from "@testing-library/react";
import { vi, describe, it, expect } from "vitest";
import LoadTestConfig from "./LoadTestConfig";

vi.mock("./LoadTestPresetSelector", () => ({
  default: ({ onSelect }: { onSelect: (name: string) => void }) => (
    <button data-testid="preset-selector" onClick={() => onSelect("test-preset")}>
      Select Preset
    </button>
  ),
}));

vi.mock("./LoadTestParamForm", () => ({
  default: () => <div data-testid="param-form">Param Form</div>,
}));

const baseConfig = {
  endpoint: "http://test:8080",
  model: "test-model",
  total_requests: 100,
  concurrency: 10,
  rps: 5,
  max_tokens: 512,
  prompt_template: "Hello",
  temperature: 0.7,
  stream: false,
};

const baseProps = {
  config: baseConfig,
  onChange: vi.fn(),
  onSubmit: vi.fn(),
  onStop: vi.fn(),
  isRunning: false,
  status: "idle" as const,
};

describe("LoadTestConfig", () => {
  it("renders preset selector", () => {
    render(<LoadTestConfig {...baseProps} />);
    expect(screen.getByTestId("preset-selector")).toBeInTheDocument();
  });

  it("renders param form", () => {
    render(<LoadTestConfig {...baseProps} />);
    expect(screen.getByTestId("param-form")).toBeInTheDocument();
  });

  it("renders without crashing when isRunning is true", () => {
    render(<LoadTestConfig {...baseProps} isRunning={true} />);
    expect(screen.getByTestId("param-form")).toBeInTheDocument();
  });
});
