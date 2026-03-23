import { describe, it, expect, beforeEach } from "vitest";
import { loadPresets, savePreset, deletePreset } from "./presets";

beforeEach(() => {
  localStorage.clear();
});

describe("loadPresets", () => {
  it("includes builtin preset 경량", () => {
    const presets = loadPresets();
    expect(presets["경량"]).toBeDefined();
  });

  it("includes builtin preset 표준", () => {
    const presets = loadPresets();
    expect(presets["표준"]).toBeDefined();
  });

  it("includes builtin preset 스트레스", () => {
    const presets = loadPresets();
    expect(presets["스트레스"]).toBeDefined();
  });
});

describe("savePreset", () => {
  it("saved preset appears in loadPresets", () => {
    savePreset("내테스트", { total_requests: 100 });
    const presets = loadPresets();
    expect(presets["내테스트"]).toBeDefined();
    expect(presets["내테스트"].total_requests).toBe(100);
  });

  it("uses defaults for omitted fields", () => {
    savePreset("부분설정", {});
    const presets = loadPresets();
    expect(presets["부분설정"].concurrency).toBe(20);
  });

  it("throws when saving over a builtin preset", () => {
    expect(() => savePreset("경량", {})).toThrow("Cannot overwrite builtin preset");
  });
});

describe("deletePreset", () => {
  it("removes user preset from loadPresets", () => {
    savePreset("삭제용", { total_requests: 50 });
    expect(loadPresets()["삭제용"]).toBeDefined();
    deletePreset("삭제용");
    expect(loadPresets()["삭제용"]).toBeUndefined();
  });

  it("throws when deleting a builtin preset", () => {
    expect(() => deletePreset("표준")).toThrow("Cannot delete builtin preset");
  });
});
