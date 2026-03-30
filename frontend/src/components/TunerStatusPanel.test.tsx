import { render, screen, fireEvent } from "@testing-library/react";
import { vi, describe, it, expect } from "vitest";
import TunerStatusPanel from "./TunerStatusPanel";
import { ERROR_MESSAGES } from "../constants/errorMessages";

const defaultProps = {
  error: null,
  warning: null,
  applyStatus: null,
  interruptedWarning: null,
  autoBenchmark: false,
  benchmarkSaved: false,
  benchmarkSavedId: null,
  onDismissInterrupted: vi.fn(),
  onAutoBenchmarkChange: vi.fn(),
  onTabChange: undefined,
};

describe("TunerStatusPanel", () => {
  it("renders error alert when error prop is set", () => {
    render(<TunerStatusPanel {...defaultProps} error="Something went wrong" />);
    expect(screen.getByRole("alert")).toHaveTextContent("Something went wrong");
  });

  it("renders warning alert when warning prop is set", () => {
    render(<TunerStatusPanel {...defaultProps} warning="Low memory" />);
    expect(screen.getByRole("alert")).toHaveTextContent("Low memory");
  });

  it("shows success message when applyStatus is 'success'", () => {
    render(<TunerStatusPanel {...defaultProps} applyStatus="success" />);
    expect(screen.getByRole("status")).toHaveTextContent(ERROR_MESSAGES.TUNER.APPLY_BEST_SUCCESS);
  });

  it("shows current values success message when applyStatus matches", () => {
    render(<TunerStatusPanel {...defaultProps} applyStatus={ERROR_MESSAGES.TUNER.APPLY_CURRENT_SUCCESS} />);
    expect(screen.getByRole("status")).toHaveTextContent(ERROR_MESSAGES.TUNER.APPLY_CURRENT_VALUES_SUCCESS);
  });

  it("renders interrupted warning with dismiss button", () => {
    const onDismiss = vi.fn();
    render(<TunerStatusPanel {...defaultProps} interruptedWarning="Previous tuning was interrupted." onDismissInterrupted={onDismiss} />);
    expect(screen.getByRole("alert")).toHaveTextContent("Previous tuning was interrupted.");
    const dismissBtn = screen.getByRole("button", { name: /dismiss tuner interruption warning/i });
    fireEvent.click(dismissBtn);
    expect(onDismiss).toHaveBeenCalledTimes(1);
  });

  it("does not render interrupted warning when prop is null", () => {
    render(<TunerStatusPanel {...defaultProps} interruptedWarning={null} />);
    expect(screen.queryByText(/interrupted/i)).not.toBeInTheDocument();
  });

  it("renders auto-benchmark checkbox and calls handler on change", () => {
    const onChange = vi.fn();
    render(<TunerStatusPanel {...defaultProps} autoBenchmark={false} onAutoBenchmarkChange={onChange} />);
    const checkbox = screen.getByRole("checkbox");
    expect(checkbox).not.toBeChecked();
    fireEvent.click(checkbox);
    expect(onChange).toHaveBeenCalledWith(true);
  });

  it("renders auto-benchmark checkbox as checked when autoBenchmark is true", () => {
    render(<TunerStatusPanel {...defaultProps} autoBenchmark={true} />);
    expect(screen.getByRole("checkbox")).toBeChecked();
  });

  it("shows benchmark saved message with ID", () => {
    render(<TunerStatusPanel {...defaultProps} benchmarkSaved={true} benchmarkSavedId={42} />);
    expect(screen.getByRole("status")).toHaveTextContent(/Benchmark saved.*ID: 42/);
  });

  it("shows benchmark saved message without ID when benchmarkSavedId is null", () => {
    render(<TunerStatusPanel {...defaultProps} benchmarkSaved={true} benchmarkSavedId={null} />);
    expect(screen.getByRole("status")).toHaveTextContent("Benchmark saved ✓");
  });

  it("shows 'Go to BenchmarkPage' button when benchmarkSaved and onTabChange provided", () => {
    const onTabChange = vi.fn();
    render(<TunerStatusPanel {...defaultProps} benchmarkSaved={true} onTabChange={onTabChange} />);
    const btn = screen.getByRole("button", { name: /go to benchmarkpage/i });
    fireEvent.click(btn);
    expect(onTabChange).toHaveBeenCalledWith("benchmark");
  });

  it("does not show 'Go to BenchmarkPage' button when onTabChange is undefined", () => {
    render(<TunerStatusPanel {...defaultProps} benchmarkSaved={true} onTabChange={undefined} />);
    expect(screen.queryByRole("button", { name: /go to benchmarkpage/i })).not.toBeInTheDocument();
  });
});
