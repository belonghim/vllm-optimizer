import { render, screen } from "@testing-library/react";
import MetricCard from "./MetricCard";

describe("MetricCard", () => {
  it("renders label and value", () => {
    render(<MetricCard label="TPS" value={42.5} unit="tok/s" />);
    expect(screen.getByText("TPS")).toBeInTheDocument();
    expect(screen.getByText(42.5)).toBeInTheDocument();
    expect(screen.getByText("tok/s")).toBeInTheDocument();
  });

  it("renders em dash when value is null", () => {
    render(<MetricCard label="RPS" value={null} unit="req/s" />);
    expect(screen.getByText("RPS")).toBeInTheDocument();
    expect(screen.getByText("—")).toBeInTheDocument();
  });
});
