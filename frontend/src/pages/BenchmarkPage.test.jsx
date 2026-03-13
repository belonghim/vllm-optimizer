import { render, screen } from "@testing-library/react";
import { vi } from "vitest";
import BenchmarkPage from "./BenchmarkPage";

vi.mock("../contexts/MockDataContext", () => ({
  useMockData: () => ({ isMockEnabled: true }),
}));

describe("BenchmarkPage", () => {
  it("renders Model column header", () => {
    render(<BenchmarkPage />);
    expect(screen.getByText("Model")).toBeInTheDocument();
  });

  it("renders GPU Eff. column header", () => {
    render(<BenchmarkPage />);
    expect(screen.getByText("GPU Eff.")).toBeInTheDocument();
  });
});
