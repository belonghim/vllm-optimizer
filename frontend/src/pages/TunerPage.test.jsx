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

  it("shows IDLE status tag initially", () => {
    render(<TunerPage isActive={true} />);
    expect(screen.getByText("IDLE")).toBeInTheDocument();
  });
});
