import { useState } from 'react';
import ErrorAlert from './ErrorAlert';
import type { ServingAdvice, ServingRecommendation } from '../types';

interface TunerServingAdviceProps {
  advice: ServingAdvice | null | undefined;
}

const KIND_LABELS: Record<ServingRecommendation['kind'], string> = {
  required: 'required',
  workload: 'workload',
  avoid: 'avoid',
};

const STATUS_LABELS: Record<ServingRecommendation['status'], string> = {
  present: 'present',
  missing: 'missing',
  mismatch: 'mismatch',
};

function statusColor(rec: ServingRecommendation): string {
  if (rec.kind === 'avoid') return 'var(--red-color)';
  return rec.status === 'present' ? 'var(--green-color)' : 'var(--accent-color)';
}

export default function TunerServingAdvice({ advice }: TunerServingAdviceProps) {
  const [copied, setCopied] = useState(false);

  if (!advice || advice.recommendations.length === 0) return null;

  const copyAddArgs = async () => {
    if (!advice.add_args) return;
    try {
      if (!navigator.clipboard?.writeText) return;
      await navigator.clipboard.writeText(advice.add_args);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      // Clipboard unavailable (e.g. insecure context) — the args stay selectable as text.
    }
  };

  return (
    <div data-testid="tma-serving-advice" style={{ marginBottom: '0.75rem' }}>
      <div className="section-title" style={{ marginBottom: '0.5rem' }}>
        Serving arguments
      </div>
      <table className="table" aria-label="Serving arguments">
        <thead>
          <tr>
            <th>Flag / value</th>
            <th>Kind</th>
            <th>Status</th>
            <th>Why</th>
          </tr>
        </thead>
        <tbody>
          {advice.recommendations.map((rec, index) => {
            const showCurrent =
              rec.current != null && (rec.status === 'mismatch' || rec.kind === 'avoid');
            return (
              <tr
                key={`${rec.flag}-${index}`}
                style={
                  rec.kind === 'avoid' ? { background: 'var(--red-rgb-alpha-0-05)' } : undefined
                }
              >
                <td style={{ fontFamily: 'var(--font-mono)' }}>
                  {rec.flag}
                  {rec.value != null && (
                    <span style={{ color: 'var(--muted-color)' }}> {rec.value}</span>
                  )}
                </td>
                <td style={{ color: rec.kind === 'avoid' ? 'var(--red-color)' : undefined }}>
                  {KIND_LABELS[rec.kind]}
                </td>
                <td style={{ color: statusColor(rec) }}>{STATUS_LABELS[rec.status]}</td>
                <td>
                  {rec.reason}
                  {showCurrent && (
                    <div style={{ color: 'var(--red-color)', fontSize: '10px' }}>
                      current: {rec.current}
                    </div>
                  )}
                  {rec.evidence && (
                    <div
                      style={{ color: 'var(--muted-color)', fontSize: '10px' }}
                      title={rec.evidence}
                    >
                      {rec.evidence}
                    </div>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>

      {advice.add_args && (
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            flexWrap: 'wrap',
            fontSize: '11px',
            marginTop: '0.5rem',
          }}
        >
          <span style={{ color: 'var(--muted-color)' }}>
            Add to VLLM_ADDITIONAL_ARGS / predictor args:
          </span>
          <code data-testid="tma-add-args" style={{ color: 'var(--accent-color)' }}>
            {advice.add_args}
          </code>
          <button
            type="button"
            className="btn btn-secondary"
            style={{ fontSize: '11px', padding: '2px 8px' }}
            onClick={() => void copyAddArgs()}
          >
            {copied ? 'Copied' : 'Copy'}
          </button>
        </div>
      )}

      {advice.notes.map((note, index) =>
        note.level === 'warning' ? (
          <ErrorAlert key={`${note.level}-${index}`} message={note.text} severity="warning" />
        ) : (
          <div
            key={`${note.level}-${index}`}
            style={{ fontSize: '11px', color: 'var(--muted-color)', marginTop: '4px' }}
          >
            {note.text}
          </div>
        )
      )}
    </div>
  );
}
