import { renderHook, act } from "@testing-library/react";
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

    await new Promise((resolve) => setTimeout(resolve, 50));

    expect(result.current.isLoading).toBe(false);
  });

  it("addTarget adds a target with isDefault true when targets are empty", async () => {
    const { result } = renderHook(() => useClusterConfig(), { wrapper });

    await new Promise((resolve) => setTimeout(resolve, 50));

    expect(result.current.targets.length).toBe(0);

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

    await new Promise((resolve) => setTimeout(resolve, 50));

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

    await new Promise((resolve) => setTimeout(resolve, 50));

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

    await new Promise((resolve) => setTimeout(resolve, 50));

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

    await new Promise((resolve) => setTimeout(resolve, 50));

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

    await new Promise((resolve) => setTimeout(resolve, 50));

    expect(result.current.maxTargets).toBe(5);
  });
});
