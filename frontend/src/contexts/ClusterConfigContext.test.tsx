import React from "react";
import { renderHook, act, waitFor } from "@testing-library/react";
import { vi, describe, it, expect, beforeEach, afterEach } from "vitest";
import { ClusterConfigProvider, useClusterConfig } from "./ClusterConfigContext";

beforeEach(() => {
  vi.spyOn(Storage.prototype, "getItem").mockReturnValue(null);
  vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {});
  vi.spyOn(global, "fetch").mockResolvedValue({
    json: () =>
      Promise.resolve({
        vllm_endpoint: "",
        vllm_namespace: "",
        vllm_is_name: "",
      }),
  } as unknown as Response);
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("ClusterConfigContext", () => {
  const defaultTarget = {
    namespace: "vllm-lab-dev",
    inferenceService: "llm-ov",
    isDefault: true,
  };

  const wrapper = ({ children }: { children: React.ReactNode }) => (
    <ClusterConfigProvider>{children}</ClusterConfigProvider>
  );

  it("has initial state with default target and isLoading false after effect", async () => {
    const { result } = renderHook(() => useClusterConfig(), { wrapper });

    expect(result.current.targets).toEqual([defaultTarget]);
    expect(result.current.isLoading).toBe(true);

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });
  });

  it("addTarget adds a non-default target when default target exists", async () => {
    const { result } = renderHook(() => useClusterConfig(), { wrapper });

    await waitFor(() => {
      expect(result.current.targets).toEqual([defaultTarget]);
    });

    act(() => {
      result.current.addTarget("ns1", "svc1");
    });

    expect(result.current.targets.length).toBe(2);
    expect(result.current.targets[1]).toEqual({
      namespace: "ns1",
      inferenceService: "svc1",
      isDefault: false,
    });
  });

  it("addTarget does not exceed MAX_TARGETS limit (5)", async () => {
    const { result } = renderHook(() => useClusterConfig(), { wrapper });

    await waitFor(() => {
      expect(result.current.targets).toEqual([defaultTarget]);
    });

    act(() => {
      result.current.addTarget("ns1", "svc1");
      result.current.addTarget("ns2", "svc2");
      result.current.addTarget("ns3", "svc3");
      result.current.addTarget("ns4", "svc4");
      result.current.addTarget("ns5", "svc5");
    });

    expect(result.current.targets.length).toBe(5);

    act(() => {
      result.current.addTarget("ns6", "svc6");
    });

    expect(result.current.targets.length).toBe(5);
  });

  it("removeTarget removes non-default target by (namespace, inferenceService) key", async () => {
    const { result } = renderHook(() => useClusterConfig(), { wrapper });

    await waitFor(() => {
      expect(result.current.targets).toEqual([defaultTarget]);
    });

    act(() => {
      result.current.addTarget("ns1", "svc1");
      result.current.addTarget("ns2", "svc2");
    });

    expect(result.current.targets.length).toBe(3);
    expect(result.current.targets[0].isDefault).toBe(true);
    expect(result.current.targets[2].isDefault).toBe(false);

    act(() => {
      result.current.removeTarget("ns2", "svc2");
    });

    expect(result.current.targets.length).toBe(2);
    expect(result.current.targets[1].namespace).toBe("ns1");
  });

  it("removeTarget does NOT remove isDefault target (no-op)", async () => {
    const { result } = renderHook(() => useClusterConfig(), { wrapper });

    await waitFor(() => {
      expect(result.current.targets).toEqual([defaultTarget]);
    });

    act(() => {
      result.current.addTarget("ns1", "svc1");
      result.current.addTarget("ns2", "svc2");
    });

    expect(result.current.targets.length).toBe(3);
    expect(result.current.targets[0].isDefault).toBe(true);

    act(() => {
      result.current.removeTarget("vllm-lab-dev", "llm-ov");
    });

    expect(result.current.targets.length).toBe(3);
    expect(result.current.targets[0]).toEqual(defaultTarget);
  });

  it("setDefaultTarget changes default to specified target", async () => {
    const { result } = renderHook(() => useClusterConfig(), { wrapper });

    await waitFor(() => {
      expect(result.current.targets).toEqual([defaultTarget]);
    });

    act(() => {
      result.current.addTarget("ns1", "svc1");
      result.current.addTarget("ns2", "svc2");
    });

    expect(result.current.targets[0].isDefault).toBe(true);
    expect(result.current.targets[2].isDefault).toBe(false);

    act(() => {
      result.current.setDefaultTarget("ns2", "svc2");
    });

    expect(result.current.targets[0].isDefault).toBe(false);
    expect(result.current.targets[2].isDefault).toBe(true);
  });

  it("exposes maxTargets constant as 5", async () => {
    const { result } = renderHook(() => useClusterConfig(), { wrapper });

    await waitFor(() => {
      expect(result.current.maxTargets).toBe(5);
    });
  });

  it("migrates versionless config and preserves fields", async () => {
    const legacy = JSON.stringify({
      endpoint: "http://x",
      targets: [{ namespace: "ns", inferenceService: "is", isDefault: true }],
    });
    vi.mocked(Storage.prototype.getItem).mockReturnValue(legacy);

    const { result } = renderHook(() => useClusterConfig(), { wrapper });

    await waitFor(() => {
      expect(result.current.endpoint).toBe("http://is-predictor.ns.svc.cluster.local:8080");
    });
    expect(result.current.targets[0].namespace).toBe("ns");
    expect(result.current.targets[0].inferenceService).toBe("is");
  });

  it("writes version field to localStorage", async () => {
    const { result } = renderHook(() => useClusterConfig(), { wrapper });

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    const calls = vi.mocked(Storage.prototype.setItem).mock.calls.filter(
      ([key]) => key === "vllm-opt-cluster-config"
    );
    expect(calls.length).toBeGreaterThan(0);
    const lastStored = JSON.parse(calls[calls.length - 1][1]);
    expect(lastStored.version).toBe(2);
  });

  it("updateConfig removes duplicate target when modified default matches existing non-default", async () => {
    const { result } = renderHook(() => useClusterConfig(), { wrapper });

    await waitFor(() => {
      expect(result.current.targets).toEqual([defaultTarget]);
    });

    act(() => {
      result.current.addTarget("ns1", "svc1");
      result.current.addTarget("ns2", "svc2");
    });

    expect(result.current.targets.length).toBe(3);
    expect(result.current.targets[1]).toEqual({
      namespace: "ns1",
      inferenceService: "svc1",
      isDefault: false,
    });
    expect(result.current.targets[2]).toEqual({
      namespace: "ns2",
      inferenceService: "svc2",
      isDefault: false,
    });

    act(() => {
      result.current.updateConfig("namespace", "ns2");
      result.current.updateConfig("inferenceservice", "svc2");
    });

    expect(result.current.targets.length).toBe(2);
    expect(result.current.targets[0]).toEqual({
      namespace: "ns2",
      inferenceService: "svc2",
      isDefault: true,
    });
  });

  it("updateConfig preserves both targets when modified default does not match any non-default", async () => {
    const { result } = renderHook(() => useClusterConfig(), { wrapper });

    await waitFor(() => {
      expect(result.current.targets).toEqual([defaultTarget]);
    });

    act(() => {
      result.current.addTarget("ns1", "svc1");
      result.current.addTarget("ns2", "svc2");
    });

    expect(result.current.targets.length).toBe(3);

    act(() => {
      result.current.updateConfig("namespace", "ns3");
    });

    expect(result.current.targets.length).toBe(3);
    expect(result.current.targets[0]).toEqual({
      namespace: "ns3",
      inferenceService: "llm-ov",
      isDefault: true,
    });
    expect(result.current.targets[1]).toEqual({
      namespace: "ns1",
      inferenceService: "svc1",
      isDefault: false,
    });
    expect(result.current.targets[2]).toEqual({
      namespace: "ns2",
      inferenceService: "svc2",
      isDefault: false,
    });
  });

  it("aborts previous resolvedModelName re-fetch when deps change", async () => {
    vi.mocked(Storage.prototype.getItem).mockReturnValue(JSON.stringify({
      endpoint: "http://llm-ov-predictor.vllm-lab-dev.svc.cluster.local:8080",
      targets: [{ namespace: "vllm-lab-dev", inferenceService: "llm-ov", isDefault: true }],
      maxTargets: 5,
      version: 2,
    }));

    const signals: (AbortSignal | null)[] = [];
    const fetchMock = vi.fn((_: RequestInfo | URL, init?: RequestInit) => {
      signals.push((init?.signal as AbortSignal | null) ?? null);
      return Promise.resolve({
        json: () => Promise.resolve({ resolved_model_name: "qwen2-5-7b-instruct" }),
      } as unknown as Response);
    });
    vi.spyOn(global, "fetch").mockImplementation(fetchMock);

    const { result } = renderHook(() => useClusterConfig(), { wrapper });

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledTimes(1);
    });

    const previousRefetchSignal = signals[0];

    act(() => {
      result.current.updateConfig("namespace", "ns-abort");
    });

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledTimes(2);
    });

    expect(previousRefetchSignal?.aborted).toBe(true);
  });

  it("keeps previous resolvedModelName when re-fetch fails", async () => {
    vi.mocked(Storage.prototype.getItem).mockReturnValue(JSON.stringify({
      endpoint: "http://llm-ov-predictor.vllm-lab-dev.svc.cluster.local:8080",
      targets: [{ namespace: "vllm-lab-dev", inferenceService: "llm-ov", isDefault: true }],
      maxTargets: 5,
      version: 2,
    }));

    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({
        json: () => Promise.resolve({ resolved_model_name: "model-initial" }),
      } as unknown as Response)
      .mockRejectedValueOnce(new Error("network failure"));
    vi.spyOn(global, "fetch").mockImplementation(fetchMock);
    const consoleErrorSpy = vi.spyOn(console, "error").mockImplementation(() => {});

    const { result } = renderHook(() => useClusterConfig(), { wrapper });

    await waitFor(() => {
      expect(result.current.resolvedModelName).toBe("model-initial");
    });

    act(() => {
      result.current.updateConfig("namespace", "ns-error");
    });

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledTimes(2);
    });

    expect(result.current.resolvedModelName).toBe("model-initial");
    expect(consoleErrorSpy).toHaveBeenCalledWith(
      "Failed to re-fetch resolved model name",
      expect.any(Error),
    );
  });
});
