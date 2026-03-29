import { useState, useEffect, useCallback } from "react";
import { authFetch } from '../utils/authFetch';
import { API, SWEEP_PRESETS } from "../constants";
import { useThemeColors } from "../contexts/ThemeContext";
import { fmt } from "../utils/format";
import MetricCard from "./MetricCard";
import SweepChart from "./SweepChart";
import ErrorAlert from "./ErrorAlert";
import { useSSE } from "../hooks/useSSE";

export interface SweepStepResult {
  step: number;
  rps: number;
  stats: {
    latency: { p99: number; mean: number };
    tps: { mean: number };
    success: number;
    failed: number;
    total: number;
    rps_actual: number;
  };
  saturated: boolean;
  saturation_reason: string | null;
}

interface SweepConfigState {
  rps_start: number;
  rps_end: number;
  rps_step: number;
  requests_per_step: number;
  concurrency: number;
  max_tokens: number;
  prompt: string;
  saturation_error_rate: number;
  saturation_latency_factor: number;
  min_stable_steps: number;
  stream: boolean;
}

export interface SweepResult {
  config: SweepConfigState;
  steps: SweepStepResult[];
  saturation_point: number | null;
  optimal_rps: number | null;
  total_duration: number;
}

interface LoadTestSweepModeProps {
  isActive: boolean;
  onRunningChange?: (running: boolean) => void;
  endpoint: string;
  model: string;
}

function LoadTestSweepMode({ isActive, onRunningChange, endpoint, model }: LoadTestSweepModeProps) {
  const { COLORS } = useThemeColors();
  const [sweepConfig, setSweepConfig] = useState<SweepConfigState>({
    rps_start: 1, rps_end: 20, rps_step: 5, requests_per_step: 10,
    concurrency: 5, max_tokens: 128, prompt: "Explain quantum computing in simple terms",
    saturation_error_rate: 0.1, saturation_latency_factor: 3.0, min_stable_steps: 1, stream: true,
  });
  const [sweepStatus, setSweepStatus] = useState<'idle' | 'running' | 'completed' | 'stopped' | 'error'>('idle');
  const [sweepSteps, setSweepSteps] = useState<SweepStepResult[]>([]);
  const [sweepResult, setSweepResult] = useState<SweepResult | null>(null);
  const [sweepError, setSweepError] = useState<string | null>(null);
  const [sweepSSEUrl, setSweepSSEUrl] = useState<string | null>(null);
  const [sweepHistory, setSweepHistory] = useState<SweepResult[]>([]);
  const [sweepHistoryLoading, setSweepHistoryLoading] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [saveStatus, setSaveStatus] = useState<string | null>(null);

  useEffect(() => {
    onRunningChange?.(sweepStatus === 'running');
  }, [sweepStatus, onRunningChange]);

  useSSE(sweepSSEUrl, {
    sweep_step: (data) => setSweepSteps(prev => [...prev, data as SweepStepResult]),
    sweep_completed: (data) => {
      setSweepResult(data as SweepResult);
      setSweepStatus('completed');
      setSweepSSEUrl(null);
    },
    stopped: () => {
      setSweepStatus('stopped');
      setSweepSSEUrl(null);
    },
    error: (data) => {
      setSweepError((data as { error?: string } | null)?.error || "An unknown error occurred during the sweep test.");
      setSweepStatus('error');
      setSweepSSEUrl(null);
    },
  }, {
    onError: () => {
      setSweepError("SSE connection failed.");
      setSweepStatus('error');
      setSweepSSEUrl(null);
    },
  });

   const fetchSweepHistory = async () => {
     setSweepHistoryLoading(true);
     try {
       const resp = await authFetch(`${API}/load_test/sweep/history?limit=20`);
       if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
       const data = await resp.json();
       setSweepHistory(data);
     } catch (e) {
       console.error('Failed to fetch sweep test history', e);
       // fail silently - history is optional
     } finally {
       setSweepHistoryLoading(false);
     }
   };

  useEffect(() => {
    if (isActive) fetchSweepHistory();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isActive]);

  const handleSweepConfigChange = useCallback((key: string, value: string | number | boolean) => setSweepConfig(c => ({ ...c, [key]: value })), []);

  const applySweepPreset = useCallback((preset: typeof SWEEP_PRESETS[number]) => {
    setSweepConfig(c => ({
      ...c,
      rps_start: preset.rps_start,
      rps_end: preset.rps_end,
      rps_step: preset.rps_step,
      requests_per_step: preset.requests_per_step,
      concurrency: preset.concurrency,
    }));
  }, []);

  const startSweep = async () => {
    setSweepStatus('running');
    setSweepSteps([]);
    setSweepResult(null);
    setSweepError(null);

    const body = { endpoint, model, ...sweepConfig };
    try {
      const resp = await authFetch(`${API}/load_test/sweep`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      if (!resp.ok) {
        const errorData = await resp.json().catch(() => ({ detail: `HTTP ${resp.status}` }));
        throw new Error(errorData.detail || `HTTP ${resp.status}`);
      }
      setSweepSSEUrl(`${API}/load_test/stream`);
    } catch (err) {
      setSweepError((err as Error).message);
      setSweepStatus('error');
    }
  };

  const stop = async () => {
    try {
      setSweepSSEUrl(null);
      await authFetch(`${API}/load_test/stop`, { method: "POST" });
      setSweepStatus("stopped");
    } catch (err) {
      console.error('Failed to stop load test:', err);
      setSweepError(`Failed to stop load test: ${(err as Error).message}`);
    }
  };

   const saveSweepAsBenchmark = async (sweep: SweepResult) => {
     if (isSaving || !sweep) return;
     setIsSaving(true); setSaveStatus(null);
     try {
       const resp = await authFetch(`${API}/load_test/sweep/save`, {
         method: "POST", headers: { "Content-Type": "application/json" },
         body: JSON.stringify(sweep),
       });
       if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
       setSaveStatus("ok");
       await fetchSweepHistory();
     } catch (e) {
       console.error('Failed to save sweep test result as benchmark', e);
       setSaveStatus("error");
     } finally {
       setIsSaving(false);
     }
   };

   const deleteSweepResult = async (sweepId: string) => {
     try {
       const resp = await authFetch(`${API}/load_test/sweep/history/${sweepId}`, { method: "DELETE" });
       if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
       await fetchSweepHistory();
     } catch (e) {
       console.error('Failed to delete sweep result', e);
       // fail silently
     }
   };

  return (
    <>
      <div className="panel" style={{ padding: '8px 16px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
          <span className="label label-no-mb" style={{ marginRight: '4px' }}>SWEEP PRESETS:</span>
          {SWEEP_PRESETS.map(preset => (
            <button key={preset.name} className="btn btn-outline" title={preset.description} onClick={() => applySweepPreset(preset)}>
              {preset.name}
            </button>
          ))}
        </div>
      </div>

      <div className="panel">
        <div className="section-title">Sweep Test Settings</div>
        <div className="grid-form grid-form-compact">
          {([
            ["RPS Start", "rps_start", "number"], ["RPS End", "rps_end", "number"], ["RPS Step", "rps_step", "number"],
            ["Requests/Step", "requests_per_step", "number"], ["Concurrency", "concurrency", "number"], ["Max Tokens", "max_tokens", "number"],
            ["Saturation Error Rate", "saturation_error_rate", "number"],
            ["Min Stable Steps", "min_stable_steps", "number"],
          ] as const).map(([label, key, type]) => (
            <div key={key}>
              <label className="label">{label}</label>
              <input
                className="input" type={type} aria-label={label}
                value={sweepConfig[key as keyof SweepConfigState] as string | number}
                onChange={e => handleSweepConfigChange(key, type === "number" ? +e.target.value : e.target.value)}
                disabled={sweepStatus === 'running'}
              />
            </div>
          ))}
        </div>
        <div className="loadtest-config-actions">
          <button className="btn btn-primary" onClick={startSweep} disabled={sweepStatus === 'running'}>▶ Start Sweep</button>
          <button className="btn btn-danger" onClick={stop} disabled={sweepStatus !== 'running'}>■ Stop</button>
          <span className={`tag tag-${sweepStatus}`}>{sweepStatus.toUpperCase()}</span>
        </div>
      </div>

      <ErrorAlert message={sweepError} className="error-alert--mb8" />

      {sweepStatus === 'running' && (
        <div className="panel" aria-live="polite">
          <div className="loadtest-progress-header">
            {sweepSteps.length === 0 ? (
              <span className="label">Starting Sweep...</span>
            ) : (
              <span className="label">Step {sweepSteps.length + 1} In Progress...</span>
            )}
          </div>
        </div>
      )}

      {sweepSteps.length > 0 && (
        <div className="panel">
          <div className="section-title">Sweep Results</div>
          <table className="table" aria-label="Sweep Step Results">
            <thead>
              <tr><th>Step</th><th>RPS</th><th>P99 Latency</th><th>TPS</th><th>Success %</th><th>Status</th></tr>
            </thead>
            <tbody>
              {sweepSteps.map((step, index) => (
                <tr key={index} data-testid="sweep-step-row" style={step.saturated ? { backgroundColor: 'var(--sweep-step-bg)' } : {}}>
                  <td>{step.step}</td>
                  <td>{fmt(step.rps, 1)}</td>
                  <td>{fmt(step.stats.latency.p99 * 1000, 0)} ms</td>
                  <td>{fmt(step.stats.tps.mean, 1)}</td>
                  <td>{fmt(step.stats.total > 0 ? (step.stats.success / step.stats.total) * 100 : 0, 1)}%</td>
                  <td>{step.saturated ? <span style={{color: COLORS.red}} title={step.saturation_reason ?? ''}>Saturated</span> : 'OK'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {sweepResult && (
        <div className="flex-col-16">
          <div className="grid-5 gap-1">
            <MetricCard label="Optimal RPS" value={sweepResult.optimal_rps ?? 'N/A'} unit="" color="green" />
            <MetricCard label="Saturation RPS" value={sweepResult.saturation_point ?? 'None'} unit="" color="red" />
            <MetricCard label="Total Steps" value={sweepResult.steps.length} unit="" color="cyan" />
            <MetricCard label="Duration" value={`${fmt(sweepResult.total_duration, 1)}s`} unit="" color="amber" />
          </div>
          {sweepResult.steps && sweepResult.steps.length > 0 && (
            <SweepChart steps={sweepResult.steps} saturationRps={sweepResult.saturation_point} />
          )}
          {sweepStatus === 'completed' && (
            <div className="loadtest-save-row">
              <button className="btn btn-primary" onClick={() => saveSweepAsBenchmark(sweepResult)} disabled={isSaving || saveStatus === 'ok'}>
                {saveStatus === 'ok' ? '✓ Saved' : isSaving ? 'Saving...' : '⬆ Save to Benchmark'}
              </button>
            </div>
          )}
        </div>
      )}

      {sweepHistory.length > 0 && (
        <div className="panel">
          <div className="section-title">Sweep Save History</div>
          {sweepHistoryLoading && <div className="label">Loading...</div>}
          <table className="table" aria-label="Saved Sweep Results List">
            <thead>
              <tr><th>Optimal RPS</th><th>Steps</th><th>Duration</th><th>Actions</th></tr>
            </thead>
            <tbody>
              {sweepHistory.map((h, idx) => {
                const hAny = h as unknown as Record<string, unknown>;
                const sweepId = hAny.sweep_id as string | undefined;
                return (
                  <tr key={sweepId ?? idx}>
                    <td>{fmt(h.optimal_rps as number | null | undefined, 1) ?? 'N/A'}</td>
                    <td>{Array.isArray(h.steps) ? h.steps.length : '—'}</td>
                    <td>{fmt(h.total_duration, 1)}s</td>
                    <td>
                      {sweepId && (
                        <button className="btn btn-danger" style={{ padding: '2px 8px', fontSize: '12px' }} onClick={() => deleteSweepResult(sweepId)}>
                          Delete
                        </button>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}

export default LoadTestSweepMode;
