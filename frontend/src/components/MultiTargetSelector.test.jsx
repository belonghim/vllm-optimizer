import { render, screen, fireEvent } from "@testing-library/react";
import { vi } from "vitest";
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
    render(<MultiTargetSelector targetStatuses={{}} />);
    expect(screen.getByText("모니터링 대상 (1/5)")).toBeInTheDocument();
    expect(screen.getByText("vllm-lab-dev")).toBeInTheDocument();
    expect(screen.getByText("llm-ov")).toBeInTheDocument();
    expect(screen.getByTestId("add-target-btn")).toBeInTheDocument();
  });

  it("shows add form when add button is clicked", () => {
    render(<MultiTargetSelector targetStatuses={{}} />);
    fireEvent.click(screen.getByTestId("add-target-btn"));
    expect(screen.getByPlaceholderText("Namespace")).toBeInTheDocument();
    expect(screen.getByPlaceholderText("InferenceService")).toBeInTheDocument();
  });

  it("calls addTarget when form is submitted", () => {
    render(<MultiTargetSelector targetStatuses={{}} />);
    fireEvent.click(screen.getByTestId("add-target-btn"));
    fireEvent.change(screen.getByPlaceholderText("Namespace"), { target: { value: "vllm-lab-prod" } });
    fireEvent.change(screen.getByPlaceholderText("InferenceService"), { target: { value: "llm-cuda" } });
    fireEvent.click(screen.getByTestId("confirm-add-btn"));
    expect(mockContext.addTarget).toHaveBeenCalledWith("vllm-lab-prod", "llm-cuda");
  });

  it("does not show delete button on default target", () => {
    render(<MultiTargetSelector targetStatuses={{}} />);
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
    render(<MultiTargetSelector targetStatuses={{}} />);
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
    render(<MultiTargetSelector targetStatuses={statuses} />);
    expect(screen.getByTestId("no-monitoring-warning")).toBeInTheDocument();
  });
});
