import React from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { vi, describe, it, expect, beforeEach, afterEach } from "vitest";
import TargetSelector from "../components/TargetSelector";
import { ClusterConfigProvider, useClusterConfig } from "../contexts/ClusterConfigContext";
import { http, HttpResponse } from "msw";
import { server } from "../mocks/server";
import { act } from "react";

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

describe("TargetSelector", () => {
  describe("Rendering", () => {
    it("renders placeholder when targets exist but no value is selected", async () => {
      server.use(
        http.get("/api/config", () =>
          HttpResponse.json({
            vllm_endpoint: "",
            vllm_namespace: "",
            vllm_is_name: "",
            cr_type: "inferenceservice",
            resolved_model_name: "",
          })
        )
      );

      render(<TargetSelector data-testid="test-selector" />, { wrapper });

      await waitFor(() => {
        expect(screen.getByTestId("test-selector")).toBeInTheDocument();
      });

      expect(screen.getByText("Select a target")).toBeInTheDocument();
    });

    it("shows placeholder when value does not match any context target", async () => {
      server.use(
        http.get("/api/config", () =>
          HttpResponse.json({
            vllm_endpoint: "",
            vllm_namespace: "",
            vllm_is_name: "",
            cr_type: "inferenceservice",
            resolved_model_name: "",
          })
        )
      );

      const nonExistentTarget = {
        namespace: "non-existent",
        inferenceService: "non-existent",
        isDefault: true,
        crType: "inferenceservice",
      };

      render(
        <TargetSelector data-testid="test-selector" value={nonExistentTarget} />,
        { wrapper }
      );

      await waitFor(() => {
        expect(screen.getByTestId("test-selector-trigger")).toBeInTheDocument();
      });

      expect(screen.getByText("Select a target")).toBeInTheDocument();
    });
  });

  describe("Dropdown", () => {
    it("opens dropdown when trigger is clicked", async () => {
      server.use(
        http.get("/api/config", () =>
          HttpResponse.json({
            vllm_endpoint: "",
            vllm_namespace: "",
            vllm_is_name: "",
            cr_type: "inferenceservice",
            resolved_model_name: "",
          })
        )
      );

      render(<TargetSelector data-testid="test-selector" />, { wrapper });

      await waitFor(() => {
        expect(screen.getByTestId("test-selector-trigger")).toBeInTheDocument();
      });

      fireEvent.click(screen.getByTestId("test-selector-trigger"));

      expect(screen.getByTestId("test-selector-dropdown")).toBeInTheDocument();
    });

    it("closes dropdown when clicked outside", async () => {
      server.use(
        http.get("/api/config", () =>
          HttpResponse.json({
            vllm_endpoint: "",
            vllm_namespace: "",
            vllm_is_name: "",
            cr_type: "inferenceservice",
            resolved_model_name: "",
          })
        )
      );

      render(<TargetSelector data-testid="test-selector" />, { wrapper });

      await waitFor(() => {
        expect(screen.getByTestId("test-selector-trigger")).toBeInTheDocument();
      });

      fireEvent.click(screen.getByTestId("test-selector-trigger"));

      await waitFor(() => {
        expect(screen.getByTestId("test-selector-dropdown")).toBeInTheDocument();
      });

      fireEvent.mouseDown(document.body);

      expect(screen.queryByTestId("test-selector-dropdown")).not.toBeInTheDocument();
    });

    it("closes dropdown when Escape is pressed", async () => {
      server.use(
        http.get("/api/config", () =>
          HttpResponse.json({
            vllm_endpoint: "",
            vllm_namespace: "",
            vllm_is_name: "",
            cr_type: "inferenceservice",
            resolved_model_name: "",
          })
        )
      );

      render(<TargetSelector data-testid="test-selector" />, { wrapper });

      await waitFor(() => {
        expect(screen.getByTestId("test-selector-trigger")).toBeInTheDocument();
      });

      fireEvent.click(screen.getByTestId("test-selector-trigger"));

      await waitFor(() => {
        expect(screen.getByTestId("test-selector-dropdown")).toBeInTheDocument();
      });

      fireEvent.keyDown(screen.getByTestId("test-selector-trigger"), {
        key: "Escape",
      });

      expect(screen.queryByTestId("test-selector-dropdown")).not.toBeInTheDocument();
    });
  });

  describe("Keyboard Navigation", () => {
    it("opens dropdown with ArrowDown key", async () => {
      server.use(
        http.get("/api/config", () =>
          HttpResponse.json({
            vllm_endpoint: "",
            vllm_namespace: "",
            vllm_is_name: "",
            cr_type: "inferenceservice",
            resolved_model_name: "",
          })
        )
      );

      render(<TargetSelector data-testid="test-selector" />, { wrapper });

      await waitFor(() => {
        expect(screen.getByTestId("test-selector-trigger")).toBeInTheDocument();
      });

      fireEvent.keyDown(screen.getByTestId("test-selector-trigger"), {
        key: "ArrowDown",
      });

      expect(screen.getByTestId("test-selector-dropdown")).toBeInTheDocument();
    });

    it("opens dropdown with Enter key", async () => {
      server.use(
        http.get("/api/config", () =>
          HttpResponse.json({
            vllm_endpoint: "",
            vllm_namespace: "",
            vllm_is_name: "",
            cr_type: "inferenceservice",
            resolved_model_name: "",
          })
        )
      );

      render(<TargetSelector data-testid="test-selector" />, { wrapper });

      await waitFor(() => {
        expect(screen.getByTestId("test-selector-trigger")).toBeInTheDocument();
      });

      fireEvent.keyDown(screen.getByTestId("test-selector-trigger"), {
        key: "Enter",
      });

      expect(screen.getByTestId("test-selector-dropdown")).toBeInTheDocument();
    });

    it("navigates options with ArrowDown key", async () => {
      server.use(
        http.get("/api/config", () =>
          HttpResponse.json({
            vllm_endpoint: "",
            vllm_namespace: "",
            vllm_is_name: "",
            cr_type: "inferenceservice",
            resolved_model_name: "",
          })
        )
      );

      render(<TargetSelector data-testid="test-selector" />, { wrapper });

      await waitFor(() => {
        expect(screen.getByTestId("test-selector-trigger")).toBeInTheDocument();
      });

      fireEvent.click(screen.getByTestId("test-selector-trigger"));

      await waitFor(() => {
        expect(screen.getByTestId("test-selector-dropdown")).toBeInTheDocument();
      });

      fireEvent.keyDown(screen.getByTestId("test-selector-trigger"), {
        key: "ArrowDown",
      });

      const options = screen.getAllByRole("option");
      expect(options.length).toBeGreaterThan(0);
    });

    it("selects option with Enter key", async () => {
      const onChange = vi.fn();

      server.use(
        http.get("/api/config", () =>
          HttpResponse.json({
            vllm_endpoint: "",
            vllm_namespace: "",
            vllm_is_name: "",
            cr_type: "inferenceservice",
            resolved_model_name: "",
          })
        )
      );

      render(
        <TargetSelector data-testid="test-selector" onChange={onChange} />,
        { wrapper }
      );

      await waitFor(() => {
        expect(screen.getByTestId("test-selector-trigger")).toBeInTheDocument();
      });

      fireEvent.click(screen.getByTestId("test-selector-trigger"));

      await waitFor(() => {
        expect(screen.getByTestId("test-selector-dropdown")).toBeInTheDocument();
      });

      fireEvent.keyDown(screen.getByTestId("test-selector-trigger"), {
        key: "ArrowDown",
      });

      fireEvent.keyDown(screen.getByTestId("test-selector-trigger"), {
        key: "Enter",
      });

      expect(onChange).toHaveBeenCalled();
    });
  });

  describe("Selection", () => {
    it("calls onChange when option is clicked", async () => {
      const onChange = vi.fn();

      server.use(
        http.get("/api/config", () =>
          HttpResponse.json({
            vllm_endpoint: "",
            vllm_namespace: "",
            vllm_is_name: "",
            cr_type: "inferenceservice",
            resolved_model_name: "",
          })
        )
      );

      render(
        <TargetSelector data-testid="test-selector" onChange={onChange} />,
        { wrapper }
      );

      await waitFor(() => {
        expect(screen.getByTestId("test-selector-trigger")).toBeInTheDocument();
      });

      fireEvent.click(screen.getByTestId("test-selector-trigger"));

      await waitFor(() => {
        expect(screen.getByTestId("test-selector-dropdown")).toBeInTheDocument();
      });

      const options = screen.getAllByRole("option");
      if (options.length > 0) {
        fireEvent.click(options[0]);
        expect(onChange).toHaveBeenCalled();
      }
    });

    it("closes dropdown after selection", async () => {
      const onChange = vi.fn();

      server.use(
        http.get("/api/config", () =>
          HttpResponse.json({
            vllm_endpoint: "",
            vllm_namespace: "",
            vllm_is_name: "",
            cr_type: "inferenceservice",
            resolved_model_name: "",
          })
        )
      );

      render(
        <TargetSelector data-testid="test-selector" onChange={onChange} />,
        { wrapper }
      );

      await waitFor(() => {
        expect(screen.getByTestId("test-selector-trigger")).toBeInTheDocument();
      });

      fireEvent.click(screen.getByTestId("test-selector-trigger"));

      await waitFor(() => {
        expect(screen.getByTestId("test-selector-dropdown")).toBeInTheDocument();
      });

      const options = screen.getAllByRole("option");
      if (options.length > 0) {
        fireEvent.click(options[0]);
      }

      expect(screen.queryByTestId("test-selector-dropdown")).not.toBeInTheDocument();
    });
  });

  describe("Grouping", () => {
    it("groups targets by CR type", async () => {
      server.use(
        http.get("/api/config", () =>
          HttpResponse.json({
            vllm_endpoint: "",
            vllm_namespace: "",
            vllm_is_name: "",
            cr_type: "inferenceservice",
            resolved_model_name: "",
          })
        )
      );

      render(<TargetSelector data-testid="test-selector" />, { wrapper });

      await waitFor(() => {
        expect(screen.getByTestId("test-selector-trigger")).toBeInTheDocument();
      });

      fireEvent.click(screen.getByTestId("test-selector-trigger"));

      await waitFor(() => {
        expect(screen.getByTestId("test-selector-dropdown")).toBeInTheDocument();
      });

      expect(screen.getByText("KServe (isvc)")).toBeInTheDocument();
    });

    it("shows star for default target", async () => {
      server.use(
        http.get("/api/config", () =>
          HttpResponse.json({
            vllm_endpoint: "",
            vllm_namespace: "",
            vllm_is_name: "",
            cr_type: "inferenceservice",
            resolved_model_name: "",
          })
        )
      );

      render(<TargetSelector data-testid="test-selector" />, { wrapper });

      await waitFor(() => {
        expect(screen.getByTestId("test-selector-trigger")).toBeInTheDocument();
      });

      fireEvent.click(screen.getByTestId("test-selector-trigger"));

      await waitFor(() => {
        expect(screen.getByTestId("test-selector-dropdown")).toBeInTheDocument();
      });

      const starElements = screen.getAllByText("★");
      expect(starElements.length).toBeGreaterThan(0);
    });
  });

  describe("Arrow indicator", () => {
    it("shows down arrow when closed", async () => {
      server.use(
        http.get("/api/config", () =>
          HttpResponse.json({
            vllm_endpoint: "",
            vllm_namespace: "",
            vllm_is_name: "",
            cr_type: "inferenceservice",
            resolved_model_name: "",
          })
        )
      );

      render(<TargetSelector data-testid="test-selector" />, { wrapper });

      await waitFor(() => {
        expect(screen.getByTestId("test-selector-trigger")).toBeInTheDocument();
      });

      expect(screen.getByText("▼")).toBeInTheDocument();
    });

    it("shows up arrow when open", async () => {
      server.use(
        http.get("/api/config", () =>
          HttpResponse.json({
            vllm_endpoint: "",
            vllm_namespace: "",
            vllm_is_name: "",
            cr_type: "inferenceservice",
            resolved_model_name: "",
          })
        )
      );

      render(<TargetSelector data-testid="test-selector" />, { wrapper });

      await waitFor(() => {
        expect(screen.getByTestId("test-selector-trigger")).toBeInTheDocument();
      });

      fireEvent.click(screen.getByTestId("test-selector-trigger"));

      await waitFor(() => {
        expect(screen.getByText("▲")).toBeInTheDocument();
      });
    });
  });
});
