import { useEffect, useRef } from 'react';
import type { Dispatch, SetStateAction } from 'react';
import { API } from '../constants';
import type { ClusterConfig, ClusterTarget } from '../types';
import { authFetch } from '../utils/authFetch';
import { CONFIGMAP_TIMEOUT_MS, createConfigMapTarget, isRecord } from './clusterConfigShared';

const POLLING_INTERVAL_MS = 300000; // 5 minutes

function syncConfigMapTarget(
  targets: ClusterTarget[],
  cmTarget: ClusterTarget
): { targets: ClusterTarget[]; updated: boolean } {
  const cmIdx = targets.findIndex((t) => t.source === 'configmap' && t.crType === cmTarget.crType);
  if (cmIdx >= 0) {
    const existing = targets[cmIdx];
    if (
      existing.namespace === cmTarget.namespace &&
      existing.inferenceService === cmTarget.inferenceService
    ) {
      return { targets, updated: false };
    }
    const next = [...targets];
    next[cmIdx] = cmTarget;
    return { targets: next, updated: true };
  }

  const sameIdx = targets.findIndex(
    (t) =>
      t.namespace === cmTarget.namespace &&
      t.inferenceService === cmTarget.inferenceService &&
      t.crType === cmTarget.crType
  );
  if (sameIdx >= 0) {
    const next = [...targets];
    next[sameIdx] = cmTarget;
    return { targets: next, updated: true };
  }

  return { targets: [cmTarget, ...targets], updated: true };
}

export interface UseConfigMapTargetsParams {
  isLoading: boolean;
  crType: string;
  setConfig: Dispatch<SetStateAction<ClusterConfig>>;
  configRef: { readonly current: ClusterConfig };
}

/**
 * Fetches ConfigMap default targets once after loading completes and keeps them
 * in sync via 5-minute polling. Also resolves the model name for the fetched
 * targets via /api/vllm-config.
 */
export function useConfigMapTargets({
  isLoading,
  crType,
  setConfig,
  configRef,
}: UseConfigMapTargetsParams): void {
  // Initial fetch of ConfigMap default targets (runs once after isLoading becomes false)
  const initialConfigMapFetchRef = useRef(false);
  useEffect(() => {
    if (isLoading) return;
    if (initialConfigMapFetchRef.current) return;
    initialConfigMapFetchRef.current = true;

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), CONFIGMAP_TIMEOUT_MS);

    authFetch(`${API}/config/default-targets`, { signal: controller.signal })
      .then((r) => r.json())
      .then((data: unknown) => {
        if (!isRecord(data)) return;
        const isvc = isRecord(data.isvc) ? data.isvc : null;
        const llmisvc = isRecord(data.llmisvc) ? data.llmisvc : null;

        const isvcHasValue = isvc && typeof isvc.name === 'string' && isvc.name !== '';
        const llmisvcHasValue = llmisvc && typeof llmisvc.name === 'string' && llmisvc.name !== '';

        if (!isvcHasValue && !llmisvcHasValue) return;

        setConfig((prev) => {
          let targets = prev.targets;
          let updated = false;

          if (isvcHasValue && typeof isvc.name === 'string' && typeof isvc.namespace === 'string') {
            const result = syncConfigMapTarget(
              targets,
              createConfigMapTarget(isvc.namespace, isvc.name, 'inferenceservice')
            );
            targets = result.targets;
            updated = updated || result.updated;
          }

          if (
            llmisvcHasValue &&
            typeof llmisvc.name === 'string' &&
            typeof llmisvc.namespace === 'string'
          ) {
            const result = syncConfigMapTarget(
              targets,
              createConfigMapTarget(llmisvc.namespace, llmisvc.name, 'llminferenceservice')
            );
            targets = result.targets;
            updated = updated || result.updated;
          }

          return updated ? { ...prev, targets } : prev;
        });

        const resolveTargetModels = async (targets: ClusterTarget[], signal: AbortSignal) => {
          const updated = await Promise.all(
            targets.map(async (t) => {
              try {
                const params = new URLSearchParams({
                  namespace: t.namespace,
                  is_name: t.inferenceService,
                  ...(t.crType ? { cr_type: t.crType } : {}),
                });
                const r = await authFetch(`${API}/vllm-config?${params}`, { signal });
                if (!r.ok) return t;
                const d = await r.json();
                const modelName = d.resolvedModelName || d.modelName;
                return modelName ? { ...t, modelName } : t;
              } catch (err) {
                console.warn('model resolve failed', err);
                return t;
              }
            })
          );
          if (signal.aborted) return;
          setConfig((prev) => ({
            ...prev,
            targets: prev.targets.map((pt) => {
              const match = updated.find(
                (u) =>
                  u.namespace === pt.namespace &&
                  u.inferenceService === pt.inferenceService &&
                  u.crType === pt.crType
              );
              return match?.modelName ? { ...pt, modelName: match.modelName } : pt;
            }),
          }));
        };

        const newTargets: ClusterTarget[] = [];
        if (isvcHasValue && typeof isvc.name === 'string' && typeof isvc.namespace === 'string') {
          newTargets.push(createConfigMapTarget(isvc.namespace, isvc.name, 'inferenceservice'));
        }
        if (
          llmisvcHasValue &&
          typeof llmisvc.name === 'string' &&
          typeof llmisvc.namespace === 'string'
        ) {
          newTargets.push(
            createConfigMapTarget(llmisvc.namespace, llmisvc.name, 'llminferenceservice')
          );
        }
        if (newTargets.length > 0) {
          resolveTargetModels(newTargets, controller.signal).catch(console.warn);
        }
      })
      .catch((err: Error) => {
        if (err.name !== 'AbortError') {
          console.warn('Failed to fetch ConfigMap default targets:', err);
        }
      })
      .finally(() => {
        clearTimeout(timeoutId);
      });

    return () => {
      controller.abort();
      clearTimeout(timeoutId);
    };
  }, [isLoading, crType, setConfig]);

  // 5-minute periodic polling to detect ConfigMap changes
  useEffect(() => {
    if (isLoading) return;

    const pollConfigMap = () => {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), CONFIGMAP_TIMEOUT_MS);

      authFetch(`${API}/config/default-targets`, { signal: controller.signal })
        .then((r) => r.json())
        .then((data: unknown) => {
          if (!isRecord(data)) return;
          const isvc = isRecord(data.isvc) ? data.isvc : null;
          const llmisvc = isRecord(data.llmisvc) ? data.llmisvc : null;

          const isvcHasValue = isvc && typeof isvc.name === 'string' && isvc.name !== '';
          const llmisvcHasValue =
            llmisvc && typeof llmisvc.name === 'string' && llmisvc.name !== '';

          setConfig((prev) => {
            const current = configRef.current;
            let targets = current.targets;
            let updated = false;

            if (
              isvcHasValue &&
              typeof isvc.name === 'string' &&
              typeof isvc.namespace === 'string'
            ) {
              const result = syncConfigMapTarget(
                targets,
                createConfigMapTarget(isvc.namespace, isvc.name, 'inferenceservice')
              );
              targets = result.targets;
              updated = updated || result.updated;
            }

            if (
              llmisvcHasValue &&
              typeof llmisvc.name === 'string' &&
              typeof llmisvc.namespace === 'string'
            ) {
              const result = syncConfigMapTarget(
                targets,
                createConfigMapTarget(llmisvc.namespace, llmisvc.name, 'llminferenceservice')
              );
              targets = result.targets;
              updated = updated || result.updated;
            }

            return updated ? { ...prev, targets } : prev;
          });
        })
        .catch((err: Error) => {
          if (err.name !== 'AbortError') {
            console.warn('Polling failed to fetch ConfigMap default targets:', err);
          }
        })
        .finally(() => {
          clearTimeout(timeoutId);
        });
    };

    const intervalId = setInterval(pollConfigMap, POLLING_INTERVAL_MS);

    return () => {
      clearInterval(intervalId);
    };
  }, [isLoading, crType, setConfig, configRef]);
}
