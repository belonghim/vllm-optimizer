import { useState } from 'react';

interface TunerWarmupSuggestionsProps {
  configurations: Record<string, unknown>[];
}

export default function TunerWarmupSuggestions({ configurations }: TunerWarmupSuggestionsProps) {
  const [expanded, setExpanded] = useState(false);

  if (!configurations || configurations.length === 0) return null;

  return (
    <div className="panel">
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: expanded ? '0.75rem' : 0 }}>
        <div className="section-title" style={{ margin: 0 }}>LLM Warmup Suggestions</div>
        <span className="tag tag-running" style={{ fontSize: '11px' }}>{configurations.length} configs</span>
        <button
          type="button"
          className="btn btn-secondary"
          style={{ marginLeft: 'auto', fontSize: '11px', padding: '2px 8px' }}
          onClick={() => setExpanded(e => !e)}
        >
          {expanded ? 'Collapse' : 'Expand'}
        </button>
      </div>
      {!expanded && (
        <div style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
          LLM pre-seeded {configurations.length} warm-start configuration{configurations.length !== 1 ? 's' : ''} to guide the Bayesian search.
        </div>
      )}
      {expanded && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
          {configurations.map((cfg, i) => (
            <div key={i} style={{ background: 'var(--bg-surface)', borderRadius: '4px', padding: '0.5rem 0.75rem' }}>
              <div style={{ fontSize: '11px', fontWeight: 600, color: 'var(--text-muted)', marginBottom: '4px' }}>
                Config {i + 1}
              </div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.75rem' }}>
                {Object.entries(cfg).map(([k, v]) => (
                  <span key={k} style={{ fontSize: '11px' }}>
                    <span style={{ color: 'var(--text-muted)' }}>{k}:</span>{' '}
                    <span style={{ color: 'var(--accent)' }}>{String(v)}</span>
                  </span>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
