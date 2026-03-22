import { render, screen, waitFor } from "@testing-library/react";
import { vi, describe, it, expect, beforeEach, afterEach } from "vitest";
import BenchmarkPage from "./BenchmarkPage";

let mockEnabled = true;

vi.mock("../contexts/MockDataContext", () => ({
  useMockData: () => ({ isMockEnabled: mockEnabled }),
}));

beforeEach(() => {
  global.ResizeObserver = class ResizeObserver {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
});

afterEach(() => {
  mockEnabled = true;
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

describe("BenchmarkPage", () => {
  describe("mock mode", () => {
    it("renders Model column header", () => {
      render(<BenchmarkPage />);
      expect(screen.getByText("Model")).toBeInTheDocument();
    });

    it("renders GPU Eff. column header", () => {
      render(<BenchmarkPage />);
      expect(screen.getByText("GPU Eff.")).toBeInTheDocument();
    });

    it("renders benchmark rows with mock data", () => {
      render(<BenchmarkPage />);
      const rows = screen.getAllByRole("row");
      expect(rows.length).toBeGreaterThan(1);
    });
  });

  describe("real API mode", () => {
    it("shows empty state message when benchmarks list is empty", async () => {
      mockEnabled = false;
      vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
        ok: true,
        json: async () => [],
      }));
      render(<BenchmarkPage isActive={true} />);
      await waitFor(() =>
        expect(screen.getByText("부하 테스트 결과를 저장하면 여기 나타납니다.")).toBeInTheDocument()
      );
    });

    it("shows error banner when fetch fails", async () => {
      mockEnabled = false;
      vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 500 }));
      render(<BenchmarkPage isActive={true} />);
      await waitFor(() =>
        expect(screen.getByText(/벤치마크 조회 실패/)).toBeInTheDocument()
      );
    });
  });
});