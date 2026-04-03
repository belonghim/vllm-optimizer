import { describe, it, expect } from "vitest";
import { buildDefaultEndpoint } from "./endpointUtils";

describe("buildDefaultEndpoint", () => {
  it("returns isvc pattern for inferenceservice crType", () => {
    const result = buildDefaultEndpoint("inferenceservice", "my-ns", "my-model");
    expect(result).toBe("http://my-model-predictor.my-ns.svc.cluster.local:8080");
  });

  it("returns llmis gateway pattern for llminferenceservice crType", () => {
    const result = buildDefaultEndpoint("llminferenceservice", "my-ns", "my-model");
    expect(result).toBe("http://my-model-openshift-default.my-ns.svc.cluster.local:80");
  });

  it("falls back to isvc pattern for empty string crType", () => {
    const result = buildDefaultEndpoint("", "fallback-ns", "fallback-model");
    expect(result).toBe("http://fallback-model-predictor.fallback-ns.svc.cluster.local:8080");
  });

  it("falls back to isvc pattern for unknown crType", () => {
    const result = buildDefaultEndpoint("unknown-type", "some-ns", "some-model");
    expect(result).toBe("http://some-model-predictor.some-ns.svc.cluster.local:8080");
  });

  it("interpolates namespace and isName correctly in isvc pattern", () => {
    const result = buildDefaultEndpoint("inferenceservice", "vllm-lab-dev", "llm-ov");
    expect(result).toBe("http://llm-ov-predictor.vllm-lab-dev.svc.cluster.local:8080");
  });

  it("interpolates namespace and isName correctly in llmis pattern", () => {
    const result = buildDefaultEndpoint("llminferenceservice", "llm-d-demo", "small-llm-d");
    expect(result).toBe("http://small-llm-d-openshift-default.llm-d-demo.svc.cluster.local:80");
  });
});
