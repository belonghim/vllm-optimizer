import React from "react";
import { renderHook, waitFor } from "@testing-library/react";
import { vi, describe, it, expect, beforeEach, afterEach } from "vitest";
import { useTunerLogic } from "../hooks/useTunerLogic";
import { ClusterConfigProvider } from "../contexts/ClusterConfigContext";
import { MockDataProvider } from "../contexts/MockDataContext";
import { http, HttpResponse } from "msw";
import { server } from "../mocks/server";
import type { ClusterTarget } from "../types";

beforeEach(() => {
  vi.spyOn(Storage.prototype, "getItem").mockReturnValue(null);
  vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {});
});

afterEach(() => {
  vi.restoreAllMocks();
});

const wrapper = ({ children }: { children: React.ReactNode }) => {
  return (
    <MockDataProvider>
      <ClusterConfigProvider>
        {children}
      </ClusterConfigProvider>
    </MockDataProvider>
  );
};

describe("useTunerLogic", () => {
  describe("targetOverride", () => {
    it("accepts targetOverride parameter", async () => {
      server.use(
        http.get("/api/config", () =>
          HttpResponse.json({
            vllm_endpoint: "",
            vllm_namespace: "",
            vllm_is_name: "",
            cr_type: "inferenceservice",
            resolved_model_name: "",
          })
        )
      );

      const targetOverride: ClusterTarget = {
        namespace: "test-ns",
        inferenceService: "test-isvc",
        isDefault: false,
        crType: "inferenceservice",
      };

      const { result } = renderHook(
        () => useTunerLogic({ isActive: true, targetOverride }),
        { wrapper }
      );

      await waitFor(() => {
        expect(result.current.initialized).toBe(true);
      });
    });

    it("uses targetOverride namespace when provided", async () => {
      let lastRequestBody: Record<string, unknown> | null = null;

      server.use(
        http.get("/api/config", () =>
          HttpResponse.json({
            vllm_endpoint: "",
            vllm_namespace: "",
            vllm_is_name: "",
            cr_type: "inferenceservice",
            resolved_model_name: "",
          })
        ),
        http.get("/api/tuner/status", () =>
          HttpResponse.json({ running: false, trials_completed: 0 })
        ),
        http.get("/api/tuner/trials", () => HttpResponse.json([])),
        http.get("/api/tuner/importance", () => HttpResponse.json({})),
        http.post("/api/tuner/start", async ({ request }) => {
          lastRequestBody = await request.json() as Record<string, unknown>;
          return HttpResponse.json({ success: true });
        })
      );

      const targetOverride: ClusterTarget = {
        namespace: "override-ns",
        inferenceService: "override-isvc",
        isDefault: false,
        crType: "inferenceservice",
      };

      const { result } = renderHook(
        () => useTunerLogic({ isActive: true, targetOverride }),
        { wrapper }
      );

      await waitFor(() => {
        expect(result.current.initialized).toBe(true);
      });

      await result.current.start();

      await waitFor(() => {
        expect(lastRequestBody).not.toBeNull();
        expect(lastRequestBody?.vllm_namespace).toBe("override-ns");
        expect(lastRequestBody?.vllm_is_name).toBe("override-isvc");
      });
    });

    it("uses targetOverride crType to build endpoint", async () => {
      let lastRequestBody: Record<string, unknown> | null = null;

      server.use(
        http.get("/api/config", () =>
          HttpResponse.json({
            vllm_endpoint: "",
            vllm_namespace: "",
            vllm_is_name: "",
            cr_type: "inferenceservice",
            resolved_model_name: "",
          })
        ),
        http.get("/api/tuner/status", () =>
          HttpResponse.json({ running: false, trials_completed: 0 })
        ),
        http.get("/api/tuner/trials", () => HttpResponse.json([])),
        http.get("/api/tuner/importance", () => HttpResponse.json({})),
        http.post("/api/tuner/start", async ({ request }) => {
          lastRequestBody = await request.json() as Record<string, unknown>;
          return HttpResponse.json({ success: true });
        })
      );

      const targetOverride: ClusterTarget = {
        namespace: "llmis-ns",
        inferenceService: "llmis-svc",
        isDefault: false,
        crType: "llminferenceservice",
      };

      const { result } = renderHook(
        () => useTunerLogic({ isActive: true, targetOverride }),
        { wrapper }
      );

      await waitFor(() => {
        expect(result.current.initialized).toBe(true);
      });

      await result.current.start();

      await waitFor(() => {
        expect(lastRequestBody).not.toBeNull();
        expect(lastRequestBody?.vllm_cr_type).toBe("llminferenceservice");
        // LLMIS endpoint format: http://openshift-ai-inference-openshift-default.openshift-ingress.svc/{namespace}/{name}
        const endpoint = lastRequestBody?.vllm_endpoint as string;
        expect(endpoint).toContain("llmis-ns");
        expect(endpoint).toContain("llmis-svc");
      });
    });

    it("falls back to context values when targetOverride is null", async () => {
      let lastRequestBody: Record<string, unknown> | null = null;

      server.use(
        http.get("/api/config", () =>
          HttpResponse.json({
            vllm_endpoint: "http://default-predictor.default-ns.svc.cluster.local:8080",
            vllm_namespace: "default-ns",
            vllm_is_name: "default-isvc",
            cr_type: "inferenceservice",
            resolved_model_name: "",
          })
        ),
        http.get("/api/tuner/status", () =>
          HttpResponse.json({ running: false, trials_completed: 0 })
        ),
        http.get("/api/tuner/trials", () => HttpResponse.json([])),
        http.get("/api/tuner/importance", () => HttpResponse.json({})),
        http.post("/api/tuner/start", async ({ request }) => {
          lastRequestBody = await request.json() as Record<string, unknown>;
          return HttpResponse.json({ success: true });
        })
      );

      const { result } = renderHook(
        () => useTunerLogic({ isActive: true, targetOverride: null }),
        { wrapper }
      );

      await waitFor(() => {
        expect(result.current.initialized).toBe(true);
      });

      await result.current.start();

      await waitFor(() => {
        expect(lastRequestBody).not.toBeNull();
        expect(lastRequestBody?.vllm_namespace).toBe("default-ns");
        expect(lastRequestBody?.vllm_is_name).toBe("default-isvc");
      });
    });

    it("builds correct isvc endpoint when targetOverride crType is inferenceservice", async () => {
      let lastRequestBody: Record<string, unknown> | null = null;

      server.use(
        http.get("/api/config", () =>
          HttpResponse.json({
            vllm_endpoint: "",
            vllm_namespace: "",
            vllm_is_name: "",
            cr_type: "inferenceservice",
            resolved_model_name: "",
          })
        ),
        http.get("/api/tuner/status", () =>
          HttpResponse.json({ running: false, trials_completed: 0 })
        ),
        http.get("/api/tuner/trials", () => HttpResponse.json([])),
        http.get("/api/tuner/importance", () => HttpResponse.json({})),
        http.post("/api/tuner/start", async ({ request }) => {
          lastRequestBody = await request.json() as Record<string, unknown>;
          return HttpResponse.json({ success: true });
        })
      );

      const targetOverride: ClusterTarget = {
        namespace: "isvc-ns",
        inferenceService: "isvc-name",
        isDefault: false,
        crType: "inferenceservice",
      };

      const { result } = renderHook(
        () => useTunerLogic({ isActive: true, targetOverride }),
        { wrapper }
      );

      await waitFor(() => {
        expect(result.current.initialized).toBe(true);
      });

      await result.current.start();

      await waitFor(() => {
        expect(lastRequestBody).not.toBeNull();
        // KServe endpoint format: http://{name}-predictor.{namespace}.svc.cluster.local:8080
        const endpoint = lastRequestBody?.vllm_endpoint as string;
        expect(endpoint).toBe("http://isvc-name-predictor.isvc-ns.svc.cluster.local:8080");
      });
    });
  });
});