import { describe, it, expect } from "vitest";
import { fmt } from "./format";

describe("fmt", () => {
  it("formats a number with default 1 decimal place", () => {
    expect(fmt(1.234)).toBe("1.2");
  });

  it("formats a number with specified decimal places", () => {
    expect(fmt(1.234, 2)).toBe("1.23");
  });

  it("returns em-dash for null", () => {
    expect(fmt(null)).toBe("—");
  });

  it("returns em-dash for undefined", () => {
    expect(fmt(undefined)).toBe("—");
  });

  it("formats zero correctly", () => {
    expect(fmt(0)).toBe("0.0");
  });

  it("formats negative numbers", () => {
    expect(fmt(-3.567, 1)).toBe("-3.6");
  });

  it("formats zero decimals when d=0", () => {
    expect(fmt(42.9, 0)).toBe("43");
  });
});
