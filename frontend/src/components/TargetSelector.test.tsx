import { render, screen, fireEvent } from "@testing-library/react";
import { vi, describe, it, expect, beforeEach } from "vitest";
import TargetSelector from "./TargetSelector";
import { useClusterConfig } from "../contexts/ClusterConfigContext";

vi.mock("../contexts/ClusterConfigContext", () => ({
  useClusterConfig: vi.fn(),
}));

describe("TargetSelector", () => {
  const mockTargets = [
    { namespace: "vllm-lab-dev", inferenceService: "llm-ov", isDefault: true, crType: "inferenceservice" },
    { namespace: "llm-d-demo", inferenceService: "small-llm-d", isDefault: false, crType: "llminferenceservice" },
  ];

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders empty state when no targets", () => {
    vi.mocked(useClusterConfig).mockReturnValue({
      targets: [],
    } as any);
    render(<TargetSelector />);
    expect(screen.getByText("No targets available")).toBeInTheDocument();
  });

  it("renders trigger button with selected value", () => {
    vi.mocked(useClusterConfig).mockReturnValue({
      targets: mockTargets,
    } as any);
    render(<TargetSelector value={mockTargets[0]} />);
    expect(screen.getByText("llm-ov")).toBeInTheDocument();
    expect(screen.getByText("(vllm-lab-dev)")).toBeInTheDocument();
  });

  it("shows placeholder when no value selected", () => {
    vi.mocked(useClusterConfig).mockReturnValue({
      targets: mockTargets,
    } as any);
    render(<TargetSelector />);
    expect(screen.getByText("Select a target")).toBeInTheDocument();
  });

  it("opens dropdown when trigger is clicked", () => {
    vi.mocked(useClusterConfig).mockReturnValue({
      targets: mockTargets,
    } as any);
    render(<TargetSelector />);
    fireEvent.click(screen.getByRole("button"));
    expect(screen.getByTestId("target-selector-dropdown")).toBeInTheDocument();
  });

  it("shows targets grouped by CR type", () => {
    vi.mocked(useClusterConfig).mockReturnValue({
      targets: mockTargets,
    } as any);
    render(<TargetSelector />);
    fireEvent.click(screen.getByRole("button"));
    expect(screen.getByText("KServe (isvc)")).toBeInTheDocument();
    expect(screen.getByText("LLMIS (llmisvc)")).toBeInTheDocument();
  });

  it("displays star for default target", () => {
    vi.mocked(useClusterConfig).mockReturnValue({
      targets: mockTargets,
    } as any);
    render(<TargetSelector />);
    fireEvent.click(screen.getByRole("button"));
    const starElement = screen.getByText("★");
    expect(starElement).toBeInTheDocument();
    expect(screen.getByText("llm-ov")).toBeInTheDocument();
  });

  it("calls onChange with target when option is clicked", () => {
    const onChange = vi.fn();
    vi.mocked(useClusterConfig).mockReturnValue({
      targets: mockTargets,
    } as any);
    render(<TargetSelector onChange={onChange} />);
    fireEvent.click(screen.getByRole("button"));
    fireEvent.click(screen.getByText("small-llm-d"));
    expect(onChange).toHaveBeenCalledWith({
      namespace: "llm-d-demo",
      inferenceService: "small-llm-d",
      isDefault: false,
      crType: "llminferenceservice",
    });
  });

  it("closes dropdown after selection", () => {
    vi.mocked(useClusterConfig).mockReturnValue({
      targets: mockTargets,
    } as any);
    render(<TargetSelector onChange={() => {}} />);
    fireEvent.click(screen.getByRole("button"));
    expect(screen.getByTestId("target-selector-dropdown")).toBeInTheDocument();
    fireEvent.click(screen.getByText("small-llm-d"));
    expect(screen.queryByTestId("target-selector-dropdown")).not.toBeInTheDocument();
  });

  it("supports keyboard navigation to open dropdown", () => {
    vi.mocked(useClusterConfig).mockReturnValue({
      targets: mockTargets,
    } as any);
    render(<TargetSelector />);
    const trigger = screen.getByRole("button");
    fireEvent.keyDown(trigger, { key: "ArrowDown" });
    expect(screen.getByTestId("target-selector-dropdown")).toBeInTheDocument();
  });

  it("closes dropdown on Escape", () => {
    vi.mocked(useClusterConfig).mockReturnValue({
      targets: mockTargets,
    } as any);
    render(<TargetSelector />);
    const trigger = screen.getByRole("button");
    fireEvent.keyDown(trigger, { key: "ArrowDown" });
    expect(screen.getByTestId("target-selector-dropdown")).toBeInTheDocument();
    fireEvent.keyDown(trigger, { key: "Escape" });
    expect(screen.queryByTestId("target-selector-dropdown")).not.toBeInTheDocument();
  });

  it("renders with data-testid", () => {
    vi.mocked(useClusterConfig).mockReturnValue({
      targets: mockTargets,
    } as any);
    render(<TargetSelector data-testid="my-selector" />);
    expect(screen.getByTestId("my-selector")).toBeInTheDocument();
    fireEvent.click(screen.getByTestId("my-selector-trigger"));
    expect(screen.getByTestId("my-selector-dropdown")).toBeInTheDocument();
  });
});
