interface TunerResourceInputsProps {
  editedValues: Record<string, unknown>;
  getResourceValue: (tier: string, key: string) => string;
  handleResourceChange: (resourceKey: string, value: string) => void;
  resourceErrors: Record<string, boolean>;
}

export default function TunerResourceInputs({
  editedValues,
  getResourceValue,
  handleResourceChange,
  resourceErrors,
}: TunerResourceInputsProps) {
  return (
    <>
      <tr>
        <td title="resources.requests.cpu">CPU Requests</td>
        <td className="td-current">
          <div>
            <input type="text" aria-label="CPU Requests"
                   value={editedValues["resources.requests.cpu"] as string ?? getResourceValue("requests", "cpu")}
                   onChange={e => handleResourceChange("resources.requests.cpu", e.target.value)}
                   placeholder="e.g. 4, 500m" />
            {resourceErrors["resources.requests.cpu"] && (
              <div style={{ color: 'red', fontSize: '12px', marginTop: '4px' }}>Invalid format</div>
            )}
          </div>
        </td>
        <td>—</td>
        <td className="td-desc">CPU request (e.g. 4, 500m)</td>
      </tr>
      <tr>
        <td title="resources.limits.cpu">CPU Limits</td>
        <td className="td-current">
          <div>
            <input type="text" aria-label="CPU Limits"
                   value={editedValues["resources.limits.cpu"] as string ?? getResourceValue("limits", "cpu")}
                   onChange={e => handleResourceChange("resources.limits.cpu", e.target.value)}
                   placeholder="e.g. 8, 1000m" />
            {resourceErrors["resources.limits.cpu"] && (
              <div style={{ color: 'red', fontSize: '12px', marginTop: '4px' }}>Invalid format</div>
            )}
          </div>
        </td>
        <td>—</td>
        <td className="td-desc">CPU limit (e.g. 8, 1000m)</td>
      </tr>
      <tr>
        <td title="resources.requests.memory">Memory Requests</td>
        <td className="td-current">
          <div>
            <input type="text" aria-label="Memory Requests"
                   value={editedValues["resources.requests.memory"] as string ?? getResourceValue("requests", "memory")}
                   onChange={e => handleResourceChange("resources.requests.memory", e.target.value)}
                   placeholder="e.g. 8Gi, 512Mi" />
            {resourceErrors["resources.requests.memory"] && (
              <div style={{ color: 'red', fontSize: '12px', marginTop: '4px' }}>Invalid format</div>
            )}
          </div>
        </td>
        <td>—</td>
        <td className="td-desc">Memory request (e.g. 8Gi, 512Mi)</td>
      </tr>
      <tr>
        <td title="resources.limits.memory">Memory Limits</td>
        <td className="td-current">
          <div>
            <input type="text" aria-label="Memory Limits"
                   value={editedValues["resources.limits.memory"] as string ?? getResourceValue("limits", "memory")}
                   onChange={e => handleResourceChange("resources.limits.memory", e.target.value)}
                   placeholder="e.g. 16Gi" />
            {resourceErrors["resources.limits.memory"] && (
              <div style={{ color: 'red', fontSize: '12px', marginTop: '4px' }}>Invalid format</div>
            )}
          </div>
        </td>
        <td>—</td>
        <td className="td-desc">Memory limit (e.g. 16Gi)</td>
      </tr>
      <tr>
        <td title="resources.limits.nvidia.com/gpu">GPU Limits</td>
        <td className="td-current">
          <div>
            <input type="number" min={0} step={1} aria-label="GPU Limits"
                   value={editedValues["resources.limits.nvidia.com/gpu"] as string ?? getResourceValue("limits", "nvidia.com/gpu")}
                   onChange={e => handleResourceChange("resources.limits.nvidia.com/gpu", e.target.value)}
                   placeholder="0" />
            {resourceErrors["resources.limits.nvidia.com/gpu"] && (
              <div style={{ color: 'red', fontSize: '12px', marginTop: '4px' }}>Invalid format</div>
            )}
          </div>
        </td>
        <td>—</td>
        <td className="td-desc">GPU count</td>
      </tr>
    </>
  );
}
