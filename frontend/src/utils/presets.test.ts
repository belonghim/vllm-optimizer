import { describe, it, expect, beforeEach } from "vitest";
import { loadPresets, savePreset, deletePreset } from "./presets";

beforeEach(() => {
  localStorage.clear();
});

describe("loadPresets", () => {
  it("includes builtin preset Light", () => {
     const presets = loadPresets();
     expect(presets["Lightweight"]).toBeDefined();
   });

  it("includes builtin preset Standard", () => {
     const presets = loadPresets();
     expect(presets["Standard"]).toBeDefined();
   });

  it("includes builtin preset Stress", () => {
     const presets = loadPresets();
     expect(presets["Stress"]).toBeDefined();
   });
});

describe("savePreset", () => {
  it("saved preset appears in loadPresets", () => {
     savePreset("MyTest", { total_requests: 100 });
     const presets = loadPresets();
     expect(presets["MyTest"]).toBeDefined();
     expect(presets["MyTest"].total_requests).toBe(100);
   });

  it("uses defaults for omitted fields", () => {
     savePreset("PartialConfig", {});
     const presets = loadPresets();
     expect(presets["PartialConfig"].concurrency).toBe(20);
   });

  it("throws when saving over a builtin preset", () => {
     expect(() => savePreset("Lightweight", {})).toThrow("Cannot overwrite builtin preset");
   });
});

describe("deletePreset", () => {
  it("removes user preset from loadPresets", () => {
     savePreset("ForDeletion", { total_requests: 50 });
     expect(loadPresets()["ForDeletion"]).toBeDefined();
     deletePreset("ForDeletion");
     expect(loadPresets()["ForDeletion"]).toBeUndefined();
   });

  it("throws when deleting a builtin preset", () => {
     expect(() => deletePreset("Standard")).toThrow("Cannot delete builtin preset");
   });
});
