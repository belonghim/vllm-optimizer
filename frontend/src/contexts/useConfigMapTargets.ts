import { useEffect, useRef } from 'react';
import type { Dispatch, SetStateAction } from 'react';
import { API } from '../constants';
import type { ClusterConfig, ClusterTarget } from '../types';
import { authFetch } from '../utils/authFetch';
import { CONFIGMAP_TIMEOUT_MS, createConfigMapTarget, isRecord } from './clusterConfigShared';

const POLLING_INTERVAL_MS = 300000; // 5 minutes

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
          let targets = [...prev.targets];

          if (isvcHasValue && typeof isvc.name === 'string' && typeof isvc.namespace === 'string') {
            const newIsvcTarget = createConfigMapTarget(
              isvc.namespace,
              isvc.name,
              'inferenceservice'
            );
            targets = targets.filter((t) => t.crType !== 'inferenceservice');
            targets.unshift(newIsvcTarget);
          }

          if (
            llmisvcHasValue &&
            typeof llmisvc.name === 'string' &&
            typeof llmisvc.namespace === 'string'
          ) {
            const newLlmisvcTarget = createConfigMapTarget(
              llmisvc.namespace,
              llmisvc.name,
              'llminferenceservice'
            );
            targets = targets.filter((t) => t.crType !== 'llminferenceservice');
            targets.unshift(newLlmisvcTarget);
          }

          return { ...prev, targets };
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
            let updated = false;
            const newTargets = [...current.targets];

            if (
              isvcHasValue &&
              typeof isvc.name === 'string' &&
              typeof isvc.namespace === 'string'
            ) {
              const newIsvcTarget = createConfigMapTarget(
                isvc.namespace,
                isvc.name,
                'inferenceservice'
              );

              const cmIdx = newTargets.findIndex(
                (t) => t.source === 'configmap' && t.crType === 'inferenceservice'
              );
              if (cmIdx >= 0) {
                if (
                  newTargets[cmIdx].namespace !== isvc.namespace ||
                  newTargets[cmIdx].inferenceService !== isvc.name
                ) {
                  newTargets[cmIdx] = newIsvcTarget;
                  updated = true;
                }
              } else {
                newTargets.unshift(newIsvcTarget);
                updated = true;
              }
            }

            if (
              llmisvcHasValue &&
              typeof llmisvc.name === 'string' &&
              typeof llmisvc.namespace === 'string'
            ) {
              const newLlmisvcTarget = createConfigMapTarget(
                llmisvc.namespace,
                llmisvc.name,
                'llminferenceservice'
              );

              const cmIdx = newTargets.findIndex(
                (t) => t.source === 'configmap' && t.crType === 'llminferenceservice'
              );
              if (cmIdx >= 0) {
                if (
                  newTargets[cmIdx].namespace !== llmisvc.namespace ||
                  newTargets[cmIdx].inferenceService !== llmisvc.name
                ) {
                  newTargets[cmIdx] = newLlmisvcTarget;
                  updated = true;
                }
              } else {
                newTargets.unshift(newLlmisvcTarget);
                updated = true;
              }
            }

            return updated ? { ...prev, targets: newTargets } : prev;
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
