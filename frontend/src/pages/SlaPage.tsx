import { useState, useEffect, useCallback, FormEvent } from "react";
import { authFetch } from '../utils/authFetch';
import { API, COLORS, TOOLTIP_STYLE, TARGET_COLORS } from "../constants";
import { ERROR_MESSAGES } from "../constants/errorMessages";
import ErrorAlert from "../components/ErrorAlert";
import LoadingSpinner from "../components/LoadingSpinner";
import { BarChart, Bar, Cell, XAxis, YAxis, CartesianGrid, Tooltip, ReferenceLine, ResponsiveContainer, Legend } from 'recharts';
import { useBenchmarkSelection } from '../contexts/BenchmarkSelectionContext';
import SlaProfileForm, { SlaFormState } from "../components/SlaProfileForm";
import SlaProfileList from "../components/SlaProfileList";
import ConfirmDialog from "../components/ConfirmDialog";

import type { SlaThresholds, SlaProfile } from "../types";
export type { SlaThresholds, SlaProfile };

interface SlaVerdict {
  metric: string;
  value: number | null;
  threshold: number | null;
  pass: boolean;
  status: 'pass' | 'fail' | 'insufficient_data' | 'skipped';
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

const EMPTY_FORM: SlaFormState = { name: '', availMin: '', p95Ms: '', errRate: '', minTps: '', meanTtftMs: '', p95TtftMs: '' };

export default function SlaPage({ isActive }: { isActive: boolean }) {
  const { selectedIds } = useBenchmarkSelection();
  const [profiles, setProfiles] = useState<SlaProfile[]>([]);
  const [currentEval, setCurrentEval] = useState<SlaEvaluateResponse | null>(null);
  const [selectedProfileId, setSelectedProfileId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [formState, setFormState] = useState<SlaFormState>(EMPTY_FORM);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [chartMetric, setChartMetric] = useState<'p95_latency' | 'availability' | 'error_rate' | 'min_tps' | 'ttft_mean' | 'ttft_p95'>('p95_latency');
  const [confirmState, setConfirmState] = useState<{
    open: boolean;
    title?: string;
    message: string;
    onConfirm: () => void;
  }>({
    open: false,
    title: undefined,
    message: "",
    onConfirm: () => {},
  });

  const handleFormChange = (field: keyof SlaFormState, value: string) =>
    setFormState(prev => ({ ...prev, [field]: value }));

  const loadProfiles = useCallback(async () => {
    setLoading(true);
    try {
      const res = await authFetch(`${API}/sla/profiles`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setProfiles(await res.json() as SlaProfile[]);
      setError(null);
    } catch (err) {
      setError(`${ERROR_MESSAGES.SLA.PROFILE_LOAD_FAILED}: ${(err as Error).message}`);
    } finally {
      setLoading(false);
    }
  }, []);

  const handleProfileSelect = useCallback(async (profileId: number) => {
    setSelectedProfileId(profileId);
    if (selectedIds.length === 0) { setCurrentEval(null); return; }
    try {
      const res = await authFetch(`${API}/sla/evaluate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ profile_id: profileId, benchmark_ids: selectedIds.map(Number) }),
      });
      setCurrentEval(res.ok ? await res.json() as SlaEvaluateResponse : null);
    } catch (err) {
      console.error('Failed to evaluate SLA profile:', err);
      setError(`Failed to evaluate SLA profile: ${(err as Error).message}`);
      setCurrentEval(null);
    }
  }, [selectedIds]);

  useEffect(() => { if (isActive) loadProfiles(); }, [isActive, loadProfiles]);
   useEffect(() => {
     if (!isActive || !selectedProfileId) return;
     handleProfileSelect(selectedProfileId);
   }, [isActive, selectedProfileId, handleProfileSelect]);

  const resetForm = () => { setEditingId(null); setFormState(EMPTY_FORM); };

  const handleSubmit = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setError(null);
    const { name, availMin, p95Ms, errRate, minTps, meanTtftMs, p95TtftMs } = formState;
    if (!availMin && !p95Ms && !errRate && !minTps && !meanTtftMs && !p95TtftMs) { setError(ERROR_MESSAGES.SLA.NO_THRESHOLD_ERROR); return; }
    const body = {
      name,
      thresholds: {
        availability_min: availMin ? parseFloat(availMin) : null,
        p95_latency_max_ms: p95Ms ? parseFloat(p95Ms) : null,
        error_rate_max_pct: errRate ? parseFloat(errRate) : null,
        min_tps: minTps ? parseFloat(minTps) : null,
        mean_ttft_max_ms: meanTtftMs ? parseFloat(meanTtftMs) : null,
        p95_ttft_max_ms: p95TtftMs ? parseFloat(p95TtftMs) : null,
      }
    };
    try {
      const url = editingId ? `${API}/sla/profiles/${editingId}` : `${API}/sla/profiles`;
      const res = await authFetch(url, { method: editingId ? 'PUT' : 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
      if (!res.ok) {
        let detail = `HTTP ${res.status}`;
        try {
          const errBody = await res.json();
          if (errBody.detail) detail = typeof errBody.detail === 'string' ? errBody.detail : errBody.detail.map((d: { msg: string }) => d.msg).join(', ');
        } catch (e) { console.error('Failed to parse SLA API error response', e); }
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
    setFormState({
      name: p.name,
      availMin: p.thresholds.availability_min?.toString() || '',
      p95Ms: p.thresholds.p95_latency_max_ms?.toString() || '',
      errRate: p.thresholds.error_rate_max_pct?.toString() || '',
      minTps: p.thresholds.min_tps?.toString() || '',
      meanTtftMs: p.thresholds.mean_ttft_max_ms?.toString() || '',
      p95TtftMs: p.thresholds.p95_ttft_max_ms?.toString() || '',
    });
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  const deleteProfile = useCallback(async (id: number) => {
    try {
      const res = await authFetch(`${API}/sla/profiles/${id}`, { method: 'DELETE' });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      await loadProfiles();
      if (selectedProfileId === id) { setSelectedProfileId(null); setCurrentEval(null); }
    } catch (err) {
      setError(`${ERROR_MESSAGES.SLA.PROFILE_DELETE_FAILED}: ${(err as Error).message}`);
    }
  }, [loadProfiles, selectedProfileId]);

  const handleDelete = async (id: number) => {
    setConfirmState({
      open: true,
      title: "Delete SLA Profile",
      message: ERROR_MESSAGES.SLA.PROFILE_DELETE_CONFIRM,
      onConfirm: () => {
        void deleteProfile(id);
      },
    });
  };

  const chartData = (currentEval?.results ?? []).map(r => {
    const verdict = r.verdicts.find(v => v.metric === chartMetric);
    const value = verdict?.status === 'skipped' ? null : (verdict?.value ?? null);
    return { name: r.benchmark_name, value, threshold: verdict?.threshold ?? null };
  });
  const legendPayload = (currentEval?.results ?? []).map((result, index) => ({
    value: result.benchmark_name, type: 'circle' as const, id: String(result.benchmark_id), color: TARGET_COLORS[index % TARGET_COLORS.length],
  }));
  const slaThreshold = chartData.find(d => d.threshold != null)?.threshold;

  return (
    <div className="flex-col-16">
      <ErrorAlert message={error} className="error-alert--mb8" />
      <SlaProfileForm formState={formState} onChange={handleFormChange} onSubmit={handleSubmit} onCancel={resetForm} editingId={editingId} />
      {loading && profiles.length === 0 ? (
        <LoadingSpinner />
      ) : (
        <SlaProfileList profiles={profiles} onEdit={handleEdit} onDelete={handleDelete} selectedProfileId={selectedProfileId} onSelect={handleProfileSelect} loading={loading} />
      )}
      {selectedProfileId && (
        <div className="panel" aria-live="polite">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
            <div className="section-title" style={{ margin: 0 }}>{currentEval?.profile.name ?? profiles.find(p => p.id === selectedProfileId)?.name} - Metrics Trend</div>
            <div className="tab-group" style={{ display: 'flex', gap: '4px' }}>
{([
                  { id: 'p95_latency' as const, label: 'P95 Latency' },
                  { id: 'availability' as const, label: 'Availability' },
                  { id: 'error_rate' as const, label: 'Error Rate' },
                  { id: 'min_tps' as const, label: 'TPS' },
                  { id: 'ttft_mean' as const, label: 'TTFT Mean' },
                  { id: 'ttft_p95' as const, label: 'TTFT P95' }
                ] as const).map(m => (
                 <button key={m.id} type="button" className={`btn-small ${chartMetric === m.id ? 'active' : ''}`} onClick={() => setChartMetric(m.id)}
                   style={{ backgroundColor: chartMetric === m.id ? COLORS.cyan : 'transparent', color: chartMetric === m.id ? COLORS.bg : COLORS.text, border: `1px solid ${chartMetric === m.id ? COLORS.cyan : COLORS.border}` }}>
                   {m.label}
                 </button>
               ))}
            </div>
          </div>
          {selectedIds.length === 0 ? (
            <div className="td-muted" style={{ textAlign: 'center', padding: '60px' }}>{ERROR_MESSAGES.SLA.SELECT_BENCHMARK}</div>
          ) : (currentEval?.results ?? []).length > 0 ? (
            <div
              style={{
                width: '100%',
                height: '30vh',
                minHeight: '220px',
                maxHeight: '420px',
              }}
            >
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={chartData} margin={{ top: 10, right: 30, left: 0, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke={COLORS.border} />
                  <XAxis dataKey="name" tick={{ fontSize: 11, fill: COLORS.muted }} interval={0} />
                  <YAxis tick={{ fontSize: 11, fill: COLORS.muted }} />
                  <Tooltip contentStyle={TOOLTIP_STYLE} itemStyle={{ fontSize: '12px' }} labelStyle={{ fontSize: '12px', fontWeight: 'bold', marginBottom: '4px' }} formatter={(value: number | string) => [value, chartMetric]} />
                  <Legend payload={legendPayload} />
                   <Bar dataKey="value" isAnimationActive={false}>
                     {chartData.map((item, index) => (<Cell key={item.name} fill={TARGET_COLORS[index % TARGET_COLORS.length]} />))}
                   </Bar>
                  {slaThreshold != null && (
                    <ReferenceLine y={slaThreshold} stroke={COLORS.red} strokeWidth={2.5}
                      label={{ position: 'insideTopRight', value: `SLA: ${chartMetric === 'p95_latency' || chartMetric === 'ttft_mean' || chartMetric === 'ttft_p95' ? `${slaThreshold}ms` : chartMetric === 'min_tps' ? `${slaThreshold} req/s` : `${slaThreshold}%`}`, fill: COLORS.red, fontSize: 11, fontWeight: 'bold' }}
                    />
                  )}
                </BarChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <div className="td-muted" style={{ textAlign: 'center', padding: '60px' }}>{ERROR_MESSAGES.SLA.NO_EVALUATION_RESULTS}</div>
          )}
        </div>
      )}
      <ConfirmDialog
        open={confirmState.open}
        title={confirmState.title}
        message={confirmState.message}
        onCancel={() => setConfirmState(prev => ({ ...prev, open: false }))}
        onConfirm={() => {
          const callback = confirmState.onConfirm;
          setConfirmState(prev => ({ ...prev, open: false }));
          callback();
        }}
      />
    </div>
  );
}
