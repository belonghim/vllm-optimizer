import { useEffect } from 'react';
import type { Dispatch, SetStateAction } from 'react';
import { API } from '../constants';
import type { ClusterTarget } from '../types';
import { authFetch } from '../utils/authFetch';
import { isRecord } from './clusterConfigShared';

/**
 * Re-fetches the resolved model name for the default target whenever the
 * target or CR type changes, aborting the previous request.
 */
export function useResolvedModelName(
  crType: string,
  stableTargets: ClusterTarget[],
  setResolvedModelName: Dispatch<SetStateAction<string>>
): void {
  useEffect(() => {
    const defaultTarget = stableTargets[0];
    if (!defaultTarget || !crType) return;

    const namespace = defaultTarget.namespace;
    const inferenceService = defaultTarget.inferenceService;
    if (!namespace || !inferenceService) return;

    const params = new URLSearchParams({
      namespace,
      is_name: inferenceService,
      cr_type: defaultTarget.crType || crType,
    });

    const controller = new AbortController();
    authFetch(`${API}/vllm-config?${params}`, { signal: controller.signal })
      .then((r) => r.json())
      .then((data: unknown) => {
        if (!isRecord(data)) return;
        const resolved =
          typeof data.resolvedModelName === 'string'
            ? data.resolvedModelName
            : typeof data.modelName === 'string'
              ? data.modelName
              : '';
        if (resolved) setResolvedModelName(resolved);
      })
      .catch((err: Error) => {
        if (err.name !== 'AbortError') {
          console.error('Failed to re-fetch resolved model name', err);
        }
      });
    return () => controller.abort();
  }, [crType, stableTargets, setResolvedModelName]);
}
