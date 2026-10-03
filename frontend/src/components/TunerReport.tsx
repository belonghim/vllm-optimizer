import { useState } from 'react';
import { renderMarkdown } from '../utils/renderMarkdown';

interface TunerReportProps {
  markdown: string;
  summary?: Record<string, unknown>;
}

export default function TunerReport({ markdown, summary }: TunerReportProps) {
  const [collapsed, setCollapsed] = useState(false);

  return (
    <div className="panel">
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '0.5rem',
          marginBottom: collapsed ? 0 : '0.75rem',
        }}
      >
        <div className="section-title" style={{ margin: 0 }}>
          Tuning Report
        </div>
        <button
          type="button"
          className="btn btn-secondary"
          style={{ marginLeft: 'auto', fontSize: '11px', padding: '2px 8px' }}
          onClick={() => setCollapsed((c) => !c)}
        >
          {collapsed ? 'Show' : 'Hide'}
        </button>
      </div>
      {!collapsed && (
        <>
          {summary && Object.keys(summary).length > 0 && (
            <div
              style={{
                display: 'flex',
                gap: '1rem',
                flexWrap: 'wrap',
                marginBottom: '0.75rem',
                paddingBottom: '0.75rem',
                borderBottom: '1px solid var(--border)',
              }}
            >
              {Object.entries(summary).map(([k, v]) => (
                <span key={k} style={{ fontSize: '12px' }}>
                  <span style={{ color: 'var(--text-muted)' }}>{k}:</span> <span>{String(v)}</span>
                </span>
              ))}
            </div>
          )}
          <div>{renderMarkdown(markdown)}</div>
        </>
      )}
    </div>
  );
}
