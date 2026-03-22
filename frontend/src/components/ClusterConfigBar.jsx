import { useState, useEffect, useMemo } from "react";
import { useClusterConfig } from "../contexts/ClusterConfigContext";

export default function ClusterConfigBar() {
  const { endpoint, namespace, inferenceservice, isLoading, updateConfig: updateContextConfig } = useClusterConfig();

  const [localConfig, setLocalConfig] = useState({ endpoint: "", namespace: "", inferenceservice: "" });
  const [isDirty, setIsDirty] = useState(false);
  const [isSaved, setIsSaved] = useState(false);

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

  const handleInputChange = (field, value) => {
    setLocalConfig(prev => ({ ...prev, [field]: value }));
  };

  const handleSave = () => {
    if (!isDirty) return;
    updateContextConfig('endpoint', localConfig.endpoint);
    updateContextConfig('namespace', localConfig.namespace);
    updateContextConfig('inferenceservice', localConfig.inferenceservice);
    setIsSaved(true);
    setTimeout(() => setIsSaved(false), 2000);
  };

  const StatusIndicator = useMemo(() => {
    if (isSaved) {
      return <span className="config-status saved">✓ Saved</span>;
    }
    if (isDirty) {
      return <span className="config-status dirty">⚠ Unsaved</span>;
    }
    return null;
  }, [isDirty, isSaved]);

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
          {StatusIndicator}
          <button className="btn btn-primary" onClick={handleSave} disabled={!isDirty}>
            💾 Save
          </button>
        </div>
      </div>
    </div>
  );
}
