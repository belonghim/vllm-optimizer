import { render, screen, fireEvent, waitFor, act } from "@testing-library/react";
import { vi, describe, it, expect, beforeEach, afterEach } from "vitest";
import LoadTestSweepMode from "./LoadTestSweepMode";

vi.mock("../contexts/ThemeContext", () => ({
  useThemeColors: () => ({
    COLORS: {
      bg: "#0a0b0d", surface: "#111318", border: "#1e2330",
      accent: "#f5a623", cyan: "#00d4ff", green: "#00ff87",
      red: "#ff3b6b", purple: "#b060ff", text: "#c8cfe0", muted: "#4a5578",
    },
  }),
}));

vi.mock("./MetricCard", () => ({
  default: ({ label, value, unit }: { label: string; value: React.ReactNode; unit: string }) => (
    <div data-testid="metric-card">
      <span>{label}</span>: <span>{String(value)}</span> <span>{unit}</span>
    </div>
  ),
}));

vi.mock("./SweepChart", () => ({
  default: ({ saturationRps }: { saturationRps: number | null }) => (
    <div data-testid="sweep-chart">Saturation: {saturationRps ?? "None"}</div>
  ),
}));

vi.mock("./ErrorAlert", () => ({
  default: ({ message }: { message: string | null }) =>
    message ? <div data-testid="error-alert">{message}</div> : null,
}));

const mockSSEHandlers: Record<string, (data: unknown) => void> = {};

vi.mock("../hooks/useSSE", () => ({
  useSSE: (url: string | null, handlers: Record<string, (data: unknown) => void>) => {
    Object.assign(mockSSEHandlers, handlers);
  },
}));

let mockFetch: ReturnType<typeof vi.fn>;

beforeEach(() => {
  vi.clearAllMocks();
  Object.keys(mockSSEHandlers).forEach(key => { delete mockSSEHandlers[key]; });

  global.ResizeObserver = class ResizeObserver {
    observe() {}
    unobserve() {}
    disconnect() {}
  };

  mockFetch = vi.fn().mockImplementation((url: string) => {
    if (url.includes("/sweep/history?limit=20")) {
      return Promise.resolve({ ok: true, json: async () => [] });
    }
    if (url.includes("/sweep/history/")) {
      return Promise.resolve({ ok: true, json: async () => ({}) });
    }
    if (url.includes("/load_test/sweep/save")) {
      return Promise.resolve({ ok: true, json: async () => ({ id: 1 }) });
    }
    if (url.includes("/load_test/sweep")) {
      return Promise.resolve({ ok: true, json: async () => ({ test_id: "sweep-1" }) });
    }
    if (url.includes("/load_test/stop")) {
      return Promise.resolve({ ok: true, json: async () => ({}) });
    }
    return Promise.resolve({ ok: true, json: async () => ({}) });
  });
  vi.stubGlobal("fetch", mockFetch);
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

describe("LoadTestSweepMode", () => {
  it("renders without crashing", () => {
    render(<LoadTestSweepMode isActive={true} endpoint="http://test:8080" model="test-model" />);
    expect(screen.getByText("SWEEP PRESETS:")).toBeInTheDocument();
    expect(screen.getByText("▶ Start Sweep")).toBeInTheDocument();
  });

  it("renders sweep preset buttons", () => {
    render(<LoadTestSweepMode isActive={true} endpoint="http://test:8080" model="test-model" />);
    expect(screen.getByText("Quick Sweep")).toBeInTheDocument();
    expect(screen.getByText("Full Sweep")).toBeInTheDocument();
  });

  it("renders sweep config form fields", () => {
    render(<LoadTestSweepMode isActive={true} endpoint="http://test:8080" model="test-model" />);
    expect(screen.getByLabelText("RPS Start")).toBeInTheDocument();
    expect(screen.getByLabelText("RPS End")).toBeInTheDocument();
    expect(screen.getByLabelText("RPS Step")).toBeInTheDocument();
    expect(screen.getByLabelText("Requests/Step")).toBeInTheDocument();
    expect(screen.getByLabelText("Concurrency")).toBeInTheDocument();
    expect(screen.getByLabelText("Max Tokens")).toBeInTheDocument();
  });

  it("applies sweep preset when preset button is clicked", () => {
    render(<LoadTestSweepMode isActive={true} endpoint="http://test:8080" model="test-model" />);
    const rpsStartInput = screen.getByLabelText("RPS Start") as HTMLInputElement;
    expect(rpsStartInput.value).toBe("1");
    fireEvent.click(screen.getByText("Full Sweep"));
    expect(rpsStartInput.value).toBe("1");
  });

  it("calls POST /load_test/sweep on start button click", async () => {
    render(<LoadTestSweepMode isActive={true} endpoint="http://test:8080" model="test-model" />);
    await act(async () => {
      fireEvent.click(screen.getByText("▶ Start Sweep"));
    });
    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining("/load_test/sweep"),
      expect.objectContaining({ method: "POST" })
    );
  });

  it("shows running status when sweep is running", async () => {
    render(<LoadTestSweepMode isActive={true} endpoint="http://test:8080" model="test-model" />);
    await act(async () => {
      fireEvent.click(screen.getByText("▶ Start Sweep"));
    });
    expect(screen.getByText("RUNNING")).toBeInTheDocument();
  });

  it("disables start button when sweep is running", async () => {
    render(<LoadTestSweepMode isActive={true} endpoint="http://test:8080" model="test-model" />);
    await act(async () => {
      fireEvent.click(screen.getByText("▶ Start Sweep"));
    });
    expect(screen.getByText("▶ Start Sweep")).toBeDisabled();
  });

  it("enables stop button when sweep is running", async () => {
    render(<LoadTestSweepMode isActive={true} endpoint="http://test:8080" model="test-model" />);
    await act(async () => {
      fireEvent.click(screen.getByText("▶ Start Sweep"));
    });
    expect(screen.getByText("■ Stop")).not.toBeDisabled();
  });

  it("calls stop endpoint on stop button click", async () => {
    render(<LoadTestSweepMode isActive={true} endpoint="http://test:8080" model="test-model" />);
    await act(async () => {
      fireEvent.click(screen.getByText("▶ Start Sweep"));
    });
    await act(async () => {
      fireEvent.click(screen.getByText("■ Stop"));
    });
    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining("/load_test/stop"),
      expect.objectContaining({ method: "POST" })
    );
  });

  it("displays sweep step results when SSE sends sweep_step events", async () => {
    render(<LoadTestSweepMode isActive={true} endpoint="http://test:8080" model="test-model" />);
    await act(async () => {
      fireEvent.click(screen.getByText("▶ Start Sweep"));
    });
    act(() => {
      mockSSEHandlers.sweep_step({
        step: 1,
        rps: 5,
        stats: {
          latency: { p99: 0.15, mean: 0.1 },
          tps: { mean: 100 },
          success: 10,
          failed: 0,
          total: 10,
          rps_actual: 5.0,
        },
        saturated: false,
        saturation_reason: null,
      });
    });
    expect(screen.getByText("Sweep Results")).toBeInTheDocument();
    expect(screen.getByText("5.0")).toBeInTheDocument();
  });

  it("displays sweep result summary when SSE sends sweep_completed event", async () => {
    render(<LoadTestSweepMode isActive={true} endpoint="http://test:8080" model="test-model" />);
    await act(async () => {
      fireEvent.click(screen.getByText("▶ Start Sweep"));
    });
    act(() => {
      mockSSEHandlers.sweep_completed({
        config: {
          rps_start: 1, rps_end: 20, rps_step: 5, requests_per_step: 10,
          concurrency: 5, max_tokens: 128, prompt: "test",
          saturation_error_rate: 0.1, saturation_latency_factor: 3.0,
          min_stable_steps: 1, stream: true,
        },
        steps: [
          { step: 1, rps: 5, stats: { latency: { p99: 0.1, mean: 0.05 }, tps: { mean: 100 }, success: 10, failed: 0, total: 10, rps_actual: 5 }, saturated: false, saturation_reason: null },
        ],
        saturation_point: 15,
        optimal_rps: 10,
        total_duration: 60.5,
      });
    });
    expect(screen.getByText("Optimal RPS")).toBeInTheDocument();
    expect(screen.getByText("Saturation RPS")).toBeInTheDocument();
    expect(screen.getByText("Total Steps")).toBeInTheDocument();
    expect(screen.getByText("Duration")).toBeInTheDocument();
  });

  it("shows Save to Benchmark button when sweep is completed", async () => {
    render(<LoadTestSweepMode isActive={true} endpoint="http://test:8080" model="test-model" />);
    await act(async () => {
      fireEvent.click(screen.getByText("▶ Start Sweep"));
    });
    act(() => {
      mockSSEHandlers.sweep_completed({
        config: { rps_start: 1, rps_end: 20, rps_step: 5, requests_per_step: 10, concurrency: 5, max_tokens: 128, prompt: "test", saturation_error_rate: 0.1, saturation_latency_factor: 3.0, min_stable_steps: 1, stream: true },
        steps: [{ step: 1, rps: 5, stats: { latency: { p99: 0.1, mean: 0.05 }, tps: { mean: 100 }, success: 10, failed: 0, total: 10, rps_actual: 5 }, saturated: false, saturation_reason: null }],
        saturation_point: 15,
        optimal_rps: 10,
        total_duration: 60.5,
      });
    });
    expect(screen.getByText("⬆ Save to Benchmark")).toBeInTheDocument();
  });

  it("calls save endpoint on Save to Benchmark click", async () => {
    render(<LoadTestSweepMode isActive={true} endpoint="http://test:8080" model="test-model" />);
    await act(async () => {
      fireEvent.click(screen.getByText("▶ Start Sweep"));
    });
    act(() => {
      mockSSEHandlers.sweep_completed({
        config: { rps_start: 1, rps_end: 20, rps_step: 5, requests_per_step: 10, concurrency: 5, max_tokens: 128, prompt: "test", saturation_error_rate: 0.1, saturation_latency_factor: 3.0, min_stable_steps: 1, stream: true },
        steps: [{ step: 1, rps: 5, stats: { latency: { p99: 0.1, mean: 0.05 }, tps: { mean: 100 }, success: 10, failed: 0, total: 10, rps_actual: 5 }, saturated: false, saturation_reason: null }],
        saturation_point: 15,
        optimal_rps: 10,
        total_duration: 60.5,
      });
    });
    await act(async () => {
      fireEvent.click(screen.getByText("⬆ Save to Benchmark"));
    });
    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining("/load_test/sweep/save"),
      expect.objectContaining({ method: "POST" })
    );
  });

  it("shows error alert when SSE sends error event", async () => {
    render(<LoadTestSweepMode isActive={true} endpoint="http://test:8080" model="test-model" />);
    await act(async () => {
      fireEvent.click(screen.getByText("▶ Start Sweep"));
    });
    act(() => {
      mockSSEHandlers.error({ error: "Sweep test failed" });
    });
    expect(screen.getByTestId("error-alert")).toHaveTextContent("Sweep test failed");
  });

  it("fetches sweep history on mount when active", async () => {
    render(<LoadTestSweepMode isActive={true} endpoint="http://test:8080" model="test-model" />);
    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining("/sweep/history?limit=20"),
        undefined,
      );
    });
  });

  it("does not fetch sweep history when not active", () => {
    render(<LoadTestSweepMode isActive={false} endpoint="http://test:8080" model="test-model" />);
    expect(mockFetch).not.toHaveBeenCalledWith(
      expect.stringContaining("/sweep/history")
    );
  });

  it("disables config inputs when sweep is running", async () => {
    render(<LoadTestSweepMode isActive={true} endpoint="http://test:8080" model="test-model" />);
    await act(async () => {
      fireEvent.click(screen.getByText("▶ Start Sweep"));
    });
    expect(screen.getByLabelText("RPS Start")).toBeDisabled();
    expect(screen.getByLabelText("RPS End")).toBeDisabled();
  });
});
