import { createContext, useState, useEffect, useMemo, useContext, useCallback } from "react";
import { API } from "../constants";

const STORAGE_KEY = "vllm-opt-cluster-config";

const ClusterConfigContext = createContext({
  endpoint: "",
  namespace: "",
  inferenceservice: "",
  isLoading: true,
  updateConfig: () => {},
});

export function ClusterConfigProvider({ children }) {
  const [config, setConfig] = useState(() => {
    try {
      const stored = localStorage.getItem(STORAGE_KEY);
      if (stored) return JSON.parse(stored);
    } catch {
    }
    return { endpoint: "", namespace: "", inferenceservice: "" };
  });
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const hasStoredValues = () => {
      try {
        const stored = localStorage.getItem(STORAGE_KEY);
        if (!stored) return false;
        const parsed = JSON.parse(stored);
        return parsed.endpoint || parsed.namespace || parsed.inferenceservice;
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
          namespace: data.vllm_namespace || "",
          inferenceservice: data.vllm_is_name || "",
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
    setConfig(prev => ({ ...prev, [field]: value }));
  }, []);

  const value = useMemo(
    () => ({
      endpoint: config.endpoint,
      namespace: config.namespace,
      inferenceservice: config.inferenceservice,
      isLoading,
      updateConfig,
    }),
    [config.endpoint, config.namespace, config.inferenceservice, isLoading, updateConfig]
  );

  return (
    <ClusterConfigContext.Provider value={value}>
      {children}
    </ClusterConfigContext.Provider>
  );
}

export function useClusterConfig() {
  return useContext(ClusterConfigContext);
}
