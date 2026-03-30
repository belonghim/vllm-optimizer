import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi, describe, it, expect, afterEach } from "vitest";
import SlaProfileList from "./SlaProfileList";
import type { SlaProfile } from "../types";

function makeProfile(id: number, name: string): SlaProfile {
  return {
    id,
    name,
    thresholds: { availability_min: 99, p95_latency_max_ms: null, error_rate_max_pct: null, min_tps: null },
    created_at: 0,
  };
}

function makeProps(overrides = {}) {
  return {
    profiles: [] as SlaProfile[],
    onEdit: vi.fn(),
    onDelete: vi.fn(),
    selectedProfileId: null as number | null,
    onSelect: vi.fn(),
    loading: false,
    ...overrides,
  };
}

afterEach(() => {
  vi.clearAllMocks();
});

describe("SlaProfileList", () => {
  it("shows empty state message when no profiles", () => {
    render(<SlaProfileList {...makeProps()} />);
    expect(screen.getByText("No profiles registered.")).toBeInTheDocument();
  });

  it("shows Loading... when loading is true", () => {
    render(<SlaProfileList {...makeProps({ loading: true })} />);
    expect(screen.getByText("Loading...")).toBeInTheDocument();
    expect(screen.queryByText("No profiles registered.")).not.toBeInTheDocument();
  });

  it("renders profile names in table rows", () => {
    const profiles = [makeProfile(1, "Production SLA"), makeProfile(2, "Dev SLA")];
    render(<SlaProfileList {...makeProps({ profiles })} />);
    expect(screen.getByText("Production SLA")).toBeInTheDocument();
    expect(screen.getByText("Dev SLA")).toBeInTheDocument();
  });

  it("shows threshold summary text for profiles", () => {
    const profiles = [makeProfile(1, "My SLA")];
    render(<SlaProfileList {...makeProps({ profiles })} />);
    expect(screen.getByText(/Availability≥99%/)).toBeInTheDocument();
  });

  it("calls onDelete when Delete button is clicked", async () => {
    const onDelete = vi.fn();
    const user = userEvent.setup();
    const profiles = [makeProfile(42, "Test SLA")];
    render(<SlaProfileList {...makeProps({ profiles, onDelete })} />);
    await user.click(screen.getByRole("button", { name: "Delete" }));
    expect(onDelete).toHaveBeenCalledWith(42);
  });

  it("calls onEdit when Edit button is clicked", async () => {
    const onEdit = vi.fn();
    const user = userEvent.setup();
    const profiles = [makeProfile(5, "Edit Me SLA")];
    render(<SlaProfileList {...makeProps({ profiles, onEdit })} />);
    await user.click(screen.getByRole("button", { name: "Edit" }));
    expect(onEdit).toHaveBeenCalledWith(profiles[0]);
  });
});
