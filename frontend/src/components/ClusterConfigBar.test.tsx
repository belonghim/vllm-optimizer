import React from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { vi, describe, it, expect, beforeEach, afterEach } from "vitest";
import ClusterConfigBar from "./ClusterConfigBar";
import { ClusterConfigProvider } from "../contexts/ClusterConfigContext";

function renderWithProvider() {
  return render(
    <ClusterConfigProvider>
      <ClusterConfigBar />
    </ClusterConfigProvider>
  );
}

beforeEach(() => {
  vi.spyOn(Storage.prototype, "getItem").mockReturnValue(null);
  vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {});
  vi.spyOn(global, "fetch").mockResolvedValue({
    json: () =>
      Promise.resolve({ vllm_endpoint: "http://test:8080", vllm_namespace: "test-ns", vllm_is_name: "test-is" }),
    ok: true,
  } as unknown as Response);
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("ClusterConfigBar", () => {
  it("renders endpoint input", async () => {
    renderWithProvider();
    await waitFor(() => {
      const inputs = screen.queryAllByRole("textbox");
      expect(inputs.length).toBeGreaterThan(0);
    });
  });

  it("shows unsaved indicator when input changes", async () => {
    renderWithProvider();
    await waitFor(() => {
      const inputs = screen.queryAllByRole("textbox");
      expect(inputs.length).toBeGreaterThan(0);
    });
    const inputs = screen.getAllByRole("textbox");
    fireEvent.change(inputs[0], { target: { value: "http://new-endpoint:8080" } });
    await waitFor(() => {
      expect(screen.getByText("⚠ Unsaved")).toBeInTheDocument();
    });
  });

  it("renders without crashing when context is loading", () => {
    renderWithProvider();
    expect(document.body).toBeTruthy();
  });
});
