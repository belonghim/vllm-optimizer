import { createContext, useState, useEffect, useMemo, useContext, useCallback, useRef } from "react";
import type { ReactNode } from "react";
import { API } from "../constants";
import type { ClusterTarget, ClusterConfig } from "../types";
import { authFetch } from "../utils/authFetch";
import { buildDefaultEndpoint } from "../utils/endpointUtils";
import { targetMatches } from "../utils/targetKey";
import { useConfigMapTargets } from "./useConfigMapTargets";
import { useResolvedModelName } from "./useResolvedModelName";
import { CONFIGMAP_TIMEOUT_MS, isRecord } from "./clusterConfigShared";

const STORAGE_KEY = "vllm-opt-cluster-config";
const SCHEMA_VERSION = 3;

export interface ClusterConfigContextValue {
  endpoint: string;
  namespace: string;
  inferenceservice: string;
  isLoading: boolean;
  updateConfig: (field: string, value: string) => void;
  targets: ClusterTarget[];
  maxTargets: number;
  addTarget: (namespace: string, inferenceService: string, crType?: string) => void;
  removeTarget: (namespace: string, inferenceService: string, crType: string) => void;
  setDefaultTarget: (namespace: string, inferenceService: string, crType: string) => Promise<void>;
  crType: string;
  resolvedModelName: string;

  isvcTargets: ClusterTarget[];
  llmisvcTargets: ClusterTarget[];
}

const ClusterConfigContext = createContext<ClusterConfigContextValue>({
  endpoint: "",
  namespace: "",
  inferenceservice: "",
  isLoading: true,
  updateConfig: () => {},
  targets: [],
  maxTargets: Infinity,
  addTarget: () => {},
  removeTarget: () => {},
  setDefaultTarget: async () => {},
  crType: "inferenceservice",
  resolvedModelName: "",

  isvcTargets: [],
  llmisvcTargets: [],
});

function isClusterTargetArray(value: unknown): value is ClusterTarget[] {
  if (!Array.isArray(value)) return false;
  return value.every(
    (item) =>
      isRecord(item) &&
      typeof item.namespace === "string" &&
      typeof item.inferenceService === "string" &&
      typeof item.crType === "string"
  );
}

function migrateLegacyConfig(stored: Record<string, unknown>): ClusterConfig {
  if (stored.namespace && (!stored.targets || (Array.isArray(stored.targets) && stored.targets.length === 0))) {
    const { namespace, inferenceservice, ...rest } = stored;
    return {
      endpoint: typeof rest.endpoint === "string" ? rest.endpoint : "",
      maxTargets: typeof rest.maxTargets === "number" ? rest.maxTargets : Infinity,
      version: typeof rest.version === "number" ? rest.version : SCHEMA_VERSION,
      targets: [{
        namespace: typeof namespace === "string" ? namespace : "",
        inferenceService: typeof inferenceservice === "string" ? inferenceservice : "",
        crType: "inferenceservice",
      }],
    };
  }
  const targets = isClusterTargetArray(stored.targets) ? stored.targets : [];
    return {
      endpoint: typeof stored.endpoint === "string" ? stored.endpoint : "",
      maxTargets: typeof stored.maxTargets === "number" ? stored.maxTargets : Infinity,
      version: typeof stored.version === "number" ? stored.version : SCHEMA_VERSION,
      targets: targets.length > 0 ? targets : [],
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
      targets: [],
      maxTargets: Infinity,
      version: SCHEMA_VERSION,
    };
  });
  const [isLoading, setIsLoading] = useState(true);
  const [crType, setCrType] = useState<string>("inferenceservice");
  // Ref to access latest crType inside stable callbacks (updateConfig) without
  // changing their identity and causing downstream re-renders.
  const crTypeRef = useRef(crType);
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
  const isvcTargets = useMemo(() => stableTargets.filter(t => t.crType === "inferenceservice"), [stableTargets]);
  const llmisvcTargets = useMemo(() => stableTargets.filter(t => t.crType === "llminferenceservice"), [stableTargets]);

  useEffect(() => {
    crTypeRef.current = crType;
  }, [crType]);

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
        const resolvedCrType = typeof data.cr_type === "string" ? data.cr_type : "inferenceservice";
        const resolvedModel = typeof data.resolved_model_name === "string" ? data.resolved_model_name : "";

        // Only override defaults if API returned non-empty values
        const hasValidNamespace = vllmNamespace !== "";
        const hasValidIsName = vllmIsName !== "";
        
        if (!hasValidNamespace && !hasValidIsName) return;

        setConfig(prev => {
          return {
            ...prev,
            endpoint: vllmEndpoint,
            targets: [
              { namespace: vllmNamespace, inferenceService: vllmIsName, crType: resolvedCrType, source: "manual" as const },
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

  useConfigMapTargets({ isLoading, crType, setConfig, configRef });

  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(config));
  }, [config]);

  useEffect(() => {
    const defaultTarget = stableTargets[0];
    if (!defaultTarget) return;

    const newEndpoint = buildDefaultEndpoint(
      crType,
      defaultTarget.namespace,
      defaultTarget.inferenceService,
    );

    setConfig(prev => ({ ...prev, endpoint: newEndpoint }));
  }, [crType, stableTargets]);

  useResolvedModelName(crType, stableTargets, setResolvedModelName);


  const updateConfig = useCallback((field: string, value: string): void => {
    setConfig(prev => {
      if (field === 'endpoint') {
        return { ...prev, endpoint: value };
      }

      if (field === 'namespace' || field === 'inferenceservice') {
        const targets: ClusterTarget[] = prev.targets.length > 0
          ? [...prev.targets]
          : [{ namespace: "", inferenceService: "", crType: crTypeRef.current }];

        targets[0] = {
          ...targets[0],
          [field === 'inferenceservice' ? 'inferenceService' : field]: value,
        };

        const defaultTarget = targets[0];
        const deduped = targets.filter((t, i) =>
          i === 0 ||
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

      const newTarget: ClusterTarget = {
        namespace: namespace || "",
        inferenceService: inferenceService || "",
        crType: crType || "inferenceservice",
        source: "manual",
      };

      return {
        ...prev,
        targets: [...currentTargets, newTarget],
      };
    });
  }, []);

  const removeTarget = useCallback((namespace: string, inferenceService: string, crType: string): void => {
    setConfig(prev => {
      const currentTargets = prev.targets;
      const newTargets = currentTargets.filter(t => !targetMatches(t, { namespace, inferenceService, crType }));

      return {
        ...prev,
        targets: newTargets,
      };
    });
  }, []);

  const setDefaultTarget = useCallback(async (namespace: string, inferenceService: string, crType: string): Promise<void> => {
    const previousTargets = configRef.current.targets;
    setConfig(prev => {
      const currentTargets = prev.targets;
      const target = currentTargets.find(t => targetMatches(t, { namespace, inferenceService, crType }));
      if (!target) {
        const newTarget: ClusterTarget = { namespace, inferenceService, crType, source: "configmap" };
        return { ...prev, targets: [newTarget, ...currentTargets.filter(t => !targetMatches(t, { namespace, inferenceService, crType }))] };
      }

      const targetIdx = currentTargets.findIndex(t => targetMatches(t, { namespace, inferenceService, crType }));
      if (targetIdx < 0) return prev;
      const defaultTarget = currentTargets[targetIdx];
      const newTargets = [defaultTarget, ...currentTargets.filter((_, i) => i !== targetIdx)];

      return { ...prev, targets: newTargets };
    });

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), CONFIGMAP_TIMEOUT_MS);

    // Build payload matching BE contract: {isvc: {name, namespace}} or {llmisvc: {name, namespace}}
    const patchPayload = crType === "inferenceservice"
      ? { isvc: { name: inferenceService, namespace } }
      : { llmisvc: { name: inferenceService, namespace } };

    try {
      const res = await authFetch(`${API}/config/default-targets`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(patchPayload),
        signal: controller.signal,
      });
      if (!res.ok) throw new Error(`ConfigMap patch failed: ${res.status}`);
      const data: unknown = await res.json();
      if (isRecord(data) && data.configmap_updated === false) {
        throw new Error("ConfigMap write failed (RBAC or cluster error)");
      }
    } catch (err) {
      if (err instanceof Error && err.name === "AbortError") return;
      setConfig(prev => ({ ...prev, targets: previousTargets }));
      throw err;
    } finally {
      clearTimeout(timeoutId);
    }
  }, []);

  const value = useMemo((): ClusterConfigContextValue => {
    const defaultTarget = config.targets[0];
    return {
      endpoint: config.endpoint,
      namespace: defaultTarget?.namespace || "",
      inferenceservice: defaultTarget?.inferenceService || "",
      isLoading,
      updateConfig,
      targets: config.targets,
      maxTargets: config.maxTargets || Infinity,
      addTarget,
      removeTarget,
      setDefaultTarget,
      crType,
      resolvedModelName,
      isvcTargets,
      llmisvcTargets,
    };
  }, [config, isLoading, updateConfig, addTarget, removeTarget, setDefaultTarget, crType, resolvedModelName, isvcTargets, llmisvcTargets]);

  return (
    <ClusterConfigContext.Provider value={value}>
      {children}
    </ClusterConfigContext.Provider>
  );
}

export function useClusterConfig(): ClusterConfigContextValue {
  return useContext(ClusterConfigContext);
}
