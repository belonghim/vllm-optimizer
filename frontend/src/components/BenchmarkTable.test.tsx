import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi, describe, it, expect, beforeEach, afterEach } from "vitest";
import { createRef } from "react";
import BenchmarkTable from "./BenchmarkTable";
import type { BenchmarkItem } from "../pages/BenchmarkPage";

function makeBenchmark(id: number, name: string): BenchmarkItem {
  return {
    id,
    name,
    timestamp: 1700000000,
    result: { tps: { mean: 42.5 }, latency: { p99: 0.123 }, rps_actual: 10.0 },
    metadata: null,
    config: { model: "test-model" },
  };
}

function makeProps(overrides = {}) {
  return {
    benchmarks: [],
    selected: [] as (string | number)[],
    expanded: [] as (string | number)[],
    loading: false,
    importing: false,
    importInputRef: createRef<HTMLInputElement>(),
    onToggleSelect: vi.fn(),
    onToggleExpand: vi.fn(),
    onDelete: vi.fn(),
    onEdit: vi.fn(),
    onExportJSON: vi.fn(),
    onExportCSV: vi.fn(),
    onImport: vi.fn(),
    onBulkDelete: vi.fn(),
    ...overrides,
  };
}

beforeEach(() => {
  global.ResizeObserver = class ResizeObserver {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
});

afterEach(() => {
  vi.clearAllMocks();
});

describe("BenchmarkTable", () => {
  it("renders table column headers", () => {
    render(<BenchmarkTable {...makeProps()} />);
    expect(screen.getByText("Name")).toBeInTheDocument();
    expect(screen.getByText("Model ID")).toBeInTheDocument();
    expect(screen.getByText("TPS")).toBeInTheDocument();
    expect(screen.getByText("P99 ms")).toBeInTheDocument();
    expect(screen.getByText("GPU Eff.")).toBeInTheDocument();
  });

  it("shows empty state message when no benchmarks", () => {
    render(<BenchmarkTable {...makeProps({ benchmarks: [] })} />);
    expect(screen.getByText("Saved load test results will appear here.")).toBeInTheDocument();
  });

  it("shows loading indicator when loading is true", () => {
    render(<BenchmarkTable {...makeProps({ loading: true })} />);
    expect(screen.getByText("Loading...")).toBeInTheDocument();
    expect(screen.queryByText("Saved load test results will appear here.")).not.toBeInTheDocument();
  });

  it("renders benchmark rows with data", () => {
    const benchmarks = [makeBenchmark(1, "Run Alpha"), makeBenchmark(2, "Run Beta")];
    render(<BenchmarkTable {...makeProps({ benchmarks })} />);
    expect(screen.getByText("Run Alpha")).toBeInTheDocument();
    expect(screen.getByText("Run Beta")).toBeInTheDocument();
  });

  it("calls onDelete when delete button is clicked", async () => {
    const user = userEvent.setup();
    const onDelete = vi.fn();
    const benchmarks = [makeBenchmark(1, "Run Alpha")];
    render(<BenchmarkTable {...makeProps({ benchmarks, onDelete })} />);

    const deleteBtn = screen.getByRole("button", { name: "Delete benchmark" });
    await user.click(deleteBtn);
    expect(onDelete).toHaveBeenCalledWith(benchmarks[0], expect.anything());
  });

  it("calls onToggleExpand when a row is clicked", async () => {
    const user = userEvent.setup();
    const onToggleExpand = vi.fn();
    const benchmarks = [makeBenchmark(42, "Run Alpha")];
    render(<BenchmarkTable {...makeProps({ benchmarks, onToggleExpand })} />);

    await user.click(screen.getByText("Run Alpha"));
    expect(onToggleExpand).toHaveBeenCalledWith(42);
  });

  it("shows expanded metadata detail when row is in expanded list", () => {
    const b = { ...makeBenchmark(1, "Run Alpha"), metadata: { model_identifier: "meta-llama-3", hardware_type: "A100" } };
    render(<BenchmarkTable {...makeProps({ benchmarks: [b], expanded: [1] })} />);
    expect(screen.getByText("Model ID:")).toBeInTheDocument();
    expect(screen.getAllByText("meta-llama-3").length).toBeGreaterThan(0);
    expect(screen.getByText("A100")).toBeInTheDocument();
  });

  it("shows GuideLLM badge for imported benchmarks", () => {
    const b = { ...makeBenchmark(1, "GuideLLM Run"), metadata: { source: "guidellm" } };
    render(<BenchmarkTable {...makeProps({ benchmarks: [b] })} />);
    expect(screen.getByText("GuideLLM")).toBeInTheDocument();
  });
});
