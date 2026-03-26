import { mockMetrics, mockHistory, mockHistoryWithGaps } from "./mockData.ts";

describe("mockData", () => {
  it("mockMetrics returns object with expected fields", () => {
    const m = mockMetrics();
    expect(m).toHaveProperty("tps");
    expect(m).toHaveProperty("pods");
    expect(typeof m.tps).toBe("number");
  });

  it("mockHistory returns non-empty array", () => {
    const h = mockHistory();
    expect(Array.isArray(h)).toBe(true);
    expect(h.length).toBeGreaterThan(0);
  });

  it("mockHistoryWithGaps returns 60 points", () => {
    const h = mockHistoryWithGaps();
    expect(h.length).toBe(60);
  });

  it("mockHistoryWithGaps has null ttft in gap range (index 10)", () => {
    const h = mockHistoryWithGaps();
    expect(h[10].ttft).toBeNull();
    expect(h[10].lat_p99).toBeNull();
  });

  it("mockHistoryWithGaps has valid ttft before gap (index 0)", () => {
    const h = mockHistoryWithGaps();
    expect(h[0].ttft).not.toBeNull();
    expect(typeof h[0].ttft).toBe("number");
  });

  it("mockHistoryWithGaps tps is never null", () => {
    const h = mockHistoryWithGaps();
    expect(h.every(p => typeof p.tps === "number")).toBe(true);
  });
});
