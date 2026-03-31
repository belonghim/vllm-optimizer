import { vi, describe, it, expect, beforeEach, afterEach } from "vitest";
import { renderHook } from "@testing-library/react";
import { useSSE } from "./useSSE";

class MockEventSource {
  static instances: MockEventSource[] = [];
  url: string;
  onopen: (() => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;
  onerror: (() => void) | null = null;
  readyState = 1;

  constructor(url: string) {
    this.url = url;
    MockEventSource.instances.push(this);
  }

  close() {
    this.readyState = 2;
  }

  simulateOpen() {
    if (this.onopen) this.onopen();
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
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

describe("useSSE", () => {
  it("does not create EventSource when url is null", () => {
    renderHook(() => useSSE(null, {}));
    expect(MockEventSource.instances).toHaveLength(0);
  });

  it("creates EventSource and routes message to correct handler", () => {
    const progressHandler = vi.fn();
    renderHook(() => useSSE("http://test/stream", { progress: progressHandler }));

    expect(MockEventSource.instances).toHaveLength(1);
    MockEventSource.instances[0].simulateMessage({ type: "progress", data: { val: 42 } });
    expect(progressHandler).toHaveBeenCalledWith({ val: 42 });
  });

  it("calls onError when connection errors without reconnect option", () => {
    const onError = vi.fn();
    renderHook(() =>
      useSSE("http://test/stream", {}, { onError, reconnect: false })
    );

    MockEventSource.instances[0].simulateError();
    expect(onError).toHaveBeenCalledTimes(1);
  });

  it("calls onOpen when connection opens", () => {
    const onOpen = vi.fn();
    renderHook(() => useSSE("http://test/stream", {}, { onOpen }));

    MockEventSource.instances[0].simulateOpen();
    expect(onOpen).toHaveBeenCalledTimes(1);
  });
});
