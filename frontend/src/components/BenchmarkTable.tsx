import { Fragment } from "react";
import { useThemeColors } from "../contexts/ThemeContext";
import { fmt } from "../utils/format";
import { calcGpuEfficiency } from "../utils/metrics";
import { CHART_LABELS } from "../constants";
import type { BenchmarkItem, BenchmarkRunConfig } from "../pages/BenchmarkPage";

interface BenchmarkTableProps {
  benchmarks: BenchmarkItem[];
  selected: (string | number)[];
  expanded: (string | number)[];
  loading: boolean;
  importing: boolean;
  importInputRef: React.RefObject<HTMLInputElement | null>;
  onToggleSelect: (id: string | number, e: React.MouseEvent) => void;
  onToggleExpand: (id: string | number) => void;
  onDelete: (b: BenchmarkItem, e: React.MouseEvent) => void;
  onEdit: (b: BenchmarkItem) => void;
  onExportJSON: () => void;
  onExportCSV: () => void;
  onImport: (e: React.ChangeEvent<HTMLInputElement>) => void;
  onBulkDelete: () => void;
  onRerun?: (config: BenchmarkRunConfig) => void;
}

export default function BenchmarkTable({
  benchmarks, selected, expanded, loading, importing, importInputRef,
  onToggleSelect, onToggleExpand, onDelete, onEdit,
  onExportJSON, onExportCSV, onImport, onBulkDelete, onRerun,
}: BenchmarkTableProps) {
  const { COLORS } = useThemeColors();

  return (
    <div className="panel">
      <div className="section-title">Saved Benchmarks</div>
      {loading ? (
        <div style={{ textAlign: 'center', padding: '40px', color: COLORS.muted }}>Loading...</div>
      ) : (
        <>
          <div style={{ marginBottom: '16px', display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
            <button className="btn-primary" disabled={benchmarks.length === 0} onClick={onExportJSON}>Export JSON</button>
            <button className="btn-primary" disabled={benchmarks.length === 0} onClick={onExportCSV}>Export CSV</button>
            <button className="btn-outline" disabled={importing} onClick={() => importInputRef.current?.click()}>
              {importing ? "Importing..." : "Import GuideLLM Results"}
            </button>
            <input
              ref={importInputRef}
              type="file"
              accept=".json"
              style={{ display: 'none' }}
              onChange={onImport}
            />
            <button className="btn-danger" disabled={selected.length === 0} onClick={onBulkDelete}>Delete Selected ({selected.length})</button>
          </div>
          <table className="table" aria-label="Saved benchmark list">
            <thead>
              <tr>
                <th></th>
                <th>Name</th>
                <th>Model ID</th>
                <th>Config Model</th>
                <th>Date</th>
                <th>TPS</th>
                <th>{CHART_LABELS.e2eLatency.p99}</th>
                <th>RPS</th>
                <th>GPU Eff.</th>
                <th>Delete</th>
              </tr>
            </thead>
            <tbody>
              {benchmarks.map(b => {
                const eff = calcGpuEfficiency(b.result);
                const isSelected = selected.includes(b.id);
                const isExpanded = expanded.includes(b.id);
                return (
                  <Fragment key={b.id}>
                    <tr
                      onClick={() => onToggleExpand(b.id)}
                      className={`benchmark-row ${isSelected ? 'benchmark-row--selected' : ''} ${isExpanded ? 'benchmark-row--expanded' : ''}`}
                    >
                      <td 
                        onClick={(e) => onToggleSelect(b.id, e)}
                        onKeyDown={(e) => {
                          if (e.key === " " || e.key === "Enter") {
                            e.preventDefault();
                            onToggleSelect(b.id, e as unknown as React.MouseEvent);
                          }
                        }}
                        tabIndex={0}
                      >
                        <input type="checkbox" checked={isSelected} readOnly aria-label={`Select benchmark ${b.name}`} />
                      </td>
                      <td className="td-text">
                        {b.name}
                        {b.metadata?.source === "guidellm" && (
                          <span style={{ marginLeft: '6px', fontSize: '11px', padding: '1px 6px', borderRadius: '3px', background: 'var(--info-color)', color: '#fff', verticalAlign: 'middle' }}>
                            GuideLLM
                          </span>
                        )}
                      </td>
                      <td className="td-cyan">{b.metadata?.model_identifier || "—"}</td>
                      <td className="td-muted">{b.config?.model || "—"}</td>
                      <td className="td-muted">{new Date(b.timestamp * 1000).toLocaleString()}</td>
                      <td className="td-accent">{fmt(b.result?.tps?.mean, 1)}</td>
                      <td className="td-red">{fmt((b.result?.latency?.p99 || 0) * 1000, 0)}</td>
                      <td>{fmt(b.result?.rps_actual, 1)}</td>
                      <td className="td-green">
                        {eff.mismatch ? <span title="GPU metrics mismatch">N/A</span> : eff.display || "—"}
                      </td>
                      <td>
                        <button className="btn-icon" aria-label="Delete benchmark" onClick={(e) => onDelete(b, e)}>✕</button>
                      </td>
                    </tr>
                    {isExpanded && (
                      <tr className="expanded-row">
                        <td colSpan={10}>
                          <div className="metadata-detail">
                            <div className="metadata-grid">
                              <div className="metadata-item">
                                <span className="label">Model ID:</span>
                                <span className="value">{b.metadata?.model_identifier || "—"}</span>
                              </div>
                              <div className="metadata-item">
                                <span className="label">Hardware:</span>
                                <span className="value">{b.metadata?.hardware_type || "—"}</span>
                              </div>
                              <div className="metadata-item">
                                <span className="label">Runtime:</span>
                                <span className="value">{b.metadata?.runtime || "—"}</span>
                              </div>
                              <div className="metadata-item">
                                <span className="label">vLLM Version:</span>
                                <span className="value">{b.metadata?.vllm_version || "—"}</span>
                              </div>
                              <div className="metadata-item">
                                <span className="label">Replicas:</span>
                                <span className="value">{b.metadata?.replica_count || "—"}</span>
                              </div>
                              <div className="metadata-item full-width">
                                <span className="label">Notes:</span>
                                <span className="value">{b.metadata?.notes || "—"}</span>
                              </div>
                              {b.metadata?.extra && Object.entries(b.metadata.extra).length > 0 && (
                                <div className="metadata-item full-width">
                                  <span className="label">Extra Info:</span>
                                  <div className="extra-tags">
                                    {Object.entries(b.metadata.extra).map(([k, v]) => (
                                      <span key={k} className="tag">{k}: {v}</span>
                                    ))}
                                  </div>
                                </div>
                              )}
                            </div>
                            <div className="metadata-actions">
                              <button className="btn-small" onClick={() => onEdit(b)}>Edit</button>
                              {b.config && onRerun && (
                                <button
                                  className="btn-small"
                                  onClick={(e) => { e.stopPropagation(); onRerun(b.config!); }}
                                  aria-label="Rerun load test with this config"
                                >
                                  ▶ Rerun
                                </button>
                              )}
                            </div>
                          </div>
                        </td>
                      </tr>
                    )}
                  </Fragment>
                );
              })}
              {benchmarks.length === 0 && (
                <tr><td colSpan={10} className="benchmark-empty">
                  Saved load test results will appear here.
                </td></tr>
              )}
            </tbody>
          </table>
        </>
      )}
    </div>
  );
}
