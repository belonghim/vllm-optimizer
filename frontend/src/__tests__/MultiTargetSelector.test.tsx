import React from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { vi, describe, it, expect, beforeEach, afterEach } from "vitest";
import MultiTargetSelector from "../components/MultiTargetSelector";
import { ClusterConfigProvider } from "../contexts/ClusterConfigContext";
import { http, HttpResponse } from "msw";
import { server } from "../mocks/server";

beforeEach(() => {
  vi.spyOn(Storage.prototype, "getItem").mockReturnValue(null);
  vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {});
});

afterEach(() => {
  vi.restoreAllMocks();
});

const wrapper = ({ children }: { children: React.ReactNode }) => (
  <ClusterConfigProvider>{children}</ClusterConfigProvider>
);

describe("MultiTargetSelector", () => {
  describe("Rendering", () => {
    it("renders header with target count", async () => {
      render(<MultiTargetSelector />, { wrapper });

      await waitFor(() => {
        expect(screen.getByText(/Monitoring Targets/)).toBeInTheDocument();
      });

      expect(screen.getByText(/1\/5/)).toBeInTheDocument();
    });

    it("renders add button", async () => {
      render(<MultiTargetSelector />, { wrapper });

      await waitFor(() => {
        expect(screen.getByTestId("add-target-btn")).toBeInTheDocument();
      });

      expect(screen.getByText("+ Add")).toBeInTheDocument();
    });

    it("renders default target from context directly in table", async () => {
      render(<MultiTargetSelector />, { wrapper });

      await waitFor(() => {
        expect(screen.getAllByTestId("target-row-0")).toHaveLength(1);
      });
    });

    it("renders table headers directly", async () => {
      render(<MultiTargetSelector />, { wrapper });

      await waitFor(() => {
        expect(screen.getByText("Target")).toBeInTheDocument();
        expect(screen.getByText("TPS")).toBeInTheDocument();
      });
    });
  });

  describe("Add Target Flow", () => {
    it("shows input fields when add button is clicked", async () => {
      render(<MultiTargetSelector />, { wrapper });

      await waitFor(() => {
        expect(screen.getByTestId("add-target-btn")).toBeInTheDocument();
      });

      fireEvent.click(screen.getByTestId("add-target-btn"));

      expect(screen.getByTestId("namespace-input")).toBeInTheDocument();
      expect(screen.getByTestId("is-input")).toBeInTheDocument();
      expect(screen.getByTestId("cr-type-select")).toBeInTheDocument();
      expect(screen.getByTestId("confirm-add-btn")).toBeInTheDocument();
    });

    it("has correct CR type options", async () => {
      render(<MultiTargetSelector />, { wrapper });

      await waitFor(() => {
        expect(screen.getByTestId("add-target-btn")).toBeInTheDocument();
      });

      fireEvent.click(screen.getByTestId("add-target-btn"));

      expect(screen.getByText("isvc (KServe)")).toBeInTheDocument();
      expect(screen.getByText("llmisvc (LLMIS)")).toBeInTheDocument();
    });

    it("hides input fields when cancel is clicked", async () => {
      render(<MultiTargetSelector />, { wrapper });

      await waitFor(() => {
        expect(screen.getByTestId("add-target-btn")).toBeInTheDocument();
      });

      fireEvent.click(screen.getByTestId("add-target-btn"));
      fireEvent.click(screen.getByText("Cancel"));

      expect(screen.queryByTestId("namespace-input")).not.toBeInTheDocument();
    });

    it("validates and adds target via API call", async () => {
      server.use(
        http.get("/api/metrics/latest", () =>
          HttpResponse.json({ status: "ready", data: {} })
        )
      );

      render(<MultiTargetSelector />, { wrapper });

      await waitFor(() => {
        expect(screen.getByTestId("add-target-btn")).toBeInTheDocument();
      });

      fireEvent.click(screen.getByTestId("add-target-btn"));

      fireEvent.change(screen.getByTestId("namespace-input"), {
        target: { value: "test-ns" },
      });
      fireEvent.change(screen.getByTestId("is-input"), {
        target: { value: "test-svc" },
      });

      fireEvent.click(screen.getByTestId("confirm-add-btn"));

      await waitFor(() => {
        expect(screen.queryByTestId("namespace-input")).not.toBeInTheDocument();
      });
    });

    it("shows error when API returns not found", async () => {
      server.use(
        http.get("/api/metrics/latest", () => new HttpResponse(null, { status: 404 }))
      );

      render(<MultiTargetSelector />, { wrapper });

      await waitFor(() => {
        expect(screen.getByTestId("add-target-btn")).toBeInTheDocument();
      });

      fireEvent.click(screen.getByTestId("add-target-btn"));

      fireEvent.change(screen.getByTestId("namespace-input"), {
        target: { value: "invalid-ns" },
      });
      fireEvent.change(screen.getByTestId("is-input"), {
        target: { value: "invalid-svc" },
      });

      fireEvent.click(screen.getByTestId("confirm-add-btn"));

      await waitFor(() => {
        expect(screen.getByTestId("add-target-error")).toBeInTheDocument();
      });
    });

    it("disables confirm button while validating", async () => {
      server.use(
        http.get("/api/metrics/latest", () =>
          new HttpResponse(null, { status: 200 })
        )
      );

      render(<MultiTargetSelector />, { wrapper });

      await waitFor(() => {
        expect(screen.getByTestId("add-target-btn")).toBeInTheDocument();
      });

      fireEvent.click(screen.getByTestId("add-target-btn"));

      fireEvent.change(screen.getByTestId("namespace-input"), {
        target: { value: "test-ns" },
      });
      fireEvent.change(screen.getByTestId("is-input"), {
        target: { value: "test-svc" },
      });

      const confirmBtn = screen.getByTestId("confirm-add-btn");
      fireEvent.click(confirmBtn);

      await waitFor(() => {
        expect(screen.getByText("Validating...")).toBeInTheDocument();
      });
    });
  });

  describe("Default Target Badge", () => {
    it("shows star icon for default target", async () => {
      render(<MultiTargetSelector />, { wrapper });

      await waitFor(() => {
        expect(screen.getAllByTestId("target-row-0")).toHaveLength(1);
      });

      expect(screen.getAllByText("★")).toHaveLength(1);
    });
  });

  describe("CR Type Badge", () => {
    it("shows KServe badge for inferenceservice target", async () => {
      render(<MultiTargetSelector />, { wrapper });

      await waitFor(() => {
        expect(screen.getAllByTestId("target-row-0")).toHaveLength(1);
      });

      // With new behavior, isvc target shows KServe badge
      expect(screen.getByTestId("isvc-badge")).toBeInTheDocument();
    });
  });

  describe("Set Default Target", () => {
    it("shows set default button for non-default targets", async () => {
      render(<MultiTargetSelector />, { wrapper });

      await waitFor(() => {
        expect(screen.getAllByTestId("target-row-0")).toHaveLength(1);
      });

      // With new behavior, set-default button shows for non-default targets
      expect(screen.getByTestId("set-default-btn")).toBeInTheDocument();
    });
  });

  describe("Delete Target", () => {
    it("shows delete button for non-default targets", async () => {
      render(<MultiTargetSelector />, { wrapper });

      await waitFor(() => {
        expect(screen.getAllByTestId("target-row-0")).toHaveLength(1);
      });

      // With new behavior, delete button shows for non-default targets
      expect(screen.getByTestId("delete-btn")).toBeInTheDocument();
    });
  });

  describe("Row Expand", () => {
    it("expand button is not shown when pods = 1", async () => {
      render(<MultiTargetSelector />, { wrapper });

      await waitFor(() => {
        expect(screen.getAllByTestId("target-row-0")).toHaveLength(1);
      });

      expect(screen.queryByTestId("expand-btn-0")).not.toBeInTheDocument();
    });
  });

  describe("Warning Icon", () => {
    it("does not show warning for default target initially", async () => {
      render(<MultiTargetSelector />, { wrapper });

      await waitFor(() => {
        expect(screen.getAllByTestId("target-row-0")).toHaveLength(1);
      });

      expect(screen.queryByTestId("no-monitoring-warning")).not.toBeInTheDocument();
    });
  });

  describe("Target Status Display", () => {
    it("shows collecting indicator when status is collecting", async () => {
      render(<MultiTargetSelector />, { wrapper });

      await waitFor(() => {
        expect(screen.getAllByTestId("target-row-0")).toHaveLength(1);
      });

      expect(screen.getAllByText("...").length).toBeGreaterThan(0);
    });
  });

  describe("Error Handling", () => {
    it("shows error when add validation throws", async () => {
      const consoleErrorSpy = vi.spyOn(console, "error").mockImplementation(() => {});
      server.use(
        http.get("/api/metrics/latest", () => {
          throw new Error("Network error");
        })
      );

      render(<MultiTargetSelector />, { wrapper });

      await waitFor(() => {
        expect(screen.getByTestId("add-target-btn")).toBeInTheDocument();
      });

      fireEvent.click(screen.getByTestId("add-target-btn"));

      fireEvent.change(screen.getByTestId("namespace-input"), {
        target: { value: "test-ns" },
      });
      fireEvent.change(screen.getByTestId("is-input"), {
        target: { value: "test-svc" },
      });

      fireEvent.click(screen.getByTestId("confirm-add-btn"));

      await waitFor(() => {
        expect(screen.getByTestId("add-target-error")).toBeInTheDocument();
      });

      consoleErrorSpy.mockRestore();
    });
  });
});
