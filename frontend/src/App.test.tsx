import React from "react";
import { render, screen, fireEvent, act } from "@testing-library/react";
import { vi, describe, it, expect, beforeEach, afterEach } from "vitest";
import App from "./App";

vi.mock("./pages/MonitorPage", () => ({
  default: () => <div data-testid="monitor-page">Monitor</div>,
}));
vi.mock("./pages/LoadTestPage", () => ({
  default: () => <div data-testid="loadtest-page">Load Test</div>,
}));
vi.mock("./pages/BenchmarkPage", () => ({
  default: () => <div data-testid="benchmark-page">Benchmark</div>,
}));
vi.mock("./pages/TunerPage", () => ({
  default: () => <div data-testid="tuner-page">Tuner</div>,
}));
vi.mock("./pages/SlaPage", () => ({
  default: () => <div data-testid="sla-page">SLA</div>,
}));

beforeEach(() => {
  vi.spyOn(Storage.prototype, "getItem").mockReturnValue(null);
  vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {});
  vi.spyOn(global, "fetch").mockResolvedValue({
    json: () => Promise.resolve({ vllm_endpoint: "", vllm_namespace: "", vllm_is_name: "" }),
    ok: true,
  } as unknown as Response);
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("App", () => {
  it("renders the tab navigation with 5 tabs", async () => {
    await act(async () => {
      render(<App />);
    });
    expect(screen.getByText("Monitoring")).toBeInTheDocument();
    expect(screen.getByText("Auto Tuner")).toBeInTheDocument();
    expect(screen.getByText("Load Test")).toBeInTheDocument();
    expect(screen.getByText("Benchmark")).toBeInTheDocument();
    expect(screen.getByText("SLA")).toBeInTheDocument();
  });

  it("shows monitor page by default", async () => {
    await act(async () => {
      render(<App />);
    });
    expect(screen.getByTestId("monitor-page")).toBeInTheDocument();
  });

  it("switches to Load Test page on tab click", async () => {
    await act(async () => {
      render(<App />);
    });
    await act(async () => {
      fireEvent.click(screen.getByText("Load Test"));
    });
    expect(screen.getByTestId("loadtest-page")).toBeInTheDocument();
  });

  it("switches to SLA page on tab click", async () => {
    await act(async () => {
      render(<App />);
    });
    await act(async () => {
      fireEvent.click(screen.getByText("SLA"));
    });
    expect(screen.getByTestId("sla-page")).toBeInTheDocument();
  });
});
