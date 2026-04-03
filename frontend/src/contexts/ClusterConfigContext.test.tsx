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
      source: "manual",
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
      result.current.setDefaultTarget("ns2", "svc2", "inferenceservice");
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

    vi.spyOn(global, "fetch").mockResolvedValue({
      json: () => Promise.resolve({
        vllm_endpoint: "",
        vllm_namespace: "ns",
        vllm_is_name: "is",
      }),
    } as unknown as Response);

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
    expect(lastStored.version).toBe(3);
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
      source: "manual",
    });
    expect(result.current.targets[2]).toEqual({
      namespace: "ns2",
      inferenceService: "svc2",
      isDefault: false,
      source: "manual",
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
      source: "manual",
    });
    expect(result.current.targets[2]).toEqual({
      namespace: "ns2",
      inferenceService: "svc2",
      isDefault: false,
      source: "manual",
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
    const fetchMock = vi.fn((url: RequestInfo | URL, init?: RequestInit) => {
      const urlStr = url.toString();
      if (urlStr.includes("/api/config") && !urlStr.includes("default-targets")) {
        signals.push((init?.signal as AbortSignal | null) ?? null);
      }
      return Promise.resolve({
        json: () => Promise.resolve({ resolved_model_name: "qwen2-5-7b-instruct" }),
      } as unknown as Response);
    });
    vi.spyOn(global, "fetch").mockImplementation(fetchMock);

    const { result } = renderHook(() => useClusterConfig(), { wrapper });

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    const resolvedModelSignals = signals.filter(s => s !== null);
    const callCountBeforeUpdate = fetchMock.mock.calls.length;
    const previousRefetchSignal = resolvedModelSignals[resolvedModelSignals.length - 1];

    act(() => {
      result.current.updateConfig("namespace", "ns-abort");
    });

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledTimes(callCountBeforeUpdate + 1);
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

    const fetchMock = vi.fn().mockResolvedValue({
      json: () => Promise.resolve({ resolved_model_name: "model-initial" }),
    } as unknown as Response);
    vi.spyOn(global, "fetch").mockImplementation(fetchMock);
    const consoleErrorSpy = vi.spyOn(console, "error").mockImplementation(() => {});

    const { result } = renderHook(() => useClusterConfig(), { wrapper });

    await waitFor(() => {
      expect(result.current.resolvedModelName).toBe("model-initial");
    });
    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    const callCountAfterMount = fetchMock.mock.calls.length;
    fetchMock.mockRejectedValueOnce(new Error("network failure"));

    act(() => {
      result.current.updateConfig("namespace", "ns-error");
    });

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledTimes(callCountAfterMount + 1);
    });

    expect(result.current.resolvedModelName).toBe("model-initial");
    expect(consoleErrorSpy).toHaveBeenCalledWith(
      "Failed to re-fetch resolved model name",
      expect.any(Error),
    );
  });

  describe("ConfigMap sync", () => {
    it("fetches default targets from /api/config/default-targets on mount after isLoading becomes false", async () => {
      const fetchMock = vi.fn((url: string | URL) => {
        if (url.toString().includes("/config/default-targets")) {
          return Promise.resolve({
            json: () => Promise.resolve({ isvc: { name: "cm-isvc", namespace: "cm-ns" }, llmisvc: { name: "", namespace: "" } }),
          });
        }
        return Promise.resolve({
          json: () => Promise.resolve({ vllm_endpoint: "", vllm_namespace: "", vllm_is_name: "" }),
        });
      }) as unknown as typeof fetch;
      vi.spyOn(global, "fetch").mockImplementation(fetchMock);

      const { result } = renderHook(() => useClusterConfig(), { wrapper });

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      // Wait for the ConfigMap fetch to complete
      await waitFor(() => {
        const isvcTarget = result.current.targets.find(t => t.crType === "inferenceservice");
        expect(isvcTarget).toBeDefined();
        expect(isvcTarget?.namespace).toBe("cm-ns");
        expect(isvcTarget?.inferenceService).toBe("cm-isvc");
      });
    });

    it("ConfigMap values override localStorage default target", async () => {
      vi.mocked(Storage.prototype.getItem).mockReturnValue(JSON.stringify({
        endpoint: "http://local-predictor.local-ns.svc.cluster.local:8080",
        targets: [{ namespace: "local-ns", inferenceService: "local-is", isDefault: true }],
        maxTargets: 5,
        version: 2,
      }));

      const fetchMock = vi.fn((url: string | URL) => {
        if (url.toString().includes("/config/default-targets")) {
          return Promise.resolve({
            json: () => Promise.resolve({ isvc: { name: "cm-isvc", namespace: "cm-ns" }, llmisvc: { name: "", namespace: "" } }),
          });
        }
        return Promise.resolve({
          json: () => Promise.resolve({ vllm_endpoint: "", vllm_namespace: "", vllm_is_name: "" }),
        });
      }) as unknown as typeof fetch;
      vi.spyOn(global, "fetch").mockImplementation(fetchMock);

      const { result } = renderHook(() => useClusterConfig(), { wrapper });

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      await waitFor(() => {
        const isvcTarget = result.current.targets.find(t => t.crType === "inferenceservice");
        expect(isvcTarget?.namespace).toBe("cm-ns");
        expect(isvcTarget?.inferenceService).toBe("cm-isvc");
      });
    });

    it("does not update targets when ConfigMap returns empty isvc and llmisvc", async () => {
      const fetchMock = vi.fn((url: string | URL) => {
        if (url.toString().includes("/config/default-targets")) {
          return Promise.resolve({
            json: () => Promise.resolve({ isvc: { name: "", namespace: "" }, llmisvc: { name: "", namespace: "" } }),
          });
        }
        return Promise.resolve({
          json: () => Promise.resolve({ vllm_endpoint: "", vllm_namespace: "", vllm_is_name: "" }),
        });
      }) as unknown as typeof fetch;
      vi.spyOn(global, "fetch").mockImplementation(fetchMock);

      const { result } = renderHook(() => useClusterConfig(), { wrapper });

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      const defaultTarget = result.current.targets.find(t => t.isDefault);
      expect(defaultTarget?.namespace).toBe("vllm-lab-dev");
      expect(defaultTarget?.inferenceService).toBe("llm-ov");
    });

    it("handles ConfigMap fetch error gracefully", async () => {
      const consoleWarnSpy = vi.spyOn(console, "warn").mockImplementation(() => {});
      const fetchMock = vi.fn((url: string | URL) => {
        if (url.toString().includes("/config/default-targets")) {
          return Promise.reject(new Error("ConfigMap fetch failed"));
        }
        return Promise.resolve({
          json: () => Promise.resolve({ vllm_endpoint: "", vllm_namespace: "", vllm_is_name: "" }),
        });
      }) as unknown as typeof fetch;
      vi.spyOn(global, "fetch").mockImplementation(fetchMock);

      const { result } = renderHook(() => useClusterConfig(), { wrapper });

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      expect(consoleWarnSpy).toHaveBeenCalledWith(
        "Failed to fetch ConfigMap default targets:",
        expect.any(Error),
      );

      // Should still have default target from initial config
      const defaultTarget = result.current.targets.find(t => t.isDefault);
      expect(defaultTarget?.namespace).toBe("vllm-lab-dev");
      expect(defaultTarget?.inferenceService).toBe("llm-ov");
    });

    it("cleans up polling interval on unmount", async () => {
      const clearIntervalSpy = vi.spyOn(global, "clearInterval");
      const fetchMock = vi.fn((url: string | URL) => {
        if (url.toString().includes("/config/default-targets")) {
          return Promise.resolve({
            json: () => Promise.resolve({ isvc: { name: "", namespace: "" }, llmisvc: { name: "", namespace: "" } }),
          });
        }
        return Promise.resolve({
          json: () => Promise.resolve({ vllm_endpoint: "", vllm_namespace: "", vllm_is_name: "" }),
        });
      }) as unknown as typeof fetch;
      vi.spyOn(global, "fetch").mockImplementation(fetchMock);

      const { unmount } = renderHook(() => useClusterConfig(), { wrapper });

      await waitFor(() => {
        expect(fetchMock).toHaveBeenCalled();
      });

      unmount();

      expect(clearIntervalSpy).toHaveBeenCalled();
    });

    it("adds both isvc and llmisvc targets when both are present in ConfigMap", async () => {
      const fetchMock = vi.fn((url: string | URL) => {
        if (url.toString().includes("/config/default-targets")) {
          return Promise.resolve({
            json: () => Promise.resolve({
              isvc: { name: "kserve-isvc", namespace: "kserve-ns" },
              llmisvc: { name: "llmis-isvc", namespace: "llmis-ns" },
            }),
          });
        }
        return Promise.resolve({
          json: () => Promise.resolve({ vllm_endpoint: "", vllm_namespace: "", vllm_is_name: "" }),
        });
      }) as unknown as typeof fetch;
      vi.spyOn(global, "fetch").mockImplementation(fetchMock);

      const { result } = renderHook(() => useClusterConfig(), { wrapper });

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      await waitFor(() => {
        const isvcTarget = result.current.targets.find(t => t.crType === "inferenceservice");
        const llmisvcTarget = result.current.targets.find(t => t.crType === "llminferenceservice");
        expect(isvcTarget).toBeDefined();
        expect(isvcTarget?.namespace).toBe("kserve-ns");
        expect(isvcTarget?.inferenceService).toBe("kserve-isvc");
        expect(llmisvcTarget).toBeDefined();
        expect(llmisvcTarget?.namespace).toBe("llmis-ns");
        expect(llmisvcTarget?.inferenceService).toBe("llmis-isvc");
      });
    });
  });

  describe("isvcTargets and llmisvcTargets filtering", () => {
    it("isvcTargets includes targets with crType=inferenceservice and crType=undefined", async () => {
      vi.mocked(Storage.prototype.getItem).mockReturnValue(JSON.stringify({
        endpoint: "http://x",
        targets: [
          { namespace: "ns1", inferenceService: "isvc1", isDefault: true, crType: "inferenceservice" },
          { namespace: "ns2", inferenceService: "isvc2", isDefault: false, crType: undefined },
          { namespace: "ns3", inferenceService: "llmisvc1", isDefault: false, crType: "llminferenceservice" },
        ],
        maxTargets: 5,
        version: 2,
      }));

      const { result } = renderHook(() => useClusterConfig(), { wrapper });

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      expect(result.current.isvcTargets.length).toBe(2);
      expect(result.current.isvcTargets.map(t => t.inferenceService)).toContain("isvc1");
      expect(result.current.isvcTargets.map(t => t.inferenceService)).toContain("isvc2");
    });

    it("llmisvcTargets includes only targets with crType=llminferenceservice", async () => {
      vi.mocked(Storage.prototype.getItem).mockReturnValue(JSON.stringify({
        endpoint: "http://x",
        targets: [
          { namespace: "ns1", inferenceService: "isvc1", isDefault: true, crType: "inferenceservice" },
          { namespace: "ns2", inferenceService: "isvc2", isDefault: false, crType: undefined },
          { namespace: "ns3", inferenceService: "llmisvc1", isDefault: false, crType: "llminferenceservice" },
        ],
        maxTargets: 5,
        version: 2,
      }));

      const { result } = renderHook(() => useClusterConfig(), { wrapper });

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      expect(result.current.llmisvcTargets.length).toBe(1);
      expect(result.current.llmisvcTargets[0].inferenceService).toBe("llmisvc1");
    });
  });
});
