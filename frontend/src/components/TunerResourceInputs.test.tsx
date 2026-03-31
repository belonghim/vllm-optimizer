import "@testing-library/jest-dom";
import { render, screen, fireEvent } from "@testing-library/react";
import { vi, describe, it, expect, beforeEach } from "vitest";
import TunerResourceInputs from "./TunerResourceInputs";

function renderInTable(ui: React.ReactElement) {
  return render(
    <table>
      <tbody>{ui}</tbody>
    </table>
  );
}

describe("TunerResourceInputs", () => {
  const handleResourceChange = vi.fn();
  const getResourceValue = vi.fn((tier: string, key: string) => {
    const map: Record<string, string> = {
      "requests/cpu": "4",
      "requests/memory": "8Gi",
      "limits/cpu": "8",
      "limits/memory": "16Gi",
      "limits/nvidia.com/gpu": "1",
    };
    return map[`${tier}/${key}`] ?? "";
  });

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders all five resource input fields", () => {
    renderInTable(
      <TunerResourceInputs
        editedValues={{}}
        getResourceValue={getResourceValue}
        handleResourceChange={handleResourceChange}
        resourceErrors={{}}
      />
    );
    expect(screen.getByLabelText("CPU Requests")).toBeInTheDocument();
    expect(screen.getByLabelText("CPU Limits")).toBeInTheDocument();
    expect(screen.getByLabelText("Memory Requests")).toBeInTheDocument();
    expect(screen.getByLabelText("Memory Limits")).toBeInTheDocument();
    expect(screen.getByLabelText("GPU Limits")).toBeInTheDocument();
  });

  it("shows values from getResourceValue when editedValues is empty", () => {
    renderInTable(
      <TunerResourceInputs
        editedValues={{}}
        getResourceValue={getResourceValue}
        handleResourceChange={handleResourceChange}
        resourceErrors={{}}
      />
    );
    const cpuReqInput = screen.getByLabelText("CPU Requests") as HTMLInputElement;
    expect(cpuReqInput.value).toBe("4");
    const memLimInput = screen.getByLabelText("Memory Limits") as HTMLInputElement;
    expect(memLimInput.value).toBe("16Gi");
  });

  it("shows value from editedValues over getResourceValue", () => {
    renderInTable(
      <TunerResourceInputs
        editedValues={{ "resources.requests.cpu": "12" }}
        getResourceValue={getResourceValue}
        handleResourceChange={handleResourceChange}
        resourceErrors={{}}
      />
    );
    const cpuReqInput = screen.getByLabelText("CPU Requests") as HTMLInputElement;
    expect(cpuReqInput.value).toBe("12");
  });

  it("calls handleResourceChange with correct key on CPU Requests change", () => {
    renderInTable(
      <TunerResourceInputs
        editedValues={{}}
        getResourceValue={getResourceValue}
        handleResourceChange={handleResourceChange}
        resourceErrors={{}}
      />
    );
    const cpuReqInput = screen.getByLabelText("CPU Requests");
    fireEvent.change(cpuReqInput, { target: { value: "6" } });
    expect(handleResourceChange).toHaveBeenCalledWith("resources.requests.cpu", "6");
  });

  it("calls handleResourceChange with correct key on GPU Limits change", () => {
    renderInTable(
      <TunerResourceInputs
        editedValues={{}}
        getResourceValue={getResourceValue}
        handleResourceChange={handleResourceChange}
        resourceErrors={{}}
      />
    );
    const gpuInput = screen.getByLabelText("GPU Limits");
    fireEvent.change(gpuInput, { target: { value: "2" } });
    expect(handleResourceChange).toHaveBeenCalledWith(
      "resources.limits.nvidia.com/gpu",
      "2"
    );
  });

  it("shows error message when resourceErrors has a truthy entry", () => {
    renderInTable(
      <TunerResourceInputs
        editedValues={{}}
        getResourceValue={getResourceValue}
        handleResourceChange={handleResourceChange}
        resourceErrors={{ "resources.requests.cpu": true }}
      />
    );
    expect(screen.getByText("Invalid format")).toBeInTheDocument();
  });

  it("does not show error message when resourceErrors is empty", () => {
    renderInTable(
      <TunerResourceInputs
        editedValues={{}}
        getResourceValue={getResourceValue}
        handleResourceChange={handleResourceChange}
        resourceErrors={{}}
      />
    );
    expect(screen.queryByText("Invalid format")).not.toBeInTheDocument();
  });
});
