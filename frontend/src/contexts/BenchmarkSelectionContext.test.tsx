import React from "react";
import { renderHook, act } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { BenchmarkSelectionProvider, useBenchmarkSelection } from "./BenchmarkSelectionContext";

const wrapper = ({ children }: { children: React.ReactNode }) => (
  <BenchmarkSelectionProvider>{children}</BenchmarkSelectionProvider>
);

describe("BenchmarkSelectionContext", () => {
  it("has empty selectedIds by default", () => {
    const { result } = renderHook(() => useBenchmarkSelection(), { wrapper });
    expect(result.current.selectedIds).toEqual([]);
  });

  it("adds a single id", () => {
    const { result } = renderHook(() => useBenchmarkSelection(), { wrapper });
    act(() => {
      result.current.setSelectedIds([1]);
    });
    expect(result.current.selectedIds).toEqual([1]);
  });

  it("supports multiple selected ids", () => {
    const { result } = renderHook(() => useBenchmarkSelection(), { wrapper });
    act(() => {
      result.current.setSelectedIds([1, 2, "abc"]);
    });
    expect(result.current.selectedIds).toEqual([1, 2, "abc"]);
  });

  it("clears ids by setting empty array", () => {
    const { result } = renderHook(() => useBenchmarkSelection(), { wrapper });
    act(() => {
      result.current.setSelectedIds([1, 2]);
    });
    act(() => {
      result.current.setSelectedIds([]);
    });
    expect(result.current.selectedIds).toEqual([]);
  });
});
