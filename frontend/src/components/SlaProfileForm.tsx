import { FormEvent } from "react";
import { ERROR_MESSAGES } from "../constants/errorMessages";

export interface SlaFormState {
  name: string;
  availMin: string;
  p95Ms: string;
  errRate: string;
  minTps: string;
}

interface SlaProfileFormProps {
  formState: SlaFormState;
  onChange: (field: keyof SlaFormState, value: string) => void;
  onSubmit: (e: FormEvent<HTMLFormElement>) => void;
  onCancel: () => void;
  editingId: number | null;
}

export default function SlaProfileForm({ formState, onChange, onSubmit, onCancel, editingId }: SlaProfileFormProps) {
  const { name, availMin, p95Ms, errRate, minTps } = formState;
  return (
    <div className="panel">
      <div className="section-title">{editingId ? ERROR_MESSAGES.SLA.EDIT_TITLE : ERROR_MESSAGES.SLA.CREATE_TITLE}</div>
      <form onSubmit={onSubmit} className="form-grid" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '16px', marginBottom: '24px' }}>
        <div className="form-group">
          <label>Profile Name *</label>
          <input type="text" value={name} onChange={e => onChange('name', e.target.value)} required placeholder="e.g. Llama3 Production SLA" />
        </div>
        <div className="form-group">
          <label>Min Availability (%)</label>
          <input type="number" min="0" max="100" step="0.1" value={availMin} onChange={e => onChange('availMin', e.target.value)} placeholder="99.9" />
        </div>
        <div className="form-group">
          <label>Max P95 Latency (ms)</label>
          <input type="number" min="0" step="1" value={p95Ms} onChange={e => onChange('p95Ms', e.target.value)} placeholder="500" />
        </div>
        <div className="form-group">
          <label>Max Error Rate (%)</label>
          <input type="number" min="0" max="100" step="0.1" value={errRate} onChange={e => onChange('errRate', e.target.value)} placeholder="1.0" />
        </div>
        <div className="form-group">
          <label>Min TPS</label>
          <input type="number" min="0" step="0.1" value={minTps} onChange={e => onChange('minTps', e.target.value)} placeholder="10.0" />
        </div>
        <div className="form-actions" style={{ gridColumn: '1 / -1', display: 'flex', gap: '8px', justifyContent: 'flex-end' }}>
          {editingId && <button type="button" className="btn-secondary" onClick={onCancel}>Cancel</button>}
          <button type="submit" className="btn-primary">{editingId ? 'Save' : 'Create Profile'}</button>
        </div>
      </form>
    </div>
  );
}
