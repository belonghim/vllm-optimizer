import { useEffect } from "react";
import type { Dispatch, SetStateAction } from "react";
import { API } from "../constants";
import type { ClusterTarget } from "../types";
import { authFetch } from "../utils/authFetch";
import { isRecord } from "./clusterConfigShared";

/**
 * Re-fetches the resolved model name from /api/config whenever the default
 * target or CR type changes, aborting the previous request.
 */
export function useResolvedModelName(
  crType: string,
  stableTargets: ClusterTarget[],
  setResolvedModelName: Dispatch<SetStateAction<string>>,
): void {
  useEffect(() => {
    const defaultTarget = stableTargets[0];
    if (!defaultTarget || !crType) return;

    const namespace = defaultTarget.namespace;
    const inferenceService = defaultTarget.inferenceService;
    if (!namespace || !inferenceService) return;

    const controller = new AbortController();
    // No auth required — /config endpoint reads env variables with no auth middleware
    authFetch(`${API}/config`, { signal: controller.signal })
      .then(r => r.json())
      .then((data: unknown) => {
        if (isRecord(data) && typeof data.resolved_model_name === "string") {
          setResolvedModelName(data.resolved_model_name);
        }
      })
      .catch((err: Error) => {
        if (err.name !== "AbortError") {
          console.error("Failed to re-fetch resolved model name", err);
        }
      });
    return () => controller.abort();
  }, [crType, stableTargets, setResolvedModelName]);
}
