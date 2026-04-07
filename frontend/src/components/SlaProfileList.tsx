import { COLORS } from "../constants";
import { ERROR_MESSAGES } from "../constants/errorMessages";
import type { SlaProfile, SlaThresholds } from "../types";

interface SlaProfileListProps {
  profiles: SlaProfile[];
  onEdit: (p: SlaProfile) => void;
  onDelete: (id: number) => void;
  selectedProfileId: number | null;
  onSelect: (id: number) => void;
  loading: boolean;
}

function renderThresholds(t: SlaThresholds): string {
  const parts: string[] = [];
  if (t.availability_min != null) parts.push(`Availability≥${t.availability_min}%`);
  if (t.p95_latency_max_ms != null) parts.push(`P95≤${t.p95_latency_max_ms}ms`);
  if (t.error_rate_max_pct != null) parts.push(`Error Rate≤${t.error_rate_max_pct}%`);
  if (t.min_tps != null) parts.push(`TPS≥${t.min_tps}`);
  if (t.mean_ttft_max_ms != null) parts.push(`TTFT Mean≤${t.mean_ttft_max_ms}ms`);
  if (t.p95_ttft_max_ms != null) parts.push(`TTFT P95≤${t.p95_ttft_max_ms}ms`);
  return parts.join(' · ') || ERROR_MESSAGES.SLA.NO_THRESHOLDS_SET;
}

export default function SlaProfileList({ profiles, onEdit, onDelete, selectedProfileId, onSelect, loading }: SlaProfileListProps) {
  return (
    <div className="panel">
      <div className="section-title">SLA Profile List</div>
      {loading ? (
        <div style={{ textAlign: 'center', padding: '40px', color: COLORS.muted }}>Loading...</div>
      ) : (
        <table className="table">
          <thead>
            <tr>
              <th style={{ width: '40px' }}></th>
              <th>Name</th>
              <th>Threshold Summary</th>
              <th style={{ textAlign: 'right' }}>Actions</th>
            </tr>
          </thead>
          <tbody>
            {profiles.map(p => (
              <tr key={p.id}>
                <td>
                  <input
                    type="radio"
                    name="sla-profile"
                    checked={selectedProfileId === p.id}
                    onChange={() => onSelect(p.id)}
                    style={{ cursor: 'pointer', accentColor: COLORS.cyan }}
                  />
                </td>
                <td className="td-text">{p.name}</td>
                <td className="td-muted" style={{ fontSize: '0.85rem' }}>{renderThresholds(p.thresholds)}</td>
                <td style={{ textAlign: 'right' }}>
                  <button className="btn-small" onClick={() => onEdit(p)} style={{ marginRight: '8px' }}>Edit</button>
                  <button className="btn-outline-small" onClick={() => onDelete(p.id)} style={{ color: COLORS.red, borderColor: COLORS.red }}>Delete</button>
                </td>
              </tr>
            ))}
            {profiles.length === 0 && (
              <tr><td colSpan={4} className="td-muted" style={{ textAlign: 'center', padding: '20px' }}>{ERROR_MESSAGES.SLA.NO_PROFILES}</td></tr>
            )}
          </tbody>
        </table>
      )}
    </div>
  );
}
