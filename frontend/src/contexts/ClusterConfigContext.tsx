import { createContext, useState, useEffect, useMemo, useContext, useCallback } from "react";
import type { ReactNode } from "react";
import { API } from "../constants";
import type { ClusterTarget, ClusterConfig } from "../types";

const STORAGE_KEY = "vllm-opt-cluster-config";
const SCHEMA_VERSION = 2;
const MAX_TARGETS = 5;

interface ClusterConfigContextValue {
  endpoint: string;
  namespace: string;
  inferenceservice: string;
  isLoading: boolean;
  updateConfig: (field: string, value: string) => void;
  targets: ClusterTarget[];
  maxTargets: number;
  addTarget: (namespace: string, inferenceService: string) => void;
  removeTarget: (namespace: string, inferenceService: string) => void;
  setDefaultTarget: (namespace: string, inferenceService: string) => void;
}

const ClusterConfigContext = createContext<ClusterConfigContextValue>({
  endpoint: "",
  namespace: "",
  inferenceservice: "",
  isLoading: true,
  updateConfig: () => {},
  targets: [],
  maxTargets: MAX_TARGETS,
  addTarget: () => {},
  removeTarget: () => {},
  setDefaultTarget: () => {},
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
      typeof item.isDefault === "boolean"
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
    targets,
  };
}

function migrateSchema(stored: Record<string, unknown>): ClusterConfig {
  const version = stored.version;
  if (!version || (typeof version === "number" && version < 2)) {
    const migrated = migrateLegacyConfig(stored);
    return { ...migrated, version: SCHEMA_VERSION };
  }
  return migrateLegacyConfig(stored);
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
    } catch {
      /* localStorage unavailable */
    }
    return {
      endpoint: "",
      targets: [],
      maxTargets: MAX_TARGETS,
      version: SCHEMA_VERSION,
    };
  });
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const hasStoredValues = (): boolean => {
      try {
        const stored = localStorage.getItem(STORAGE_KEY);
        if (!stored) return false;
        const parsed: unknown = JSON.parse(stored);
        if (!isRecord(parsed)) return false;
        return !!(parsed.endpoint || (Array.isArray(parsed.targets) && parsed.targets.length > 0));
      } catch {
        return false;
      }
    };

    if (hasStoredValues()) {
      setIsLoading(false);
      return;
    }

    const controller = new AbortController();
    fetch(`${API}/config`, { signal: controller.signal })
      .then(r => r.json())
      .then((data: unknown) => {
        if (!isRecord(data)) return;
        const vllmEndpoint = typeof data.vllm_endpoint === "string" ? data.vllm_endpoint : "";
        const vllmNamespace = typeof data.vllm_namespace === "string" ? data.vllm_namespace : "";
        const vllmIsName = typeof data.vllm_is_name === "string" ? data.vllm_is_name : "";

        const apiConfig: ClusterConfig = {
          endpoint: vllmEndpoint,
          targets: vllmNamespace ? [{
            namespace: vllmNamespace,
            inferenceService: vllmIsName,
            isDefault: true,
          }] : [],
          maxTargets: MAX_TARGETS,
          version: SCHEMA_VERSION,
        };
        setConfig(apiConfig);
        localStorage.setItem(STORAGE_KEY, JSON.stringify(apiConfig));
      })
      .catch((err: Error) => {
        if (err.name === 'AbortError') return;
        console.warn('[ClusterConfig] config fetch failed:', err.message);
      })
      .finally(() => setIsLoading(false));
    return () => controller.abort();
  }, []);

  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(config));
  }, [config]);

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
        return { ...prev, targets };
      }
      return prev;
    });
  }, []);

  const addTarget = useCallback((namespace: string, inferenceService: string): void => {
    setConfig(prev => {
      const currentTargets = prev.targets;
      if (currentTargets.length >= MAX_TARGETS) return prev;

      const newTarget: ClusterTarget = {
        namespace: namespace || "",
        inferenceService: inferenceService || "",
        isDefault: currentTargets.length === 0,
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

  const setDefaultTarget = useCallback((namespace: string, inferenceService: string): void => {
    setConfig(prev => {
      const currentTargets = prev.targets;
      const target = currentTargets.find(t => t.namespace === namespace && t.inferenceService === inferenceService);
      if (!target) return prev;

      const newTargets = currentTargets.map((t) => ({
        ...t,
        isDefault: t.namespace === namespace && t.inferenceService === inferenceService,
      }));

      return {
        ...prev,
        targets: newTargets,
      };
    });
  }, []);

  const value = useMemo((): ClusterConfigContextValue => {
    const defaultTarget = config.targets.find(t => t.isDefault) || config.targets[0];
    return {
      endpoint: config.endpoint,
      namespace: defaultTarget?.namespace || "",
      inferenceservice: defaultTarget?.inferenceService || "",
      isLoading,
      updateConfig,
      targets: config.targets,
      maxTargets: config.maxTargets || MAX_TARGETS,
      addTarget,
      removeTarget,
      setDefaultTarget,
    };
  }, [config, isLoading, updateConfig, addTarget, removeTarget, setDefaultTarget]);

  return (
    <ClusterConfigContext.Provider value={value}>
      {children}
    </ClusterConfigContext.Provider>
  );
}

export function useClusterConfig(): ClusterConfigContextValue {
  return useContext(ClusterConfigContext);
}
