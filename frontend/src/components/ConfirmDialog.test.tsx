/// <reference types="vitest/globals" />
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import ConfirmDialog from "./ConfirmDialog";

describe("ConfirmDialog", () => {
  it("renders nothing when closed", () => {
    const { container } = render(
      <ConfirmDialog open={false} message="Are you sure?" onConfirm={() => {}} onCancel={() => {}} />
    );
    expect(container.firstChild).toBeNull();
  });

  it("renders message when open", () => {
    render(
      <ConfirmDialog open={true} message="Are you sure?" onConfirm={() => {}} onCancel={() => {}} />
    );
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.getByText("Are you sure?")).toBeInTheDocument();
  });

  it("renders optional title", () => {
    render(
      <ConfirmDialog open={true} title="Confirm Delete" message="This cannot be undone" onConfirm={() => {}} onCancel={() => {}} />
    );
    expect(screen.getByText("Confirm Delete")).toBeInTheDocument();
  });

  it("calls onConfirm when Confirm clicked", async () => {
    const onConfirm = vi.fn();
    render(
      <ConfirmDialog open={true} message="Delete?" onConfirm={onConfirm} onCancel={() => {}} />
    );
    await userEvent.click(screen.getByText("Confirm"));
    expect(onConfirm).toHaveBeenCalledOnce();
  });

  it("calls onCancel when Cancel clicked", async () => {
    const onCancel = vi.fn();
    render(
      <ConfirmDialog open={true} message="Delete?" onConfirm={() => {}} onCancel={onCancel} />
    );
    await userEvent.click(screen.getByText("Cancel"));
    expect(onCancel).toHaveBeenCalledOnce();
  });
});
