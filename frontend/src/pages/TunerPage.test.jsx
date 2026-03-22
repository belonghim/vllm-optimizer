import { render, screen } from "@testing-library/react";
import { vi, describe, it, expect, beforeEach, afterEach } from "vitest";
import TunerPage from "./TunerPage";

// OUT OF SCOPE: SSE streaming, form interaction, chart rendering, polling interval tests

vi.mock("../contexts/MockDataContext", () => ({
  useMockData: () => ({ isMockEnabled: true }),
}));

beforeEach(() => {
  global.ResizeObserver = class ResizeObserver {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
  // /api/config is always called regardless of isMockEnabled
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => ({}) }));
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

describe("TunerPage", () => {
  it("renders without crashing", () => {
    render(<TunerPage />);
    expect(screen.getByText("▶ Start Tuning")).toBeInTheDocument();
  });

  it("shows Start Tuning button enabled initially", () => {
    render(<TunerPage />);
    const btn = screen.getByText("▶ Start Tuning");
    expect(btn).not.toBeDisabled();
  });

  it("shows Stop button disabled initially", () => {
    render(<TunerPage />);
    const btn = screen.getByText("■ Stop");
    expect(btn).toBeDisabled();
  });

  it("shows IDLE status tag initially", () => {
    render(<TunerPage />);
    expect(screen.getByText("IDLE")).toBeInTheDocument();
  });

  it("shows trials counter 0 / n_trials", () => {
    render(<TunerPage />);
    expect(screen.getByText(/0 \/ \d+ trials/)).toBeInTheDocument();
  });

  it("displays n_trials input field", () => {
    render(<TunerPage />);
    expect(screen.getByDisplayValue("10")).toBeInTheDocument();
  });
});
