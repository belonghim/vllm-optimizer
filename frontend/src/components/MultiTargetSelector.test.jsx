import { render, screen, fireEvent } from "@testing-library/react";
import { vi, describe, it, expect, beforeEach } from "vitest";
import MultiTargetSelector from "./MultiTargetSelector";
import { useClusterConfig } from "../contexts/ClusterConfigContext";

vi.mock("../contexts/ClusterConfigContext", () => ({
  useClusterConfig: vi.fn(),
}));

describe("MultiTargetSelector", () => {
  const mockContext = {
    targets: [
      { namespace: "vllm-lab-dev", inferenceService: "llm-ov", isDefault: true },
    ],
    maxTargets: 5,
    addTarget: vi.fn(),
    removeTarget: vi.fn(),
    setDefaultTarget: vi.fn(),
  };

  beforeEach(() => {
    useClusterConfig.mockReturnValue(mockContext);
  });

  it("renders targets and add button", () => {
    render(<MultiTargetSelector targetStatuses={{}} targetStates={{}} />);
    expect(screen.getByText("모니터링 대상 (1/5)")).toBeInTheDocument();
    expect(screen.getByText("vllm-lab-dev")).toBeInTheDocument();
    expect(screen.getByText("llm-ov")).toBeInTheDocument();
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
    const key = "vllm-lab-dev/llm-ov";
    render(<MultiTargetSelector 
      targetStatuses={{ [key]: { status: 'collecting' } }} 
      targetStates={{ [key]: { status: 'collecting' } }} 
    />);
    const dots = screen.getAllByText("...");
    expect(dots.length).toBeGreaterThan(0);
  });

  it("shows metric values when data is available", () => {
    const key = "vllm-lab-dev/llm-ov";
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

  it("calls addTarget when form is submitted", () => {
    render(<MultiTargetSelector targetStatuses={{}} targetStates={{}} />);
    fireEvent.click(screen.getByTestId("add-target-btn"));
    fireEvent.change(screen.getByPlaceholderText("Namespace"), { target: { value: "vllm-lab-prod" } });
    fireEvent.change(screen.getByPlaceholderText("InferenceService"), { target: { value: "llm-cuda" } });
    fireEvent.click(screen.getByTestId("confirm-add-btn"));
    expect(mockContext.addTarget).toHaveBeenCalledWith("vllm-lab-prod", "llm-cuda");
  });

  it("does not show delete button on default target", () => {
    render(<MultiTargetSelector targetStatuses={{}} targetStates={{}} />);
    expect(screen.queryByTestId("delete-btn")).not.toBeInTheDocument();
  });

  it("shows delete button on non-default target", () => {
    const multiMock = {
      ...mockContext,
      targets: [
        { namespace: "vllm-lab-dev", inferenceService: "llm-ov", isDefault: true },
        { namespace: "vllm-lab-prod", inferenceService: "llm-cuda", isDefault: false },
      ],
    };
    useClusterConfig.mockReturnValue(multiMock);
    render(<MultiTargetSelector targetStatuses={{}} targetStates={{}} />);
    expect(screen.getAllByTestId("delete-btn")).toHaveLength(1);
  });

  it("shows warning for namespace without monitoring label", () => {
    const targetKey = "vllm/llm-cuda";
    const statuses = {
      [targetKey]: { hasMonitoringLabel: false }
    };
    const multiMock = {
      ...mockContext,
      targets: [
        { namespace: "vllm-lab-dev", inferenceService: "llm-ov", isDefault: true },
        { namespace: "vllm", inferenceService: "llm-cuda", isDefault: false },
      ],
    };
    useClusterConfig.mockReturnValue(multiMock);
    render(<MultiTargetSelector targetStatuses={statuses} targetStates={{}} />);
    expect(screen.getByTestId("no-monitoring-warning")).toBeInTheDocument();
  });
});
