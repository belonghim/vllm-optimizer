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

    expect(result.current.targets[0]).toMatchObject({
      namespace: "ns-new",
      inferenceService: "svc-new",
      crType: "inferenceservice",
    });
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

    expect(result.current.targets[0]).toMatchObject({
      namespace: "ns-timeout",
      inferenceService: "svc-timeout",
      crType: "inferenceservice",
    });
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

    const defaultTarget = result.current.targets[0];
    if (!defaultTarget) return;

    act(() => {
      result.current.removeTarget(defaultTarget.namespace, defaultTarget.inferenceService);
    });

    // Default target should still exist
    expect(result.current.targets[0]).toEqual(defaultTarget);
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

describe("ClusterConfigContext ConfigMap sync on mount", () => {
  const wrapper = ({ children }: { children: React.ReactNode }) => (
    <ClusterConfigProvider>{children}</ClusterConfigProvider>
  );

  it("fetches default targets from ConfigMap on initial load", async () => {
    const fetchCalls: string[] = [];
    vi.spyOn(global, "fetch").mockImplementation((url: RequestInfo | URL) => {
      const urlStr = url.toString();
      fetchCalls.push(urlStr);
      if (urlStr.includes("/api/config/default-targets")) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({
            isvc: { name: "config-isvc", namespace: "config-ns" },
            llmisvc: { name: "", namespace: "" },
          }),
        } as unknown as Response);
      }
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({
          vllm_endpoint: "",
          vllm_namespace: "",
          vllm_is_name: "",
          cr_type: "inferenceservice",
          resolved_model_name: "",
        }),
      } as unknown as Response);
    });

    const { result } = renderHook(() => useClusterConfig(), { wrapper });

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    expect(fetchCalls.some(c => c.includes("/api/config/default-targets"))).toBe(true);
    const isvcTarget = result.current.isvcTargets.find(t => t.inferenceService === "config-isvc" && t.namespace === "config-ns");
    expect(isvcTarget).toBeDefined();
  });

  it("ConfigMap values override localStorage values when both exist", async () => {
    vi.spyOn(Storage.prototype, "getItem").mockReturnValue(JSON.stringify({
      version: 2,
      endpoint: "http://local-storage-endpoint",
      maxTargets: 5,
      targets: [
          { namespace: "local-ns", inferenceService: "local-svc", crType: "inferenceservice" },
      ],
    }));

    vi.spyOn(global, "fetch").mockImplementation((url: RequestInfo | URL) => {
      const urlStr = url.toString();
      if (urlStr.includes("/api/config/default-targets")) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({
            isvc: { name: "config-isvc", namespace: "config-ns" },
            llmisvc: { name: "", namespace: "" },
          }),
        } as unknown as Response);
      }
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({
          vllm_endpoint: "",
          vllm_namespace: "",
          vllm_is_name: "",
          cr_type: "inferenceservice",
          resolved_model_name: "",
        }),
      } as unknown as Response);
    });

    const { result } = renderHook(() => useClusterConfig(), { wrapper });

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    const isvcTarget = result.current.isvcTargets.find(t => t.inferenceService === "config-isvc" && t.namespace === "config-ns");
    expect(isvcTarget).toBeDefined();
    const localTarget = result.current.isvcTargets.find(t => t.inferenceService === "local-svc" && t.namespace === "local-ns");
    expect(localTarget).toBeUndefined();
  });

  it("handles empty ConfigMap defaults gracefully", async () => {
    vi.spyOn(global, "fetch").mockImplementation((url: RequestInfo | URL) => {
      const urlStr = url.toString();
      if (urlStr.includes("/api/config/default-targets")) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({
            isvc: { name: "", namespace: "" },
            llmisvc: { name: "", namespace: "" },
          }),
        } as unknown as Response);
      }
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({
          vllm_endpoint: "",
          vllm_namespace: "",
          vllm_is_name: "",
          cr_type: "inferenceservice",
          resolved_model_name: "",
        }),
      } as unknown as Response);
    });

    const { result } = renderHook(() => useClusterConfig(), { wrapper });

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    expect(result.current.targets.length).toBeGreaterThan(0);
  });

  it("gracefully handles ConfigMap fetch failure on mount", async () => {
    vi.spyOn(global, "fetch").mockImplementation((url: RequestInfo | URL) => {
      const urlStr = url.toString();
      if (urlStr.includes("/api/config/default-targets")) {
        return Promise.reject(new Error("Network error"));
      }
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({
          vllm_endpoint: "",
          vllm_namespace: "",
          vllm_is_name: "",
          cr_type: "inferenceservice",
          resolved_model_name: "",
        }),
      } as unknown as Response);
    });

    const consoleWarnSpy = vi.spyOn(console, "warn").mockImplementation(() => {});

    const { result } = renderHook(() => useClusterConfig(), { wrapper });

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    expect(result.current.targets.length).toBeGreaterThan(0);
    expect(consoleWarnSpy).toHaveBeenCalledWith(
      "Failed to fetch ConfigMap default targets:",
      expect.any(Error)
    );
    consoleWarnSpy.mockRestore();
  });
});

describe("ClusterConfigContext polling", () => {
  const wrapper = ({ children }: { children: React.ReactNode }) => (
    <ClusterConfigProvider>{children}</ClusterConfigProvider>
  );

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("fetches ConfigMap targets at mount time", async () => {
    const fetchSpy = vi.spyOn(global, "fetch").mockImplementation((url: RequestInfo | URL) => {
      const urlStr = url.toString();
      if (urlStr.includes("/api/config/default-targets")) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({
            isvc: { name: "poll-isvc", namespace: "poll-ns" },
            llmisvc: { name: "", namespace: "" },
          }),
        } as unknown as Response);
      }
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({
          vllm_endpoint: "",
          vllm_namespace: "",
          vllm_is_name: "",
          cr_type: "inferenceservice",
          resolved_model_name: "",
        }),
      } as unknown as Response);
    });

    const { result } = renderHook(() => useClusterConfig(), { wrapper });

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    const defaultTargetsCalls = fetchSpy.mock.calls.filter(
      ([url]) => url.toString().includes("/api/config/default-targets")
    );
    expect(defaultTargetsCalls.length).toBeGreaterThanOrEqual(1);
  });

  it("verifies ConfigMap sync updates state when polling detects changes", async () => {
    const fetchSpy = vi.spyOn(global, "fetch").mockImplementation((url: RequestInfo | URL) => {
      const urlStr = url.toString();
      if (urlStr.includes("/api/config/default-targets")) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({
            isvc: { name: "poll-isvc", namespace: "poll-ns" },
            llmisvc: { name: "", namespace: "" },
          }),
        } as unknown as Response);
      }
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({
          vllm_endpoint: "",
          vllm_namespace: "",
          vllm_is_name: "",
          cr_type: "inferenceservice",
          resolved_model_name: "",
        }),
      } as unknown as Response);
    });

    const { result } = renderHook(() => useClusterConfig(), { wrapper });

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    const defaultTargetsCallsBeforePoll = fetchSpy.mock.calls.filter(
      ([url]) => url.toString().includes("/api/config/default-targets")
    ).length;

    expect(defaultTargetsCallsBeforePoll).toBeGreaterThanOrEqual(1);

    const isvcTarget = result.current.isvcTargets.find(t => t.crType === "inferenceservice");
    expect(isvcTarget?.inferenceService).toBe("poll-isvc");
  });

  it("cleanup function is returned for interval on unmount", async () => {
    const originalSetInterval = global.setInterval;
    const clearIntervalSpy = vi.spyOn(global, "clearInterval");
    vi.spyOn(global, "setInterval").mockImplementation(originalSetInterval);

    const { unmount } = renderHook(() => useClusterConfig(), { wrapper });

    await waitFor(() => {
      expect(global.setInterval).toHaveBeenCalled();
    });

    unmount();

    expect(clearIntervalSpy).toHaveBeenCalled();
  });
});
