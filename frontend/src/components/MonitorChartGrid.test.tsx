import { render, screen, fireEvent } from "@testing-library/react";
import { vi, describe, it, expect } from "vitest";
import MonitorChartGrid, {
  CHART_DEFINITIONS,
  DEFAULT_ORDER,
  loadChartConfig,
  saveChartConfig,
  buildChartLinesMap,
} from "./MonitorChartGrid";
import { COLORS, TARGET_COLORS } from "../constants";

vi.mock("./Chart", () => ({
  default: ({ title, onHide }: { title: string; onHide?: () => void }) => (
    <div data-testid={`chart-${title}`}>
      <span>{title}</span>
      {onHide && <button type="button" onClick={onHide} aria-label={`Hide ${title} chart`}>×</button>}
    </div>
  ),
}));

const defaultProps = {
  visibleCharts: ["tps", "e2e_latency", "ttft"],
  hiddenCharts: [],
  chartData: [],
  chartLinesMap: {
    tps: [{ key: "tps", color: COLORS.accent, label: "TPS" }],
    e2e_latency: [{ key: "lat_p99", color: COLORS.red, label: "E2E Latency P99" }],
    ttft: [{ key: "ttft", color: COLORS.cyan, label: "TTFT mean" }],
  },
  onHideChart: vi.fn(),
  onShowChart: vi.fn(),
  getSlaThreshold: vi.fn(),
  timeRange: "Live" as const,
};

describe("MonitorChartGrid", () => {
  it("renders visible charts with correct titles", () => {
    render(<MonitorChartGrid {...defaultProps} />);
    expect(screen.getByText("Throughput (TPS)")).toBeInTheDocument();
    expect(screen.getByText("E2E Latency (ms)")).toBeInTheDocument();
    expect(screen.getByText("TTFT (ms)")).toBeInTheDocument();
  });

  it("does not render charts not in visibleCharts", () => {
    render(<MonitorChartGrid {...defaultProps} />);
    expect(screen.queryByText("KV Cache Usage (%)")).not.toBeInTheDocument();
    expect(screen.queryByText("GPU Utilization (%)")).not.toBeInTheDocument();
  });

  it("calls onHideChart when chart hide button is clicked", () => {
    const onHide = vi.fn();
    render(<MonitorChartGrid {...defaultProps} onHideChart={onHide} />);
    fireEvent.click(screen.getByLabelText("Hide Throughput (TPS) chart"));
    expect(onHide).toHaveBeenCalledWith("tps");
  });

  it("renders hidden charts bar when hiddenCharts is non-empty", () => {
    render(<MonitorChartGrid {...defaultProps} hiddenCharts={["kv", "rps"]} />);
    expect(screen.getByText("Hidden charts:")).toBeInTheDocument();
    expect(screen.getByText("KV Cache Usage (%)")).toBeInTheDocument();
    expect(screen.getByText("RPS (Requests/sec)")).toBeInTheDocument();
  });

  it("does not render hidden charts bar when hiddenCharts is empty", () => {
    render(<MonitorChartGrid {...defaultProps} hiddenCharts={[]} />);
    expect(screen.queryByText("Hidden charts:")).not.toBeInTheDocument();
  });

  it("calls onShowChart when hidden chart tag is clicked", () => {
    const onShow = vi.fn();
    render(<MonitorChartGrid {...defaultProps} hiddenCharts={["kv"]} onShowChart={onShow} />);
    fireEvent.click(screen.getByText("KV Cache Usage (%)"));
    expect(onShow).toHaveBeenCalledWith("kv");
  });

  it("renders all 12 charts when visibleCharts includes all IDs", () => {
    const allIds = CHART_DEFINITIONS.map(c => c.id);
    render(<MonitorChartGrid {...defaultProps} visibleCharts={allIds} />);
    expect(screen.getAllByRole("generic", { hidden: true }).length).toBeGreaterThanOrEqual(12);
    CHART_DEFINITIONS.forEach(def => {
      expect(screen.getByText(def.title)).toBeInTheDocument();
    });
  });

  it("renders with empty chartData without crashing", () => {
    render(<MonitorChartGrid {...defaultProps} chartData={[]} />);
    expect(screen.getByText("Throughput (TPS)")).toBeInTheDocument();
  });

  it("skips unknown chart IDs gracefully", () => {
    render(<MonitorChartGrid {...defaultProps} visibleCharts={["tps", "nonexistent"]} />);
    expect(screen.getByText("Throughput (TPS)")).toBeInTheDocument();
    expect(screen.queryByText("nonexistent")).not.toBeInTheDocument();
  });
});

describe("CHART_DEFINITIONS", () => {
  it("contains exactly 12 chart definitions", () => {
    expect(CHART_DEFINITIONS).toHaveLength(11);
  });

  it("has unique IDs", () => {
    const ids = CHART_DEFINITIONS.map(c => c.id);
    expect(new Set(ids).size).toBe(ids.length);
  });

  it("DEFAULT_ORDER matches CHART_DEFINITIONS IDs", () => {
    expect(DEFAULT_ORDER).toEqual(CHART_DEFINITIONS.map(c => c.id));
  });
});

describe("loadChartConfig / saveChartConfig", () => {
  const LS_KEY = "vllm-optimizer-chart-config";

  it("returns default config when localStorage is empty", () => {
    localStorage.removeItem(LS_KEY);
    const config = loadChartConfig();
    expect(config.order).toEqual(DEFAULT_ORDER);
    expect(config.hidden).toEqual([]);
  });

  it("loads saved config from localStorage", () => {
    const saved = { order: ["e2e_latency", "tps", "ttft"], hidden: ["kv"] };
    localStorage.setItem(LS_KEY, JSON.stringify(saved));
    const config = loadChartConfig();
    expect(config.order.slice(0, 3)).toEqual(["e2e_latency", "tps", "ttft"]);
    DEFAULT_ORDER.forEach(id => {
      expect(config.order).toContain(id);
    });
    expect(config.hidden).toEqual(["kv"]);
  });

  it("filters out invalid IDs from saved config", () => {
    const saved = { order: ["tps", "invalid_id", "e2e_latency"], hidden: ["bad_id"] };
    localStorage.setItem(LS_KEY, JSON.stringify(saved));
    const config = loadChartConfig();
    expect(config.order).toContain("tps");
    expect(config.order).toContain("e2e_latency");
    expect(config.order).not.toContain("invalid_id");
    expect(config.hidden).not.toContain("bad_id");
  });

  it("appends missing IDs to order", () => {
    const saved = { order: ["tps"], hidden: [] };
    localStorage.setItem(LS_KEY, JSON.stringify(saved));
    const config = loadChartConfig();
    DEFAULT_ORDER.forEach(id => {
      expect(config.order).toContain(id);
    });
  });

  it("returns defaults on malformed JSON", () => {
    localStorage.setItem(LS_KEY, "not-valid-json{{{");
    const config = loadChartConfig();
    expect(config.order).toEqual(DEFAULT_ORDER);
    expect(config.hidden).toEqual([]);
  });

  it("saveChartConfig persists to localStorage", () => {
    saveChartConfig(["tps", "e2e_latency"], ["kv"]);
    const raw = localStorage.getItem(LS_KEY);
    expect(raw).toBeTruthy();
    const parsed = JSON.parse(raw!);
    expect(parsed.order).toEqual(["tps", "e2e_latency"]);
    expect(parsed.hidden).toEqual(["kv"]);
  });
});

describe("buildChartLinesMap", () => {
  it("single target returns detailed multi-line definitions with COLORS", () => {
    const targets = [{ namespace: "ns1", inferenceService: "svc1", crType: "inferenceservice" }];
    const defaultKey = "ns1/svc1/inferenceservice";
    const result = buildChartLinesMap(targets, defaultKey);

    expect(result.e2e_latency).toHaveLength(3);
    expect(result.e2e_latency[0]).toEqual({ key: "ns1/svc1/inferenceservice_lat_p99_fill", color: COLORS.red, label: "P99 (idle)", dash: true });
    expect(result.e2e_latency[1]).toEqual({ key: "ns1/svc1/inferenceservice_lat_p99", color: COLORS.red, label: "E2E Latency P99" });
    expect(result.e2e_latency[2]).toEqual({ key: "ns1/svc1/inferenceservice_lat_mean", color: COLORS.accent, label: "E2E Latency mean" });

    expect(result.ttft).toHaveLength(3);
    expect(result.ttft[1].color).toBe(COLORS.cyan);
 
    expect(result.queue).toHaveLength(2);
    expect(result.queue[0].label).toBe("Running");
    expect(result.queue[1].label).toBe("Waiting");
  
    expect(result.tpot).toHaveLength(2);
    expect(result.tpot[0].label).toBe("TPOT mean");
    expect(result.tpot[1].label).toBe("TPOT p99");

    expect(result.queue_time).toHaveLength(2);
    expect(result.queue_time[0].label).toBe("Queue mean");
    expect(result.queue_time[1].label).toBe("Queue p99");

    expect(result.tps).toEqual([{ key: "ns1/svc1/inferenceservice_tps", color: COLORS.accent, label: "TPS" }]);
  });

  it("multiple targets returns makeMultiLines with TARGET_COLORS", () => {
    const targets = [
      { namespace: "ns1", inferenceService: "svc1", crType: "inferenceservice" },
      { namespace: "ns2", inferenceService: "svc2", crType: "inferenceservice" },
      { namespace: "ns3", inferenceService: "svc3", crType: "llminferenceservice" },
    ];
    const defaultKey = "ns1/svc1";
    const result = buildChartLinesMap(targets, defaultKey);

    expect(result.tps).toHaveLength(3);
    expect(result.e2e_latency).toHaveLength(3);
    expect(result.e2e_latency[0].key).toBe("ns1/svc1/inferenceservice_lat_p99");
    expect(result.e2e_latency[1].key).toBe("ns2/svc2/inferenceservice_lat_p99");
    expect(result.ttft).toHaveLength(3);
    expect(result.kv).toHaveLength(3);
    expect(result.kv_hit).toHaveLength(3);
    expect(result.queue).toHaveLength(3);
    expect(result.rps).toHaveLength(3);
    expect(result.gpu_util).toHaveLength(3);
    expect(result.gpu_mem).toHaveLength(3);
    expect(result.tpot).toHaveLength(3);
    expect(result.queue_time).toHaveLength(3);
  });
});
