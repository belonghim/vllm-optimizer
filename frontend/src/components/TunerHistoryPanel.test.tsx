import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { vi, describe, it, expect, beforeEach, afterEach } from "vitest";
import TunerHistoryPanel from "./TunerHistoryPanel";

const mockSessions = [
  {
    id: 1,
    timestamp: 1711100000,
    objective: "balanced",
    n_trials: 10,
    best_score: 42.5,
    best_tps: 150.3,
    best_p99: 250,
  },
  {
    id: 2,
    timestamp: 1711200000,
    objective: "throughput",
    n_trials: 20,
    best_score: 55.0,
    best_tps: 200.1,
    best_p99: 180,
  },
];

const mockSessionDetail = {
  id: 1,
  timestamp: 1711100000,
  objective: "balanced",
  best_params: { max_num_seqs: 256, gpu_memory: 0.9 },
  best_tps: 150.3,
  best_p99: 250,
  trials: [],
};

beforeEach(() => {
  vi.stubGlobal(
    "fetch",
    vi.fn((url) => {
      const s = url.toString();
      if (s.includes("/tuner/sessions") && !s.match(/\/tuner\/sessions\/\d+/)) {
        return Promise.resolve({ ok: true, json: async () => mockSessions });
      }
      if (s.match(/\/tuner\/sessions\/\d+/)) {
        return Promise.resolve({ ok: true, json: async () => mockSessionDetail });
      }
      return Promise.resolve({ ok: true, json: async () => ({}) });
    })
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

describe("TunerHistoryPanel", () => {
  it("renders session list after fetch", async () => {
    render(<TunerHistoryPanel />);

    await waitFor(() => {
      expect(screen.getByText("balanced")).toBeInTheDocument();
    });

    expect(screen.getByText("throughput")).toBeInTheDocument();
    expect(screen.getByText("10")).toBeInTheDocument();
    expect(screen.getByText("20")).toBeInTheDocument();
  });

  it("shows 'No saved history' when sessions list is empty", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.resolve({ ok: true, json: async () => [] }))
    );

    render(<TunerHistoryPanel />);

    await waitFor(() => {
      expect(screen.getByText("No saved history.")).toBeInTheDocument();
    });
  });

  it("shows error message when fetch fails", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.resolve({ ok: false, status: 500 }))
    );

    render(<TunerHistoryPanel />);

    await waitFor(() => {
      expect(screen.getByText(/Failed to fetch history/)).toBeInTheDocument();
    });
  });

  it("allows selecting sessions for comparison", async () => {
    render(<TunerHistoryPanel />);

    await waitFor(() => {
      expect(screen.getByText("balanced")).toBeInTheDocument();
    });

    expect(screen.getByText("0 / 2 selected")).toBeInTheDocument();

    const rows = screen.getAllByRole("row");
    fireEvent.click(rows[1]);

    expect(screen.getByText("1 / 2 selected")).toBeInTheDocument();
  });

  it("enables compare button when 2 sessions are selected", async () => {
    render(<TunerHistoryPanel />);

    await waitFor(() => {
      expect(screen.getByText("balanced")).toBeInTheDocument();
    });

    const compareBtn = screen.getByRole("button", { name: /compare selected/i });
    expect(compareBtn).toBeDisabled();

    const rows = screen.getAllByRole("row");
    fireEvent.click(rows[1]);
    fireEvent.click(rows[2]);

    expect(compareBtn).not.toBeDisabled();
  });

  it("shows delete confirmation dialog when delete button is clicked", async () => {
    render(<TunerHistoryPanel />);

    await waitFor(() => {
      expect(screen.getByText("balanced")).toBeInTheDocument();
    });

    const deleteBtn = screen.getByRole("button", { name: /delete tuning session 1/i });
    fireEvent.click(deleteBtn);

    await waitFor(() => {
      expect(screen.getByRole("dialog")).toBeInTheDocument();
    });
    expect(screen.getByText("Delete this tuning session?")).toBeInTheDocument();
  });

  it("renders section title 'Tuning History'", async () => {
    render(<TunerHistoryPanel />);
    await waitFor(() => {
      expect(screen.getByText("Tuning History")).toBeInTheDocument();
    });
  });
});
