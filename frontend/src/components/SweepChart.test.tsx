/// <reference types="vitest/globals" />
import { render, screen } from "@testing-library/react";
import SweepChart from "./SweepChart";
import type { SweepStepResult } from "./SweepChart";

vi.mock("../contexts/ThemeContext", () => ({
  useThemeColors: () => ({ COLORS: ["#00ff00", "#ff0000"] }),
}));

vi.mock("recharts", () => ({
  ComposedChart: ({ children }: { children: React.ReactNode }) => <div data-testid="chart">{children}</div>,
  Line: () => null,
  XAxis: () => null,
  YAxis: () => null,
  CartesianGrid: () => null,
  Tooltip: () => null,
  Legend: () => null,
  ReferenceLine: () => null,
  ResponsiveContainer: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

const makeStep = (step: number, rps: number): SweepStepResult => ({
  step,
  rps,
  stats: { latency: { p99: 100, mean: 80 }, tps: { mean: 50 }, success: 10, failed: 0, total: 10, rps_actual: rps },
  saturated: false,
  saturation_reason: null,
});

describe("SweepChart", () => {
  it("renders with empty steps", () => {
    const { container } = render(<SweepChart steps={[]} />);
    expect(container).toBeInTheDocument();
  });

  it("renders chart with step data", () => {
    render(<SweepChart steps={[makeStep(1, 10), makeStep(2, 20)]} />);
    expect(screen.getByTestId("chart")).toBeInTheDocument();
  });

  it("renders saturation reference line when saturationRps provided", () => {
    render(<SweepChart steps={[makeStep(1, 10)]} saturationRps={10} />);
    expect(screen.getByTestId("chart")).toBeInTheDocument();
  });
});
