import { useState, useEffect } from "react";
import { authFetch } from '../utils/authFetch';
import { API } from "../constants";
import { fmt } from "../utils/format";
import MetricCard from "./MetricCard";

interface TuningSessionSummary {
  id: number;
  timestamp: number;
  objective: string;
  n_trials: number;
  best_score: number | null;
  best_tps: number | null;
  best_p99: number | null;
}

interface TuningSessionDetail {
  id: number;
  timestamp: number;
  objective: string;
  best_params: Record<string, unknown> | null;
  best_tps: number | null;
  best_p99: number | null;
  trials: unknown[];
}

export default function TunerHistoryPanel() {
  const [sessions, setSessions] = useState<TuningSessionSummary[]>([]);
  const [selectedIds, setSelectedIds] = useState<number[]>([]);
  const [compareData, setCompareData] = useState<TuningSessionDetail[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchSessions = async () => {
    try {
      const res = await authFetch(`${API}/tuner/sessions`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setSessions(Array.isArray(data) ? data : []);
    } catch (err) {
      setError(`Failed to fetch history: ${(err as Error).message}`);
    }
  };

  useEffect(() => {
    fetchSessions();
  }, []);

  const toggleSelect = (id: number) => {
    setSelectedIds(prev => {
      if (prev.includes(id)) return prev.filter(x => x !== id);
      if (prev.length >= 2) return prev;
      return [...prev, id];
    });
  };

  const handleDelete = async (id: number, e: React.MouseEvent) => {
    e.stopPropagation();
    if (!window.confirm("Delete this tuning session?")) return;
    try {
      const res = await authFetch(`${API}/tuner/sessions/${id}`, { method: 'DELETE' });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setSessions(prev => prev.filter(s => s.id !== id));
      setSelectedIds(prev => prev.filter(x => x !== id));
      if (compareData.some(d => d.id === id)) {
        setCompareData(prev => prev.filter(d => d.id !== id));
      }
    } catch (err) {
      setError(`Delete failed: ${(err as Error).message}`);
    }
  };

  const handleCompare = async () => {
    if (selectedIds.length !== 2) return;
    setIsLoading(true);
    setError(null);
    try {
      const details = await Promise.all(
        selectedIds.map(async (id) => {
          const res = await authFetch(`${API}/tuner/sessions/${id}`);
          if (!res.ok) throw new Error(`HTTP ${res.status} (Session ${id})`);
          return res.json();
        })
      );
      setCompareData(details);
    } catch (err) {
      setError(`Failed to fetch comparison data: ${(err as Error).message}`);
    } finally {
      setIsLoading(false);
    }
  };

  const allParamKeys = Array.from(new Set(
    compareData.flatMap(d => d.best_params ? Object.keys(d.best_params) : [])
  )).sort();

  return (
    <div className="flex-col-16">
      <div className="panel">
        <div className="section-title">Tuning History</div>
        {error && <div className="error-msg" style={{marginBottom: '12px'}}>{error}</div>}
        
        <div style={{ marginBottom: '12px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span className="td-muted">{selectedIds.length} / 2 selected</span>
          <button 
            className="btn-primary" 
            disabled={selectedIds.length !== 2 || isLoading}
            onClick={handleCompare}
          >
            {isLoading ? "Loading..." : "Compare Selected"}
          </button>
        </div>

        <table className="table">
          <thead>
            <tr>
              <th style={{width: '40px'}}></th>
              <th>Date</th>
              <th>Objective</th>
              <th>Trials</th>
              <th>Best TPS</th>
              <th>Best P99</th>
              <th style={{width: '60px'}}>Delete</th>
            </tr>
          </thead>
          <tbody>
            {sessions.map(s => (
              <tr 
                key={s.id} 
                onClick={() => toggleSelect(s.id)}
                onKeyDown={(e) => (e.key === " " || e.key === "Enter") && toggleSelect(s.id)}
                tabIndex={0}
                style={{ cursor: 'pointer', backgroundColor: selectedIds.includes(s.id) ? 'var(--bg-highlight)' : 'transparent' }}
              >
                <td>
                  <input 
                    type="checkbox" 
                    checked={selectedIds.includes(s.id)} 
                    onChange={() => {}} 
                    disabled={!selectedIds.includes(s.id) && selectedIds.length >= 2}
                  />
                </td>
                <td className="td-muted">{new Date(s.timestamp * 1000).toLocaleString()}</td>
                <td className="td-cyan">{s.objective}</td>
                <td>{s.n_trials}</td>
                <td className="td-accent">{fmt(s.best_tps, 1)}</td>
                <td className="td-red">{fmt(s.best_p99, 0)}</td>
                <td>
                  <button className="btn-icon" aria-label={`Delete tuning session ${s.id}`} onClick={(e) => handleDelete(s.id, e)}>✕</button>
                </td>
              </tr>
            ))}
            {sessions.length === 0 && (
              <tr><td colSpan={7} className="td-muted" style={{textAlign: 'center', padding: '24px'}}>No saved history.</td></tr>
            )}
          </tbody>
        </table>
      </div>

      {compareData.length === 2 && (
        <div className="panel tuner-compare-panel">
          <div className="section-title">Session Comparison</div>
          
          <div className="grid-2" style={{ gap: '24px', marginBottom: '24px' }}>
            {compareData.map((d) => (
              <div key={d.id} className="compare-column">
                <div className="td-muted" style={{ marginBottom: '8px', fontSize: '12px' }}>
                  Session #{d.id} ({new Date((sessions.find(s => s.id === d.id)?.timestamp || 0) * 1000).toLocaleString()})
                </div>
                <div className="grid-2" style={{ gap: '8px' }}>
                  <MetricCard label="Best TPS" value={fmt(d.best_tps, 1)} unit="tok/s" color="amber" />
                  <MetricCard label="P99 Latency" value={fmt(d.best_p99, 0)} unit="ms" color="cyan" />
                </div>
              </div>
            ))}
          </div>

          <table className="table">
            <thead>
              <tr>
                <th>Parameter</th>
                <th>Session #{compareData[0].id}</th>
                <th>Session #{compareData[1].id}</th>
              </tr>
            </thead>
            <tbody>
              {allParamKeys.map(key => {
                const val0 = compareData[0].best_params?.[key];
                const val1 = compareData[1].best_params?.[key];
                const isDifferent = String(val0) !== String(val1);
                
                return (
                  <tr key={key}>
                    <td className="td-muted">{key}</td>
                    <td className={isDifferent ? "td-green" : ""}>{val0 !== undefined ? String(val0) : "—"}</td>
                    <td className={isDifferent ? "td-green" : ""}>{val1 !== undefined ? String(val1) : "—"}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
