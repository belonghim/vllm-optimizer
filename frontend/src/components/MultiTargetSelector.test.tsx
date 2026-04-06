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
      { namespace: "llm-d-demo", inferenceService: "small-llm-d", crType: "inferenceservice" },
    ],
    maxTargets: 5,
    addTarget: vi.fn(),
    removeTarget: vi.fn(),
    setDefaultTarget: vi.fn(),
    isvcTargets: [
      { namespace: "llm-d-demo", inferenceService: "small-llm-d", crType: "inferenceservice" },
    ],
    llmisvcTargets: [],
  };

  beforeEach(() => {
    vi.mocked(useClusterConfig).mockReturnValue(mockContext as unknown as ClusterConfigContextValue);
    vi.clearAllMocks();
  });

  it("renders targets and add button", () => {
    render(<MultiTargetSelector targetStatuses={{}} targetStates={{}} />);
    expect(screen.getByText("Monitoring Targets (1/5)")).toBeInTheDocument();
    expect(screen.getByTestId("add-target-btn")).toBeInTheDocument();
  });

  it("renders as table with header columns", () => {
    render(<MultiTargetSelector targetStatuses={{}} targetStates={{}} />);
    expect(document.querySelector('.monitor-table')).toBeInTheDocument();
    expect(screen.getByText("TPS")).toBeInTheDocument();
    expect(screen.getByText("RPS")).toBeInTheDocument();
    expect(screen.getByText("GPU%")).toBeInTheDocument();
  });

  it("shows collecting state with dots", () => {
    const key = "llm-d-demo/small-llm-d/inferenceservice";
    render(<MultiTargetSelector 
      targetStatuses={{ [key]: { status: 'collecting' as const, hasMonitoringLabel: false } }} 
      targetStates={{ [key]: { status: 'collecting' } }} 
    />);
    const dots = screen.getAllByText("...");
    expect(dots.length).toBeGreaterThan(0);
  });

  it("shows metric values when data is available", () => {
    const key = "llm-d-demo/small-llm-d/inferenceservice";
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
    expect(screen.getByText("Add a monitoring target")).toBeInTheDocument();
  });

  it("renders target row with data-testid", () => {
    render(<MultiTargetSelector targetStatuses={{}} targetStates={{}} />);
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

  it("shows radio button on all targets and delete button disabled if only one", () => {
    render(<MultiTargetSelector targetStatuses={{}} targetStates={{}} />);
    expect(screen.getByTestId("radio-default-0")).toBeInTheDocument();
    expect(screen.getByTestId("delete-btn")).toBeDisabled();
  });

  it("shows radio buttons and enabled delete buttons on multiple targets", () => {
    const multiMock = {
      ...mockContext,
      targets: [
        { namespace: "llm-d-demo", inferenceService: "small-llm-d", crType: "inferenceservice" },
        { namespace: "llm-d-prod", inferenceService: "large-llm-d", crType: "inferenceservice" },
      ],
      isvcTargets: [
        { namespace: "llm-d-demo", inferenceService: "small-llm-d", crType: "inferenceservice" },
        { namespace: "llm-d-prod", inferenceService: "large-llm-d", crType: "inferenceservice" },
      ],
      llmisvcTargets: [],
    };
    vi.mocked(useClusterConfig).mockReturnValue(multiMock as unknown as ClusterConfigContextValue);
    render(<MultiTargetSelector targetStatuses={{}} targetStates={{}} />);
    expect(screen.getByTestId("radio-default-0")).toBeInTheDocument();
    expect(screen.getByTestId("radio-default-1")).toBeInTheDocument();
    const deleteBtns = screen.getAllByTestId("delete-btn");
    expect(deleteBtns).toHaveLength(2);
    expect(deleteBtns[0]).not.toBeDisabled();
    expect(deleteBtns[1]).not.toBeDisabled();
  });

  it("shows Apply button only when radio selection differs from current default", () => {
    const multiMock = {
      ...mockContext,
      targets: [
        { namespace: "llm-d-demo", inferenceService: "small-llm-d", crType: "inferenceservice" },
        { namespace: "llm-d-prod", inferenceService: "large-llm-d", crType: "inferenceservice" },
      ],
      isvcTargets: [
        { namespace: "llm-d-demo", inferenceService: "small-llm-d", crType: "inferenceservice" },
        { namespace: "llm-d-prod", inferenceService: "large-llm-d", crType: "inferenceservice" },
      ],
      llmisvcTargets: [],
    };
    vi.mocked(useClusterConfig).mockReturnValue(multiMock as unknown as ClusterConfigContextValue);
    render(<MultiTargetSelector targetStatuses={{}} targetStates={{}} />);
    
    expect(screen.queryByTestId("apply-default-btn")).not.toBeInTheDocument();
    
    fireEvent.click(screen.getByTestId("radio-default-1"));
    
    expect(screen.getByTestId("apply-default-btn")).toBeInTheDocument();
    
    fireEvent.click(screen.getByTestId("radio-default-0"));
    expect(screen.queryByTestId("apply-default-btn")).not.toBeInTheDocument();
  });

  it("calls removeTarget when delete button is clicked", () => {
    const mockRemoveTarget = vi.fn();
    const multiMock = {
      ...mockContext,
      targets: [
        { namespace: "llm-d-demo", inferenceService: "small-llm-d", crType: "inferenceservice" },
        { namespace: "llm-d-prod", inferenceService: "large-llm-d", crType: "inferenceservice" },
      ],
      isvcTargets: [
        { namespace: "llm-d-demo", inferenceService: "small-llm-d", crType: "inferenceservice" },
        { namespace: "llm-d-prod", inferenceService: "large-llm-d", crType: "inferenceservice" },
      ],
      llmisvcTargets: [],
      removeTarget: mockRemoveTarget,
    };
    vi.mocked(useClusterConfig).mockReturnValue(multiMock as unknown as ClusterConfigContextValue);
    render(<MultiTargetSelector targetStatuses={{}} targetStates={{}} />);
    fireEvent.click(screen.getAllByTestId("delete-btn")[1]);
    expect(mockRemoveTarget).toHaveBeenCalledWith("llm-d-prod", "large-llm-d", "inferenceservice");
  });

  it("calls setDefaultTarget when Apply button is clicked", async () => {
    const mockSetDefaultTarget = vi.fn();
    const multiMock = {
      ...mockContext,
      targets: [
        { namespace: "llm-d-demo", inferenceService: "small-llm-d", crType: "inferenceservice" },
        { namespace: "llm-d-prod", inferenceService: "large-llm-d", crType: "inferenceservice" },
      ],
      isvcTargets: [
        { namespace: "llm-d-demo", inferenceService: "small-llm-d", crType: "inferenceservice" },
        { namespace: "llm-d-prod", inferenceService: "large-llm-d", crType: "inferenceservice" },
      ],
      llmisvcTargets: [],
      setDefaultTarget: mockSetDefaultTarget,
    };
    vi.mocked(useClusterConfig).mockReturnValue(multiMock as unknown as ClusterConfigContextValue);
    render(<MultiTargetSelector targetStatuses={{}} targetStates={{}} />);
    
    fireEvent.click(screen.getByTestId("radio-default-1"));
    fireEvent.click(screen.getByTestId("apply-default-btn"));
    
    expect(mockSetDefaultTarget).toHaveBeenCalledWith("llm-d-prod", "large-llm-d", "inferenceservice");
  });

  it("shows warning for namespace without monitoring label", () => {
    const targetKey = "vllm/llm-cuda/inferenceservice";
    const statuses = {
      [targetKey]: { status: 'ok' as const, hasMonitoringLabel: false }
    };
    const multiMock = {
      ...mockContext,
      targets: [
        { namespace: "llm-d-demo", inferenceService: "small-llm-d", crType: "inferenceservice" },
        { namespace: "vllm", inferenceService: "llm-cuda", crType: "inferenceservice" },
      ],
      isvcTargets: [
        { namespace: "llm-d-demo", inferenceService: "small-llm-d", crType: "inferenceservice" },
        { namespace: "vllm", inferenceService: "llm-cuda", crType: "inferenceservice" },
      ],
      llmisvcTargets: [],
    };
    vi.mocked(useClusterConfig).mockReturnValue(multiMock as unknown as ClusterConfigContextValue);
    render(<MultiTargetSelector targetStatuses={statuses} targetStates={{}} />);
    expect(screen.getByTestId("no-monitoring-warning")).toBeInTheDocument();
  });

  it("renders CR type dropdown in add-target form", () => {
    render(<MultiTargetSelector targetStatuses={{}} targetStates={{}} />);
    fireEvent.click(screen.getByTestId("add-target-btn"));
    expect(screen.getByTestId("cr-type-select")).toBeInTheDocument();
    expect(screen.getByText("isvc (KServe)")).toBeInTheDocument();
    expect(screen.getByText("LLMIS (llmisvc)")).toBeInTheDocument();
  });

  it("shows LLMIS badge for target with crType llminferenceservice", () => {
    const llmisMock = {
      ...mockContext,
      targets: [
        { namespace: "llm-d-demo", inferenceService: "small-llm-d", crType: "llminferenceservice" },
      ],
      isvcTargets: [],
      llmisvcTargets: [
        { namespace: "llm-d-demo", inferenceService: "small-llm-d", crType: "llminferenceservice" },
      ],
    };
    vi.mocked(useClusterConfig).mockReturnValue(llmisMock as unknown as ClusterConfigContextValue);
    render(<MultiTargetSelector targetStatuses={{}} targetStates={{}} />);
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

  it("renders ISVC and LLMISVC targets with different keys", () => {
    const multiMock = {
      ...mockContext,
      targets: [
        { namespace: "ns", inferenceService: "svc", crType: "inferenceservice" },
        { namespace: "ns", inferenceService: "svc", crType: "llminferenceservice" },
      ],
      isvcTargets: [
        { namespace: "ns", inferenceService: "svc", crType: "inferenceservice" },
      ],
      llmisvcTargets: [
        { namespace: "ns", inferenceService: "svc", crType: "llminferenceservice" },
      ],
    };
    vi.mocked(useClusterConfig).mockReturnValue(multiMock as unknown as ClusterConfigContextValue);
    render(<MultiTargetSelector targetStatuses={{}} targetStates={{}} />);
    expect(screen.getByTestId("llmis-badge")).toBeInTheDocument();
    expect(screen.getByTestId("llmis-badge")).toHaveTextContent("LLMIS");
  });
});
