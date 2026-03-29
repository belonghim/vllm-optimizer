import { memo } from "react";

interface LoadTestPresetSelectorProps {
  presetNames: string[];
  selectedPreset: string;
  onSelect: (name: string) => void;
  onSave: () => void;
  onDelete: () => void;
  canDelete: boolean;
}

const LoadTestPresetSelector = memo(function LoadTestPresetSelector({ presetNames, selectedPreset, onSelect, onSave, onDelete, canDelete }: LoadTestPresetSelectorProps) {
  return (
    <div style={{ marginBottom: "16px" }}>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: "8px", alignItems: "flex-end" }}>
        <div>
          <label className="label" htmlFor="ltc-preset">Preset</label>
          <select
            id="ltc-preset"
            className="input"
            value={selectedPreset}
            onChange={e => onSelect(e.target.value)}
          >
            <option value="">-- Select --</option>
            {presetNames.map(name => (
              <option key={name} value={name}>{name}</option>
            ))}
          </select>
        </div>
        <button type="button" className="btn btn-primary" onClick={onSave} style={{ height: "36px" }}>
          💾 Save
        </button>
        <button type="button" className="btn btn-danger" onClick={onDelete} disabled={!canDelete} style={{ height: "36px" }}>
          🗑 Delete
        </button>
      </div>
    </div>
  );
});

export default LoadTestPresetSelector;
