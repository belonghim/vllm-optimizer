import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { vi, describe, it, expect, beforeEach } from "vitest";
import TargetAddForm from "./TargetAddForm";
import { useClusterConfig } from "../contexts/ClusterConfigContext";

vi.mock("../contexts/ClusterConfigContext", () => ({
  useClusterConfig: vi.fn(),
}));

vi.mock("../utils/authFetch", () => ({
  authFetch: vi.fn(),
}));

import { authFetch } from "../utils/authFetch";

describe("TargetAddForm", () => {
  const mockAddTarget = vi.fn();
  const mockOnSuccess = vi.fn();
  const mockOnCancel = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(useClusterConfig).mockReturnValue({
      addTarget: mockAddTarget,
      crType: "inferenceservice",
    } as unknown as ReturnType<typeof useClusterConfig>);
  });

  it("renders namespace input, CR type dropdown, and Discover button", () => {
    render(<TargetAddForm />);

    expect(screen.getByPlaceholderText("Namespace")).toBeInTheDocument();
    expect(screen.getByLabelText("CR Type")).toBeInTheDocument();
    expect(screen.getByText("isvc (KServe)")).toBeInTheDocument();
    expect(screen.getByText("LLMIS (llmisvc)")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Discover" })).toBeInTheDocument();
  });

  it("calls /api/metrics/discover with correct namespace param when Discover clicked", async () => {
    vi.mocked(authFetch).mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ isvc: [], llmisvc: [] }),
    } as unknown as Response);

    render(<TargetAddForm />);

    fireEvent.change(screen.getByPlaceholderText("Namespace"), {
      target: { value: "vllm-lab-dev" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Discover" }));

    await waitFor(() => {
      expect(authFetch).toHaveBeenCalledWith(
        "/api/metrics/discover?namespace=vllm-lab-dev"
      );
    });
  });

  it("shows dropdown with discovered CRs when CRs are found", async () => {
    vi.mocked(authFetch).mockResolvedValueOnce({
      ok: true,
      json: () =>
        Promise.resolve({
          isvc: ["llm-ov", "llm-cuda"],
          llmisvc: [],
        }),
    } as unknown as Response);

    render(<TargetAddForm />);

    fireEvent.change(screen.getByPlaceholderText("Namespace"), {
      target: { value: "vllm-lab-dev" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Discover" }));

    await waitFor(() => {
      expect(screen.getByText("Select Resource:")).toBeInTheDocument();
      expect(screen.getByText("llm-ov")).toBeInTheDocument();
      expect(screen.getByText("llm-cuda")).toBeInTheDocument();
    });
  });

  it("shows manual input field when no CRs are found", async () => {
    vi.mocked(authFetch).mockResolvedValueOnce({
      ok: true,
      json: () =>
        Promise.resolve({
          isvc: [],
          llmisvc: [],
        }),
    } as unknown as Response);

    render(<TargetAddForm />);

    fireEvent.change(screen.getByPlaceholderText("Namespace"), {
      target: { value: "empty-ns" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Discover" }));

    await waitFor(() => {
      expect(
        screen.getByText("No resources found. Enter manually:")
      ).toBeInTheDocument();
      expect(
        screen.getByPlaceholderText("InferenceService Name")
      ).toBeInTheDocument();
    });
  });

  it("calls addTarget with correct params when Add Target clicked (discovered CR)", async () => {
    vi.mocked(authFetch).mockResolvedValueOnce({
      ok: true,
      json: () =>
        Promise.resolve({
          isvc: ["llm-ov"],
          llmisvc: [],
        }),
    } as unknown as Response);

    render(<TargetAddForm onSuccess={mockOnSuccess} />);

    fireEvent.change(screen.getByPlaceholderText("Namespace"), {
      target: { value: "vllm-lab-dev" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Discover" }));

    await waitFor(() => {
      expect(screen.getByText("llm-ov")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: "Add Target" }));

    await waitFor(() => {
      expect(mockAddTarget).toHaveBeenCalledWith(
        "vllm-lab-dev",
        "llm-ov",
        "inferenceservice"
      );
    });
  });

  it("calls addTarget with correct params when Add Target clicked (manual input)", async () => {
    vi.mocked(authFetch).mockResolvedValueOnce({
      ok: true,
      json: () =>
        Promise.resolve({
          isvc: [],
          llmisvc: [],
        }),
    } as unknown as Response);

    render(<TargetAddForm onSuccess={mockOnSuccess} />);

    fireEvent.change(screen.getByPlaceholderText("Namespace"), {
      target: { value: "vllm-lab-dev" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Discover" }));

    await waitFor(() => {
      expect(
        screen.getByPlaceholderText("InferenceService Name")
      ).toBeInTheDocument();
    });

    fireEvent.change(screen.getByPlaceholderText("InferenceService Name"), {
      target: { value: "my-custom-llm" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Add Target" }));

    await waitFor(() => {
      expect(mockAddTarget).toHaveBeenCalledWith(
        "vllm-lab-dev",
        "my-custom-llm",
        "inferenceservice"
      );
    });
  });

  it("calls onSuccess callback after adding target", async () => {
    vi.mocked(authFetch).mockResolvedValueOnce({
      ok: true,
      json: () =>
        Promise.resolve({
          isvc: ["llm-ov"],
          llmisvc: [],
        }),
    } as unknown as Response);

    render(<TargetAddForm onSuccess={mockOnSuccess} />);

    fireEvent.change(screen.getByPlaceholderText("Namespace"), {
      target: { value: "vllm-lab-dev" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Discover" }));

    await waitFor(() => {
      expect(screen.getByText("llm-ov")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: "Add Target" }));

    await waitFor(() => {
      expect(mockOnSuccess).toHaveBeenCalled();
    });
  });

  it("calls onCancel callback when Cancel clicked", () => {
    render(<TargetAddForm onCancel={mockOnCancel} />);

    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(mockOnCancel).toHaveBeenCalled();
  });

  it("uses llmisvc data when CR type is llminferenceservice", async () => {
    vi.mocked(useClusterConfig).mockReturnValue({
      addTarget: mockAddTarget,
      crType: "llminferenceservice",
    } as unknown as ReturnType<typeof useClusterConfig>);

    vi.mocked(authFetch).mockResolvedValueOnce({
      ok: true,
      json: () =>
        Promise.resolve({
          isvc: [],
          llmisvc: ["small-llm-d"],
        }),
    } as unknown as Response);

    render(<TargetAddForm />);

    fireEvent.change(screen.getByPlaceholderText("Namespace"), {
      target: { value: "llm-d-demo" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Discover" }));

    await waitFor(() => {
      expect(screen.getByText("small-llm-d")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: "Add Target" }));

    await waitFor(() => {
      expect(mockAddTarget).toHaveBeenCalledWith(
        "llm-d-demo",
        "small-llm-d",
        "llminferenceservice"
      );
    });
  });

  it("shows error message when discovery fails", async () => {
    vi.mocked(authFetch).mockResolvedValueOnce({
      ok: false,
    } as unknown as Response);

    render(<TargetAddForm />);

    fireEvent.change(screen.getByPlaceholderText("Namespace"), {
      target: { value: "invalid-ns" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Discover" }));

    await waitFor(() => {
      expect(screen.getByText("Failed to discover resources")).toBeInTheDocument();
    });
  });

  it("shows error when namespace is empty and Discover clicked", async () => {
    render(<TargetAddForm />);

    const namespaceInput = screen.getByPlaceholderText("Namespace");
    fireEvent.change(namespaceInput, { target: { value: "test" } });
    fireEvent.change(namespaceInput, { target: { value: "" } });

    const discoverBtn = screen.getByRole("button", { name: "Discover" });
    expect(discoverBtn).toBeDisabled();

    fireEvent.click(discoverBtn);
    expect(authFetch).not.toHaveBeenCalled();
  });

  it("disables Add Target button when namespace is empty", () => {
    render(<TargetAddForm />);

    expect(screen.getByRole("button", { name: "Add Target" })).toBeDisabled();
  });

  it("disables Discover button when namespace is empty", () => {
    render(<TargetAddForm />);

    expect(screen.getByRole("button", { name: "Discover" })).toBeDisabled();
  });

  it("clears discovered names when CR type changes", async () => {
    vi.mocked(authFetch).mockResolvedValueOnce({
      ok: true,
      json: () =>
        Promise.resolve({
          isvc: ["llm-ov"],
          llmisvc: [],
        }),
    } as unknown as Response);

    render(<TargetAddForm />);

    fireEvent.change(screen.getByPlaceholderText("Namespace"), {
      target: { value: "vllm-lab-dev" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Discover" }));

    await waitFor(() => {
      expect(screen.getByText("llm-ov")).toBeInTheDocument();
    });

    fireEvent.change(screen.getByLabelText("CR Type"), {
      target: { value: "llminferenceservice" },
    });

    expect(screen.queryByText("Select Resource:")).not.toBeInTheDocument();
  });
});
