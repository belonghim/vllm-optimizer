import React from "react";
import { render, screen, act, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi, describe, it, expect, beforeEach, afterEach } from "vitest";
import MultiTargetSelector from "./MultiTargetSelector";
import { ClusterConfigProvider } from "../contexts/ClusterConfigContext";
import { http, HttpResponse } from "msw";
import { server } from "../mocks/server";

const TARGET_KEY = "test-ns/test-model/inferenceservice";
const TARGET_STATUSES = { [TARGET_KEY]: { status: "ready", hasMonitoringLabel: true } };
const TARGET_STATES = {
  [TARGET_KEY]: {
    status: "ready",
    data: { pods: 2, pods_ready: 2, tps: 10, rps: 5, ttft_mean: 100, ttft_p99: 200, latency_mean: 150, latency_p99: 300, kv_cache: 0.5, kv_hit_rate: 0.8, gpu_util: 0.7, gpu_mem_used: 10, gpu_mem_total: 40, running: 2, waiting: 0 },
  },
};
const SAMPLE_PODS = [
  { pod_name: "pod-0", tps: 5, rps: 2.5, ttft_mean: 100, ttft_p99: 200, latency_mean: 150, latency_p99: 300, kv_cache: 0.5, kv_hit_rate: 0.8, gpu_util: 0.7, gpu_mem_used: 10, gpu_mem_total: 40, running: 1, waiting: 0 },
  { pod_name: "pod-1", tps: 5, rps: 2.5, ttft_mean: 100, ttft_p99: 200, latency_mean: 150, latency_p99: 300, kv_cache: 0.5, kv_hit_rate: 0.8, gpu_util: 0.7, gpu_mem_used: 10, gpu_mem_total: 40, running: 1, waiting: 0 },
];

const wrapper = ({ children }: { children: React.ReactNode }) => (
  <ClusterConfigProvider>{children}</ClusterConfigProvider>
);

beforeEach(() => {
  vi.spyOn(Storage.prototype, "getItem").mockReturnValue(null);
  vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {});
  server.use(
    http.get("/api/config/default-targets", () =>
      HttpResponse.json({ isvc: { name: "", namespace: "" }, llmisvc: { name: "", namespace: "" } })
    ),
  );
});

afterEach(() => {
  vi.restoreAllMocks();
});

async function renderAndWaitReady() {
  render(
    <MultiTargetSelector targetStatuses={TARGET_STATUSES} targetStates={TARGET_STATES} />,
    { wrapper },
  );
  await waitFor(() => expect(screen.getByTestId("expand-btn-0")).toBeInTheDocument());
}

describe("MultiTargetSelector pod cache", () => {
  describe("Cache hit/miss", () => {
    it("does NOT re-fetch when cache is fresh (< 10s TTL)", async () => {
      let fetchCount = 0;
      server.use(
        http.post("/api/metrics/pods", () => {
          fetchCount++;
          return HttpResponse.json({ [TARGET_KEY]: { per_pod: SAMPLE_PODS } });
        }),
      );

      const mockNow = vi.spyOn(Date, "now").mockReturnValue(1_000_000);
      await renderAndWaitReady();

      const expandBtn = screen.getByTestId("expand-btn-0");

      await act(async () => { await userEvent.click(expandBtn); });
      await waitFor(() => expect(fetchCount).toBe(1));

      await act(async () => { await userEvent.click(expandBtn); });
      mockNow.mockReturnValue(1_005_000);
      await act(async () => { await userEvent.click(expandBtn); });
      expect(fetchCount).toBe(1);
    });

    it("re-fetches when cache is stale (> 10s TTL)", async () => {
      let fetchCount = 0;
      server.use(
        http.post("/api/metrics/pods", () => {
          fetchCount++;
          return HttpResponse.json({ [TARGET_KEY]: { per_pod: SAMPLE_PODS } });
        }),
      );

      const mockNow = vi.spyOn(Date, "now").mockReturnValue(1_000_000);
      await renderAndWaitReady();

      const expandBtn = screen.getByTestId("expand-btn-0");

      await act(async () => { await userEvent.click(expandBtn); });
      await waitFor(() => expect(fetchCount).toBe(1));

      await act(async () => { await userEvent.click(expandBtn); });
      mockNow.mockReturnValue(1_011_000);
      await act(async () => { await userEvent.click(expandBtn); });
      await waitFor(() => expect(fetchCount).toBe(2));
    });
  });

  describe("Request deduplication", () => {
    it("does not start a second fetch when one is already pending", async () => {
      let fetchCount = 0;
      let resolveFirst!: () => void;
      server.use(
        http.post("/api/metrics/pods", () => {
          fetchCount++;
          return new Promise<Response>(resolve => {
            resolveFirst = () => resolve(HttpResponse.json({ [TARGET_KEY]: { per_pod: SAMPLE_PODS } }) as unknown as Response);
          });
        }),
      );

      await renderAndWaitReady();
      const expandBtn = screen.getByTestId("expand-btn-0");

      await act(async () => { await userEvent.click(expandBtn); });
      await act(async () => { await userEvent.click(expandBtn); });
      await act(async () => { await userEvent.click(expandBtn); });

      expect(fetchCount).toBe(1);
      resolveFirst();
    });
  });

  describe("Graceful degradation", () => {
    it("keeps stale data visible when re-fetch fails after TTL", async () => {
      let callIndex = 0;
      server.use(
        http.post("/api/metrics/pods", () => {
          callIndex++;
          if (callIndex === 1) {
            return HttpResponse.json({ [TARGET_KEY]: { per_pod: SAMPLE_PODS } });
          }
          return HttpResponse.error();
        }),
      );

      const mockNow = vi.spyOn(Date, "now").mockReturnValue(1_000_000);
      await renderAndWaitReady();
      const expandBtn = screen.getByTestId("expand-btn-0");

      await act(async () => { await userEvent.click(expandBtn); });
      await waitFor(() => expect(screen.getByText("pod-0")).toBeInTheDocument());

      await act(async () => { await userEvent.click(expandBtn); });
      mockNow.mockReturnValue(1_011_000);
      await act(async () => { await userEvent.click(expandBtn); });
      await waitFor(() => expect(callIndex).toBe(2));

      expect(screen.getByText("pod-0")).toBeInTheDocument();
    });
  });
});
