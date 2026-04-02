// Test fixtures use LLMIS-style names (llm-d-demo/small-llm-d) intentionally
// to verify MultiTargetSelector works with both CR types (ISVC and LLMISVC).
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { vi, describe, it, expect, beforeEach } from "vitest";
import MultiTargetSelector from "./MultiTargetSelector";
import { useClusterConfig, ClusterConfigContextValue } from "../contexts/ClusterConfigContext";

vi.mock("../contexts/ClusterConfigContext", () => ({
  useClusterConfig: vi.fn(),
}));

vi.mock("../utils/authFetch", () => ({
  authFetch: vi.fn(() => Promise.resolve({ ok: true })),
}));

import { authFetch } from "../utils/authFetch";

describe("MultiTargetSelector", () => {
  const mockContext = {
    targets: [
      { namespace: "llm-d-demo", inferenceService: "small-llm-d", isDefault: true },
    ],
    maxTargets: 5,
    addTarget: vi.fn(),
    removeTarget: vi.fn(),
    setDefaultTarget: vi.fn(),
    isvcTargets: [
      { namespace: "llm-d-demo", inferenceService: "small-llm-d", isDefault: true },
    ],
    llmisvcTargets: [],
  };

  beforeEach(() => {
    vi.mocked(useClusterConfig).mockReturnValue(mockContext as unknown as ClusterConfigContextValue);
    vi.clearAllMocks();
  });

  const openDropdown = () => {
    const dropdownBtn = screen.getByTestId("dropdown-toggle-btn");
    fireEvent.click(dropdownBtn);
  };

  it("renders targets and add button", () => {
    render(<MultiTargetSelector targetStatuses={{}} targetStates={{}} />);
    expect(screen.getByText("Monitoring Targets (1/5)")).toBeInTheDocument();
    expect(screen.getByTestId("dropdown-toggle-btn")).toBeInTheDocument();
    expect(screen.getByTestId("add-target-btn")).toBeInTheDocument();
  });

  it("renders as table with header columns", () => {
    render(<MultiTargetSelector targetStatuses={{}} targetStates={{}} />);
    openDropdown();
    expect(document.querySelector('.monitor-table')).toBeInTheDocument();
    expect(screen.getByText("TPS")).toBeInTheDocument();
    expect(screen.getByText("RPS")).toBeInTheDocument();
    expect(screen.getByText("GPU%")).toBeInTheDocument();
  });

  it("shows collecting state with dots", () => {
    const key = "llm-d-demo/small-llm-d";
    render(<MultiTargetSelector 
      targetStatuses={{ [key]: { status: 'collecting' as const, hasMonitoringLabel: false } }} 
      targetStates={{ [key]: { status: 'collecting' } }} 
    />);
    openDropdown();
    const dots = screen.getAllByText("...");
    expect(dots.length).toBeGreaterThan(0);
  });

  it("shows metric values when data is available", () => {
    const key = "llm-d-demo/small-llm-d";
    const mockData = {
      tps: 245, rps: 12.5, ttft_mean: 85, ttft_p99: 120,
      latency_mean: 300, latency_p99: 450, kv_cache: 45.2,
      kv_hit_rate: 78.3, gpu_util: 65.1, gpu_mem_used: 18.4,
      gpu_mem_total: 24, running: 3, waiting: 1, pods: 1, pods_ready: 1
    };
    render(<MultiTargetSelector
      targetStatuses={{}}
      targetStates={{ [key]: { status: 'ready', data: mockData } }}
    />);
    openDropdown();
    expect(screen.getByText("245")).toBeInTheDocument();
    expect(screen.getByText("1 / 1")).toBeInTheDocument();
  });

  it("shows empty state message when no targets", () => {
    const emptyMock = {
      ...mockContext,
      targets: [],
      isvcTargets: [],
      llmisvcTargets: [],
    };
    vi.mocked(useClusterConfig).mockReturnValue(emptyMock as unknown as ClusterConfigContextValue);
    render(<MultiTargetSelector targetStatuses={{}} targetStates={{}} />);
    openDropdown();
    expect(screen.getByText("Add a monitoring target")).toBeInTheDocument();
  });

  it("renders target row with data-testid", () => {
    render(<MultiTargetSelector targetStatuses={{}} targetStates={{}} />);
    openDropdown();
    expect(screen.getByTestId("target-row-0")).toBeInTheDocument();
  });

  it("shows add form when add button is clicked", () => {
    render(<MultiTargetSelector targetStatuses={{}} targetStates={{}} />);
    fireEvent.click(screen.getByTestId("add-target-btn"));
    expect(screen.getByPlaceholderText("Namespace")).toBeInTheDocument();
    expect(screen.getByPlaceholderText("InferenceService")).toBeInTheDocument();
  });

  it("calls addTarget when form is submitted", async () => {
    render(<MultiTargetSelector targetStatuses={{}} targetStates={{}} />);
    fireEvent.click(screen.getByTestId("add-target-btn"));
    fireEvent.change(screen.getByPlaceholderText("Namespace"), { target: { value: "vllm-lab-prod" } });
    fireEvent.change(screen.getByPlaceholderText("InferenceService"), { target: { value: "llm-cuda" } });
    fireEvent.click(screen.getByTestId("confirm-add-btn"));
    await waitFor(() => {
      expect(mockContext.addTarget).toHaveBeenCalledWith("vllm-lab-prod", "llm-cuda", "inferenceservice");
    });
  });

  it("shows error message when target validation fails", async () => {
    vi.mocked(authFetch).mockResolvedValueOnce({ ok: false } as unknown as Response);
    render(<MultiTargetSelector targetStatuses={{}} targetStates={{}} />);
    fireEvent.click(screen.getByTestId("add-target-btn"));
    fireEvent.change(screen.getByPlaceholderText("Namespace"), { target: { value: "invalid-ns" } });
    fireEvent.change(screen.getByPlaceholderText("InferenceService"), { target: { value: "invalid-is" } });
    fireEvent.click(screen.getByTestId("confirm-add-btn"));
    
    await waitFor(() => {
       expect(screen.getByTestId("add-target-error")).toHaveTextContent("Target not found");
    });
    expect(mockContext.addTarget).not.toHaveBeenCalled();
  });

  it("does not show delete or set-default button on default target", () => {
    render(<MultiTargetSelector targetStatuses={{}} targetStates={{}} />);
    openDropdown();
    expect(screen.queryByTestId("delete-btn")).not.toBeInTheDocument();
    expect(screen.queryByTestId("set-default-btn")).not.toBeInTheDocument();
  });

  it("shows delete and set-default buttons on non-default target", () => {
    const multiMock = {
      ...mockContext,
      targets: [
        { namespace: "llm-d-demo", inferenceService: "small-llm-d", isDefault: true },
        { namespace: "llm-d-prod", inferenceService: "large-llm-d", isDefault: false },
      ],
      isvcTargets: [
        { namespace: "llm-d-demo", inferenceService: "small-llm-d", isDefault: true },
        { namespace: "llm-d-prod", inferenceService: "large-llm-d", isDefault: false },
      ],
      llmisvcTargets: [],
    };
    vi.mocked(useClusterConfig).mockReturnValue(multiMock as unknown as ClusterConfigContextValue);
    render(<MultiTargetSelector targetStatuses={{}} targetStates={{}} />);
    openDropdown();
    expect(screen.getAllByTestId("delete-btn")).toHaveLength(1);
    expect(screen.getAllByTestId("set-default-btn")).toHaveLength(1);
  });

  it("calls removeTarget when delete button is clicked", () => {
    const mockRemoveTarget = vi.fn();
    const multiMock = {
      ...mockContext,
      targets: [
        { namespace: "llm-d-demo", inferenceService: "small-llm-d", isDefault: true },
        { namespace: "llm-d-prod", inferenceService: "large-llm-d", isDefault: false },
      ],
      isvcTargets: [
        { namespace: "llm-d-demo", inferenceService: "small-llm-d", isDefault: true },
        { namespace: "llm-d-prod", inferenceService: "large-llm-d", isDefault: false },
      ],
      llmisvcTargets: [],
      removeTarget: mockRemoveTarget,
    };
    vi.mocked(useClusterConfig).mockReturnValue(multiMock as unknown as ClusterConfigContextValue);
    render(<MultiTargetSelector targetStatuses={{}} targetStates={{}} />);
    openDropdown();
    fireEvent.click(screen.getByTestId("delete-btn"));
    expect(mockRemoveTarget).toHaveBeenCalledWith("llm-d-prod", "large-llm-d");
  });

  it("calls setDefaultTarget when set-default button is clicked", () => {
    const mockSetDefaultTarget = vi.fn();
    const multiMock = {
      ...mockContext,
      targets: [
        { namespace: "llm-d-demo", inferenceService: "small-llm-d", isDefault: true },
        { namespace: "llm-d-prod", inferenceService: "large-llm-d", isDefault: false },
      ],
      isvcTargets: [
        { namespace: "llm-d-demo", inferenceService: "small-llm-d", isDefault: true },
        { namespace: "llm-d-prod", inferenceService: "large-llm-d", isDefault: false },
      ],
      llmisvcTargets: [],
      setDefaultTarget: mockSetDefaultTarget,
    };
    vi.mocked(useClusterConfig).mockReturnValue(multiMock as unknown as ClusterConfigContextValue);
    render(<MultiTargetSelector targetStatuses={{}} targetStates={{}} />);
    openDropdown();
    fireEvent.click(screen.getByTestId("set-default-btn"));
    expect(mockSetDefaultTarget).toHaveBeenCalledWith("llm-d-prod", "large-llm-d", "inferenceservice");
  });

  it("shows warning for namespace without monitoring label", () => {
    const targetKey = "vllm/llm-cuda";
    const statuses = {
      [targetKey]: { status: 'ok' as const, hasMonitoringLabel: false }
    };
    const multiMock = {
      ...mockContext,
      targets: [
        { namespace: "llm-d-demo", inferenceService: "small-llm-d", isDefault: true },
        { namespace: "vllm", inferenceService: "llm-cuda", isDefault: false },
      ],
      isvcTargets: [
        { namespace: "llm-d-demo", inferenceService: "small-llm-d", isDefault: true },
        { namespace: "vllm", inferenceService: "llm-cuda", isDefault: false },
      ],
      llmisvcTargets: [],
    };
    vi.mocked(useClusterConfig).mockReturnValue(multiMock as unknown as ClusterConfigContextValue);
    render(<MultiTargetSelector targetStatuses={statuses} targetStates={{}} />);
    openDropdown();
    expect(screen.getByTestId("no-monitoring-warning")).toBeInTheDocument();
  });

  it("renders CR type dropdown in add-target form", () => {
    render(<MultiTargetSelector targetStatuses={{}} targetStates={{}} />);
    fireEvent.click(screen.getByTestId("add-target-btn"));
    expect(screen.getByTestId("cr-type-select")).toBeInTheDocument();
    expect(screen.getByText("isvc (KServe)")).toBeInTheDocument();
    expect(screen.getByText("llmisvc (LLMIS)")).toBeInTheDocument();
  });

  it("shows LLMIS badge for target with crType llminferenceservice", () => {
    const llmisMock = {
      ...mockContext,
      targets: [
        { namespace: "llm-d-demo", inferenceService: "small-llm-d", isDefault: true, crType: "llminferenceservice" },
      ],
      isvcTargets: [],
      llmisvcTargets: [
        { namespace: "llm-d-demo", inferenceService: "small-llm-d", isDefault: true, crType: "llminferenceservice" },
      ],
    };
    vi.mocked(useClusterConfig).mockReturnValue(llmisMock as unknown as ClusterConfigContextValue);
    render(<MultiTargetSelector targetStatuses={{}} targetStates={{}} />);
    openDropdown();
    expect(screen.getByTestId("llmis-badge")).toBeInTheDocument();
    expect(screen.getByTestId("llmis-badge")).toHaveTextContent("LLMIS");
  });

  it("calls addTarget with crType when form is submitted", async () => {
    render(<MultiTargetSelector targetStatuses={{}} targetStates={{}} />);
    fireEvent.click(screen.getByTestId("add-target-btn"));
    fireEvent.change(screen.getByPlaceholderText("Namespace"), { target: { value: "llm-d-demo" } });
    fireEvent.change(screen.getByPlaceholderText("InferenceService"), { target: { value: "llm-svc" } });
    fireEvent.change(screen.getByTestId("cr-type-select"), { target: { value: "llminferenceservice" } });
    fireEvent.click(screen.getByTestId("confirm-add-btn"));
    await waitFor(() => {
      expect(mockContext.addTarget).toHaveBeenCalledWith("llm-d-demo", "llm-svc", "llminferenceservice");
    });
  });
});