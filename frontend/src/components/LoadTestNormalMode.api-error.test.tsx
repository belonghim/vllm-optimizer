import { render, screen, fireEvent, waitFor, act } from "@testing-library/react";
import { vi, describe, it, expect, beforeAll, beforeEach, afterEach, afterAll } from "vitest";
import { setupServer } from "msw/node";
import { http, HttpResponse } from "msw";
import LoadTestNormalMode from "./LoadTestNormalMode";

const server = setupServer(
  http.get("*/status/interrupted", () =>
    HttpResponse.json({ interrupted_runs: [] })
  ),
  http.post("*/load_test/start", () =>
    HttpResponse.json({
      test_id: "test-123",
      status: "started",
      config: { model: "test-model" },
    })
  )
);

beforeAll(() => server.listen({ onUnhandledRequest: "bypass" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

vi.mock("../contexts/MockDataContext", () => ({
  useMockData: () => ({ isMockEnabled: false }),
}));

vi.mock("../contexts/ClusterConfigContext", () => ({
  useClusterConfig: () => ({
    endpoint: "http://test-endpoint:8080",
    namespace: "test-ns",
    inferenceservice: "test-is",
    isLoading: false,
    resolvedModelName: "test-model",
    updateConfig: vi.fn(),
    targets: [],
    maxTargets: 5,
    addTarget: vi.fn(),
    removeTarget: vi.fn(),
    setDefaultTarget: vi.fn(),
    crType: "inferenceservice",
    updateCrType: vi.fn(),
  }),
}));

vi.mock("../contexts/ThemeContext", () => ({
  useThemeColors: () => ({
    COLORS: {
      bg: "#0a0b0d", surface: "#111318", border: "#1e2330",
      accent: "#f5a623", cyan: "#00d4ff", green: "#00ff87",
      red: "#ff3b6b", purple: "#b060ff", text: "#c8cfe0", muted: "#4a5578",
    },
  }),
}));

vi.mock("./MetricCard", () => ({
  default: ({ label }: { label: string }) => (
    <div data-testid="metric-card">{label}</div>
  ),
}));

vi.mock("./Chart", () => ({
  default: ({ title }: { title: string }) => (
    <div data-testid="chart">{title}</div>
  ),
}));

vi.mock("./LoadTestConfig", () => ({
  default: ({
    onSubmit,
    onStop,
    isRunning,
  }: {
    onSubmit: () => void;
    onStop: () => void;
    isRunning: boolean;
    status: string;
  }) => (
    <div data-testid="load-test-config">
      <button type="button" onClick={onSubmit} disabled={isRunning}>
        ▶ Run Load Test
      </button>
      <button type="button" onClick={onStop} disabled={!isRunning}>
        ■ Stop
      </button>
    </div>
  ),
}));

class MockEventSource {
  static CONNECTING = 0;
  static OPEN = 1;
  static CLOSED = 2;
  readyState = MockEventSource.CONNECTING;
  onmessage: ((e: MessageEvent) => void) | null = null;
  onerror: (() => void) | null = null;
  close() { this.readyState = MockEventSource.CLOSED; }
}

beforeEach(() => {
  global.EventSource = MockEventSource as unknown as typeof EventSource;
  global.ResizeObserver = class ResizeObserver {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
});

describe("LoadTestNormalMode — API error scenarios (MSW)", () => {
  it("displays ErrorAlert when /load_test/start returns 500", async () => {
    server.use(
      http.post("*/load_test/start", () =>
        HttpResponse.json(
          { error: "Internal server error", error_type: "server_error" },
          { status: 500 }
        )
      )
    );

    render(<LoadTestNormalMode isActive={true} />);

    await act(async () => {
      fireEvent.click(screen.getByText("▶ Run Load Test"));
    });

    await waitFor(() => {
      expect(screen.getByRole("alert")).toBeInTheDocument();
    });
    expect(screen.getByRole("alert")).toHaveTextContent(/HTTP 500/);
  });

  it("displays ErrorAlert when /load_test/start returns 400 preflight error", async () => {
    server.use(
      http.post("*/load_test/start", () =>
        HttpResponse.json(
          { error: "Preflight failed", error_type: "preflight_error" },
          { status: 400 }
        )
      )
    );

    render(<LoadTestNormalMode isActive={true} />);

    await act(async () => {
      fireEvent.click(screen.getByText("▶ Run Load Test"));
    });

    await waitFor(() => {
      expect(screen.getByRole("alert")).toBeInTheDocument();
    });
    expect(screen.getByRole("alert")).toHaveTextContent(/HTTP 400/);
  });

  it("re-enables the start button after a 500 error (state recovery)", async () => {
    server.use(
      http.post("*/load_test/start", () =>
        HttpResponse.json({ error: "Server error" }, { status: 500 })
      )
    );

    render(<LoadTestNormalMode isActive={true} />);

    const startButton = screen.getByText("▶ Run Load Test");
    expect(startButton).not.toBeDisabled();

    await act(async () => {
      fireEvent.click(startButton);
    });

    await waitFor(() => {
      expect(screen.getByRole("alert")).toBeInTheDocument();
    });

    expect(screen.getByText("▶ Run Load Test")).not.toBeDisabled();
  });
});
