import { render, screen, fireEvent, waitFor, act } from "@testing-library/react";
import { vi, describe, it, expect, beforeEach, afterEach } from "vitest";
import LoadTestNormalMode from "./LoadTestNormalMode";

vi.mock("../contexts/MockDataContext", () => ({
  useMockData: () => ({ isMockEnabled: false }),
}));

vi.mock("../contexts/ClusterConfigContext", () => ({
  useClusterConfig: () => ({
    endpoint: "http://test-endpoint:8080",
    namespace: "test-ns",
    inferenceservice: "test-is",
    isLoading: false,
    updateConfig: vi.fn(),
    targets: [],
    maxTargets: 5,
    addTarget: vi.fn(),
    removeTarget: vi.fn(),
    setDefaultTarget: vi.fn(),
    crType: "inferenceservice",
  }),
}));

vi.mock("../contexts/ThemeContext", () => ({
  useThemeColors: () => ({
    COLORS: {
      bg: "#0a0b0d", surface: "#111318", border: "#1e2330",
      accent: "#f5a623", cyan: "#00d4ff", green: "#00ff87",
      red: "#ff3b6b", purple: "#b060ff", text: "#c8cfe0", muted: "#4a5578",
    },
  }),
}));

// Mock child components to simplify rendering
vi.mock("./MetricCard", () => ({
  default: ({ label, value, unit }: { label: string; value: React.ReactNode; unit: string }) => (
    <div data-testid="metric-card">
      <span>{label}</span>: <span>{value}</span> <span>{unit}</span>
    </div>
  ),
}));

vi.mock("./Chart", () => ({
  default: ({ title }: { title: string }) => <div data-testid="chart">{title}</div>,
}));

vi.mock("./LoadTestConfig", () => ({
  default: ({ onSubmit, onStop, isRunning, status }: {
    onSubmit: () => void;
    onStop: () => void;
    isRunning: boolean;
    status: string;
  }) => (
    <div data-testid="load-test-config">
      <button type="button" onClick={onSubmit} disabled={isRunning}>▶ Run Load Test</button>
      <button type="button" onClick={onStop} disabled={!isRunning}>■ Stop</button>
      <span data-testid="status">{status}</span>
    </div>
  ),
}));

vi.mock("./ErrorAlert", () => ({
  default: ({ message }: { message: string | null }) =>
    message ? <div data-testid="error-alert">{message}</div> : null,
}));

// Mock useLoadTestSSE hook
const mockConnect = vi.fn();
const mockDisconnect = vi.fn();
const mockSetStatus = vi.fn();
const mockSetResult = vi.fn();
const mockSetProgress = vi.fn();
const mockSetLatencyData = vi.fn();
const mockSetError = vi.fn();

let mockSSEStatus: "idle" | "running" | "completed" | "error" | "stopped" = "idle";
let mockSSEResult: Record<string, unknown> | null = null;
let mockSSEProgress = 0;
let mockSSEError: string | null = null;
let mockSSEReconnecting = false;

vi.mock("../hooks/useLoadTestSSE", () => ({
  useLoadTestSSE: () => ({
    status: mockSSEStatus,
    setStatus: mockSetStatus,
    isReconnecting: mockSSEReconnecting,
    retryCount: 0,
    error: mockSSEError,
    setError: mockSetError,
    result: mockSSEResult,
    setResult: mockSetResult,
    progress: mockSSEProgress,
    setProgress: mockSetProgress,
    latencyData: [],
    setLatencyData: mockSetLatencyData,
    connect: mockConnect,
    disconnect: mockDisconnect,
  }),
}));

// Mock fetch
let mockFetch: ReturnType<typeof vi.fn>;

beforeEach(() => {
  mockSSEStatus = "idle";
  mockSSEResult = null;
  mockSSEProgress = 0;
  mockSSEError = null;
  mockSSEReconnecting = false;

  vi.clearAllMocks();

  // ResizeObserver mock for Recharts
  global.ResizeObserver = class ResizeObserver {
    observe() {}
    unobserve() {}
    disconnect() {}
  };

  mockFetch = vi.fn().mockImplementation((url: string) => {
    if (url.includes("/status/interrupted")) {
      return Promise.resolve({ ok: true, json: async () => ({ interrupted_runs: [] }) });
    }
    return Promise.resolve({
      ok: true,
      json: async () => ({ test_id: "test-123", status: "started", config: { model: "test-model" } }),
    });
  });
  vi.stubGlobal("fetch", mockFetch);
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

describe("LoadTestNormalMode", () => {
  it("renders without crashing", () => {
    render(<LoadTestNormalMode isActive={true} />);
    expect(screen.getByText("PRESETS:")).toBeInTheDocument();
    expect(screen.getByText("▶ Run Load Test")).toBeInTheDocument();
  });

  it("renders preset buttons", () => {
    render(<LoadTestNormalMode isActive={true} />);
    expect(screen.getByText("Quick Smoke")).toBeInTheDocument();
    expect(screen.getByText("Standard")).toBeInTheDocument();
    expect(screen.getByText("Stress")).toBeInTheDocument();
  });

  it("applies preset when preset button is clicked", () => {
    render(<LoadTestNormalMode isActive={true} />);
    const quickSmokeBtn = screen.getByText("Quick Smoke");
    fireEvent.click(quickSmokeBtn);
    // Preset click should not throw
    expect(quickSmokeBtn).toBeInTheDocument();
  });

  it("calls connect on start button click", async () => {
    render(<LoadTestNormalMode isActive={true} />);
    await act(async () => {
      fireEvent.click(screen.getByText("▶ Run Load Test"));
    });
    expect(mockSetStatus).toHaveBeenCalledWith("running");
    expect(mockConnect).toHaveBeenCalled();
  });

  it("calls stop on stop button click", async () => {
    mockSSEStatus = "running";
    render(<LoadTestNormalMode isActive={true} />);
    await act(async () => {
      fireEvent.click(screen.getByText("■ Stop"));
    });
    expect(mockDisconnect).toHaveBeenCalled();
  });

  it("shows progress bar when status is running", () => {
    mockSSEStatus = "running";
    mockSSEProgress = 45;
    render(<LoadTestNormalMode isActive={true} />);
    expect(screen.getByText("Progress")).toBeInTheDocument();
    expect(screen.getByText("45%")).toBeInTheDocument();
  });

  it("shows reconnecting banner when SSE is reconnecting", () => {
    mockSSEStatus = "running";
    mockSSEReconnecting = true;
    render(<LoadTestNormalMode isActive={true} />);
    expect(screen.getByText(/Reconnecting SSE/)).toBeInTheDocument();
  });

  it("displays error alert when error exists", () => {
    mockSSEError = "Test error message";
    render(<LoadTestNormalMode isActive={true} />);
    expect(screen.getByTestId("error-alert")).toHaveTextContent("Test error message");
  });

  it("shows metric cards when result is available", () => {
    mockSSEStatus = "completed";
    mockSSEResult = {
      total: 200,
      total_requested: 200,
      success: 198,
      failed: 2,
      elapsed: 20.0,
      rps_actual: 10.0,
      latency: { mean: 0.1, p50: 0.1, p95: 0.15, p99: 0.2, min: 0.05, max: 0.3 },
      ttft: { mean: 0.05, p95: 0.08 },
      tps: { mean: 100, total: 2000 },
      gpu_efficiency: { value: 5.0, display: "5.0", mismatch: false },
    };
    render(<LoadTestNormalMode isActive={true} />);
    expect(screen.getByText("Mean TPS")).toBeInTheDocument();
    expect(screen.getAllByText("TTFT Mean").length).toBeGreaterThan(0);
    expect(screen.getAllByText("E2E Latency P99").length).toBeGreaterThan(0);
    expect(screen.getByText("Success Rate")).toBeInTheDocument();
  });

  it("shows latency distribution table when result is available", () => {
    mockSSEStatus = "completed";
    mockSSEResult = {
      total: 200,
      total_requested: 200,
      success: 200,
      failed: 0,
      latency: { mean: 0.1, p50: 0.1, p95: 0.15, p99: 0.2 },
      ttft: { mean: 0.05, p95: 0.08 },
      tps: { mean: 100, total: 2000 },
      gpu_efficiency: { value: 5.0, display: "5.0", mismatch: false },
    };
    render(<LoadTestNormalMode isActive={true} />);
    expect(screen.getByText("E2E Latency Distribution")).toBeInTheDocument();
    expect(screen.getByText("Total Requests")).toBeInTheDocument();
    expect(screen.getByText("Success")).toBeInTheDocument();
    expect(screen.getByText("Failed")).toBeInTheDocument();
  });

  it("shows Save as Benchmark button when completed", () => {
    mockSSEStatus = "completed";
    mockSSEResult = {
      total: 200,
      success: 200,
      failed: 0,
      latency: { mean: 0.1, p50: 0.1, p95: 0.15, p99: 0.2 },
      ttft: { mean: 0.05, p95: 0.08 },
      tps: { mean: 100, total: 2000 },
      gpu_efficiency: { value: 5.0, display: "5.0", mismatch: false },
    };
    render(<LoadTestNormalMode isActive={true} />);
    expect(screen.getByText("⬆ Save as Benchmark")).toBeInTheDocument();
  });

  it("calls benchmark/save on Save as Benchmark click", async () => {
    mockSSEStatus = "completed";
    mockSSEResult = {
      total: 200,
      success: 200,
      failed: 0,
      latency: { mean: 0.1, p50: 0.1, p95: 0.15, p99: 0.2 },
      ttft: { mean: 0.05, p95: 0.08 },
      tps: { mean: 100, total: 2000 },
      gpu_efficiency: { value: 5.0, display: "5.0", mismatch: false },
    };
    render(<LoadTestNormalMode isActive={true} />);
    await act(async () => {
      fireEvent.click(screen.getByText("⬆ Save as Benchmark"));
    });
    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining("benchmark/save"),
      expect.objectContaining({ method: "POST" })
    );
  });

  it("shows success feedback after save", async () => {
    mockSSEStatus = "completed";
    mockSSEResult = {
      total: 200,
      success: 200,
      failed: 0,
      latency: { mean: 0.1, p50: 0.1, p95: 0.15, p99: 0.2 },
      ttft: { mean: 0.05, p95: 0.08 },
      tps: { mean: 100, total: 2000 },
      gpu_efficiency: { value: 5.0, display: "5.0", mismatch: false },
    };
    render(<LoadTestNormalMode isActive={true} />);
    await act(async () => {
      fireEvent.click(screen.getByText("⬆ Save as Benchmark"));
    });
    await waitFor(() => {
      expect(screen.getByText("✓ Saved")).toBeInTheDocument();
    });
  });

  it("fetches interrupted status on mount when active", async () => {
    render(<LoadTestNormalMode isActive={true} />);
    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining("/status/interrupted"),
        expect.anything()
      );
    });
  });

  it("does not fetch interrupted status when not active", () => {
    render(<LoadTestNormalMode isActive={false} />);
    expect(mockFetch).not.toHaveBeenCalledWith(
      expect.stringContaining("/status/interrupted"),
      expect.anything()
    );
  });

  it("handles network failure on Save as Benchmark gracefully", async () => {
    mockSSEStatus = "completed";
    mockSSEResult = {
      total: 200,
      success: 200,
      failed: 0,
      latency: { mean: 0.1, p50: 0.1, p95: 0.15, p99: 0.2 },
      ttft: { mean: 0.05, p95: 0.08 },
      tps: { mean: 100, total: 2000 },
      gpu_efficiency: { value: 5.0, display: "5.0", mismatch: false },
    };
    // Override fetch: fail only benchmark/save, succeed for others
    mockFetch.mockImplementation((url: string) => {
      if (url.includes("benchmark/save")) {
        return Promise.reject(new Error("Network error"));
      }
      if (url.includes("/status/interrupted")) {
        return Promise.resolve({ ok: true, json: async () => ({ interrupted_runs: [] }) });
      }
      return Promise.resolve({ ok: true, json: async () => ({}) });
    });
    render(<LoadTestNormalMode isActive={true} />);
    await act(async () => {
      fireEvent.click(screen.getByText("⬆ Save as Benchmark"));
    });
    // Component should not crash; save button should remain
    expect(screen.getByText("⬆ Save as Benchmark")).toBeInTheDocument();
  });

  it("handles 500 error on Save as Benchmark", async () => {
    mockSSEStatus = "completed";
    mockSSEResult = {
      total: 200,
      success: 200,
      failed: 0,
      latency: { mean: 0.1, p50: 0.1, p95: 0.15, p99: 0.2 },
      ttft: { mean: 0.05, p95: 0.08 },
      tps: { mean: 100, total: 2000 },
      gpu_efficiency: { value: 5.0, display: "5.0", mismatch: false },
    };
    // Override fetch: return 500 only for benchmark/save
    mockFetch.mockImplementation((url: string) => {
      if (url.includes("benchmark/save")) {
        return Promise.resolve({ ok: false, status: 500, json: async () => ({}) });
      }
      if (url.includes("/status/interrupted")) {
        return Promise.resolve({ ok: true, json: async () => ({ interrupted_runs: [] }) });
      }
      return Promise.resolve({ ok: true, json: async () => ({}) });
    });
    render(<LoadTestNormalMode isActive={true} />);
    await act(async () => {
      fireEvent.click(screen.getByText("⬆ Save as Benchmark"));
    });
    // Component should not crash
    expect(screen.getByText("⬆ Save as Benchmark")).toBeInTheDocument();
  });
});
