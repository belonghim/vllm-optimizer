import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
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
    it("renders Model ID column header", () => {
      render(<BenchmarkPage />);
      expect(screen.getByText("Model ID")).toBeInTheDocument();
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
        expect(screen.getByText("Saved load test results will appear here.")).toBeInTheDocument()
      );
    });

    it("shows error banner when fetch fails", async () => {
      mockEnabled = false;
      vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 500 }));
      render(<BenchmarkPage isActive={true} />);
      await waitFor(() =>
        expect(screen.getByText(/Failed to fetch benchmarks/)).toBeInTheDocument()
      );
    });
  });

  describe("delete", () => {
    it("shows delete button for each row", () => {
      render(<BenchmarkPage isActive={true} />);
      const buttons = screen.getAllByRole("button", { name: "Delete benchmark" });
      expect(buttons.length).toBeGreaterThan(0);
    });

    it("removes row after confirmed delete", async () => {
      const user = userEvent.setup();
      render(<BenchmarkPage isActive={true} />);

      const buttons = screen.getAllByRole("button", { name: "Delete benchmark" });
      const initialRows = screen.getAllByRole("row").length;
      await user.click(buttons[0]);
      await user.click(screen.getByRole("button", { name: "Confirm" }));

      await waitFor(() => {
        expect(screen.getAllByRole("row").length).toBe(initialRows - 1);
      });
    });

    it("keeps row when confirm cancelled", async () => {
      const user = userEvent.setup();
      render(<BenchmarkPage isActive={true} />);

      const buttons = screen.getAllByRole("button", { name: "Delete benchmark" });
      const initialRows = screen.getAllByRole("row").length;
      await user.click(buttons[0]);
      await user.click(screen.getByRole("button", { name: "Cancel" }));

      expect(screen.getAllByRole("row").length).toBe(initialRows);
    });
  });
});