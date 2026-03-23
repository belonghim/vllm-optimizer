import { useState, useEffect, useMemo } from "react";
import { authFetch } from '../utils/authFetch';
import { API, COLORS, TOOLTIP_STYLE } from "../constants";
import { fmt } from "../utils/format";
import { mockBenchmarks } from "../mockData";
import { calcGpuEfficiency } from "../utils/metrics";
import { BarChart, Bar, CartesianGrid, XAxis, YAxis, Tooltip, ResponsiveContainer } from "recharts";
import { useMockData } from "../contexts/MockDataContext";
import ErrorAlert from "../components/ErrorAlert";

interface BenchmarkMetadata {
  model_identifier?: string | null;
  hardware_type?: string | null;
  runtime?: string | null;
  vllm_version?: string | null;
  replica_count?: number | null;
  notes?: string | null;
  extra?: Record<string, string>;
}

interface BenchmarkConfig {
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

interface Benchmark {
  id: string | number;
  name: string;
  timestamp: number;
  config?: BenchmarkConfig;
  result: BenchmarkResultData;
  metadata?: BenchmarkMetadata | null;
}

interface BenchmarkPageProps {
  isActive: boolean;
}

function BenchmarkPage({ isActive }: BenchmarkPageProps) {
  const [benchmarks, setBenchmarks] = useState<Benchmark[]>([]);
  const [selected, setSelected] = useState<(string | number)[]>([]);
  const [expanded, setExpanded] = useState<(string | number)[]>([]);
  const [editing, setEditing] = useState<Benchmark | null>(null);
  const [error, setError] = useState<string | null>(null);
  const { isMockEnabled } = useMockData();

  useEffect(() => {
    if (!isActive) return;

    if (isMockEnabled) {
      setBenchmarks(mockBenchmarks());
      setError(null);
      return;
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
        setError(`벤치마크 조회 실패: ${(err as Error).message}`);
      });
    return () => controller.abort();
  }, [isMockEnabled, isActive]);

  const toggleSelect = (id: string | number, e: React.MouseEvent) => {
    e.stopPropagation();
    setSelected(s =>
      s.includes(id) ? s.filter(x => x !== id) : [...s, id]
    );
  };

  const toggleExpand = (id: string | number) => {
    setExpanded(s =>
      s.includes(id) ? s.filter(x => x !== id) : [...s, id]
    );
  };

  const handleDelete = async (b: Benchmark, e: React.MouseEvent) => {
    e.stopPropagation();
    if (!window.confirm(`벤치마크 '${b.name}'을(를) 삭제하시겠습니까?`)) return;

    if (isMockEnabled) {
      setBenchmarks(prev => prev.filter(x => x.id !== b.id));
      setSelected(prev => prev.filter(x => x !== b.id));
      setExpanded(prev => prev.filter(x => x !== b.id));
      return;
    }

    try {
      const res = await authFetch(`${API}/benchmark/${b.id}`, { method: 'DELETE' });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setBenchmarks(prev => prev.filter(x => x.id !== b.id));
      setSelected(prev => prev.filter(x => x !== b.id));
      setExpanded(prev => prev.filter(x => x !== b.id));
    } catch (err) {
      setError(`삭제 실패: ${(err as Error).message}`);
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
      const updated: Benchmark = await res.json();
      setBenchmarks(prev => prev.map(b => b.id === benchmarkId ? updated : b));
      setEditing(null);
    } catch (err) {
      setError(`메타데이터 저장 실패: ${(err as Error).message}`);
    }
  };

  const updateMetadataField = (field: keyof BenchmarkMetadata, value: any) => {
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
         <div className="section-title">저장된 벤치마크</div>
         <table className="table" aria-label="저장된 벤치마크 목록">
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
              <th>삭제</th>
            </tr>
          </thead>
          <tbody>
            {benchmarks.map(b => {
              const eff = calcGpuEfficiency(b.result);
              const isSelected = selected.includes(b.id);
              const isExpanded = expanded.includes(b.id);
              return (
                <React.Fragment key={b.id}>
                  <tr onClick={() => toggleExpand(b.id)}
                    className={`benchmark-row ${isSelected ? 'benchmark-row--selected' : ''} ${isExpanded ? 'benchmark-row--expanded' : ''}`}>
                    <td onClick={(e) => toggleSelect(b.id, e)}>
                      <input type="checkbox" checked={isSelected} readOnly aria-label={`벤치마크 ${b.name} 선택`} />
                    </td>
                    <td className="td-text">{b.name}</td>
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
                      <button className="btn-icon" aria-label="벤치마크 삭제" onClick={(e) => handleDelete(b, e)}>✕</button>
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
                            <button className="btn-small" onClick={() => setEditing(b)}>편집</button>
                          </div>
                        </div>
                      </td>
                    </tr>
                  )}
                </React.Fragment>
              );
            })}
            {benchmarks.length === 0 && (
              <tr><td colSpan={10} className="benchmark-empty">
                부하 테스트 결과를 저장하면 여기 나타납니다.
              </td></tr>
            )}
          </tbody>
        </table>
      </div>

      {editing && (
        <div className="modal-overlay">
          <div className="modal-content">
            <div className="modal-header">
              <h3>벤치마크 메타데이터 편집</h3>
              <button className="btn-close" onClick={() => setEditing(null)}>✕</button>
            </div>
            <form onSubmit={handleSaveMetadata} className="metadata-form">
              <div className="form-group">
                <label>Model Identifier</label>
                <input
                  type="text"
                  value={editing.metadata?.model_identifier || ""}
                  onChange={e => updateMetadataField('model_identifier', e.target.value)}
                  placeholder="예: llama-3.1-8b-instruct"
                />
                <small className="help-text">실제 모델 이름을 입력하세요 (기본값은 서빙 이름 llm-ov)</small>
              </div>
              <div className="form-row">
                <div className="form-group">
                  <label>Hardware Type</label>
                  <input
                    type="text"
                    value={editing.metadata?.hardware_type || ""}
                    onChange={e => updateMetadataField('hardware_type', e.target.value)}
                    placeholder="예: A100, L4, CPU"
                  />
                </div>
                <div className="form-group">
                  <label>Runtime</label>
                  <input
                    type="text"
                    value={editing.metadata?.runtime || ""}
                    onChange={e => updateMetadataField('runtime', e.target.value)}
                    placeholder="예: OpenVINO, CUDA"
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
                    placeholder="예: 0.6.2"
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
                    + 항목 추가
                  </button>
                </div>
              </div>
              <div className="form-actions">
                <button type="button" className="btn-secondary" onClick={() => setEditing(null)}>취소</button>
                <button type="submit" className="btn-primary">저장</button>
              </div>
            </form>
          </div>
        </div>
      )}

      {compareData.length >= 2 && (
        <div className="panel">
          <div className="section-title">비교 차트</div>
          <div className="benchmark-compare-charts">
            <div>
              <div className="label">TPS 비교</div>
              <ResponsiveContainer width="100%" height={200}>
                <BarChart data={compareData}>
                  <CartesianGrid strokeDasharray="3 3" stroke={COLORS.border} />
                  <XAxis dataKey="name" tick={{ fontSize: 9, fill: COLORS.muted }} />
                  <YAxis tick={{ fontSize: 9, fill: COLORS.muted }} />
                  <Tooltip contentStyle={TOOLTIP_STYLE} />
                  <Bar dataKey="tps" fill={COLORS.accent} name="TPS" />
                </BarChart>
              </ResponsiveContainer>
            </div>
            <div>
              <div className="label">P99 Latency 비교 (ms)</div>
              <ResponsiveContainer width="100%" height={200}>
                <BarChart data={compareData}>
                  <CartesianGrid strokeDasharray="3 3" stroke={COLORS.border} />
                  <XAxis dataKey="name" tick={{ fontSize: 9, fill: COLORS.muted }} />
                  <YAxis tick={{ fontSize: 9, fill: COLORS.muted }} />
                  <Tooltip contentStyle={TOOLTIP_STYLE} />
                  <Bar dataKey="p99" fill={COLORS.red} name="P99 ms" />
                </BarChart>
              </ResponsiveContainer>
            </div>
            <div>
              <div className="label">GPU 효율 비교 (TPS/GPU%)</div>
              <ResponsiveContainer width="100%" height={200}>
                <BarChart data={compareData.filter(d => d.metricsTargetMatched)}>
                  <CartesianGrid strokeDasharray="3 3" stroke={COLORS.border} />
                  <XAxis dataKey="name" tick={{ fontSize: 9, fill: COLORS.muted }} />
                  <YAxis tick={{ fontSize: 9, fill: COLORS.muted }} />
                  <Tooltip contentStyle={TOOLTIP_STYLE} />
                  <Bar dataKey="gpuEff" fill={COLORS.green} name="GPU Eff." />
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
