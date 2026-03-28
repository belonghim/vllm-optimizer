import { useState, useEffect, useCallback, FormEvent } from "react";
import { authFetch } from '../utils/authFetch';
import { API, COLORS, TOOLTIP_STYLE, TARGET_COLORS } from "../constants";
import { ERROR_MESSAGES } from "../constants/errorMessages";
import ErrorAlert from "../components/ErrorAlert";
import { BarChart, Bar, Cell, XAxis, YAxis, CartesianGrid, Tooltip, ReferenceLine, ResponsiveContainer, Legend } from 'recharts';
import { useBenchmarkSelection } from '../contexts/BenchmarkSelectionContext';

interface SlaThresholds {
  availability_min: number | null;
  p95_latency_max_ms: number | null;
  error_rate_max_pct: number | null;
  min_tps: number | null;
}

interface SlaProfile {
  id: number;
  name: string;
  thresholds: SlaThresholds;
  created_at: number;
}

interface SlaVerdict {
  metric: string;
  value: number | null;
  threshold: number | null;
  pass: boolean;
  status: 'pass' | 'fail' | 'insufficient_data';
}

interface SlaEvaluationResult {
  benchmark_id: number;
  benchmark_name: string;
  timestamp: number;
  verdicts: SlaVerdict[];
  overall_pass: boolean;
}

interface SlaEvaluateResponse {
  profile: SlaProfile;
  results: SlaEvaluationResult[];
  warnings?: string[];
}

export default function SlaPage({ isActive }: { isActive: boolean }) {
  const { selectedIds } = useBenchmarkSelection();
  const [profiles, setProfiles] = useState<SlaProfile[]>([]);
  const [currentEval, setCurrentEval] = useState<SlaEvaluateResponse | null>(null);
  const [selectedProfileId, setSelectedProfileId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const [formName, setFormName] = useState('');
  const [formAvailMin, setFormAvailMin] = useState('');
  const [formP95Ms, setFormP95Ms] = useState('');
  const [formErrRate, setFormErrRate] = useState('');
  const [formMinTps, setFormMinTps] = useState('');
  const [editingId, setEditingId] = useState<number | null>(null);

  const [chartMetric, setChartMetric] = useState<'p95_latency' | 'availability' | 'error_rate' | 'min_tps'>('p95_latency');

   const loadProfiles = useCallback(async () => {
     setLoading(true);
     try {
       const res = await authFetch(`${API}/sla/profiles`);
       if (!res.ok) throw new Error(`HTTP ${res.status}`);
       const data: SlaProfile[] = await res.json();
       setProfiles(data);
       setError(null);
     } catch (err) {
       setError(`${ERROR_MESSAGES.SLA.PROFILE_LOAD_FAILED}: ${(err as Error).message}`);
     } finally {
       setLoading(false);
     }
   }, []);

  const handleProfileSelect = useCallback(async (profileId: number) => {
    setSelectedProfileId(profileId);
    if (selectedIds.length === 0) {
      setCurrentEval(null);
      return;
    }
    try {
      const res = await authFetch(`${API}/sla/evaluate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ profile_id: profileId, benchmark_ids: selectedIds.map(Number) }),
      });
      if (res.ok) {
        setCurrentEval(await res.json() as SlaEvaluateResponse);
      } else {
        setCurrentEval(null);
      }
    } catch (err) {
      console.error('Failed to evaluate SLA profile:', err);
      setError(`Failed to evaluate SLA profile: ${(err as Error).message}`);
      setCurrentEval(null);
    }
  }, [selectedIds, loadProfiles]);

  useEffect(() => {
    if (!isActive) return;
    loadProfiles();
  }, [isActive, loadProfiles]);

  useEffect(() => {
    if (!isActive || !selectedProfileId) return;
    handleProfileSelect(selectedProfileId);
  }, [isActive, selectedIds, selectedProfileId, handleProfileSelect]);

  const handleSubmit = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setError(null);
    
     const hasAnyThreshold = formAvailMin || formP95Ms || formErrRate || formMinTps;
     if (!hasAnyThreshold) {
       setError(ERROR_MESSAGES.SLA.NO_THRESHOLD_ERROR);
       return;
     }
    
    const body = {
      name: formName,
      thresholds: {
        availability_min: formAvailMin ? parseFloat(formAvailMin) : null,
        p95_latency_max_ms: formP95Ms ? parseFloat(formP95Ms) : null,
        error_rate_max_pct: formErrRate ? parseFloat(formErrRate) : null,
        min_tps: formMinTps ? parseFloat(formMinTps) : null,
      }
    };

    try {
      const url = editingId ? `${API}/sla/profiles/${editingId}` : `${API}/sla/profiles`;
      const method = editingId ? 'PUT' : 'POST';
      const res = await authFetch(url, {
        method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body)
      });
      if (!res.ok) {
        let detail = `HTTP ${res.status}`;
        try {
           const errBody = await res.json();
           if (errBody.detail) {
             detail = typeof errBody.detail === 'string'
               ? errBody.detail
               : errBody.detail.map((d: { msg: string }) => d.msg).join(', ');
          }
       } catch {
       }
        throw new Error(detail);
      }
      
       resetForm();
       await loadProfiles();
     } catch (err) {
       setError(`${ERROR_MESSAGES.SLA.PROFILE_SAVE_FAILED}: ${(err as Error).message}`);
     }
  };

  const handleEdit = (p: SlaProfile) => {
    setEditingId(p.id);
    setFormName(p.name);
    setFormAvailMin(p.thresholds.availability_min?.toString() || '');
    setFormP95Ms(p.thresholds.p95_latency_max_ms?.toString() || '');
    setFormErrRate(p.thresholds.error_rate_max_pct?.toString() || '');
    setFormMinTps(p.thresholds.min_tps?.toString() || '');
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

   const handleDelete = async (id: number) => {
     if (!window.confirm(ERROR_MESSAGES.SLA.PROFILE_DELETE_CONFIRM)) return;
     try {
       const res = await authFetch(`${API}/sla/profiles/${id}`, { method: 'DELETE' });
       if (!res.ok) throw new Error(`HTTP ${res.status}`);
       await loadProfiles();
       if (selectedProfileId === id) {
         setSelectedProfileId(null);
         setCurrentEval(null);
       }
     } catch (err) {
       setError(`${ERROR_MESSAGES.SLA.PROFILE_DELETE_FAILED}: ${(err as Error).message}`);
     }
   };

  const resetForm = () => {
    setEditingId(null);
    setFormName('');
    setFormAvailMin('');
    setFormP95Ms('');
    setFormErrRate('');
    setFormMinTps('');
  };

   const renderThresholds = (t: SlaThresholds) => {
     const parts = [];
      if (t.availability_min != null) parts.push(`Availability≥${t.availability_min}%`);
     if (t.p95_latency_max_ms != null) parts.push(`P95≤${t.p95_latency_max_ms}ms`);
      if (t.error_rate_max_pct != null) parts.push(`Error Rate≤${t.error_rate_max_pct}%`);
     if (t.min_tps != null) parts.push(`TPS≥${t.min_tps}`);
     return parts.join(' · ') || ERROR_MESSAGES.SLA.NO_THRESHOLDS_SET;
   };

  const chartData = (currentEval?.results ?? []).map(r => {
    const verdict = r.verdicts.find(v => v.metric === chartMetric);
    return {
      name: r.benchmark_name,
      value: verdict?.value ?? null,
      threshold: verdict?.threshold ?? null,
    };
  });

  const legendPayload = (currentEval?.results ?? []).map((result, index) => ({
    value: result.benchmark_name,
    type: 'circle' as const,
    id: String(result.benchmark_id),
    color: TARGET_COLORS[index % TARGET_COLORS.length],
  }));

  const slaThreshold = chartData.find(d => d.threshold != null)?.threshold;

  return (
    <div className="flex-col-16">
      <ErrorAlert message={error} className="error-alert--mb8" />

       <div className="panel">
         <div className="section-title">{editingId ? ERROR_MESSAGES.SLA.EDIT_TITLE : ERROR_MESSAGES.SLA.CREATE_TITLE}</div>
        <form onSubmit={handleSubmit} className="form-grid" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '16px', marginBottom: '24px' }}>
          <div className="form-group">
            <label>Profile Name *</label>
             <input type="text" value={formName} onChange={e => setFormName(e.target.value)} required placeholder="e.g. Llama3 Production SLA" />
          </div>
          <div className="form-group">
             <label>Min Availability (%)</label>
            <input type="number" min="0" max="100" step="0.1" value={formAvailMin} onChange={e => setFormAvailMin(e.target.value)} placeholder="99.9" />
          </div>
          <div className="form-group">
             <label>Max P95 Latency (ms)</label>
            <input type="number" min="0" step="1" value={formP95Ms} onChange={e => setFormP95Ms(e.target.value)} placeholder="500" />
          </div>
          <div className="form-group">
             <label>Max Error Rate (%)</label>
            <input type="number" min="0" max="100" step="0.1" value={formErrRate} onChange={e => setFormErrRate(e.target.value)} placeholder="1.0" />
          </div>
          <div className="form-group">
             <label>Min TPS</label>
            <input type="number" min="0" step="0.1" value={formMinTps} onChange={e => setFormMinTps(e.target.value)} placeholder="10.0" />
          </div>
          <div className="form-actions" style={{ gridColumn: '1 / -1', display: 'flex', gap: '8px', justifyContent: 'flex-end' }}>
             {editingId && <button type="button" className="btn-secondary" onClick={resetForm}>Cancel</button>}
             <button type="submit" className="btn-primary">{editingId ? 'Save' : 'Create Profile'}</button>
          </div>
        </form>

         <div className="section-title" style={{ marginTop: '32px' }}>SLA Profile List</div>
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
                      onChange={() => handleProfileSelect(p.id)}
                      style={{ cursor: 'pointer', accentColor: COLORS.cyan }}
                    />
                  </td>
                  <td className="td-text">{p.name}</td>
                  <td className="td-muted" style={{ fontSize: '0.85rem' }}>{renderThresholds(p.thresholds)}</td>
                  <td style={{ textAlign: 'right' }}>
                     <button className="btn-small" onClick={() => handleEdit(p)} style={{ marginRight: '8px' }}>Edit</button>
                     <button className="btn-outline-small" onClick={() => handleDelete(p.id)} style={{ color: COLORS.red, borderColor: COLORS.red }}>Delete</button>
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

       {selectedProfileId && (
         <div className="panel" aria-live="polite">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
            <div className="section-title" style={{ margin: 0 }}>{currentEval?.profile.name ?? profiles.find(p => p.id === selectedProfileId)?.name} - Metrics Trend</div>
            <div className="tab-group" style={{ display: 'flex', gap: '4px' }}>
              {([
                { id: 'p95_latency' as const, label: 'P95 Latency' },
                { id: 'availability' as const, label: 'Availability' },
                { id: 'error_rate' as const, label: 'Error Rate' },
                { id: 'min_tps' as const, label: 'TPS' }
              ] as const).map(m => (
                <button 
                  key={m.id}
                  className={`btn-small ${chartMetric === m.id ? 'active' : ''}`}
                  onClick={() => setChartMetric(m.id)}
                  style={{
                    backgroundColor: chartMetric === m.id ? COLORS.cyan : 'transparent',
                    color: chartMetric === m.id ? COLORS.bg : COLORS.text,
                    border: `1px solid ${chartMetric === m.id ? COLORS.cyan : COLORS.border}`
                  }}
                >
                  {m.label}
                </button>
              ))}
            </div>
          </div>
          
           {selectedIds.length === 0 ? (
             <div className="td-muted" style={{ textAlign: 'center', padding: '60px' }}>
               {ERROR_MESSAGES.SLA.SELECT_BENCHMARK}
             </div>
           ) : (currentEval?.results ?? []).length > 0 ? (
            <div style={{ height: '300px', width: '100%' }}>
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={chartData} margin={{ top: 10, right: 30, left: 0, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke={COLORS.border} />
                  <XAxis dataKey="name" tick={{ fontSize: 11, fill: COLORS.muted }} interval={0} />
                  <YAxis tick={{ fontSize: 11, fill: COLORS.muted }} />
                   <Tooltip
                     contentStyle={TOOLTIP_STYLE}
                     itemStyle={{ fontSize: '12px' }}
                     labelStyle={{ fontSize: '12px', fontWeight: 'bold', marginBottom: '4px' }}
                     formatter={(value: number | string) => [value, chartMetric]}
                   />
                  <Legend payload={legendPayload} />
                  <Bar dataKey="value" isAnimationActive={false}>
                    {chartData.map((_, index) => (
                      <Cell key={index} fill={TARGET_COLORS[index % TARGET_COLORS.length]} />
                    ))}
                  </Bar>
                  {slaThreshold != null && (
                    <ReferenceLine
                      y={slaThreshold}
                      stroke={COLORS.red}
                      strokeWidth={2.5}
                      label={{
                        position: 'insideTopRight',
                        value: `SLA: ${
                          chartMetric === 'p95_latency' ? `${slaThreshold}ms` :
                          chartMetric === 'min_tps' ? `${slaThreshold} req/s` :
                          `${slaThreshold}%`
                        }`,
                        fill: COLORS.red,
                        fontSize: 11,
                        fontWeight: 'bold',
                      }}
                    />
                  )}
                </BarChart>
              </ResponsiveContainer>
            </div>
           ) : (
             <div className="td-muted" style={{ textAlign: 'center', padding: '60px' }}>
               {ERROR_MESSAGES.SLA.NO_EVALUATION_RESULTS}
             </div>
           )}
        </div>
      )}
    </div>
  );
}
