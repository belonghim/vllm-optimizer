import { render, screen, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi, describe, it, expect, afterEach } from "vitest";
import SlaProfileForm from "./SlaProfileForm";
import type { SlaFormState } from "./SlaProfileForm";

const defaultFormState: SlaFormState = {
  name: "",
  availMin: "",
  p95Ms: "",
  errRate: "",
  minTps: "",
  meanTtftMs: "",
  p95TtftMs: "",
};

function makeProps(overrides = {}) {
  return {
    formState: defaultFormState,
    onChange: vi.fn(),
    onSubmit: vi.fn((e) => e.preventDefault()),
    onCancel: vi.fn(),
    editingId: null as number | null,
    ...overrides,
  };
}

afterEach(() => {
  vi.clearAllMocks();
});

describe("SlaProfileForm", () => {
  it("renders Create New SLA Profile title when editingId is null", () => {
    render(<SlaProfileForm {...makeProps()} />);
    expect(screen.getByText("Create New SLA Profile")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Create Profile" })).toBeInTheDocument();
  });

  it("renders Edit SLA Profile title and Save/Cancel buttons when editingId is set", () => {
    render(<SlaProfileForm {...makeProps({ editingId: 5 })} />);
    expect(screen.getByText("Edit SLA Profile")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Cancel" })).toBeInTheDocument();
  });

  it("does not show Cancel button when editingId is null", () => {
    render(<SlaProfileForm {...makeProps()} />);
    expect(screen.queryByRole("button", { name: "Cancel" })).not.toBeInTheDocument();
  });

  it("calls onChange when name field is typed into", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<SlaProfileForm {...makeProps({ onChange })} />);
    await user.type(screen.getByPlaceholderText(/Llama3/), "My SLA");
    expect(onChange).toHaveBeenCalledWith("name", expect.any(String));
  });

  it("calls onSubmit when form is submitted", () => {
    const onSubmit = vi.fn((e) => e.preventDefault());
    render(<SlaProfileForm {...makeProps({ onSubmit })} />);
    fireEvent.submit(screen.getByRole("button", { name: "Create Profile" }).closest("form")!);
    expect(onSubmit).toHaveBeenCalled();
  });

  it("calls onCancel when Cancel button is clicked in edit mode", async () => {
    const user = userEvent.setup();
    const onCancel = vi.fn();
    render(<SlaProfileForm {...makeProps({ editingId: 3, onCancel })} />);
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    expect(onCancel).toHaveBeenCalled();
  });
});
