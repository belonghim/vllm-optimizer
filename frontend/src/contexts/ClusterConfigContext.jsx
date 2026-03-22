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
    stored.targets = [{
      namespace: stored.namespace,
      inferenceService: stored.inferenceservice || "",
      isDefault: true,
    }];
  }
  delete stored.namespace;
  delete stored.inferenceservice;
  return stored;
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

        targets[0] = {
          ...targets[0],
          [field === 'inferenceservice' ? 'inferenceService' : field]: value,
        };
        return { ...prev, targets };
      }
      return prev;
    });
  }, []);

  const addTarget = useCallback((namespace, inferenceService) => {
    setConfig(prev => {
      const currentTargets = prev.targets || [];
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

  const removeTarget = useCallback((index) => {
    setConfig(prev => {
      const currentTargets = prev.targets || [];
      const target = currentTargets[index];

      if (target && target.isDefault) return prev;

      const newTargets = currentTargets.filter((_, i) => i !== index);

      if (target && target.isDefault && newTargets.length > 0) {
        newTargets[0] = { ...newTargets[0], isDefault: true };
      }

      return {
        ...prev,
        targets: newTargets,
      };
    });
  }, []);

  const setDefaultTarget = useCallback((index) => {
    setConfig(prev => {
      const currentTargets = prev.targets || [];
      if (index < 0 || index >= currentTargets.length) return prev;

      const newTargets = currentTargets.map((t, i) => ({
        ...t,
        isDefault: i === index,
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
      targets: config.targets || [],
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
