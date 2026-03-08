import { mockMetrics, mockHistory } from "./mockData";

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
});
