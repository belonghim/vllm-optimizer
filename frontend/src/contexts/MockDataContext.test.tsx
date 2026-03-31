import React from "react";
import { renderHook, act } from "@testing-library/react";
import { vi, describe, it, expect, beforeEach, afterEach } from "vitest";
import { MockDataProvider, useMockData } from "./MockDataContext";

beforeEach(() => {
  vi.spyOn(Storage.prototype, "getItem").mockReturnValue(null);
  vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {});
});

afterEach(() => {
  vi.restoreAllMocks();
});

const wrapper = ({ children }: { children: React.ReactNode }) => (
  <MockDataProvider>{children}</MockDataProvider>
);

describe("MockDataContext", () => {
  it("defaults to isMockEnabled=false when no stored value", () => {
    const { result } = renderHook(() => useMockData(), { wrapper });
    expect(result.current.isMockEnabled).toBe(false);
  });

  it("reads stored value from localStorage", () => {
    vi.spyOn(Storage.prototype, "getItem").mockReturnValue("false");
    const { result } = renderHook(() => useMockData(), { wrapper });
    expect(result.current.isMockEnabled).toBe(false);
  });

  it("toggles isMockEnabled when toggleMockEnabled is called", () => {
    const { result } = renderHook(() => useMockData(), { wrapper });
    expect(result.current.isMockEnabled).toBe(false);
    act(() => {
      result.current.toggleMockEnabled();
    });
    expect(result.current.isMockEnabled).toBe(true);
  });

  it("persists toggle to localStorage", () => {
    const setItemSpy = vi.spyOn(Storage.prototype, "setItem");
    const { result } = renderHook(() => useMockData(), { wrapper });
    act(() => {
      result.current.toggleMockEnabled();
    });
    expect(setItemSpy).toHaveBeenCalledWith("vllm-opt-mock-enabled", "true");
  });
});
