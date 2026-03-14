import { render, screen, fireEvent, waitFor, act } from "@testing-library/react";
import { vi, describe, it, expect, beforeEach, afterEach } from "vitest";
import LoadTestPage from "./LoadTestPage";

vi.mock("../contexts/MockDataContext", () => ({
  useMockData: () => ({ isMockEnabled: false }),
}));

// Mock ResizeObserver for Recharts
beforeEach(() => {
  global.ResizeObserver = class ResizeObserver {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
});

let mockEsInstance = null;

class MockEventSource {
  constructor(url) {
    this.url = url;
    this.onmessage = null;
    this.onerror = null;
    mockEsInstance = this;
  }
  close() {}
}

beforeEach(() => {
  mockEsInstance = null;
  vi.stubGlobal("EventSource", MockEventSource);
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        test_id: "test-123",
        status: "started",
        config: { model: "resolved-model", endpoint: "", total_requests: 200, concurrency: 20 },
      }),
    })
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

describe("LoadTestPage", () => {
  it("renders without crashing", () => {
    render(<LoadTestPage />);
    expect(screen.getByText("▶ Run Load Test")).toBeInTheDocument();
  });

  it("shows Total Requests as total_requested when available", async () => {
    render(<LoadTestPage />);

    // Start the test
    await act(async () => {
      fireEvent.click(screen.getByText("▶ Run Load Test"));
    });
    await waitFor(() => expect(mockEsInstance).not.toBeNull());

    // Simulate completed SSE event with total_requested
    act(() => {
      mockEsInstance.onmessage({
        data: JSON.stringify({
          type: "completed",
          data: {
            total: 150,
            total_requested: 200,
            success: 148,
            failed: 2,
            elapsed: 15.0,
            rps_actual: 10.0,
            latency: { mean: 0.35, p50: 0.30, p95: 0.45, p99: 0.52, min: 0.10, max: 0.80 },
            ttft: { mean: 0.085, p95: 0.120 },
            tps: { mean: 238, total: 1480 },
          },
        }),
      });
    });

    // "Total Requests" 행에 200 (total_requested)이 표시돼야 함
    expect(screen.getByText("200")).toBeInTheDocument();
  });

  it("does not set NaN progress when d.total is undefined", async () => {
    render(<LoadTestPage />);

    await act(async () => {
      fireEvent.click(screen.getByText("▶ Run Load Test"));
    });
    await waitFor(() => expect(mockEsInstance).not.toBeNull());

    // SSE progress with empty data — should not crash
    act(() => {
      mockEsInstance.onmessage({
        data: JSON.stringify({ type: "progress", data: {} }),
      });
    });

    // No NaN in the DOM (progress bar shows "running" status section)
    const progressText = document.body.textContent;
    expect(progressText).not.toContain("NaN");
  });

  it("sets status to completed on completed event", async () => {
    render(<LoadTestPage />);

    await act(async () => {
      fireEvent.click(screen.getByText("▶ Run Load Test"));
    });
    await waitFor(() => expect(mockEsInstance).not.toBeNull());

    act(() => {
      mockEsInstance.onmessage({
        data: JSON.stringify({
          type: "completed",
          data: {
            total: 200, total_requested: 200, success: 200, failed: 0,
            elapsed: 20.0, rps_actual: 10.0,
            latency: { mean: 0.1, p50: 0.1, p95: 0.15, p99: 0.2, min: 0.05, max: 0.3 },
            ttft: { mean: 0.05, p95: 0.08 },
            tps: { mean: 100, total: 2000 },
          },
        }),
      });
    });

    // COMPLETED 상태 태그 표시
    expect(screen.getByText("COMPLETED")).toBeInTheDocument();
  });
});
