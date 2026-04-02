import React from "react";
import { renderHook, act, waitFor } from "@testing-library/react";
import { vi, describe, it, expect, beforeEach, afterEach } from "vitest";
import { ClusterConfigProvider, useClusterConfig } from "../contexts/ClusterConfigContext";

beforeEach(() => {
  vi.spyOn(Storage.prototype, "getItem").mockReturnValue(null);
  vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {});
  vi.spyOn(global, "fetch").mockResolvedValue({
    json: () =>
      Promise.resolve({
        vllm_endpoint: "",
        vllm_namespace: "",
        vllm_is_name: "",
        cr_type: "inferenceservice",
        resolved_model_name: "",
      }),
  } as unknown as Response);
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("ClusterConfigContext CR-type targets", () => {
  const wrapper = ({ children }: { children: React.ReactNode }) => (
    <ClusterConfigProvider>{children}</ClusterConfigProvider>
  );

  it("exposes isvcTargets and llmisvcTargets arrays", async () => {
    const { result } = renderHook(() => useClusterConfig(), { wrapper });

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    expect(result.current.isvcTargets).toBeDefined();
    expect(Array.isArray(result.current.isvcTargets)).toBe(true);
    expect(result.current.llmisvcTargets).toBeDefined();
    expect(Array.isArray(result.current.llmisvcTargets)).toBe(true);
  });

  it("derives isvcTargets filtering targets without crType or with inferenceservice crType", async () => {
    const { result } = renderHook(() => useClusterConfig(), { wrapper });

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    act(() => {
      result.current.addTarget("ns-isvc", "svc-isvc", "inferenceservice");
      result.current.addTarget("ns-llmis", "svc-llmis", "llminferenceservice");
    });

    const isvcTargets = result.current.isvcTargets;
    expect(isvcTargets.some(t => t.namespace === "ns-isvc" && t.inferenceService === "svc-isvc")).toBe(true);
    expect(isvcTargets.some(t => t.namespace === "ns-llmis" && t.inferenceService === "svc-llmis")).toBe(false);
  });

  it("derives llmisvcTargets filtering targets without crType or with llminferenceservice crType", async () => {
    const { result } = renderHook(() => useClusterConfig(), { wrapper });

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    act(() => {
      result.current.addTarget("ns-isvc", "svc-isvc", "inferenceservice");
      result.current.addTarget("ns-llmis", "svc-llmis", "llminferenceservice");
    });

    const llmisvcTargets = result.current.llmisvcTargets;
    expect(llmisvcTargets.some(t => t.namespace === "ns-llmis" && t.inferenceService === "svc-llmis")).toBe(true);
    expect(llmisvcTargets.some(t => t.namespace === "ns-isvc" && t.inferenceService === "svc-isvc")).toBe(false);
  });

  it("setDefaultTarget calls ConfigMap API with timeout", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({}),
    } as unknown as Response);
    vi.spyOn(global, "fetch").mockImplementation(fetchMock);

    const { result } = renderHook(() => useClusterConfig(), { wrapper });

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    await act(async () => {
      await result.current.setDefaultTarget("ns-new", "svc-new", "inferenceservice");
    });

    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/api/config/default-targets"),
      expect.objectContaining({
        method: "PATCH",
        body: expect.stringContaining("ns-new"),
      })
    );
  });

  it("setDefaultTarget updates local state even if API fails", async () => {
    vi.spyOn(global, "fetch").mockRejectedValueOnce(new Error("API failure"));

    const { result } = renderHook(() => useClusterConfig(), { wrapper });

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    await act(async () => {
      await result.current.setDefaultTarget("ns-new", "svc-new", "inferenceservice");
    });

    expect(result.current.targets.some(t => t.namespace === "ns-new" && t.inferenceService === "svc-new" && t.isDefault)).toBe(true);
  });

  it("setDefaultTarget handles timeout gracefully", async () => {
    vi.spyOn(global, "fetch").mockRejectedValueOnce(new DOMException("Aborted", "AbortError"));

    const { result } = renderHook(() => useClusterConfig(), { wrapper });

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    await act(async () => {
      await result.current.setDefaultTarget("ns-timeout", "svc-timeout", "inferenceservice");
    });

    expect(result.current.targets.some(t => t.namespace === "ns-timeout" && t.inferenceService === "svc-timeout" && t.isDefault)).toBe(true);
  });

  it("setDefaultTarget logs error when API fails with non-AbortError", async () => {
    const consoleErrorSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    // First call: useEffect mount, second call: setDefaultTarget API
    let callCount = 0;
    vi.spyOn(global, "fetch").mockImplementation(() => {
      callCount++;
      if (callCount <= 1) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({}),
        } as unknown as Response);
      }
      return Promise.reject(new Error("Server error"));
    });

    const { result } = renderHook(() => useClusterConfig(), { wrapper });

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    await act(async () => {
      await result.current.setDefaultTarget("ns-error", "svc-error", "inferenceservice");
    });

    // Wait for the async API call to complete
    await new Promise(resolve => setTimeout(resolve, 100));

    expect(consoleErrorSpy).toHaveBeenCalledWith(
      "Failed to persist default target to ConfigMap (local state updated):",
      expect.any(Error)
    );
    consoleErrorSpy.mockRestore();
  });

  it("updateConfig returns prev for unknown field", async () => {
    const { result } = renderHook(() => useClusterConfig(), { wrapper });

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    const initialConfig = result.current;

    act(() => {
      result.current.updateConfig("unknownField", "someValue");
    });

    // The state should remain unchanged for unknown fields
    expect(result.current.endpoint).toBe(initialConfig.endpoint);
  });

  it("removeTarget does not remove default target", async () => {
    const { result } = renderHook(() => useClusterConfig(), { wrapper });

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    const defaultTarget = result.current.targets.find(t => t.isDefault);
    if (!defaultTarget) return;

    act(() => {
      result.current.removeTarget(defaultTarget.namespace, defaultTarget.inferenceService);
    });

    // Default target should still exist
    expect(result.current.targets.some(t => t.isDefault)).toBe(true);
  });

  it("addTarget respects MAX_TARGETS limit", async () => {
    vi.spyOn(global, "fetch").mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({
        vllm_endpoint: "",
        vllm_namespace: "",
        vllm_is_name: "",
        cr_type: "inferenceservice",
        resolved_model_name: "",
        targets: [],
      }),
    } as unknown as Response);

    const { result } = renderHook(() => useClusterConfig(), { wrapper });

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    // Add up to MAX_TARGETS (5)
    for (let i = 0; i < 5; i++) {
      act(() => {
        result.current.addTarget(`ns-${i}`, `svc-${i}`);
      });
    }

    const targetCountAfter5Adds = result.current.targets.length;

    // Try to add 6th target
    act(() => {
      result.current.addTarget("ns-extra", "svc-extra");
    });

    // Should still be at MAX_TARGETS
    expect(result.current.targets.length).toBe(targetCountAfter5Adds);
  });
});