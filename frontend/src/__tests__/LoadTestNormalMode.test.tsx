import React from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { vi, describe, it, expect, beforeEach, afterEach } from "vitest";
import LoadTestNormalMode from "../components/LoadTestNormalMode";
import { ClusterConfigProvider } from "../contexts/ClusterConfigContext";
import { MockDataProvider } from "../contexts/MockDataContext";
import { http, HttpResponse } from "msw";
import { server } from "../mocks/server";

beforeEach(() => {
  vi.spyOn(Storage.prototype, "getItem").mockReturnValue(null);
  vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {});
});

afterEach(() => {
  vi.restoreAllMocks();
});

const wrapper = ({ children }: { children: React.ReactNode }) => (
  <ClusterConfigProvider>
    <MockDataProvider>{children}</MockDataProvider>
  </ClusterConfigProvider>
);

describe("LoadTestNormalMode", () => {
  describe("Endpoint Handling", () => {
    it("uses globalEndpoint when targetEndpoint is not provided", async () => {
      const globalEndpoint = "http://llm-ov-predictor.vllm-lab-dev.svc.cluster.local:8080";
      const onEndpointChange = vi.fn();

      server.use(
        http.get("/api/config", () =>
          HttpResponse.json({
            vllm_endpoint: globalEndpoint,
            vllm_namespace: "vllm-lab-dev",
            vllm_is_name: "llm-ov",
            cr_type: "inferenceservice",
            resolved_model_name: "qwen2-5-7b-instruct",
          })
        )
      );

      render(
        <LoadTestNormalMode
          isActive={true}
          onEndpointChange={onEndpointChange}
        />,
        { wrapper }
      );

      await waitFor(() => {
        expect(onEndpointChange).toHaveBeenCalledWith(globalEndpoint);
      });
    });

    it("uses targetEndpoint when provided", async () => {
      const targetEndpoint = "http://custom-predictor.custom-ns.svc.cluster.local:8080";
      const onEndpointChange = vi.fn();

      server.use(
        http.get("/api/config", () =>
          HttpResponse.json({
            vllm_endpoint: "http://llm-ov-predictor.vllm-lab-dev.svc.cluster.local:8080",
            vllm_namespace: "vllm-lab-dev",
            vllm_is_name: "llm-ov",
            cr_type: "inferenceservice",
            resolved_model_name: "qwen2-5-7b-instruct",
          })
        )
      );

      render(
        <LoadTestNormalMode
          isActive={true}
          targetEndpoint={targetEndpoint}
          onEndpointChange={onEndpointChange}
        />,
        { wrapper }
      );

      await waitFor(() => {
        expect(onEndpointChange).toHaveBeenCalledWith(targetEndpoint);
      });
    });
  });
});