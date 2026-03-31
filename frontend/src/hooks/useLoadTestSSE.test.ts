import { vi, describe, it, expect, beforeEach, afterEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useLoadTestSSE } from "./useLoadTestSSE";

class MockEventSource {
  static instances: MockEventSource[] = [];
  onmessage: ((event: { data: string }) => void) | null = null;
  onerror: (() => void) | null = null;
  readyState = 1;

  constructor() {
    MockEventSource.instances.push(this);
  }

  close() {
    this.readyState = 2;
  }

  simulateMessage(data: unknown) {
    if (this.onmessage) this.onmessage({ data: JSON.stringify(data) });
  }

  simulateError() {
    if (this.onerror) this.onerror();
  }
}

beforeEach(() => {
  MockEventSource.instances = [];
  vi.stubGlobal("EventSource", MockEventSource);
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

describe("useLoadTestSSE", () => {
  it("has correct initial state", () => {
    const { result } = renderHook(() => useLoadTestSSE());

    expect(result.current.status).toBe("idle");
    expect(result.current.progress).toBe(0);
    expect(result.current.error).toBeNull();
    expect(result.current.result).toBeNull();
    expect(result.current.latencyData).toEqual([]);
    expect(result.current.isReconnecting).toBe(false);
    expect(result.current.retryCount).toBe(0);
  });

  it("connect() creates an EventSource connection", () => {
    const { result } = renderHook(() => useLoadTestSSE());

    act(() => {
      result.current.connect(100);
    });

    expect(MockEventSource.instances).toHaveLength(1);
  });

  it("progress message updates progress and latencyData", () => {
    const { result } = renderHook(() => useLoadTestSSE());

    act(() => {
      result.current.connect(100);
    });

    act(() => {
      MockEventSource.instances[0].simulateMessage({
        type: "progress",
        data: { total: 50, latency: { mean: 0.1 }, tps: { mean: 10 } },
      });
    });

    expect(result.current.progress).toBe(50);
    expect(result.current.latencyData).toHaveLength(1);
    expect(result.current.latencyData[0].lat).toBe(100);
    expect(result.current.latencyData[0].tps).toBe(10);
  });

  it("completed message sets status=completed and progress=100", () => {
    const { result } = renderHook(() => useLoadTestSSE());

    act(() => {
      result.current.connect(10);
    });

    act(() => {
      MockEventSource.instances[0].simulateMessage({
        type: "completed",
        data: { summary: "done" },
      });
    });

    expect(result.current.status).toBe("completed");
    expect(result.current.progress).toBe(100);
    expect(result.current.result).toEqual({ summary: "done" });
  });

  it("error message sets status=error and stores error string", () => {
    const { result } = renderHook(() => useLoadTestSSE());

    act(() => {
      result.current.connect(10);
    });

    act(() => {
      MockEventSource.instances[0].simulateMessage({
        type: "error",
        data: { error: "Load test failed" },
      });
    });

    expect(result.current.status).toBe("error");
    expect(result.current.error).toBe("Load test failed");
  });

  it("disconnect() closes the EventSource", () => {
    const { result } = renderHook(() => useLoadTestSSE());

    act(() => {
      result.current.connect(10);
    });

    const es = MockEventSource.instances[0];

    act(() => {
      result.current.disconnect();
    });

    expect(es.readyState).toBe(2);
  });
});
