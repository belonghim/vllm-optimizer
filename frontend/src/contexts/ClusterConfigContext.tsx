import { createContext, useState, useEffect, useMemo, useContext, useCallback, useRef } from "react";
import type { ReactNode } from "react";
import { API } from "../constants";
import type { ClusterTarget, ClusterConfig } from "../types";
import { authFetch } from "../utils/authFetch";
import { buildDefaultEndpoint } from "../utils/endpointUtils";

const STORAGE_KEY = "vllm-opt-cluster-config";
const SCHEMA_VERSION = 3;
const MAX_TARGETS = 5;
const DEFAULT_NAMESPACE = "vllm-lab-dev";
const DEFAULT_INFERENCESERVICE = "llm-ov";
const DEFAULT_CR_TYPE = "inferenceservice";
const CONFIGMAP_TIMEOUT_MS = 5000;
const POLLING_INTERVAL_MS = 300000; // 5 minutes

export interface ClusterConfigContextValue {
  endpoint: string;
  namespace: string;
  inferenceservice: string;
  isLoading: boolean;
  updateConfig: (field: string, value: string) => void;
  targets: ClusterTarget[];
  maxTargets: number;
  addTarget: (namespace: string, inferenceService: string, crType?: string) => void;
  removeTarget: (namespace: string, inferenceService: string) => void;
  setDefaultTarget: (namespace: string, inferenceService: string, crType: string) => void;
  crType: string;
  resolvedModelName: string;
  updateCrType: (value: string) => Promise<{ configmap_updated: boolean }>;
  isvcTargets: ClusterTarget[];
  llmisvcTargets: ClusterTarget[];
}

const ClusterConfigContext = createContext<ClusterConfigContextValue>({
  endpoint: "",
  namespace: DEFAULT_NAMESPACE,
  inferenceservice: DEFAULT_INFERENCESERVICE,
  isLoading: true,
  updateConfig: () => {},
  targets: [],
  maxTargets: MAX_TARGETS,
  addTarget: () => {},
  removeTarget: () => {},
  setDefaultTarget: () => {},
  crType: DEFAULT_CR_TYPE,
  resolvedModelName: "",
  updateCrType: async () => ({ configmap_updated: true }),
  isvcTargets: [],
  llmisvcTargets: [],
});

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isClusterTargetArray(value: unknown): value is ClusterTarget[] {
  if (!Array.isArray(value)) return false;
  return value.every(
    (item) =>
      isRecord(item) &&
      typeof item.namespace === "string" &&
      typeof item.inferenceService === "string" &&
      typeof item.isDefault === "boolean" &&
      (item.crType === undefined || typeof item.crType === "string")
  );
}

function migrateLegacyConfig(stored: Record<string, unknown>): ClusterConfig {
  if (stored.namespace && (!stored.targets || (Array.isArray(stored.targets) && stored.targets.length === 0))) {
    const { namespace, inferenceservice, ...rest } = stored;
    return {
      endpoint: typeof rest.endpoint === "string" ? rest.endpoint : "",
      maxTargets: typeof rest.maxTargets === "number" ? rest.maxTargets : MAX_TARGETS,
      version: typeof rest.version === "number" ? rest.version : SCHEMA_VERSION,
      targets: [{
        namespace: typeof namespace === "string" ? namespace : "",
        inferenceService: typeof inferenceservice === "string" ? inferenceservice : "",
        isDefault: true,
      }],
    };
  }
  const targets = isClusterTargetArray(stored.targets) ? stored.targets : [];
    return {
      endpoint: typeof stored.endpoint === "string" ? stored.endpoint : "",
      maxTargets: typeof stored.maxTargets === "number" ? stored.maxTargets : MAX_TARGETS,
      version: typeof stored.version === "number" ? stored.version : SCHEMA_VERSION,
      targets: targets.length > 0
        ? targets
        : [{ namespace: DEFAULT_NAMESPACE, inferenceService: DEFAULT_INFERENCESERVICE, isDefault: true }],
    };
}

function migrateSchema(stored: Record<string, unknown>): ClusterConfig {
  const version = stored.version;
  if (!version || (typeof version === "number" && version < 2)) {
    const migrated = migrateLegacyConfig(stored);
    return { ...migrated, version: SCHEMA_VERSION };
  }
  const base = migrateLegacyConfig(stored);
  if (typeof version === "number" && version < 3) {
    return {
      ...base,
      version: SCHEMA_VERSION,
      targets: base.targets.map(t => ({ ...t, source: t.source ?? "manual" })),
    };
  }
  return base;
}

interface ClusterConfigProviderProps {
  children: ReactNode;
}

export function ClusterConfigProvider({ children }: ClusterConfigProviderProps): React.JSX.Element {
  const [config, setConfig] = useState<ClusterConfig>(() => {
    try {
      const stored = localStorage.getItem(STORAGE_KEY);
      if (stored) {
        const parsed: unknown = JSON.parse(stored);
        if (isRecord(parsed)) {
          return migrateSchema(parsed);
        }
      }
    } catch (e) {
      console.error('Failed to parse stored cluster configuration from localStorage', e);
    }
    return {
      endpoint: "",
      targets: [{ namespace: DEFAULT_NAMESPACE, inferenceService: DEFAULT_INFERENCESERVICE, isDefault: true }],
      maxTargets: MAX_TARGETS,
      version: SCHEMA_VERSION,
    };
  });
  const [isLoading, setIsLoading] = useState(true);
  const [crType, setCrType] = useState<string>(DEFAULT_CR_TYPE);
  const [resolvedModelName, setResolvedModelName] = useState<string>("");
  const stableTargetsRef = useRef<ClusterTarget[]>(config.targets);
  const prevTargetsJsonRef = useRef(JSON.stringify(config.targets));
  const configRef = useRef(config);
  const currentTargetsJson = JSON.stringify(config.targets);
  if (currentTargetsJson !== prevTargetsJsonRef.current) {
    prevTargetsJsonRef.current = currentTargetsJson;
    stableTargetsRef.current = config.targets;
  }
  const stableTargets = stableTargetsRef.current;

  // Derive CR-type-specific targets from flat targets array
  const isvcTargets = useMemo(() => stableTargets.filter(t => t.crType === "inferenceservice" || t.crType === undefined), [stableTargets]);
  const llmisvcTargets = useMemo(() => stableTargets.filter(t => t.crType === "llminferenceservice"), [stableTargets]);

  useEffect(() => {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), CONFIGMAP_TIMEOUT_MS);

    // No auth required — /api/config endpoint reads env variables with no auth middleware
    authFetch(`${API}/config`, { signal: controller.signal })
      .then(r => r.json())
      .then((data: unknown) => {
        if (!isRecord(data)) return;
        const vllmEndpoint = typeof data.vllm_endpoint === "string" ? data.vllm_endpoint : "";
        const vllmNamespace = typeof data.vllm_namespace === "string" ? data.vllm_namespace : "";
        const vllmIsName = typeof data.vllm_is_name === "string" ? data.vllm_is_name : "";
        const resolvedCrType = typeof data.cr_type === "string" ? data.cr_type : DEFAULT_CR_TYPE;
        const resolvedModel = typeof data.resolved_model_name === "string" ? data.resolved_model_name : "";

        // Only override defaults if API returned non-empty values
        const hasValidNamespace = vllmNamespace !== "";
        const hasValidIsName = vllmIsName !== "";
        
        if (!hasValidNamespace && !hasValidIsName) return;

        setConfig(prev => {
          const nonDefaultTargets = prev.targets.filter(t => !t.isDefault);
          const resolvedNamespace = vllmNamespace || DEFAULT_NAMESPACE;
          const resolvedIsName = vllmIsName || DEFAULT_INFERENCESERVICE;
          return {
            ...prev,
            endpoint: vllmEndpoint,
            targets: [
              { namespace: resolvedNamespace, inferenceService: resolvedIsName, isDefault: true, source: "manual" as const },
              ...nonDefaultTargets,
            ],
          };
        });
        setCrType(resolvedCrType);
        setResolvedModelName(resolvedModel);
      })
      .catch((err: Error) => {
        if (err.name === 'AbortError') return;
      })
      .finally(() => {
        clearTimeout(timeoutId);
        setIsLoading(false);
      });

    return () => {
      controller.abort();
      clearTimeout(timeoutId);
    };
  }, []);

  useEffect(() => {
    configRef.current = config;
  }, [config]);

  // Initial fetch of ConfigMap default targets (runs once after isLoading becomes false)
  const initialConfigMapFetchRef = useRef(false);
  useEffect(() => {
    if (isLoading) return;
    if (initialConfigMapFetchRef.current) return;
    initialConfigMapFetchRef.current = true;

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), CONFIGMAP_TIMEOUT_MS);

    authFetch(`${API}/config/default-targets`, { signal: controller.signal })
      .then(r => r.json())
      .then((data: unknown) => {
        if (!isRecord(data)) return;
        const isvc = isRecord(data.isvc) ? data.isvc : null;
        const llmisvc = isRecord(data.llmisvc) ? data.llmisvc : null;

        const isvcHasValue = isvc && typeof isvc.name === "string" && isvc.name !== "";
        const llmisvcHasValue = llmisvc && typeof llmisvc.name === "string" && llmisvc.name !== "";

        if (!isvcHasValue && !llmisvcHasValue) return;

        setConfig(prev => {
          let targets = prev.targets;

          if (isvcHasValue && typeof isvc.name === "string" && typeof isvc.namespace === "string") {
            targets = targets.filter(t => !(t.crType === "inferenceservice" || t.crType === undefined));
            const newIsvcTarget: ClusterTarget = {
              namespace: isvc.namespace,
              inferenceService: isvc.name,
              isDefault: crType === "inferenceservice",
              crType: "inferenceservice",
              source: "configmap",
            };
            targets = [newIsvcTarget, ...targets];
          }

          if (llmisvcHasValue && typeof llmisvc.name === "string" && typeof llmisvc.namespace === "string") {
            targets = targets.filter(t => t.crType !== "llminferenceservice");
            const newLlmisvcTarget: ClusterTarget = {
              namespace: llmisvc.namespace,
              inferenceService: llmisvc.name,
              isDefault: crType === "llminferenceservice",
              crType: "llminferenceservice",
              source: "configmap",
            };
            targets = [newLlmisvcTarget, ...targets];
          }

          return { ...prev, targets };
        });
      })
      .catch((err: Error) => {
        if (err.name !== "AbortError") {
          console.warn("Failed to fetch ConfigMap default targets:", err);
        }
      })
      .finally(() => {
        clearTimeout(timeoutId);
      });

    return () => {
      controller.abort();
      clearTimeout(timeoutId);
    };
  }, [isLoading, crType]);

  // 5-minute periodic polling to detect ConfigMap changes
  useEffect(() => {
    if (isLoading) return;

    const pollConfigMap = () => {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), CONFIGMAP_TIMEOUT_MS);

      authFetch(`${API}/config/default-targets`, { signal: controller.signal })
        .then(r => r.json())
        .then((data: unknown) => {
          if (!isRecord(data)) return;
          const isvc = isRecord(data.isvc) ? data.isvc : null;
          const llmisvc = isRecord(data.llmisvc) ? data.llmisvc : null;

          const isvcHasValue = isvc && typeof isvc.name === "string" && isvc.name !== "";
          const llmisvcHasValue = llmisvc && typeof llmisvc.name === "string" && llmisvc.name !== "";

          setConfig(prev => {
            const current = configRef.current;
            let updated = false;
            let newTargets = [...current.targets];

            if (isvcHasValue && typeof isvc.name === "string" && typeof isvc.namespace === "string") {
              const isDefaultForIsvc = crType === "inferenceservice";
              const newIsvcTarget: ClusterTarget = {
                namespace: isvc.namespace,
                inferenceService: isvc.name,
                isDefault: isDefaultForIsvc,
                crType: "inferenceservice",
                source: "configmap",
              };

              const cmIdx = newTargets.findIndex(t => t.source === "configmap" && (t.crType === "inferenceservice" || t.crType === undefined));
              if (cmIdx >= 0) {
                if (newTargets[cmIdx].namespace !== isvc.namespace || newTargets[cmIdx].inferenceService !== isvc.name) {
                  newTargets[cmIdx] = newIsvcTarget;
                  updated = true;
                }
              } else {
                newTargets.unshift(newIsvcTarget);
                updated = true;
              }
            }

            if (llmisvcHasValue && typeof llmisvc.name === "string" && typeof llmisvc.namespace === "string") {
              const isDefaultForLlmisvc = crType === "llminferenceservice";
              const newLlmisvcTarget: ClusterTarget = {
                namespace: llmisvc.namespace,
                inferenceService: llmisvc.name,
                isDefault: isDefaultForLlmisvc,
                crType: "llminferenceservice",
                source: "configmap",
              };

              const cmIdx = newTargets.findIndex(t => t.source === "configmap" && t.crType === "llminferenceservice");
              if (cmIdx >= 0) {
                if (newTargets[cmIdx].namespace !== llmisvc.namespace || newTargets[cmIdx].inferenceService !== llmisvc.name) {
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
          if (err.name !== "AbortError") {
            console.warn("Polling failed to fetch ConfigMap default targets:", err);
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
  }, [isLoading, crType]);

  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(config));
  }, [config]);

  useEffect(() => {
    const defaultTarget = stableTargets.find(t => t.isDefault) || stableTargets[0];
    if (!defaultTarget) return;

    const newEndpoint = buildDefaultEndpoint(
      crType,
      defaultTarget.namespace,
      defaultTarget.inferenceService,
    );

    setConfig(prev => ({ ...prev, endpoint: newEndpoint }));
  }, [crType, stableTargets]);

  useEffect(() => {
    const defaultTarget = stableTargets.find(t => t.isDefault) || stableTargets[0];
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
  }, [crType, stableTargets]);

  const updateCrType = useCallback(async (value: string): Promise<{ configmap_updated: boolean }> => {
    // No auth required — /config endpoint reads env variables with no auth middleware
    const res = await authFetch(`${API}/config`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ cr_type: value }),
    });
    if (res.status === 409) throw new Error('Auto-tuner is running. Cannot change CR type.');
    if (!res.ok) throw new Error(`Failed to update CR type: ${res.status}`);
    const data: unknown = await res.json();
    if (isRecord(data) && typeof data.cr_type === "string") setCrType(data.cr_type);
    const configmapUpdated = isRecord(data) && data.configmap_updated === true;
    return { configmap_updated: configmapUpdated };
  }, []);

  const updateConfig = useCallback((field: string, value: string): void => {
    setConfig(prev => {
      if (field === 'endpoint') {
        return { ...prev, endpoint: value };
      }

      if (field === 'namespace' || field === 'inferenceservice') {
        const targets: ClusterTarget[] = prev.targets.length > 0
          ? [...prev.targets]
          : [{ namespace: "", inferenceService: "", isDefault: true }];

        const defaultIdx = targets.findIndex(t => t.isDefault);
        const idx = defaultIdx >= 0 ? defaultIdx : 0;

        targets[idx] = {
          ...targets[idx],
          [field === 'inferenceservice' ? 'inferenceService' : field]: value,
        };

        const defaultTarget = targets[idx];
        const deduped = targets.filter((t, i) =>
          i === idx ||
          !(t.namespace === defaultTarget.namespace && t.inferenceService === defaultTarget.inferenceService)
        );

        return { ...prev, targets: deduped };
      }
      return prev;
    });
  }, []);

  const addTarget = useCallback((namespace: string, inferenceService: string, crType?: string): void => {
    setConfig(prev => {
      const currentTargets = prev.targets;
      if (currentTargets.length >= MAX_TARGETS) return prev;

      const newTarget: ClusterTarget = {
        namespace: namespace || "",
        inferenceService: inferenceService || "",
        isDefault: currentTargets.length === 0,
        source: "manual",
        ...(crType && { crType }),
      };

      return {
        ...prev,
        targets: [...currentTargets, newTarget],
      };
    });
  }, []);

  const removeTarget = useCallback((namespace: string, inferenceService: string): void => {
    setConfig(prev => {
      const currentTargets = prev.targets;
      const target = currentTargets.find(t => t.namespace === namespace && t.inferenceService === inferenceService);

      if (target && target.isDefault) return prev;

      const newTargets = currentTargets.filter(t => !(t.namespace === namespace && t.inferenceService === inferenceService));

      return {
        ...prev,
        targets: newTargets,
      };
    });
  }, []);

  const setDefaultTarget = useCallback(async (namespace: string, inferenceService: string, crType: string): Promise<void> => {
    setConfig(prev => {
      const currentTargets = prev.targets;
      const target = currentTargets.find(t => t.namespace === namespace && t.inferenceService === inferenceService);
      if (!target) {
        const newTarget: ClusterTarget = { namespace, inferenceService, isDefault: true, crType, source: "configmap" };
        return { ...prev, targets: [newTarget, ...currentTargets.filter(t => !(t.namespace === namespace && t.inferenceService === inferenceService))] };
      }

      const newTargets = currentTargets.map((t) => ({
        ...t,
        isDefault: t.namespace === namespace && t.inferenceService === inferenceService,
        source: (t.namespace === namespace && t.inferenceService === inferenceService) ? "configmap" : t.source,
      }));

      return { ...prev, targets: newTargets };
    });

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), CONFIGMAP_TIMEOUT_MS);

    // Build payload matching BE contract: {isvc: {name, namespace}} or {llmisvc: {name, namespace}}
    const patchPayload = crType === "inferenceservice"
      ? { isvc: { name: inferenceService, namespace } }
      : { llmisvc: { name: inferenceService, namespace } };

    try {
      await authFetch(`${API}/config/default-targets`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(patchPayload),
        signal: controller.signal,
      });
    } catch (err) {
      if (err instanceof Error && err.name !== "AbortError") {
        console.error("Failed to persist default target to ConfigMap (local state updated):", err);
      }
    } finally {
      clearTimeout(timeoutId);
    }
  }, []);

  const value = useMemo((): ClusterConfigContextValue => {
    const defaultTarget = config.targets.find(t => t.isDefault) || config.targets[0];
    return {
      endpoint: config.endpoint,
      namespace: defaultTarget?.namespace || DEFAULT_NAMESPACE,
      inferenceservice: defaultTarget?.inferenceService || DEFAULT_INFERENCESERVICE,
      isLoading,
      updateConfig,
      targets: config.targets,
      maxTargets: config.maxTargets || MAX_TARGETS,
      addTarget,
      removeTarget,
      setDefaultTarget,
      crType,
      resolvedModelName,
      updateCrType,
      isvcTargets,
      llmisvcTargets,
    };
  }, [config, isLoading, updateConfig, addTarget, removeTarget, setDefaultTarget, crType, resolvedModelName, updateCrType, isvcTargets, llmisvcTargets]);

  return (
    <ClusterConfigContext.Provider value={value}>
      {children}
    </ClusterConfigContext.Provider>
  );
}

export function useClusterConfig(): ClusterConfigContextValue {
  return useContext(ClusterConfigContext);
}
