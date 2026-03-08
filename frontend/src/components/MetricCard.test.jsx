import { render, screen } from "@testing-library/react";
import MetricCard from "./MetricCard";

describe("MetricCard", () => {
  it("renders label and value", () => {
    render(<MetricCard label="TPS" value={42.5} unit="tok/s" />);
    expect(screen.getByText("TPS")).toBeInTheDocument();
  });
});
