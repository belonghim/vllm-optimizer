import React, { useState, useEffect } from "react";
import { authFetch } from '../utils/authFetch';
import { API, COLORS, TOOLTIP_STYLE } from "../constants";
import ErrorAlert from "../components/ErrorAlert";
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ReferenceLine, ResponsiveContainer } from 'recharts';

interface SlaThresholds {
  availability_min: number | null;
  p95_latency_max_ms: number | null;
  error_rate_max_pct: number | null;
  min_tps: number | null;
}

interface SlaProfile {
  id: number;
  name: string;
  model: string;
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
}

export default function SlaPage({ isActive }: { isActive: boolean }) {
  const [profiles, setProfiles] = useState<SlaProfile[]>([]);
  const [evaluations, setEvaluations] = useState<Record<number, SlaEvaluateResponse>>({});
  const [selectedProfileId, setSelectedProfileId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const [formName, setFormName] = useState('');
  const [formModel, setFormModel] = useState('');
  const [formAvailMin, setFormAvailMin] = useState('');
  const [formP95Ms, setFormP95Ms] = useState('');
  const [formErrRate, setFormErrRate] = useState('');
  const [formMinTps, setFormMinTps] = useState('');
  const [editingId, setEditingId] = useState<number | null>(null);

  const [chartMetric, setChartMetric] = useState<'p95_latency' | 'availability' | 'error_rate' | 'min_tps'>('p95_latency');

  useEffect(() => {
    if (!isActive) return;
    loadProfiles();
  }, [isActive]);

  async function loadProfiles() {
    setLoading(true);
    try {
      const res = await authFetch(`${API}/sla/profiles`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data: SlaProfile[] = await res.json();
      setProfiles(data);
      
      const newEvals: Record<number, SlaEvaluateResponse> = {};
      for (const p of data) {
        try {
          const evalRes = await authFetch(`${API}/sla/evaluate/${p.id}`);
          if (evalRes.ok) {
            newEvals[p.id] = await evalRes.json();
          }
        } catch (e) {
          console.error(`Failed to load evaluation for profile ${p.id}`, e);
        }
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
    const body = {
      name: formName,
      model: formModel,
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
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      
      resetForm();
      await loadProfiles();
    } catch (err) {
      setError(`SLA 프로필 저장 실패: ${(err as Error).message}`);
    }
  };

  const handleEdit = (p: SlaProfile) => {
    setEditingId(p.id);
    setFormName(p.name);
    setFormModel(p.model);
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
    setFormModel('');
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
      name: new Date(r.timestamp * 1000).toLocaleDateString(),
      value: verdict?.value ?? null,
      threshold: verdict?.threshold ?? null,
    };
  });

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
                  <div className="td-muted" style={{ fontSize: '0.85rem' }}>{p.model}</div>
                </div>
                {latestResult && (
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
            <label>대상 모델 *</label>
            <input type="text" value={formModel} onChange={e => setFormModel(e.target.value)} required placeholder="예: llama-3.1-8b" />
          </div>
          <div className="form-group">
            <label>가용성 최소 (%)</label>
            <input type="number" step="0.1" value={formAvailMin} onChange={e => setFormAvailMin(e.target.value)} placeholder="99.9" />
          </div>
          <div className="form-group">
            <label>P95 지연시간 최대 (ms)</label>
            <input type="number" value={formP95Ms} onChange={e => setFormP95Ms(e.target.value)} placeholder="500" />
          </div>
          <div className="form-group">
            <label>에러율 최대 (%)</label>
            <input type="number" step="0.1" value={formErrRate} onChange={e => setFormErrRate(e.target.value)} placeholder="1.0" />
          </div>
          <div className="form-group">
            <label>최소 TPS</label>
            <input type="number" step="0.1" value={formMinTps} onChange={e => setFormMinTps(e.target.value)} placeholder="10.0" />
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
              <th>모델</th>
              <th>임계값 요약</th>
              <th style={{ textAlign: 'right' }}>작업</th>
            </tr>
          </thead>
          <tbody>
            {profiles.map(p => (
              <tr key={p.id}>
                <td className="td-text">{p.name}</td>
                <td className="td-cyan">{p.model}</td>
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
          
          {chartData.length > 0 ? (
            <div style={{ height: '300px', width: '100%' }}>
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={chartData} margin={{ top: 10, right: 30, left: 0, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke={COLORS.border} />
                  <XAxis dataKey="name" tick={{ fontSize: 11, fill: COLORS.muted }} />
                  <YAxis tick={{ fontSize: 11, fill: COLORS.muted }} />
                  <Tooltip 
                    contentStyle={TOOLTIP_STYLE}
                    itemStyle={{ fontSize: '12px' }}
                    labelStyle={{ fontSize: '12px', fontWeight: 'bold', marginBottom: '4px' }}
                  />
                  <Line 
                    type="monotone" 
                    dataKey="value" 
                    stroke={COLORS.cyan} 
                    strokeWidth={2}
                    dot={{ r: 4, fill: COLORS.cyan }} 
                    activeDot={{ r: 6 }}
                    name={chartMetric}
                    connectNulls
                  />
                  {chartData[0]?.threshold != null && (
                    <ReferenceLine 
                      y={chartData[0].threshold} 
                      stroke={COLORS.red} 
                      strokeDasharray="5 5" 
                      label={{ position: 'right', value: 'SLA', fill: COLORS.red, fontSize: 10 }} 
                    />
                  )}
                </LineChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <div className="td-muted" style={{ textAlign: 'center', padding: '60px' }}>
              해당 모델의 벤치마크가 없습니다.
            </div>
          )}
        </div>
      )}
    </div>
  );
}
