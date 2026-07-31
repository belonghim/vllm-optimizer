import { useState } from 'react';

interface TunerReportProps {
  markdown: string;
  summary?: Record<string, unknown>;
}

function renderMarkdown(md: string) {
  return md.split('\n').map((line, i) => {
    if (line.startsWith('### ')) return <h4 key={i} style={{ margin: '0.75rem 0 0.25rem', fontSize: '13px', fontWeight: 700 }}>{line.slice(4)}</h4>;
    if (line.startsWith('## ')) return <h3 key={i} style={{ margin: '0.75rem 0 0.25rem', fontSize: '14px', fontWeight: 700 }}>{line.slice(3)}</h3>;
    if (line.startsWith('# ')) return <h2 key={i} style={{ margin: '0.5rem 0 0.5rem', fontSize: '15px', fontWeight: 700 }}>{line.slice(2)}</h2>;
    if (line.startsWith('- ') || line.startsWith('* ')) return <div key={i} style={{ paddingLeft: '1rem', fontSize: '12px', margin: '2px 0' }}>&bull; {line.slice(2)}</div>;
    if (line.trim() === '') return <div key={i} style={{ height: '0.4rem' }} />;
    return <p key={i} style={{ margin: '2px 0', fontSize: '12px', lineHeight: 1.6 }}>{line}</p>;
  });
}

export default function TunerReport({ markdown, summary }: TunerReportProps) {
  const [collapsed, setCollapsed] = useState(false);

  return (
    <div className="panel">
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: collapsed ? 0 : '0.75rem' }}>
        <div className="section-title" style={{ margin: 0 }}>Tuning Report</div>
        <button
          type="button"
          className="btn btn-secondary"
          style={{ marginLeft: 'auto', fontSize: '11px', padding: '2px 8px' }}
          onClick={() => setCollapsed(c => !c)}
        >
          {collapsed ? 'Show' : 'Hide'}
        </button>
      </div>
      {!collapsed && (
        <>
          {summary && Object.keys(summary).length > 0 && (
            <div style={{ display: 'flex', gap: '1rem', flexWrap: 'wrap', marginBottom: '0.75rem', paddingBottom: '0.75rem', borderBottom: '1px solid var(--border)' }}>
              {Object.entries(summary).map(([k, v]) => (
                <span key={k} style={{ fontSize: '12px' }}>
                  <span style={{ color: 'var(--text-muted)' }}>{k}:</span>{' '}
                  <span>{String(v)}</span>
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
