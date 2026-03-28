import { useState } from "react";
import type { BenchmarkItem, BenchmarkMetadata } from "../pages/BenchmarkPage";

interface BenchmarkMetadataModalProps {
  editing: BenchmarkItem;
  onClose: () => void;
  onSave: (id: string | number, metadata: BenchmarkMetadata) => void;
}

export default function BenchmarkMetadataModal({ editing, onClose, onSave }: BenchmarkMetadataModalProps) {
  const [meta, setMeta] = useState<BenchmarkMetadata>(editing.metadata || {});

  const updateField = (field: keyof BenchmarkMetadata, value: string | number | boolean | null) =>
    setMeta(prev => ({ ...prev, [field]: value }));

  const updateExtra = (key: string, value: string, oldKey?: string) => {
    const extra = { ...(meta.extra || {}) };
    if (oldKey && oldKey !== key) delete extra[oldKey];
    extra[key] = value;
    setMeta(prev => ({ ...prev, extra }));
  };

  const removeExtra = (key: string) => {
    const extra = { ...(meta.extra || {}) };
    delete extra[key];
    setMeta(prev => ({ ...prev, extra }));
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onSave(editing.id, meta);
  };

  return (
    <div className="modal-overlay">
      <div className="modal-content">
        <div className="modal-header">
          <h3>Edit Benchmark Metadata</h3>
          <button className="btn-close" onClick={onClose}>✕</button>
        </div>
        <form onSubmit={handleSubmit} className="metadata-form">
          <div className="form-group">
            <label>Model Identifier</label>
            <input
              type="text"
              value={meta.model_identifier || ""}
              onChange={e => updateField('model_identifier', e.target.value)}
              placeholder="e.g. llama-3.1-8b-instruct"
            />
            <small className="help-text">Enter the actual model name (default is serving name small-llm-d)</small>
          </div>
          <div className="form-row">
            <div className="form-group">
              <label>Hardware Type</label>
              <input
                type="text"
                value={meta.hardware_type || ""}
                onChange={e => updateField('hardware_type', e.target.value)}
                placeholder="e.g. A100, L4, CPU"
              />
            </div>
            <div className="form-group">
              <label>Runtime</label>
              <input
                type="text"
                value={meta.runtime || ""}
                onChange={e => updateField('runtime', e.target.value)}
                placeholder="e.g. OpenVINO, CUDA"
              />
            </div>
          </div>
          <div className="form-row">
            <div className="form-group">
              <label>vLLM Version</label>
              <input
                type="text"
                value={meta.vllm_version || ""}
                onChange={e => updateField('vllm_version', e.target.value)}
                placeholder="e.g. 0.6.2"
              />
            </div>
            <div className="form-group">
              <label>Replica Count</label>
              <input
                type="number"
                value={meta.replica_count || ""}
                onChange={e => updateField('replica_count', e.target.value ? parseInt(e.target.value) : null)}
              />
            </div>
          </div>
          <div className="form-group">
            <label>Notes</label>
            <textarea
              value={meta.notes || ""}
              onChange={e => updateField('notes', e.target.value)}
              rows={3}
            />
          </div>
          <div className="form-group">
            <label>Extra Metadata (Key: Value)</label>
            <div className="extra-editor">
              {Object.entries(meta.extra || {}).map(([k, v], idx) => (
                <div key={idx} className="extra-row">
                  <input
                    type="text"
                    value={k}
                    onChange={e => updateExtra(e.target.value, v, k)}
                    placeholder="Key"
                  />
                  <input
                    type="text"
                    value={v}
                    onChange={e => updateExtra(k, e.target.value)}
                    placeholder="Value"
                  />
                  <button type="button" onClick={() => removeExtra(k)}>✕</button>
                </div>
              ))}
              <button
                type="button"
                className="btn-outline-small"
                onClick={() => updateExtra(`key_${Object.keys(meta.extra || {}).length + 1}`, "value")}
              >
                + Add Entry
              </button>
            </div>
          </div>
          <div className="form-actions">
            <button type="button" className="btn-secondary" onClick={onClose}>Cancel</button>
            <button type="submit" className="btn-primary">Save</button>
          </div>
        </form>
      </div>
    </div>
  );
}
