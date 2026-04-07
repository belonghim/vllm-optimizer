import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import ExpandablePodRow from "./ExpandablePodRow";
import type { PerPodMetricSnapshot } from "../types";

describe("ExpandablePodRow", () => {
  const makePod = (overrides: Partial<PerPodMetricSnapshot> = {}): PerPodMetricSnapshot => ({
    pod_name: "test-pod-0",
    tps: 100,
    rps: 12.5,
    kv_cache: 45.2,
    running: 3,
    waiting: 1,
    gpu_util: 65.1,
    gpu_mem_used: 18.4,
    ...overrides,
  });

  it("renders pod metrics correctly", () => {
    const pods: PerPodMetricSnapshot[] = [makePod({ pod_name: "test-pod", tps: 100, rps: 12.5, running: 3, waiting: 1, kv_cache: 45.2, gpu_util: 65.1, gpu_mem_used: 18.4 })];
    render(<ExpandablePodRow pods={pods} />);

    expect(screen.getByText("test-pod")).toBeInTheDocument();
    expect(screen.getByText("100.0")).toBeInTheDocument();
    expect(screen.getByText("12.5")).toBeInTheDocument();
    expect(screen.getByText("3")).toBeInTheDocument();
    expect(screen.getByText("1")).toBeInTheDocument();
    expect(screen.getByText("45.2")).toBeInTheDocument();
    expect(screen.getByText("65.1")).toBeInTheDocument();
    expect(screen.getByText(/18\.4/)).toBeInTheDocument();
  });

  it("handles missing metrics", () => {
    const pods: PerPodMetricSnapshot[] = [
      makePod({ tps: null, rps: null, kv_cache: null, running: null, waiting: null, gpu_util: null, gpu_mem_used: null }),
    ];
    render(<ExpandablePodRow pods={pods} />);

    // fmt returns "—" for null/undefined
    const dashes = screen.getAllByText("—");
    expect(dashes.length).toBeGreaterThan(0);
  });

  it("returns null when pods array is empty", () => {
    const { container } = render(<ExpandablePodRow pods={[]} />);
    // Component returns null when pods.length === 0
    expect(container.firstChild).toBeNull();
  });

  it("uses target color", () => {
    const pods: PerPodMetricSnapshot[] = [makePod()];
    const { container } = render(<ExpandablePodRow pods={pods} parentColor="#ff0000" />);

    const th = container.querySelector("th");
    const style = th?.getAttribute("style") ?? "";
    expect(style).toContain("rgb(255, 0, 0)");
  });
});
