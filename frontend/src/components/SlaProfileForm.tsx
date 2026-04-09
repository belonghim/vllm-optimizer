import { FormEvent } from "react";
import { ERROR_MESSAGES } from "../constants/errorMessages";

export interface SlaFormState {
  name: string;
  availMin: string;
  p95Ms: string;
  errRate: string;
  meanTtftMs: string;
  p95TtftMs: string;
  meanE2eLatencyMs: string;
  meanTpotMs: string;
  p95TpotMs: string;
  meanQueueTimeMs: string;
  p95QueueTimeMs: string;
}

interface SlaProfileFormProps {
  formState: SlaFormState;
  onChange: (field: keyof SlaFormState, value: string) => void;
  onSubmit: (e: FormEvent<HTMLFormElement>) => void;
  onCancel: () => void;
  editingId: number | null;
}

export default function SlaProfileForm({ formState, onChange, onSubmit, onCancel, editingId }: SlaProfileFormProps) {
  const { name, availMin, p95Ms, errRate, meanTtftMs, p95TtftMs, meanE2eLatencyMs, meanTpotMs, p95TpotMs, meanQueueTimeMs, p95QueueTimeMs } = formState;
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
          <label>TTFT Mean (ms)</label>
          <input type="number" min="0" step="1" value={meanTtftMs} onChange={e => onChange('meanTtftMs', e.target.value)} placeholder="1000" />
        </div>
        <div className="form-group">
          <label>TTFT P95 (ms)</label>
          <input type="number" min="0" step="1" value={p95TtftMs} onChange={e => onChange('p95TtftMs', e.target.value)} placeholder="2000" />
        </div>
        <div className="form-group">
          <label>Mean E2E Latency (ms)</label>
          <input type="number" min="0" step="1" value={meanE2eLatencyMs} onChange={e => onChange('meanE2eLatencyMs', e.target.value)} placeholder="500" />
        </div>
        <div className="form-group">
          <label>TPOT Mean (ms)</label>
          <input type="number" min="0" step="0.1" value={meanTpotMs} onChange={e => onChange('meanTpotMs', e.target.value)} placeholder="50" />
        </div>
        <div className="form-group">
          <label>TPOT P95 (ms)</label>
          <input type="number" min="0" step="0.1" value={p95TpotMs} onChange={e => onChange('p95TpotMs', e.target.value)} placeholder="100" />
        </div>
        <div className="form-group">
          <label>Queue Time Mean (ms)</label>
          <input type="number" min="0" step="1" value={meanQueueTimeMs} onChange={e => onChange('meanQueueTimeMs', e.target.value)} placeholder="100" />
        </div>
        <div className="form-group">
          <label>Queue Time P95 (ms)</label>
          <input type="number" min="0" step="1" value={p95QueueTimeMs} onChange={e => onChange('p95QueueTimeMs', e.target.value)} placeholder="500" />
        </div>
        <div className="form-actions" style={{ gridColumn: '1 / -1', display: 'flex', gap: '8px', justifyContent: 'flex-end' }}>
          {editingId && <button type="button" className="btn-secondary" onClick={onCancel}>Cancel</button>}
          <button type="submit" className="btn-primary">{editingId ? 'Save' : 'Create Profile'}</button>
        </div>
      </form>
    </div>
  );
}
