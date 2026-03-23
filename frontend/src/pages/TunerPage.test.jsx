import { render, screen, fireEvent, waitFor, act } from "@testing-library/react";
import { vi, describe, it, expect, beforeEach, afterEach } from "vitest";
import TunerPage from "./TunerPage";

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

vi.mock("../contexts/MockDataContext", () => ({
  useMockData: () => ({ isMockEnabled: false }),
}));

vi.mock("../contexts/ClusterConfigContext", () => ({
  useClusterConfig: () => ({
    endpoint: "http://test-endpoint",
    namespace: "test-ns",
    inferenceservice: "test-is",
  }),
}));

beforeEach(() => {
  mockEsInstance = null;
  vi.stubGlobal("EventSource", MockEventSource);
  global.ResizeObserver = class ResizeObserver {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
  vi.stubGlobal("fetch", vi.fn((url) => {
    const s = url.toString();
    if (s.includes("/tuner/status")) {
      return Promise.resolve({ ok: true, json: async () => ({ running: false, trials_completed: 0 }) });
    }
    if (s.includes("/tuner/trials")) {
      return Promise.resolve({ ok: true, json: async () => ([]) });
    }
    if (s.includes("/tuner/importance")) {
      return Promise.resolve({ ok: true, json: async () => ({}) });
    }
    if (s.includes("/vllm-config")) {
      return Promise.resolve({ ok: true, json: async () => ({ success: true, data: {} }) });
    }
    if (s.includes("/status/interrupted")) {
      return Promise.resolve({ ok: true, json: async () => ({ interrupted_runs: [] }) });
    }
    return Promise.resolve({ ok: true, json: async () => ({ success: true }) });
  }));
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

describe("TunerPage", () => {
  it("renders without crashing", () => {
    render(<TunerPage isActive={true} />);
    expect(screen.getByText("▶ Start Tuning")).toBeInTheDocument();
  });

  it("handles tuning_error SSE event", async () => {
    vi.stubGlobal("fetch", vi.fn((url) => {
      const s = url.toString();
      if (s.includes("/tuner/start")) {
        return Promise.resolve({ ok: true, json: async () => ({ success: true }) });
      }
      if (s.includes("/tuner/status")) {
        return Promise.resolve({ ok: true, json: async () => ({ running: true, trials_completed: 0 }) });
      }
      if (s.includes("/tuner/trials")) {
        return Promise.resolve({ ok: true, json: async () => ([]) });
      }
      if (s.includes("/tuner/importance")) {
        return Promise.resolve({ ok: true, json: async () => ({}) });
      }
      if (s.includes("/vllm-config")) {
        return Promise.resolve({ ok: true, json: async () => ({ success: true, data: {} }) });
      }
      return Promise.resolve({ ok: true, json: async () => ({ success: true }) });
    }));

    render(<TunerPage isActive={true} />);

    await act(async () => {
      fireEvent.click(screen.getByText("▶ Start Tuning"));
    });

    await waitFor(() => expect(mockEsInstance).not.toBeNull());

    act(() => {
      mockEsInstance.onmessage({
        data: JSON.stringify({
          type: "tuning_error",
          data: { error: "RBAC 오류", error_type: "rbac" }
        }),
      });
    });

    expect(screen.getByText(/RBAC 오류/)).toBeInTheDocument();
    expect(mockEsInstance.closeSpy).toHaveBeenCalled();
  });

  it("handles tuning_warning SSE event", async () => {
    vi.stubGlobal("fetch", vi.fn((url) => {
      const s = url.toString();
      if (s.includes("/tuner/start")) {
        return Promise.resolve({ ok: true, json: async () => ({ success: true }) });
      }
      if (s.includes("/tuner/status")) {
        return Promise.resolve({ ok: true, json: async () => ({ running: true, trials_completed: 0 }) });
      }
      if (s.includes("/tuner/trials")) {
        return Promise.resolve({ ok: true, json: async () => ([]) });
      }
      if (s.includes("/tuner/importance")) {
        return Promise.resolve({ ok: true, json: async () => ({}) });
      }
      if (s.includes("/vllm-config")) {
        return Promise.resolve({ ok: true, json: async () => ({ success: true, data: {} }) });
      }
      return Promise.resolve({ ok: true, json: async () => ({ success: true }) });
    }));

    render(<TunerPage isActive={true} />);

    await act(async () => {
      fireEvent.click(screen.getByText("▶ Start Tuning"));
    });

    await waitFor(() => expect(mockEsInstance).not.toBeNull());

    act(() => {
      mockEsInstance.onmessage({
        data: JSON.stringify({
          type: "tuning_warning",
          data: { message: "스토리지 실패" }
        }),
      });
    });

    expect(screen.getByText(/스토리지 실패/)).toBeInTheDocument();
    expect(mockEsInstance.closeSpy).not.toHaveBeenCalled();
  });

  it("ignores events after tuning_error", async () => {
    vi.stubGlobal("fetch", vi.fn((url) => {
      const s = url.toString();
      if (s.includes("/tuner/start")) {
        return Promise.resolve({ ok: true, json: async () => ({ success: true }) });
      }
      if (s.includes("/tuner/status")) {
        return Promise.resolve({ ok: true, json: async () => ({ running: true, trials_completed: 0 }) });
      }
      if (s.includes("/tuner/trials")) {
        return Promise.resolve({ ok: true, json: async () => ([]) });
      }
      if (s.includes("/tuner/importance")) {
        return Promise.resolve({ ok: true, json: async () => ({}) });
      }
      if (s.includes("/vllm-config")) {
        return Promise.resolve({ ok: true, json: async () => ({ success: true, data: {} }) });
      }
      return Promise.resolve({ ok: true, json: async () => ({ success: true }) });
    }));

    render(<TunerPage isActive={true} />);

    await act(async () => {
      fireEvent.click(screen.getByText("▶ Start Tuning"));
    });

    await waitFor(() => expect(mockEsInstance).not.toBeNull());

    // Fire tuning_error → error shown, ES closed
    act(() => {
      mockEsInstance.onmessage({
        data: JSON.stringify({
          type: "tuning_error",
          data: { error: "K8s 권한 오류", error_type: "rbac" }
        }),
      });
    });

    expect(screen.getByText(/K8s 권한 오류/)).toBeInTheDocument();
    expect(mockEsInstance.closeSpy).toHaveBeenCalled();

    // Fire trial_complete after error → should not crash or change error state
    act(() => {
      mockEsInstance.onmessage({
        data: JSON.stringify({
          type: "trial_complete",
          data: { trial_id: 0, score: 42.0 }
        }),
      });
    });

    // Error message still visible, no crash
    expect(screen.getByText(/K8s 권한 오류/)).toBeInTheDocument();
  });

  it("handles malformed JSON in SSE without crashing", async () => {
    vi.stubGlobal("fetch", vi.fn((url) => {
      const s = url.toString();
      if (s.includes("/tuner/start")) {
        return Promise.resolve({ ok: true, json: async () => ({ success: true }) });
      }
      if (s.includes("/tuner/status")) {
        return Promise.resolve({ ok: true, json: async () => ({ running: true, trials_completed: 0 }) });
      }
      if (s.includes("/tuner/trials")) {
        return Promise.resolve({ ok: true, json: async () => ([]) });
      }
      if (s.includes("/tuner/importance")) {
        return Promise.resolve({ ok: true, json: async () => ({}) });
      }
      if (s.includes("/vllm-config")) {
        return Promise.resolve({ ok: true, json: async () => ({ success: true, data: {} }) });
      }
      return Promise.resolve({ ok: true, json: async () => ({ success: true }) });
    }));

    render(<TunerPage isActive={true} />);

    await act(async () => {
      fireEvent.click(screen.getByText("▶ Start Tuning"));
    });

    await waitFor(() => expect(mockEsInstance).not.toBeNull());

    // Fire malformed JSON — should not throw or crash
    act(() => {
      mockEsInstance.onmessage({ data: "not-valid-json{{{" });
    });

    // Page still functional, no error displayed from malformed JSON
    expect(screen.queryByText(/오류/)).not.toBeInTheDocument();
  });

  it("shows IDLE status tag initially", () => {
    render(<TunerPage isActive={true} />);
    expect(screen.getByText("IDLE")).toBeInTheDocument();
  });

  it("shows interrupted warning when previous tuner run was interrupted", async () => {
    vi.stubGlobal("fetch", vi.fn((url) => {
      const s = url.toString();
      if (s.includes("/status/interrupted")) {
        return Promise.resolve({ 
          ok: true, 
          json: async () => ({ 
            interrupted_runs: [{ id: 1, task_type: "tuner", started_at: 1711100000.0 }] 
          }) 
        });
      }
      if (s.includes("/tuner/status")) {
        return Promise.resolve({ ok: true, json: async () => ({ running: false, trials_completed: 0 }) });
      }
      if (s.includes("/tuner/trials")) {
        return Promise.resolve({ ok: true, json: async () => ([]) });
      }
      if (s.includes("/tuner/importance")) {
        return Promise.resolve({ ok: true, json: async () => ({}) });
      }
      if (s.includes("/vllm-config")) {
        return Promise.resolve({ ok: true, json: async () => ({ success: true, data: {} }) });
      }
      return Promise.resolve({ ok: true, json: async () => ({ success: true }) });
    }));

    render(<TunerPage isActive={true} />);
    
    await waitFor(() => {
      expect(screen.getByText(/이전 튜닝이 비정상 종료되었습니다/)).toBeInTheDocument();
    });

    const closeBtn = screen.getByText("×");
    fireEvent.click(closeBtn);
    expect(screen.queryByText(/이전 튜닝이 비정상 종료되었습니다/)).not.toBeInTheDocument();
  });
});
