import { render, screen, waitFor } from "@testing-library/react";
import { vi, describe, it, expect, beforeEach, afterEach } from "vitest";
import MonitorPage from "./MonitorPage";

beforeEach(() => {
  global.ResizeObserver = class ResizeObserver {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

describe("MonitorPage", () => {
  describe("mock mode", () => {
    beforeEach(() => {
      vi.mock("../contexts/MockDataContext", () => ({
        useMockData: () => ({ isMockEnabled: true }),
      }));
    });

    it("renders without crashing", () => {
      render(<MonitorPage />);
      expect(screen.getByText("Tokens / sec")).toBeInTheDocument();
    });

    it("renders metric cards with mock data", () => {
      render(<MonitorPage />);
      expect(screen.getByText("Tokens / sec")).toBeInTheDocument();
      expect(screen.getByText("TTFT Mean")).toBeInTheDocument();
      expect(screen.getByText("P99 Latency")).toBeInTheDocument();
      expect(screen.getByText("KV Cache")).toBeInTheDocument();
    });

    it("does not show error banner in mock mode", () => {
      render(<MonitorPage />);
      expect(screen.queryByText(/조회 실패/)).not.toBeInTheDocument();
    });
  });

  it("renders running and waiting request cards", () => {
    render(<MonitorPage />);
    expect(screen.getByText("Running Reqs")).toBeInTheDocument();
    expect(screen.getByText("Waiting Reqs")).toBeInTheDocument();
  });
});
