import { createContext, useState, useEffect, useMemo, useContext, useCallback } from "react";
import { API } from "../constants";

const STORAGE_KEY = "vllm-opt-cluster-config";
const MAX_TARGETS = 5;

const ClusterConfigContext = createContext({
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

function migrateLegacyConfig(stored) {
  if (stored.namespace && (!stored.targets || stored.targets.length === 0)) {
    const { namespace, inferenceservice, ...rest } = stored;
    return {
      ...rest,
      targets: [{
        namespace,
        inferenceService: inferenceservice || "",
        isDefault: true,
      }],
    };
  }
  const { namespace: _ns, inferenceservice: _is, ...rest } = stored;
  return { ...rest, targets: stored.targets || [] };
}

export function ClusterConfigProvider({ children }) {
  const [config, setConfig] = useState(() => {
    try {
      const stored = localStorage.getItem(STORAGE_KEY);
      if (stored) {
        const parsed = JSON.parse(stored);
        return migrateLegacyConfig(parsed);
      }
    } catch {
      /* localStorage unavailable */
    }
    return {
      endpoint: "",
      targets: [],
      maxTargets: MAX_TARGETS,
    };
  });
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const hasStoredValues = () => {
      try {
        const stored = localStorage.getItem(STORAGE_KEY);
        if (!stored) return false;
        const parsed = JSON.parse(stored);
        return parsed.endpoint || (parsed.targets && parsed.targets.length > 0);
      } catch {
        return false;
      }
    };

    if (hasStoredValues()) {
      setIsLoading(false);
      return;
    }

    fetch(`${API}/config`)
      .then(r => r.json())
      .then(data => {
        const apiConfig = {
          endpoint: data.vllm_endpoint || "",
          targets: data.vllm_namespace ? [{
            namespace: data.vllm_namespace,
            inferenceService: data.vllm_is_name || "",
            isDefault: true,
          }] : [],
          maxTargets: MAX_TARGETS,
        };
        setConfig(apiConfig);
        localStorage.setItem(STORAGE_KEY, JSON.stringify(apiConfig));
      })
      .catch(() => {})
      .finally(() => setIsLoading(false));
  }, []);

  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(config));
  }, [config]);

  const updateConfig = useCallback((field, value) => {
    setConfig(prev => {
      if (field === 'endpoint') {
        return { ...prev, endpoint: value };
      }

      if (field === 'namespace' || field === 'inferenceservice') {
        const targets = prev.targets.length > 0
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

  const addTarget = useCallback((namespace, inferenceService) => {
    setConfig(prev => {
      const currentTargets = prev.targets;
      if (currentTargets.length >= MAX_TARGETS) return prev;

      const newTarget = {
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

  const removeTarget = useCallback((namespace, inferenceService) => {
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

  const setDefaultTarget = useCallback((namespace, inferenceService) => {
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

  const value = useMemo(() => {
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

export function useClusterConfig() {
  return useContext(ClusterConfigContext);
}
