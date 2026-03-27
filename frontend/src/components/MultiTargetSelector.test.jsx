import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { vi, describe, it, expect, beforeEach } from "vitest";
import MultiTargetSelector from "./MultiTargetSelector";
import { useClusterConfig } from "../contexts/ClusterConfigContext";

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
  };

  beforeEach(() => {
    useClusterConfig.mockReturnValue(mockContext);
    vi.clearAllMocks();
  });

  it("renders targets and add button", () => {
    render(<MultiTargetSelector targetStatuses={{}} targetStates={{}} />);
    expect(screen.getByText("모니터링 대상 (1/5)")).toBeInTheDocument();
    expect(screen.getByText("llm-d-demo")).toBeInTheDocument();
    expect(screen.getByText("small-llm-d")).toBeInTheDocument();
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
    const key = "llm-d-demo/small-llm-d";
    render(<MultiTargetSelector 
      targetStatuses={{ [key]: { status: 'collecting' } }} 
      targetStates={{ [key]: { status: 'collecting' } }} 
    />);
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
    expect(screen.getByText("245")).toBeInTheDocument();
    expect(screen.getByText("1 / 1")).toBeInTheDocument();
  });

  it("shows empty state message when no targets", () => {
    const emptyMock = {
      ...mockContext,
      targets: [],
    };
    useClusterConfig.mockReturnValue(emptyMock);
    render(<MultiTargetSelector targetStatuses={{}} targetStates={{}} />);
    expect(screen.getByText("모니터링 대상을 추가하세요")).toBeInTheDocument();
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
    authFetch.mockResolvedValueOnce({ ok: false });
    render(<MultiTargetSelector targetStatuses={{}} targetStates={{}} />);
    fireEvent.click(screen.getByTestId("add-target-btn"));
    fireEvent.change(screen.getByPlaceholderText("Namespace"), { target: { value: "invalid-ns" } });
    fireEvent.change(screen.getByPlaceholderText("InferenceService"), { target: { value: "invalid-is" } });
    fireEvent.click(screen.getByTestId("confirm-add-btn"));
    
    await waitFor(() => {
      expect(screen.getByTestId("add-target-error")).toHaveTextContent("해당 대상을 찾을 수 없습니다");
    });
    expect(mockContext.addTarget).not.toHaveBeenCalled();
  });

  it("does not show delete or set-default button on default target", () => {
    render(<MultiTargetSelector targetStatuses={{}} targetStates={{}} />);
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
    };
    useClusterConfig.mockReturnValue(multiMock);
    render(<MultiTargetSelector targetStatuses={{}} targetStates={{}} />);
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
      removeTarget: mockRemoveTarget,
    };
    useClusterConfig.mockReturnValue(multiMock);
    render(<MultiTargetSelector targetStatuses={{}} targetStates={{}} />);
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
      setDefaultTarget: mockSetDefaultTarget,
    };
    useClusterConfig.mockReturnValue(multiMock);
    render(<MultiTargetSelector targetStatuses={{}} targetStates={{}} />);
    fireEvent.click(screen.getByTestId("set-default-btn"));
    expect(mockSetDefaultTarget).toHaveBeenCalledWith("llm-d-prod", "large-llm-d");
  });

  it("shows warning for namespace without monitoring label", () => {
    const targetKey = "vllm/llm-cuda";
    const statuses = {
      [targetKey]: { hasMonitoringLabel: false }
    };
    const multiMock = {
      ...mockContext,
      targets: [
        { namespace: "llm-d-demo", inferenceService: "small-llm-d", isDefault: true },
        { namespace: "vllm", inferenceService: "llm-cuda", isDefault: false },
      ],
    };
    useClusterConfig.mockReturnValue(multiMock);
    render(<MultiTargetSelector targetStatuses={statuses} targetStates={{}} />);
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
    };
    useClusterConfig.mockReturnValue(llmisMock);
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
});
