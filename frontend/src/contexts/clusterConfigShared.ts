import type { ClusterTarget } from "../types";

export const CONFIGMAP_TIMEOUT_MS = 5000;

export function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export function createConfigMapTarget(
  namespace: string,
  name: string,
  crType: "inferenceservice" | "llminferenceservice"
): ClusterTarget {
  return { namespace, inferenceService: name, crType, source: "configmap" };
}
