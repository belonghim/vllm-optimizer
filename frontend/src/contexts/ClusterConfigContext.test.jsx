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
  });
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("ClusterConfigContext", () => {
  const wrapper = ({ children }) => (
    <ClusterConfigProvider>{children}</ClusterConfigProvider>
  );

  it("has initial state with empty targets and isLoading false after effect", async () => {
    const { result } = renderHook(() => useClusterConfig(), { wrapper });

    expect(result.current.targets).toEqual([]);
    expect(result.current.isLoading).toBe(true);

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });
  });

  it("addTarget adds a target with isDefault true when targets are empty", async () => {
    const { result } = renderHook(() => useClusterConfig(), { wrapper });

    await waitFor(() => {
      expect(result.current.targets.length).toBe(0);
    });

    act(() => {
      result.current.addTarget("ns1", "svc1");
    });

    expect(result.current.targets.length).toBe(1);
    expect(result.current.targets[0]).toEqual({
      namespace: "ns1",
      inferenceService: "svc1",
      isDefault: true,
    });
  });

  it("addTarget does not exceed MAX_TARGETS limit (5)", async () => {
    const { result } = renderHook(() => useClusterConfig(), { wrapper });

    await waitFor(() => {
      expect(result.current.targets).toEqual([]);
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
      expect(result.current.targets).toEqual([]);
    });

    act(() => {
      result.current.addTarget("ns1", "svc1");
      result.current.addTarget("ns2", "svc2");
    });

    expect(result.current.targets.length).toBe(2);
    expect(result.current.targets[0].isDefault).toBe(true);
    expect(result.current.targets[1].isDefault).toBe(false);

    act(() => {
      result.current.removeTarget("ns2", "svc2");
    });

    expect(result.current.targets.length).toBe(1);
    expect(result.current.targets[0].namespace).toBe("ns1");
  });

  it("removeTarget does NOT remove isDefault target (no-op)", async () => {
    const { result } = renderHook(() => useClusterConfig(), { wrapper });

    await waitFor(() => {
      expect(result.current.targets).toEqual([]);
    });

    act(() => {
      result.current.addTarget("ns1", "svc1");
      result.current.addTarget("ns2", "svc2");
    });

    expect(result.current.targets.length).toBe(2);
    expect(result.current.targets[0].isDefault).toBe(true);

    act(() => {
      result.current.removeTarget("ns1", "svc1");
    });

    expect(result.current.targets.length).toBe(2);
    expect(result.current.targets[0].namespace).toBe("ns1");
  });

  it("setDefaultTarget changes default to specified target", async () => {
    const { result } = renderHook(() => useClusterConfig(), { wrapper });

    await waitFor(() => {
      expect(result.current.targets).toEqual([]);
    });

    act(() => {
      result.current.addTarget("ns1", "svc1");
      result.current.addTarget("ns2", "svc2");
    });

    expect(result.current.targets[0].isDefault).toBe(true);
    expect(result.current.targets[1].isDefault).toBe(false);

    act(() => {
      result.current.setDefaultTarget("ns2", "svc2");
    });

    expect(result.current.targets[0].isDefault).toBe(false);
    expect(result.current.targets[1].isDefault).toBe(true);
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
    Storage.prototype.getItem.mockReturnValue(legacy);

    const { result } = renderHook(() => useClusterConfig(), { wrapper });

    await waitFor(() => {
      expect(result.current.endpoint).toBe("http://x");
    });
    expect(result.current.targets[0].namespace).toBe("ns");
    expect(result.current.targets[0].inferenceService).toBe("is");
  });

  it("writes version field to localStorage", async () => {
    const { result } = renderHook(() => useClusterConfig(), { wrapper });

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    const calls = Storage.prototype.setItem.mock.calls.filter(
      ([key]) => key === "vllm-opt-cluster-config"
    );
    expect(calls.length).toBeGreaterThan(0);
    const lastStored = JSON.parse(calls[calls.length - 1][1]);
    expect(lastStored.version).toBe(2);
  });

  it("updateConfig removes duplicate target when modified default matches existing non-default", async () => {
    const { result } = renderHook(() => useClusterConfig(), { wrapper });

    await waitFor(() => {
      expect(result.current.targets).toEqual([]);
    });

    act(() => {
      result.current.addTarget("ns1", "svc1");
      result.current.addTarget("ns2", "svc2");
    });

    expect(result.current.targets.length).toBe(2);
    expect(result.current.targets[0]).toEqual({
      namespace: "ns1",
      inferenceService: "svc1",
      isDefault: true,
    });
    expect(result.current.targets[1]).toEqual({
      namespace: "ns2",
      inferenceService: "svc2",
      isDefault: false,
    });

    act(() => {
      result.current.updateConfig("namespace", "ns2");
      result.current.updateConfig("inferenceservice", "svc2");
    });

    expect(result.current.targets.length).toBe(1);
    expect(result.current.targets[0]).toEqual({
      namespace: "ns2",
      inferenceService: "svc2",
      isDefault: true,
    });
  });

  it("updateConfig preserves both targets when modified default does not match any non-default", async () => {
    const { result } = renderHook(() => useClusterConfig(), { wrapper });

    await waitFor(() => {
      expect(result.current.targets).toEqual([]);
    });

    act(() => {
      result.current.addTarget("ns1", "svc1");
      result.current.addTarget("ns2", "svc2");
    });

    expect(result.current.targets.length).toBe(2);

    act(() => {
      result.current.updateConfig("namespace", "ns3");
    });

    expect(result.current.targets.length).toBe(2);
    expect(result.current.targets[0]).toEqual({
      namespace: "ns3",
      inferenceService: "svc1",
      isDefault: true,
    });
    expect(result.current.targets[1]).toEqual({
      namespace: "ns2",
      inferenceService: "svc2",
      isDefault: false,
    });
  });
});
