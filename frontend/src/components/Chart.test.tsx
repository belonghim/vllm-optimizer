import React from "react";
import { render, screen } from "@testing-library/react";
import { vi, describe, it, expect } from "vitest";
import Chart from "./Chart";

vi.mock("recharts", () => ({
  LineChart: ({ children }: { children: React.ReactNode }) => <div data-testid="line-chart">{children}</div>,
  Line: () => null,
  XAxis: () => null,
  YAxis: () => null,
  CartesianGrid: () => null,
  Tooltip: () => null,
  ResponsiveContainer: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  ReferenceLine: () => null,
}));

vi.mock("../contexts/ThemeContext", () => ({
  useThemeColors: () => ({
    textSecondary: "#999",
    border: "#ccc",
    tooltipBg: "#fff",
    tooltipBorder: "#ccc",
    tooltipText: "#000",
    COLORS: {
      red: "#ff0000",
      border: "#ccc",
      muted: "#999",
    },
  }),
}));

const baseProps = {
  data: [],
  lines: [{ key: "tps", color: "#ff0000", label: "TPS" }],
  title: "TPS Chart",
  yLabel: "TPS",
  timeRange: "Live" as const,
};

describe("Chart", () => {
  it("renders LineChart container", () => {
    render(<Chart {...baseProps} />);
    expect(screen.getByTestId("line-chart")).toBeInTheDocument();
  });

  it("renders with empty data without crashing", () => {
    render(<Chart {...baseProps} data={[]} />);
    expect(screen.getByTestId("line-chart")).toBeInTheDocument();
  });

  it("renders with time range prop", () => {
    render(<Chart {...baseProps} timeRange="1h" />);
    expect(screen.getByTestId("line-chart")).toBeInTheDocument();
  });
});
