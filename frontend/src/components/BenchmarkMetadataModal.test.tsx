import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import { vi, describe, it, expect } from "vitest";
import BenchmarkMetadataModal from "./BenchmarkMetadataModal";
import type { BenchmarkItem } from "../pages/BenchmarkPage";

const mockItem: BenchmarkItem = {
  id: 1,
  name: "bench-1",
  timestamp: 1700000000,
  result: {},
  metadata: {
    model_identifier: "llama-3-8b",
    notes: "initial run",
  },
};

describe("BenchmarkMetadataModal", () => {
  it("renders with existing metadata values", () => {
    render(
      <BenchmarkMetadataModal
        editing={mockItem}
        onClose={vi.fn()}
        onSave={vi.fn()}
      />
    );
    expect(screen.getByDisplayValue("llama-3-8b")).toBeInTheDocument();
    expect(screen.getByDisplayValue("initial run")).toBeInTheDocument();
  });

  it("calls onClose when Cancel button is clicked", () => {
    const onClose = vi.fn();
    render(
      <BenchmarkMetadataModal
        editing={mockItem}
        onClose={onClose}
        onSave={vi.fn()}
      />
    );
    fireEvent.click(screen.getByText("Cancel"));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("calls onSave with updated metadata on form submit", () => {
    const onSave = vi.fn();
    render(
      <BenchmarkMetadataModal
        editing={mockItem}
        onClose={vi.fn()}
        onSave={onSave}
      />
    );
    const modelInput = screen.getByDisplayValue("llama-3-8b");
    fireEvent.change(modelInput, { target: { value: "qwen2-7b" } });
    fireEvent.click(screen.getByText("Save"));
    expect(onSave).toHaveBeenCalledWith(1, expect.objectContaining({ model_identifier: "qwen2-7b" }));
  });

  it("renders empty modal for item without metadata", () => {
    render(
      <BenchmarkMetadataModal
        editing={{ ...mockItem, metadata: null }}
        onClose={vi.fn()}
        onSave={vi.fn()}
      />
    );
    expect(screen.getByText("Edit Benchmark Metadata")).toBeInTheDocument();
  });
});
