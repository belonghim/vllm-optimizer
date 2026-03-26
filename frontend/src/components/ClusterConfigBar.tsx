import { useState, useEffect } from "react";
import { useClusterConfig } from "../contexts/ClusterConfigContext";
import { authFetch } from "../utils/authFetch";
import { API } from "../constants";
import ErrorAlert from "./ErrorAlert";

interface StatusIndicatorProps {
  isDirty: boolean;
  isSaved: boolean;
}

function StatusIndicator({ isDirty, isSaved }: StatusIndicatorProps) {
  if (isSaved) {
    return <span className="config-status saved">✓ Saved</span>;
  }
  if (isDirty) {
    return <span className="config-status dirty">⚠ Unsaved</span>;
  }
  return null;
}

interface LocalConfig {
  endpoint: string;
  namespace: string;
  inferenceservice: string;
}

export default function ClusterConfigBar() {
  const { endpoint, namespace, inferenceservice, isLoading, updateConfig: updateContextConfig, targets, setDefaultTarget } = useClusterConfig();

  const [localConfig, setLocalConfig] = useState<LocalConfig>({ endpoint: "", namespace: "", inferenceservice: "" });
  const [isDirty, setIsDirty] = useState(false);
  const [isSaved, setIsSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!isLoading) {
      setLocalConfig({ endpoint, namespace, inferenceservice });
    }
  }, [isLoading, endpoint, namespace, inferenceservice]);

  useEffect(() => {
    const isChanged = endpoint !== localConfig.endpoint || namespace !== localConfig.namespace || inferenceservice !== localConfig.inferenceservice;
    setIsDirty(isChanged);
    if (!isChanged) {
      setIsSaved(false);
    }
  }, [localConfig, endpoint, namespace, inferenceservice]);

  const handleInputChange = (field: keyof LocalConfig, value: string) => {
    setError(null);
    setLocalConfig(prev => ({ ...prev, [field]: value }));
  };

  const handleSave = async () => {
    if (!isDirty) return;
    setError(null);
    
    try {
      await authFetch(`${API}/config`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          vllm_endpoint: localConfig.endpoint,
          vllm_namespace: localConfig.namespace,
          vllm_is_name: localConfig.inferenceservice,
        }),
      });
        updateContextConfig('endpoint', localConfig.endpoint);

      const matchingNonDefault = targets.find(
        t => !t.isDefault &&
          t.namespace === localConfig.namespace &&
          t.inferenceService === localConfig.inferenceservice
      );
      if (matchingNonDefault) {
        setDefaultTarget(localConfig.namespace, localConfig.inferenceservice);
      } else {
        updateContextConfig('namespace', localConfig.namespace);
        updateContextConfig('inferenceservice', localConfig.inferenceservice);
      }
      setIsSaved(true);
      setTimeout(() => setIsSaved(false), 2000);
    } catch (err) {
      console.warn('[ClusterConfig] backend sync failed:', err);
      setError("설정 저장에 실패했습니다.");
      setIsSaved(false);
    }
  };

  if (isLoading) {
    return (
      <div className="cluster-config-bar panel loading">
        <div className="grid-form grid-form-compact">
          <div className="skeleton-input" />
          <div className="skeleton-input" />
          <div className="skeleton-input" />
          <div className="skeleton-button" />
        </div>
      </div>
    );
  }

  return (
    <div className="cluster-config-bar panel">
       <ErrorAlert message={error} className="mb-3" />
      <div className="grid-form grid-form-compact">
        <div>
          <label htmlFor="cfg-endpoint">vLLM Endpoint</label>
          <input id="cfg-endpoint" type="text" className="input" value={localConfig.endpoint} onChange={(e) => handleInputChange('endpoint', e.target.value)} placeholder="e.g., http://localhost:8001" />
        </div>
        <div>
          <label htmlFor="cfg-namespace">Namespace</label>
          <input id="cfg-namespace" type="text" className="input" value={localConfig.namespace} onChange={(e) => handleInputChange('namespace', e.target.value)} placeholder="e.g., vllm" />
        </div>
        <div>
          <label htmlFor="cfg-inferenceservice">InferenceService</label>
          <input id="cfg-inferenceservice" type="text" className="input" value={localConfig.inferenceservice} onChange={(e) => handleInputChange('inferenceservice', e.target.value)} placeholder="e.g., llm-ov" />
        </div>
        <div className="config-actions">
           <StatusIndicator isDirty={isDirty} isSaved={isSaved} />
           <button className="btn btn-primary" onClick={handleSave} disabled={!isDirty}>
            💾 Save
          </button>
        </div>
      </div>
    </div>
  );
}
