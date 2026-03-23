import { render, screen } from "@testing-library/react";
import ErrorAlert from "./ErrorAlert";

describe("ErrorAlert", () => {
  it("renders null when message is missing", () => {
    const { container } = render(<ErrorAlert message={null} />);
    expect(container.firstChild).toBeNull();
  });

  it("renders error message by default", () => {
    render(<ErrorAlert message="Something went wrong" />);
    const alert = screen.getByRole("alert");
    expect(alert).toHaveTextContent("⚠ Something went wrong");
    expect(alert).toHaveClass("error-alert");
    expect(alert).not.toHaveClass("error-alert--warning");
  });

  it("renders warning variant when severity is warning", () => {
    render(<ErrorAlert message="A minor warning" severity="warning" />);
    const alert = screen.getByRole("alert");
    expect(alert).toHaveTextContent("⚠ A minor warning");
    expect(alert).toHaveClass("error-alert");
    expect(alert).toHaveClass("error-alert--warning");
  });

  it("merges additional className", () => {
    render(<ErrorAlert message="Test" className="custom-class" />);
    const alert = screen.getByRole("alert");
    expect(alert).toHaveClass("error-alert");
    expect(alert).toHaveClass("custom-class");
  });
});
