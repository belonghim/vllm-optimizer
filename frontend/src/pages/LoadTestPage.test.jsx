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
  static CONNECTING = 0;
  static OPEN = 1;
  static CLOSED = 2;

  constructor(url) {
    this.url = url;
    this.onmessage = null;
    this.onerror = null;
    this.readyState = MockEventSource.CONNECTING;
    this.closeSpy = vi.fn();
    mockEsInstance = this;
  }
  close() {
    this.readyState = MockEventSource.CLOSED;
    this.closeSpy();
  }
}

beforeEach(() => {
  mockEsInstance = null;
  vi.stubGlobal("EventSource", MockEventSource);
  vi.stubGlobal(
    "fetch",
    vi.fn().mockImplementation((url) => {
      const s = url.toString();
      if (s.includes("/status/interrupted")) {
        return Promise.resolve({ ok: true, json: async () => ({ interrupted_runs: [] }) });
      }
      return Promise.resolve({
        ok: true,
        json: async () => ({
          test_id: "test-123",
          status: "started",
          config: { model: "resolved-model", endpoint: "", total_requests: 200, concurrency: 20 },
        }),
      });
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

  it("handles error SSE event", async () => {
    render(<LoadTestPage />);

    await act(async () => {
      fireEvent.click(screen.getByText("▶ Run Load Test"));
    });
    await waitFor(() => expect(mockEsInstance).not.toBeNull());

    act(() => {
      mockEsInstance.onmessage({
        data: JSON.stringify({
          type: "error",
          data: { error: "연결 시간 초과", error_type: "timeout" },
        }),
      });
    });

    expect(screen.getByText(/연결 시간 초과/)).toBeInTheDocument();
    expect(mockEsInstance.closeSpy).toHaveBeenCalled();
  });

  describe("LoadTestPage — Save as Benchmark", () => {
    it("Save as Benchmark button absent when status is idle", () => {
      render(<LoadTestPage />);
      expect(screen.queryByText("⬆ Save as Benchmark")).not.toBeInTheDocument();
    });

    it("Save as Benchmark button present when status is completed and result exists", async () => {
      render(<LoadTestPage />);
      await act(async () => { fireEvent.click(screen.getByText("▶ Run Load Test")); });
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
      expect(screen.getByText("⬆ Save as Benchmark")).toBeInTheDocument();
    });

    it("calls POST /api/benchmark/save on button click", async () => {
      vi.stubGlobal(
        "fetch",
        vi.fn()
          .mockResolvedValueOnce({ ok: true, json: async () => ({}) })
          .mockResolvedValueOnce({ ok: true, json: async () => ({ test_id: "t1", status: "started", config: { model: "m1" } }) })
          .mockResolvedValueOnce({ ok: true, json: async () => ({ id: 1, name: "m1 @ ..." }) })
      );

      render(<LoadTestPage />);
      await act(async () => { fireEvent.click(screen.getByText("▶ Run Load Test")); });
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

      await act(async () => {
        fireEvent.click(screen.getByText("⬆ Save as Benchmark"));
      });

      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining("benchmark/save"),
        expect.objectContaining({ method: "POST" })
      );
    });

    it("shows success feedback after save", async () => {
      const fetch = vi.fn(url => {
        if (url.toString().endsWith('/benchmark/save')) {
          return Promise.resolve({ ok: true, json: async () => ({ id: 1 }) });
        }
        if (url.toString().endsWith('/load_test/start')) {
          return Promise.resolve({ ok: true, json: async () => ({ test_id: "t1", status: "started", config: { model: "m1" } }) });
        }
        return Promise.resolve({ ok: true, json: async () => ({}) });
      });
      vi.stubGlobal("fetch", fetch);

      render(<LoadTestPage />);
      await act(async () => { fireEvent.click(screen.getByText("▶ Run Load Test")); });
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
      await act(async () => { fireEvent.click(screen.getByText("⬆ Save as Benchmark")); });
      await waitFor(() => expect(screen.getByText("✓ Saved")).toBeInTheDocument());
    });

    it("shows error feedback after failed save", async () => {
      const fetch = vi.fn(url => {
        if (url.toString().endsWith('/benchmark/save')) {
          return Promise.resolve({ ok: false, status: 500 });
        }
        if (url.toString().endsWith('/load_test/start')) {
          return Promise.resolve({ ok: true, json: async () => ({ test_id: "t1", status: "started", config: { model: "m1" } }) });
        }
        return Promise.resolve({ ok: true, json: async () => ({}) });
      });
      vi.stubGlobal("fetch", fetch);

      render(<LoadTestPage />);
      await act(async () => { fireEvent.click(screen.getByText("▶ Run Load Test")); });
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
      await act(async () => { fireEvent.click(screen.getByText("⬆ Save as Benchmark")); });
      await waitFor(() => expect(screen.getByText("✗ Save failed")).toBeInTheDocument());
    });

    it("hides Save as Benchmark button in initial render", () => {
      render(<LoadTestPage />);
      expect(screen.queryByText("⬆ Save as Benchmark")).not.toBeInTheDocument();
    });

    it("disables button during save", async () => {
      let resolvePromise;
      const fetch = vi.fn(url => {
        if (url.toString().endsWith('/benchmark/save')) {
          return new Promise(resolve => { resolvePromise = resolve; });
        }
        if (url.toString().endsWith('/load_test/start')) {
          return Promise.resolve({ ok: true, json: async () => ({ test_id: "t1", status: "started", config: { model: "m1" } }) });
        }
        return Promise.resolve({ ok: true, json: async () => ({}) });
      });
      vi.stubGlobal("fetch", fetch);

      render(<LoadTestPage />);
      await act(async () => { fireEvent.click(screen.getByText("▶ Run Load Test")); });
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

      await act(async () => { fireEvent.click(screen.getByText("⬆ Save as Benchmark")); });

      const button = screen.getByText("Saving...");
      expect(button).toBeDisabled();
      expect(button).toHaveTextContent("Saving...");

      resolvePromise({ ok: true, json: async () => ({ id: 1 }) });
      await waitFor(() => expect(screen.getByText("✓ Saved")).toBeInTheDocument());
    });

    it("disables button after successful save", async () => {
      const fetch = vi.fn(url => {
        if (url.toString().endsWith('/benchmark/save')) {
          return Promise.resolve({ ok: true, json: async () => ({ id: 1 }) });
        }
        if (url.toString().endsWith('/load_test/start')) {
          return Promise.resolve({ ok: true, json: async () => ({ test_id: "t1", status: "started", config: { model: "m1" } }) });
        }
        return Promise.resolve({ ok: true, json: async () => ({}) });
      });
      vi.stubGlobal("fetch", fetch);

      render(<LoadTestPage />);
      await act(async () => { fireEvent.click(screen.getByText("▶ Run Load Test")); });
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
      await act(async () => { fireEvent.click(screen.getByText("⬆ Save as Benchmark")); });
      await waitFor(() => expect(screen.getByText("✓ Saved")).toBeInTheDocument());

      const button = screen.getByText("✓ Saved");
      expect(button).toBeDisabled();
    });
  });

  describe("SSE onerror reconnect behavior", () => {
    it("closes EventSource and schedules reconnect with exponential backoff", async () => {
      render(<LoadTestPage />);
      await act(async () => { fireEvent.click(screen.getByText("▶ Run Load Test")); });
      await waitFor(() => expect(mockEsInstance).not.toBeNull());

      mockEsInstance.readyState = MockEventSource.CONNECTING;
      act(() => { mockEsInstance.onerror(); });

      // Should close the connection (exponential backoff: close + setTimeout reconnect)
      expect(mockEsInstance.closeSpy).toHaveBeenCalled();
      // Should show the reconnecting banner
      expect(screen.getByText(/재연결 중/)).toBeInTheDocument();
    });

    it("shows reconnecting banner when onerror fires in CONNECTING state", async () => {
      render(<LoadTestPage />);
      await act(async () => { fireEvent.click(screen.getByText("▶ Run Load Test")); });
      await waitFor(() => expect(mockEsInstance).not.toBeNull());

      mockEsInstance.readyState = 0; // CONNECTING
      act(() => { mockEsInstance.onerror(); });

      expect(screen.getByText(/재연결 중/)).toBeInTheDocument();
      expect(screen.queryByText(/SSE 연결 실패/)).not.toBeInTheDocument();
    });

    it("clears reconnecting banner when valid SSE message received", async () => {
      render(<LoadTestPage />);
      await act(async () => { fireEvent.click(screen.getByText("▶ Run Load Test")); });
      await waitFor(() => expect(mockEsInstance).not.toBeNull());

      mockEsInstance.readyState = 0;
      act(() => { mockEsInstance.onerror(); });
      expect(screen.getByText(/재연결 중/)).toBeInTheDocument();

      act(() => {
        mockEsInstance.onmessage({
          data: JSON.stringify({ type: "progress", data: { total: 1, total_requested: 10 } }),
        });
      });

      expect(screen.queryByText(/재연결 중/)).not.toBeInTheDocument();
    });
  });

  it("shows interrupted warning when previous loadtest run was interrupted", async () => {
    vi.stubGlobal("fetch", vi.fn((url) => {
      const s = url.toString();
      if (s.includes("/status/interrupted")) {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            interrupted_runs: [{ id: 2, task_type: "loadtest", started_at: 1711100000.0 }]
          })
        });
      }
      return Promise.resolve({ ok: true, json: async () => ({}) });
    }));

    render(<LoadTestPage isActive={true} />);

    await waitFor(() => {
      expect(screen.getByText(/이전 부하 테스트가 비정상 종료되었습니다/)).toBeInTheDocument();
    });

    const closeBtn = screen.getByText("×");
    fireEvent.click(closeBtn);
    expect(screen.queryByText(/이전 부하 테스트가 비정상 종료되었습니다/)).not.toBeInTheDocument();
  });

  it("ignores malformed JSON in SSE event without crashing", async () => {
    render(<LoadTestPage isActive={true} />);

    await act(async () => {
      fireEvent.click(screen.getByText("▶ Run Load Test"));
    });
    await waitFor(() => expect(mockEsInstance).not.toBeNull());

    act(() => {
      mockEsInstance.onmessage({ data: "not-json" });
    });

    expect(screen.queryByText(/오류/)).not.toBeInTheDocument();
    expect(mockEsInstance.closeSpy).not.toHaveBeenCalled();
  });
});
