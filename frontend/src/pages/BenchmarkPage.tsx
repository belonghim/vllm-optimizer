import { useState, useEffect, useMemo, Fragment, useCallback, useRef } from "react";
import { authFetch } from '../utils/authFetch';
import { API, TARGET_COLORS } from "../constants";
import { useThemeColors } from "../contexts/ThemeContext";
import { fmt } from "../utils/format";
import { mockBenchmarks } from "../mockData";
import { calcGpuEfficiency } from "../utils/metrics";
import { downloadJSON, downloadCSV, benchmarksToCSV } from '../utils/export';
import { BarChart, Bar, Cell, CartesianGrid, XAxis, YAxis, Tooltip, ResponsiveContainer } from "recharts";
import { useMockData } from "../contexts/MockDataContext";
import { useBenchmarkSelection } from "../contexts/BenchmarkSelectionContext";
import ErrorAlert from "../components/ErrorAlert";

interface BenchmarkMetadata {
  model_identifier?: string | null;
  hardware_type?: string | null;
  runtime?: string | null;
  vllm_version?: string | null;
  replica_count?: number | null;
  notes?: string | null;
  extra?: Record<string, string>;
  source?: string | null;
}

interface BenchmarkRunConfig {
  model?: string;
  [key: string]: unknown;
}

interface BenchmarkResultData {
  tps?: { mean?: number } | null;
  latency?: { p99?: number } | null;
  ttft?: { mean?: number } | null;
  rps_actual?: number;
  gpu_utilization_avg?: number | null;
  metrics_target_matched?: boolean;
}

interface BenchmarkItem {
  id: string | number;
  name: string;
  timestamp: number;
  config?: BenchmarkRunConfig;
  result: BenchmarkResultData;
  metadata?: BenchmarkMetadata | null;
}

interface BenchmarkPageProps {
  isActive: boolean;
  onRerun?: (config: BenchmarkRunConfig) => void;
}

function BenchmarkPage({ isActive, onRerun }: BenchmarkPageProps) {
  const { COLORS, TOOLTIP_STYLE } = useThemeColors();
  const [benchmarks, setBenchmarks] = useState<BenchmarkItem[]>([]);
  const { selectedIds: selected, setSelectedIds: setSelected } = useBenchmarkSelection();
  const [expanded, setExpanded] = useState<(string | number)[]>([]);
  const [editing, setEditing] = useState<BenchmarkItem | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const { isMockEnabled } = useMockData();
  const [importing, setImporting] = useState(false);
  const importInputRef = useRef<HTMLInputElement>(null);

  const fetchBenchmarks = useCallback(() => {
    setLoading(true);
    if (isMockEnabled) {
      setBenchmarks(
        mockBenchmarks().map((benchmark) => ({
          ...benchmark,
          config: benchmark.config ? { ...benchmark.config } : undefined,
        }))
      );
      setError(null);
      setLoading(false);
      return () => {};
    }
    const controller = new AbortController();
    authFetch(`${API}/benchmark/list`, { signal: controller.signal })
      .then(r => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then(data => {
        setBenchmarks(data);
        setError(null);
      })
      .catch(err => {
        if (err instanceof Error && err.name === 'AbortError') return;
        setError(`Failed to fetch benchmarks: ${(err as Error).message}`);
      })
      .finally(() => {
        setLoading(false);
      });
    return () => controller.abort();
  }, [isMockEnabled]);

  useEffect(() => {
    if (isActive) {
      const cleanup = fetchBenchmarks();
      return cleanup;
    }
  }, [isActive, fetchBenchmarks]);

  const toggleSelect = (id: string | number, e: React.MouseEvent) => {
    e.stopPropagation();
    setSelected(selected.includes(id) ? selected.filter(x => x !== id) : [...selected, id]);
  };

  const toggleExpand = (id: string | number) => {
    setExpanded(s =>
      s.includes(id) ? s.filter(x => x !== id) : [...s, id]
    );
  };

  const handleDelete = async (b: BenchmarkItem, e: React.MouseEvent) => {
    e.stopPropagation();
    if (!window.confirm(`Delete benchmark '${b.name}'?`)) return;

    if (isMockEnabled) {
      setBenchmarks(prev => prev.filter(x => x.id !== b.id));
      setSelected(selected.filter(x => x !== b.id));
      setExpanded(prev => prev.filter(x => x !== b.id));
      return;
    }

    try {
      const res = await authFetch(`${API}/benchmark/${b.id}`, { method: 'DELETE' });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setSelected(selected.filter(x => x !== b.id));
      fetchBenchmarks();
    } catch (err) {
      setError(`Delete failed: ${(err as Error).message}`);
    }
  };

  const handleSaveMetadata = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!editing) return;

    const benchmarkId = editing.id;
    const metadata = editing.metadata || {};

    if (isMockEnabled) {
      setBenchmarks(prev => prev.map(b => b.id === benchmarkId ? { ...b, metadata } : b));
      setEditing(null);
      return;
    }

    try {
      const res = await authFetch(`${API}/benchmark/${benchmarkId}/metadata`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(metadata),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const updated: BenchmarkItem = await res.json();
      setBenchmarks(prev => prev.map(b => b.id === benchmarkId ? updated : b));
      setEditing(null);
    } catch (err) {
      setError(`Failed to save metadata: ${(err as Error).message}`);
    }
  };

  const updateMetadataField = (field: keyof BenchmarkMetadata, value: string | number | boolean | null) => {
    if (!editing) return;
    setEditing({
      ...editing,
      metadata: {
        ...(editing.metadata || {}),
        [field]: value
      }
    });
  };

  const updateExtra = (key: string, value: string, oldKey?: string) => {
    if (!editing) return;
    const extra = { ...(editing.metadata?.extra || {}) };
    if (oldKey && oldKey !== key) {
      delete extra[oldKey];
    }
    extra[key] = value;
    updateMetadataField('extra', extra);
  };

  const removeExtra = (key: string) => {
    if (!editing) return;
    const extra = { ...(editing.metadata?.extra || {}) };
    delete extra[key];
    updateMetadataField('extra', extra);
  };

  const handleBulkDelete = async () => {
    if (selected.length === 0) return;
    if (!window.confirm(`Delete ${selected.length} benchmark(s)?`)) return;

    if (isMockEnabled) {
      setBenchmarks(prev => prev.filter(b => !selected.includes(b.id)));
      setSelected([]);
      return;
    }

    try {
      for (const id of selected) {
        const res = await authFetch(`${API}/benchmark/${id}`, { method: 'DELETE' });
        if (!res.ok) {
          throw new Error(`HTTP ${res.status} for benchmark ID ${id}`);
        }
      }
      setSelected([]);
      fetchBenchmarks();
    } catch (err) {
      setError(`Bulk delete failed: ${(err as Error).message}`);
    }
  };

  const handleExportJSON = () => {
    const dataToExport = selected.length > 0
      ? benchmarks.filter(b => selected.includes(b.id))
      : benchmarks;
    
    const timestamp = new Date().getTime();
    downloadJSON(dataToExport, `benchmarks-${timestamp}.json`);
  };

  const handleExportCSV = () => {
    const dataToExport = selected.length > 0
      ? benchmarks.filter(b => selected.includes(b.id))
      : benchmarks;
    
    const { headers, rows } = benchmarksToCSV(dataToExport);
    const timestamp = new Date().getTime();
    downloadCSV(headers, rows, `benchmarks-${timestamp}.csv`);
  };

  const handleImport = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setImporting(true);
    setError(null);
    try {
      const formData = new FormData();
      formData.append("file", file);
      const resp = await authFetch(`${API}/benchmark/import`, {
        method: "POST",
        body: formData,
      });
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({ detail: "Unknown error" }));
        throw new Error(err.detail || `HTTP ${resp.status}`);
      }
      const data = await resp.json();
      setError(null);
      fetchBenchmarks();
      alert(`${data.imported_count} benchmark(s) imported successfully.`);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Import failed");
    } finally {
      setImporting(false);
      if (importInputRef.current) importInputRef.current.value = "";
    }
  };

  const compareData = useMemo(() => benchmarks
    .filter(b => selected.includes(b.id))
    .map(b => {
      const gpuEff = calcGpuEfficiency(b.result);
      return {
        name: b.name,
        tps: b.result?.tps?.mean || 0,
        ttft: (b.result?.ttft?.mean || 0) * 1000,
        p99: (b.result?.latency?.p99 || 0) * 1000,
        rps: b.result?.rps_actual || 0,
        gpuEff: gpuEff.value || 0,
        metricsTargetMatched: !gpuEff.mismatch,
      };
    }), [benchmarks, selected]);

  return (
    <div className="flex-col-16">
      <ErrorAlert message={error} className="error-alert--mb8" />
       <div className="panel">
         <div className="section-title">Saved Benchmarks</div>
          {loading ? (
            <div style={{ textAlign: 'center', padding: '40px', color: COLORS.muted }}>Loading...</div>
          ) : (
            <>
<div style={{ marginBottom: '16px', display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
  <button className="btn-primary" disabled={benchmarks.length === 0} onClick={handleExportJSON}>Export JSON</button>
  <button className="btn-primary" disabled={benchmarks.length === 0} onClick={handleExportCSV}>Export CSV</button>
  <button className="btn-outline" disabled={importing} onClick={() => importInputRef.current?.click()}>
    {importing ? "Importing..." : "Import GuideLLM Results"}
  </button>
  <input
    ref={importInputRef}
    type="file"
    accept=".json"
    style={{ display: 'none' }}
    onChange={handleImport}
  />
  <button className="btn-danger" disabled={selected.length === 0} onClick={handleBulkDelete}>Delete Selected ({selected.length})</button>
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
              <th>P99 ms</th>
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
                  <tr onClick={() => toggleExpand(b.id)}
                    className={`benchmark-row ${isSelected ? 'benchmark-row--selected' : ''} ${isExpanded ? 'benchmark-row--expanded' : ''}`}>
                    <td onClick={(e) => toggleSelect(b.id, e)}>
                      <input type="checkbox" checked={isSelected} readOnly aria-label={`Select benchmark ${b.name}`} />
                    </td>
                    <td className="td-text">
                      {b.name}
                      {b.metadata?.source === "guidellm" && (
                        <span style={{ marginLeft: '6px', fontSize: '11px', padding: '1px 6px', borderRadius: '3px', background: '#2563eb', color: '#fff', verticalAlign: 'middle' }}>
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
                      <button className="btn-icon" aria-label="Delete benchmark" onClick={(e) => handleDelete(b, e)}>✕</button>
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
                            <button className="btn-small" onClick={() => setEditing(b)}>Edit</button>
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

      {editing && (
        <div className="modal-overlay">
          <div className="modal-content">
            <div className="modal-header">
              <h3>Edit Benchmark Metadata</h3>
              <button className="btn-close" onClick={() => setEditing(null)}>✕</button>
            </div>
            <form onSubmit={handleSaveMetadata} className="metadata-form">
              <div className="form-group">
                <label>Model Identifier</label>
                <input
                  type="text"
                  value={editing.metadata?.model_identifier || ""}
                  onChange={e => updateMetadataField('model_identifier', e.target.value)}
                  placeholder="e.g. llama-3.1-8b-instruct"
                />
                 <small className="help-text">Enter the actual model name (default is serving name small-llm-d)</small>
              </div>
              <div className="form-row">
                <div className="form-group">
                  <label>Hardware Type</label>
                  <input
                    type="text"
                    value={editing.metadata?.hardware_type || ""}
                    onChange={e => updateMetadataField('hardware_type', e.target.value)}
                     placeholder="e.g. A100, L4, CPU"
                  />
                </div>
                <div className="form-group">
                  <label>Runtime</label>
                  <input
                    type="text"
                    value={editing.metadata?.runtime || ""}
                    onChange={e => updateMetadataField('runtime', e.target.value)}
                     placeholder="e.g. OpenVINO, CUDA"
                  />
                </div>
              </div>
              <div className="form-row">
                <div className="form-group">
                  <label>vLLM Version</label>
                  <input
                    type="text"
                    value={editing.metadata?.vllm_version || ""}
                    onChange={e => updateMetadataField('vllm_version', e.target.value)}
                     placeholder="e.g. 0.6.2"
                  />
                </div>
                <div className="form-group">
                  <label>Replica Count</label>
                  <input
                    type="number"
                    value={editing.metadata?.replica_count || ""}
                    onChange={e => updateMetadataField('replica_count', e.target.value ? parseInt(e.target.value) : null)}
                  />
                </div>
              </div>
              <div className="form-group">
                <label>Notes</label>
                <textarea
                  value={editing.metadata?.notes || ""}
                  onChange={e => updateMetadataField('notes', e.target.value)}
                  rows={3}
                />
              </div>
              <div className="form-group">
                <label>Extra Metadata (Key: Value)</label>
                <div className="extra-editor">
                  {Object.entries(editing.metadata?.extra || {}).map(([k, v], idx) => (
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
                  <button type="button" className="btn-outline-small"
                    onClick={() => updateExtra(`key_${Object.keys(editing.metadata?.extra || {}).length + 1}`, "value")}>
                    + Add Entry
                  </button>
                </div>
              </div>
              <div className="form-actions">
                <button type="button" className="btn-secondary" onClick={() => setEditing(null)}>Cancel</button>
                 <button type="submit" className="btn-primary">Save</button>
              </div>
            </form>
          </div>
        </div>
      )}

      {compareData.length >= 2 && (
        <div className="panel">
           <div className="section-title">Comparison Charts</div>
          <div className="benchmark-compare-charts">
             <div>
               <div className="label">TPS Comparison</div>
               <ResponsiveContainer width="100%" height={200}>
                 <BarChart data={compareData}>
                   <CartesianGrid strokeDasharray="3 3" stroke={COLORS.border} />
                   <XAxis dataKey="name" tick={{ fontSize: 9, fill: COLORS.muted }} />
                   <YAxis tick={{ fontSize: 9, fill: COLORS.muted }} />
                   <Tooltip contentStyle={TOOLTIP_STYLE} />
                   <Bar dataKey="tps" name="TPS">
                     {compareData.map((_, index) => (
                       <Cell key={index} fill={TARGET_COLORS[index % TARGET_COLORS.length]} />
                     ))}
                   </Bar>
                 </BarChart>
               </ResponsiveContainer>
             </div>
             <div>
               <div className="label">P99 Latency Comparison (ms)</div>
               <ResponsiveContainer width="100%" height={200}>
                 <BarChart data={compareData}>
                   <CartesianGrid strokeDasharray="3 3" stroke={COLORS.border} />
                   <XAxis dataKey="name" tick={{ fontSize: 9, fill: COLORS.muted }} />
                   <YAxis tick={{ fontSize: 9, fill: COLORS.muted }} />
                   <Tooltip contentStyle={TOOLTIP_STYLE} />
                   <Bar dataKey="p99" name="P99 ms">
                     {compareData.map((_, index) => (
                       <Cell key={index} fill={TARGET_COLORS[index % TARGET_COLORS.length]} />
                     ))}
                   </Bar>
                 </BarChart>
               </ResponsiveContainer>
             </div>
             <div>
               <div className="label">GPU Efficiency Comparison (TPS/GPU%)</div>
               <ResponsiveContainer width="100%" height={200}>
                 <BarChart data={compareData.filter(d => d.metricsTargetMatched)}>
                   <CartesianGrid strokeDasharray="3 3" stroke={COLORS.border} />
                   <XAxis dataKey="name" tick={{ fontSize: 9, fill: COLORS.muted }} />
                   <YAxis tick={{ fontSize: 9, fill: COLORS.muted }} />
                   <Tooltip contentStyle={TOOLTIP_STYLE} />
                   <Bar dataKey="gpuEff" name="GPU Eff.">
                     {compareData
                       .filter(d => d.metricsTargetMatched)
                       .map((item) => {
                         const index = compareData.indexOf(item);
                         return <Cell key={index} fill={TARGET_COLORS[index % TARGET_COLORS.length]} />;
                       })}
                   </Bar>
                 </BarChart>
               </ResponsiveContainer>
             </div>
          </div>
        </div>
      )}
    </div>
  );
}
export default BenchmarkPage;
