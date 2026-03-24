import React, { useState, useEffect } from "react";
import { authFetch } from '../utils/authFetch';
import { API, COLORS, TOOLTIP_STYLE, TARGET_COLORS } from "../constants";
import ErrorAlert from "../components/ErrorAlert";
import { BarChart, Bar, Cell, XAxis, YAxis, CartesianGrid, Tooltip, ReferenceLine, ResponsiveContainer, Legend } from 'recharts';

interface SlaThresholds {
  availability_min: number | null;
  p95_latency_max_ms: number | null;
  error_rate_max_pct: number | null;
  min_tps: number | null;
}

interface SlaProfile {
  id: number;
  name: string;
  benchmark_ids: number[];
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
  const [profiles, setProfiles] = useState<SlaProfile[]>([]);
  const [evaluations, setEvaluations] = useState<Record<number, SlaEvaluateResponse>>({});
  const [selectedProfileId, setSelectedProfileId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const [formName, setFormName] = useState('');
  const [availableBenchmarks, setAvailableBenchmarks] = useState<{id: number; name: string; timestamp: number}[]>([]);
  const [formAvailMin, setFormAvailMin] = useState('');
  const [formP95Ms, setFormP95Ms] = useState('');
  const [formErrRate, setFormErrRate] = useState('');
  const [formMinTps, setFormMinTps] = useState('');
  const [editingId, setEditingId] = useState<number | null>(null);

  const [chartMetric, setChartMetric] = useState<'p95_latency' | 'availability' | 'error_rate' | 'min_tps'>('p95_latency');

  useEffect(() => {
    if (!isActive) return;
    loadProfiles();
    const fetchBenchmarks = async () => {
      try {
        const res = await authFetch(`${API}/benchmark/list`);
        if (res.ok) {
          const data = await res.json();
          setAvailableBenchmarks(data.map((b: any) => ({ id: b.id, name: b.name, timestamp: b.timestamp })));
        }
       } catch { setAvailableBenchmarks([]); }
    };
    fetchBenchmarks();
  }, [isActive]);

  async function loadProfiles() {
    setLoading(true);
    try {
      const res = await authFetch(`${API}/sla/profiles`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data: SlaProfile[] = await res.json();
      setProfiles(data);
      
      const evalResults = await Promise.allSettled(
        data.map(async (p) => {
          const evalRes = await authFetch(`${API}/sla/evaluate/${p.id}`);
          if (!evalRes.ok) return null;
          return { id: p.id, data: await evalRes.json() as SlaEvaluateResponse };
        })
      );
      const newEvals: Record<number, SlaEvaluateResponse> = {};
      for (const r of evalResults) {
        if (r.status === 'fulfilled' && r.value) newEvals[r.value.id] = r.value.data;
      }
      setEvaluations(newEvals);
      setError(null);
    } catch (err) {
      setError(`SLA 프로필 로드 실패: ${(err as Error).message}`);
    } finally {
      setLoading(false);
    }
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    
    const hasAnyThreshold = formAvailMin || formP95Ms || formErrRate || formMinTps;
    if (!hasAnyThreshold) {
      setError("최소 1개의 임계값을 입력해야 합니다.");
      return;
    }
    
    const body = {
      name: formName,
      benchmark_ids: editingId ? (profiles.find(p => p.id === editingId)?.benchmark_ids ?? []) : [],
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
              : errBody.detail.map((d: any) => d.msg).join(', ');
          }
       } catch {
       }
        throw new Error(detail);
      }
      
      resetForm();
      await loadProfiles();
    } catch (err) {
      setError(`SLA 프로필 저장 실패: ${(err as Error).message}`);
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
    if (!window.confirm("이 SLA 프로필을 삭제하시겠습니까?")) return;
    try {
      const res = await authFetch(`${API}/sla/profiles/${id}`, { method: 'DELETE' });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      await loadProfiles();
      if (selectedProfileId === id) setSelectedProfileId(null);
    } catch (err) {
      setError(`SLA 프로필 삭제 실패: ${(err as Error).message}`);
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
    if (t.availability_min != null) parts.push(`가용성≥${t.availability_min}%`);
    if (t.p95_latency_max_ms != null) parts.push(`P95≤${t.p95_latency_max_ms}ms`);
    if (t.error_rate_max_pct != null) parts.push(`에러율≤${t.error_rate_max_pct}%`);
    if (t.min_tps != null) parts.push(`TPS≥${t.min_tps}`);
    return parts.join(' · ') || 'No thresholds set';
  };

  const selectedEval = selectedProfileId ? evaluations[selectedProfileId] : null;
  const chartData = (selectedEval?.results ?? []).map(r => {
    const verdict = r.verdicts.find(v => v.metric === chartMetric);
    return {
      name: r.benchmark_name,
      value: verdict?.value ?? null,
      threshold: verdict?.threshold ?? null,
    };
  });

  const legendPayload = (selectedEval?.results ?? []).map((result, index) => ({
    value: result.benchmark_name,
    type: 'circle' as const,
    id: String(result.benchmark_id),
    color: TARGET_COLORS[index % TARGET_COLORS.length],
  }));

  const slaThreshold = chartData.find(d => d.threshold != null)?.threshold;

  return (
    <div className="flex-col-16">
      <ErrorAlert message={error} className="error-alert--mb8" />

      <div className="grid-responsive" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: '16px' }}>
        {profiles.map(p => {
          const evalData = evaluations[p.id];
          const latestResult = evalData?.results?.[evalData.results.length - 1];
          const passCount = latestResult?.verdicts.filter(v => v.status === 'pass').length || 0;
          const totalCount = latestResult?.verdicts.length || 0;
          const isSelected = selectedProfileId === p.id;

          return (
            <div 
              key={p.id} 
              className={`panel sla-summary-card ${isSelected ? 'selected' : ''}`}
              style={{ 
                cursor: 'pointer',
                border: isSelected ? `2px solid ${COLORS.cyan}` : `1px solid ${COLORS.border}`,
                transition: 'all 0.2s ease'
              }}
              onClick={() => setSelectedProfileId(p.id)}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '8px' }}>
                <div>
                  <div className="section-title" style={{ fontSize: '1.1rem', margin: 0 }}>{p.name}</div>
                  <div style={{ display: 'flex', gap: '4px', flexWrap: 'wrap', marginTop: '2px' }}>
                    {p.benchmark_ids.map((bid, idx) => {
                      const bName = availableBenchmarks.find(b => b.id === bid)?.name || `#${bid}`;
                      return (
                        <span key={bid} style={{ display: 'flex', alignItems: 'center', gap: '3px', fontSize: '0.8rem' }}>
                          <span style={{ width: '6px', height: '6px', borderRadius: '50%', backgroundColor: TARGET_COLORS[idx % TARGET_COLORS.length], display: 'inline-block' }} />
                          <span className="td-muted">{bName}</span>
                        </span>
                      );
                    })}
                  </div>
                </div>
                {latestResult && (
                  <div>
                    <div style={{ 
                      padding: '4px 8px', 
                      borderRadius: '4px', 
                      fontSize: '0.8rem', 
                      fontWeight: 'bold',
                      backgroundColor: latestResult.overall_pass ? 'rgba(0, 255, 135, 0.1)' : 'rgba(255, 59, 107, 0.1)',
                      color: latestResult.overall_pass ? COLORS.green : COLORS.red,
                      border: `1px solid ${latestResult.overall_pass ? COLORS.green : COLORS.red}`
                    }}>
                      {latestResult.overall_pass ? 'PASS' : 'FAIL'}
                    </div>
                    {(evaluations[p.id]?.warnings?.length ?? 0) > 0 && (
                      <div style={{
                        fontSize: '0.75rem',
                        color: COLORS.red,
                        marginTop: '4px'
                      }}>
                        ⚠️ 일부 벤치마크 삭제됨
                      </div>
                    )}
                  </div>
                )}
              </div>
              <div style={{ fontSize: '0.85rem' }}>
                {latestResult ? (
                  <span className="td-muted">최근 결과: <b style={{ color: COLORS.text }}>{passCount}/{totalCount}</b> 지표 통과</span>
                ) : (
                  <span className="td-muted">평가 데이터 없음</span>
                )}
              </div>
            </div>
          );
        })}
        {profiles.length === 0 && !loading && (
          <div className="panel" style={{ gridColumn: '1 / -1', textAlign: 'center', padding: '40px' }}>
            <div className="td-muted">SLA 프로필을 생성하세요</div>
          </div>
        )}
      </div>

      <div className="panel">
        <div className="section-title">{editingId ? 'SLA 프로필 편집' : '새 SLA 프로필 생성'}</div>
        <form onSubmit={handleSubmit} className="form-grid" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '16px', marginBottom: '24px' }}>
          <div className="form-group">
            <label>프로필 이름 *</label>
            <input type="text" value={formName} onChange={e => setFormName(e.target.value)} required placeholder="예: Llama3 Production SLA" />
          </div>
          <div className="form-group">
            <label>가용성 최소 (%)</label>
            <input type="number" min="0" max="100" step="0.1" value={formAvailMin} onChange={e => setFormAvailMin(e.target.value)} placeholder="99.9" />
          </div>
          <div className="form-group">
            <label>P95 지연시간 최대 (ms)</label>
            <input type="number" min="0" step="1" value={formP95Ms} onChange={e => setFormP95Ms(e.target.value)} placeholder="500" />
          </div>
          <div className="form-group">
            <label>에러율 최대 (%)</label>
            <input type="number" min="0" max="100" step="0.1" value={formErrRate} onChange={e => setFormErrRate(e.target.value)} placeholder="1.0" />
          </div>
          <div className="form-group">
            <label>최소 TPS</label>
            <input type="number" min="0" step="0.1" value={formMinTps} onChange={e => setFormMinTps(e.target.value)} placeholder="10.0" />
          </div>
          <div className="form-actions" style={{ gridColumn: '1 / -1', display: 'flex', gap: '8px', justifyContent: 'flex-end' }}>
            {editingId && <button type="button" className="btn-secondary" onClick={resetForm}>취소</button>}
            <button type="submit" className="btn-primary">{editingId ? '저장' : '프로필 생성'}</button>
          </div>
        </form>

        <div className="section-title" style={{ marginTop: '32px' }}>SLA 프로필 목록</div>
        <table className="table">
          <thead>
            <tr>
              <th>이름</th>
              <th>벤치마크</th>
              <th>임계값 요약</th>
              <th style={{ textAlign: 'right' }}>작업</th>
            </tr>
          </thead>
          <tbody>
            {profiles.map(p => (
              <tr key={p.id}>
                <td className="td-text">{p.name}</td>
                <td style={{ fontSize: '0.85rem' }}>
                  {p.benchmark_ids.map((bid, idx) => {
                    const bName = availableBenchmarks.find(b => b.id === bid)?.name || `#${bid}`;
                    return <span key={bid} style={{ marginRight: '4px' }}><span style={{ color: TARGET_COLORS[idx % TARGET_COLORS.length] }}>●</span> {bName}</span>;
                  })}
                </td>
                <td className="td-muted" style={{ fontSize: '0.85rem' }}>{renderThresholds(p.thresholds)}</td>
                <td style={{ textAlign: 'right' }}>
                  <button className="btn-small" onClick={() => handleEdit(p)} style={{ marginRight: '8px' }}>편집</button>
                  <button className="btn-outline-small" onClick={() => handleDelete(p.id)} style={{ color: COLORS.red, borderColor: COLORS.red }}>삭제</button>
                </td>
              </tr>
            ))}
            {profiles.length === 0 && (
              <tr><td colSpan={4} className="td-muted" style={{ textAlign: 'center', padding: '20px' }}>등록된 프로필이 없습니다.</td></tr>
            )}
          </tbody>
        </table>
      </div>

      {selectedProfileId && (
        <div className="panel">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
            <div className="section-title" style={{ margin: 0 }}>{evaluations[selectedProfileId]?.profile.name} - 지표 추이</div>
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
          
          {(selectedEval?.results ?? []).length > 0 ? (
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
                    formatter={(value: any) => [value, chartMetric]}
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
                      strokeDasharray="5 5"
                      label={{ position: 'right', value: 'SLA', fill: COLORS.red, fontSize: 10 }}
                    />
                  )}
                </BarChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <div className="td-muted" style={{ textAlign: 'center', padding: '60px' }}>
              벤치마크를 할당하세요
            </div>
          )}
        </div>
      )}
    </div>
  );
}
