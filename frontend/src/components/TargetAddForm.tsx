import { useState } from "react";
import { useClusterConfig } from "../contexts/ClusterConfigContext";
import { authFetch } from "../utils/authFetch";

interface DiscoverResult {
  isvc: string[];
  llmisvc: string[];
}

interface TargetAddFormProps {
  onSuccess?: () => void;
  onCancel?: () => void;
}

export default function TargetAddForm({ onSuccess, onCancel }: TargetAddFormProps) {
  const { addTarget, crType: contextCrType } = useClusterConfig();
  const [namespace, setNamespace] = useState("");
  const [crType, setCrType] = useState(contextCrType || "inferenceservice");
  const [isDiscovering, setIsDiscovering] = useState(false);
  const [discoverError, setDiscoverError] = useState<string | null>(null);
  const [discoveredNames, setDiscoveredNames] = useState<string[] | null>(null);
  const [manualName, setManualName] = useState("");
  const [selectedName, setSelectedName] = useState("");

  const handleDiscover = async () => {
    if (!namespace) {
      setDiscoverError("Please enter a namespace");
      return;
    }

    setIsDiscovering(true);
    setDiscoverError(null);
    setDiscoveredNames(null);
    setSelectedName("");
    setManualName("");

    try {
      const response = await authFetch(`/api/metrics/discover?namespace=${namespace}`);
      if (!response.ok) {
        throw new Error("Failed to discover resources");
      }
      const data: DiscoverResult = await response.json();
      const names = crType === "llminferenceservice" ? data.llmisvc : data.isvc;
      
      if (names && names.length > 0) {
        setDiscoveredNames(names);
        setSelectedName(names[0]);
      } else {
        setDiscoveredNames([]);
      }
    } catch (err) {
      setDiscoverError(err instanceof Error ? err.message : "Discovery error");
    } finally {
      setIsDiscovering(false);
    }
  };

  const handleAdd = () => {
    const finalName = discoveredNames && discoveredNames.length > 0 ? selectedName : manualName;
    if (!namespace || !finalName) return;

    addTarget(namespace, finalName, crType);
    if (onSuccess) onSuccess();
    setNamespace("");
    setDiscoveredNames(null);
    setManualName("");
    setSelectedName("");
  };

  return (
    <div className="multi-target-add-form" style={{ padding: '16px', border: '1px solid #ddd', borderRadius: '8px', marginTop: '16px' }}>
      <div className="multi-target-input-row" style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
        <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
          <label htmlFor="namespace-input" className="sr-only">Namespace</label>
          <input
            id="namespace-input"
            className="input multi-target-input"
            placeholder="Namespace"
            value={namespace}
            onChange={(e) => setNamespace(e.target.value)}
            style={{ flex: 1 }}
          />
          <label htmlFor="cr-type-select" className="sr-only">CR Type</label>
          <select
            id="cr-type-select"
            className="input multi-target-input"
            value={crType}
            onChange={(e) => {
              setCrType(e.target.value);
              setDiscoveredNames(null);
            }}
          >
            <option value="inferenceservice">isvc (KServe)</option>
            <option value="llminferenceservice">LLMIS (llmisvc)</option>
          </select>
          <button
            type="button"
            className="btn btn-primary"
            onClick={handleDiscover}
            disabled={isDiscovering || !namespace}
          >
            {isDiscovering ? "Discovering..." : "Discover"}
          </button>
        </div>

        {discoverError && (
          <div className="multi-target-error-msg" style={{ color: 'red', fontSize: '12px' }}>
            {discoverError}
          </div>
        )}

        {discoveredNames !== null && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
            {discoveredNames.length > 0 ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                <label htmlFor="resource-select" className="text-sm font-semibold text-gray-700">Select Resource:</label>
                <select
                  id="resource-select"
                  className="input multi-target-input"
                  value={selectedName}
                  onChange={(e) => setSelectedName(e.target.value)}
                >
                  {discoveredNames.map(name => (
                    <option key={name} value={name}>{name}</option>
                  ))}
                </select>
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                <label htmlFor="manual-name-input" className="text-sm font-semibold text-gray-700">No resources found. Enter manually:</label>
                <input
                  id="manual-name-input"
                  className="input multi-target-input"
                  placeholder="InferenceService Name"
                  value={manualName}
                  onChange={(e) => setManualName(e.target.value)}
                />
              </div>
            )}
          </div>
        )}
      </div>

      <div className="multi-target-btn-row" style={{ marginTop: '16px', display: 'flex', gap: '8px', justifyContent: 'flex-end' }}>
        {onCancel && (
          <button
            type="button"
            className="btn btn-secondary"
            onClick={onCancel}
          >
            Cancel
          </button>
        )}
        <button
          type="button"
          className="btn btn-green"
          onClick={handleAdd}
          disabled={!namespace || (!selectedName && !manualName)}
        >
          Add Target
        </button>
      </div>
    </div>
  );
}
