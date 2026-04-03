import { useState, useEffect } from "react";
import { useClusterConfig } from "../contexts/ClusterConfigContext";
import { authFetch } from "../utils/authFetch";
import { buildDefaultEndpoint } from "../utils/endpointUtils";
import { API } from "../constants";
import { ERROR_MESSAGES } from "../constants/errorMessages";
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
  const { endpoint, namespace, inferenceservice, isLoading, updateConfig: updateContextConfig, targets, setDefaultTarget, crType, updateCrType } = useClusterConfig();

  const [localConfig, setLocalConfig] = useState<LocalConfig>({ endpoint: "", namespace: "", inferenceservice: "" });
  const [isDirty, setIsDirty] = useState(false);
  const [isSaved, setIsSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isCrTypeUpdating, setIsCrTypeUpdating] = useState(false);
  const [configmapWarning, setConfigmapWarning] = useState(false);

  useEffect(() => {
    if (!isLoading) {
      setLocalConfig({
        endpoint: buildDefaultEndpoint(crType, namespace, inferenceservice),
        namespace,
        inferenceservice,
      });
    }
  }, [isLoading, crType, namespace, inferenceservice]);

  useEffect(() => {
    const isChanged = endpoint !== localConfig.endpoint || namespace !== localConfig.namespace || inferenceservice !== localConfig.inferenceservice;
    setIsDirty(isChanged);
    if (!isChanged) {
      setIsSaved(false);
    }
  }, [localConfig, endpoint, namespace, inferenceservice]);

  const handleInputChange = (field: keyof LocalConfig, value: string) => {
    setError(null);
    setLocalConfig(prev => {
      const next = { ...prev, [field]: value };
      if (field === 'namespace' || field === 'inferenceservice') {
        next.endpoint = buildDefaultEndpoint(crType, next.namespace, next.inferenceservice);
      }
      return next;
    });
  };

  const handleCrTypeChange = async (value: string) => {
    setError(null);
    setConfigmapWarning(false);
    setIsCrTypeUpdating(true);
    try {
      const result = await updateCrType(value);
      if (result.configmap_updated === false) {
        setConfigmapWarning(true);
        setTimeout(() => setConfigmapWarning(false), 3000);
      }
      setLocalConfig(prev => ({
        ...prev,
        endpoint: buildDefaultEndpoint(value, prev.namespace, prev.inferenceservice),
      }));
    } catch (err) {
       const msg = err instanceof Error ? err.message : String(err);
       if (msg.includes('409') || msg.toLowerCase().includes('auto-tuner')) {
         setError(ERROR_MESSAGES.CLUSTER_CONFIG.AUTO_TUNER_RUNNING);
       } else {
         setError(ERROR_MESSAGES.CLUSTER_CONFIG.CR_TYPE_UPDATE_FAILED);
       }
     } finally {
      setIsCrTypeUpdating(false);
    }
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
        (t, i) => i > 0 &&
          t.namespace === localConfig.namespace &&
          t.inferenceService === localConfig.inferenceservice
      );
      if (matchingNonDefault) {
        setDefaultTarget(localConfig.namespace, localConfig.inferenceservice, matchingNonDefault.crType || "inferenceservice");
      } else {
        updateContextConfig('namespace', localConfig.namespace);
        updateContextConfig('inferenceservice', localConfig.inferenceservice);
      }
      setIsSaved(true);
      setTimeout(() => setIsSaved(false), 2000);
      } catch {
        setError(ERROR_MESSAGES.CLUSTER_CONFIG.SAVE_FAILED);
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
          <div className="skeleton-input" />
          <div className="skeleton-button" />
        </div>
      </div>
    );
  }

  return (
    <div className="cluster-config-bar panel">
       <ErrorAlert message={error} className="mb-3" />
      {configmapWarning && (
        <div className="alert alert-warning mb-3">
          {ERROR_MESSAGES.CLUSTER_CONFIG.CONFIGMAP_WARNING}
        </div>
      )}
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
         <div>
           <label htmlFor="cfg-cr-type">Default CR Type</label>
           <select
            id="cfg-cr-type"
            className="input"
            value={crType}
            disabled={isCrTypeUpdating}
            onChange={(e) => handleCrTypeChange(e.target.value)}
          >
            <option value="inferenceservice">InferenceService</option>
            <option value="llminferenceservice">LLMInferenceService</option>
          </select>
        </div>
        <div className="config-actions">
           <StatusIndicator isDirty={isDirty} isSaved={isSaved} />
            <button type="button" className="btn btn-primary" onClick={handleSave} disabled={!isDirty}>
             💾 Save
           </button>
        </div>
      </div>
    </div>
  );
}
