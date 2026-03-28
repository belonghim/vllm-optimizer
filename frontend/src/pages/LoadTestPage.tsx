import { useState, useEffect, useCallback, useRef } from "react";
import { authFetch } from '../utils/authFetch';
import { useMockData } from "../contexts/MockDataContext";
import { useClusterConfig } from "../contexts/ClusterConfigContext";
import { API, LOAD_TEST_PRESETS, SWEEP_PRESETS } from "../constants";
import { ERROR_MESSAGES } from "../constants/errorMessages";
import { useThemeColors } from "../contexts/ThemeContext";
import { fmt } from "../utils/format";
import MetricCard from "../components/MetricCard";
import Chart from "../components/Chart";
import SweepChart from "../components/SweepChart";
import { simulateLoadTest } from "../mockData";
import LoadTestConfig, { type RerunConfig } from "../components/LoadTestConfig";
import ErrorAlert from "../components/ErrorAlert";
import { useLoadTestSSE } from "../hooks/useLoadTestSSE";
import { useSSE } from "../hooks/useSSE";
import { calcGpuEfficiency } from "../utils/metrics";

// Sweep types
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

export interface SweepResult {
  config: SweepConfigState;
  steps: SweepStepResult[];
  saturation_point: number | null;
  optimal_rps: number | null;
  total_duration: number;
}


interface LoadTestPageProps {
  isActive: boolean;
  pendingConfig?: RerunConfig | null;
  onConfigConsumed?: () => void;
  onRunningChange?: (running: boolean) => void;
}

interface LoadTestConfigState {
  endpoint: string;
  model: string;
  total_requests: number;
  concurrency: number;
  rps: number;
  max_tokens: number;
  prompt_template: string;
  temperature: number;
  stream: boolean;
  [key: string]: string | number | boolean;
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

function LoadTestPage({ isActive, pendingConfig, onConfigConsumed, onRunningChange }: LoadTestPageProps) {
  const { COLORS } = useThemeColors();
  const { endpoint: globalEndpoint, inferenceservice, isLoading: globalIsLoading } = useClusterConfig();
  const [mode, setMode] = useState<'normal' | 'sweep'>('normal');

  // Normal mode state
  const [config, setConfig] = useState<LoadTestConfigState>({
    endpoint: "", model: inferenceservice || "auto", total_requests: 200, concurrency: 20,
    rps: 10, max_tokens: 256, prompt_template: "Hello, how are you?",
    temperature: 0.7, stream: true,
  });
  const [isSaving, setIsSaving] = useState(false);
  const [saveStatus, setSaveStatus] = useState<string | null>(null);
  const [interruptedWarning, setInterruptedWarning] = useState<string | null>(null);
  const { isMockEnabled } = useMockData();
  const { status, setStatus, isReconnecting, retryCount, error, setError,
    result, setResult, progress, setProgress, latencyData, setLatencyData,
    connect, disconnect } = useLoadTestSSE();
  const disconnectRef = useRef<typeof disconnect | undefined>(undefined);

  // Sweep mode state
  const [sweepConfig, setSweepConfig] = useState<SweepConfigState>({
    rps_start: 1,
    rps_end: 20,
    rps_step: 5,
    requests_per_step: 10,
    concurrency: 5,
    max_tokens: 128,
    prompt: "Explain quantum computing in simple terms",
    saturation_error_rate: 0.1,
    saturation_latency_factor: 3.0,
    min_stable_steps: 1,
    stream: true,
  });
  const [sweepStatus, setSweepStatus] = useState<'idle' | 'running' | 'completed' | 'stopped' | 'error'>('idle');
  const [sweepSteps, setSweepSteps] = useState<SweepStepResult[]>([]);
  const [sweepResult, setSweepResult] = useState<SweepResult | null>(null);
  const [sweepError, setSweepError] = useState<string | null>(null);
  const [sweepSSEUrl, setSweepSSEUrl] = useState<string | null>(null);
  const [sweepHistory, setSweepHistory] = useState<SweepResult[]>([]);
  const [sweepHistoryLoading, setSweepHistoryLoading] = useState(false);
  const [promptMode, setPromptMode] = useState<'static' | 'synthetic'>('static');
  const [syntheticConfig, setSyntheticConfig] = useState({
    distribution: 'uniform' as 'uniform' | 'normal',
    min_tokens: 50,
    max_tokens: 500,
    mean_tokens: 200,
    stddev_tokens: 50,
  });

  useEffect(() => {
    const isSweepRunning = sweepStatus === 'running';
    const isNormalRunning = status === 'running';
    onRunningChange?.(isNormalRunning || isSweepRunning);
  }, [status, sweepStatus, onRunningChange]);


  useEffect(() => {
    disconnectRef.current = disconnect;
  }, [disconnect]);

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

  const handleSyntheticConfigChange = (key: string, value: string | number) => {
    setSyntheticConfig(prev => ({ ...prev, [key]: value }));
  };

  const start = async () => {
    setStatus("running"); setResult(null); setLatencyData([]); setProgress(0);
    setError(null); setSaveStatus(null);
    if (isMockEnabled) {
      simulateLoadTest(
        config,
        setProgress,
        (mockResult) => setResult({ ...mockResult }),
        (mockStatus) => {
          if (
            mockStatus === "idle" ||
            mockStatus === "running" ||
            mockStatus === "completed" ||
            mockStatus === "error" ||
            mockStatus === "stopped"
          ) {
            setStatus(mockStatus);
          }
        },
        setLatencyData
      );
      return;
    }
      const payload = {
        ...config,
        prompt_mode: promptMode,
        ...(promptMode === 'synthetic' ? { synthetic_config: syntheticConfig } : {}),
      };
       try {
         const resp = await authFetch(`${API}/load_test/start`, {
           method: "POST", headers: { "Content-Type": "application/json" },
           body: JSON.stringify(payload),
         });
       if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
       const startData = await resp.json();
       if (startData.config?.model) setConfig(c => ({ ...c, model: startData.config.model }));
       connect(config.total_requests);
     } catch (err) {
       setError(`${ERROR_MESSAGES.LOAD_TEST.START_FAILED_PREFIX}${(err as Error).message}`); setStatus("error");
     }
  };

  const stop = async () => {
    if (mode === 'normal') {
      disconnect();
      await authFetch(`${API}/load_test/stop`, { method: "POST" });
      setStatus("stopped");
    } else {
      setSweepSSEUrl(null);
      await authFetch(`${API}/load_test/stop`, { method: "POST" });
      setSweepStatus("stopped");
    }
  };

  const saveAsBenchmark = async () => {
    if (isSaving || !result) return;
    setIsSaving(true); setSaveStatus(null);
    const name = `${config.model}-${Math.floor(Date.now() / 1000)}`;
    try {
      const resp = await authFetch(`${API}/benchmark/save`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, config, result }),
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      setSaveStatus("ok");
    } catch {
      setSaveStatus("error");
    } finally {
      setIsSaving(false);
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
    } catch {
      setSaveStatus("error");
    } finally {
      setIsSaving(false);
    }
  };

  const fetchSweepHistory = async () => {
    setSweepHistoryLoading(true);
    try {
      const resp = await authFetch(`${API}/load_test/sweep/history?limit=20`);
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json();
      setSweepHistory(data);
    } catch {
      // fail silently - history is optional
    } finally {
      setSweepHistoryLoading(false);
    }
  };

  const deleteSweepResult = async (sweepId: string) => {
    try {
      const resp = await authFetch(`${API}/load_test/sweep/history/${sweepId}`, { method: "DELETE" });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      await fetchSweepHistory();
    } catch {
      // fail silently
    }
  };

  useEffect(() => { return () => {
    disconnectRef.current?.();
  }}, [isMockEnabled]);

  useEffect(() => {
    if (!isActive) return;
    if (!globalIsLoading && globalEndpoint) {
      setConfig(c => ({ ...c, endpoint: c.endpoint || globalEndpoint }));
    }
  }, [isActive, globalIsLoading, globalEndpoint]);

  useEffect(() => {
    if (!isActive) return;
    if (isMockEnabled) return;

     const controller = new AbortController();
     authFetch(`${API}/status/interrupted`, { signal: controller.signal })
       .then(r => r.json())
       .then(data => {
         if (data.interrupted_runs && data.interrupted_runs.some((r: { task_type: string }) => r.task_type === "loadtest")) {
           setInterruptedWarning(ERROR_MESSAGES.LOAD_TEST.INTERRUPTED_WARNING);
         }
       })
       .catch(() => {});
     return () => controller.abort();
  }, [isActive, isMockEnabled]);

  useEffect(() => {
    if (mode === 'sweep' && isActive) {
      fetchSweepHistory();
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode, isActive]);

  const handleConfigChange = useCallback((key: string, value: string | number | boolean) => setConfig(c => ({ ...c, [key]: value })), []);
  const handleSweepConfigChange = useCallback((key: string, value: string | number | boolean) => setSweepConfig(c => ({ ...c, [key]: value })), []);

  const applyPreset = useCallback((preset: typeof LOAD_TEST_PRESETS[number]) => {
    setConfig(c => ({
      ...c,
      total_requests: preset.total_requests,
      concurrency: preset.concurrency,
      rps: preset.rps,
      max_tokens: preset.max_tokens,
      stream: preset.stream,
    }));
  }, []);

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

  // Sweep Logic

  const startSweep = async () => {
    setSweepStatus('running');
    setSweepSteps([]);
    setSweepResult(null);
    setSweepError(null);

    const body = {
      endpoint: config.endpoint,
      model: config.model,
      ...sweepConfig
    };

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


  const progressFillStyle = { width: `${progress}%` };
  const gpuEff = result ? calcGpuEfficiency(result) : null;

  const renderNormalMode = () => (
    <>
      <div className="panel" style={{ padding: '8px 16px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
          <span className="label label-no-mb" style={{ marginRight: '4px' }}>PRESETS:</span>
          {LOAD_TEST_PRESETS.map(preset => (
            <button
              key={preset.name}
              className="btn btn-outline"
              title={preset.description}
              onClick={() => applyPreset(preset)}
            >
              {preset.name}
            </button>
          ))}
        </div>
      </div>
      <LoadTestConfig
          config={config}
          onChange={handleConfigChange}
          onSubmit={start}
          onStop={stop}
          isRunning={status === "running"}
          status={status}
          initialConfig={pendingConfig}
          onInitialConfigApplied={onConfigConsumed}
          promptMode={promptMode}
          onPromptModeChange={setPromptMode}
          syntheticConfig={syntheticConfig}
          onSyntheticConfigChange={handleSyntheticConfigChange}
        />

      {isReconnecting && status === "running" && (
        <div className="loadtest-reconnect-banner" aria-live="assertive" role="alert">
          ↺ Reconnecting SSE... (attempt {retryCount}/3)
        </div>
      )}

      {interruptedWarning && (
        <div style={{display: 'flex', alignItems: 'flex-start', gap: '8px'}}>
          <ErrorAlert message={interruptedWarning} severity="warning" className="error-alert--mb8" />
          <button onClick={() => setInterruptedWarning(null)} style={{background:'none',border:'none',cursor:'pointer',padding:'4px',color:'var(--muted-color)',fontSize:'18px'}}>×</button>
        </div>
      )}

      <ErrorAlert message={error} className="error-alert--mb8" />

      {status === "running" && (
        <div className="panel" aria-live="polite" aria-label="Load test progress">
          <div className="loadtest-progress-header">
            <span className="label">Progress</span>
            <span className="loadtest-progress-pct">{progress}%</span>
          </div>
          <div className="progress-bar">
            <div className="progress-fill" style={progressFillStyle} />
          </div>
        </div>
      )}

       {result && gpuEff && (
         <div aria-live="polite">
            <div className="grid-5 gap-1">
             <MetricCard label="Mean TPS" value={fmt((result.tps as Record<string, number> | undefined)?.mean, 1)} unit="tok/s" color="amber" />
             <MetricCard label="TTFT Mean" value={fmt(((result.ttft as Record<string, number> | null)?.mean || 0) * 1000, 0)} unit="ms" color="cyan" />
             <MetricCard label="P99 Latency" value={fmt(((result.latency as Record<string, number> | null)?.p99 || 0) * 1000, 0)} unit="ms" color="red" />
             <MetricCard label="Success Rate"
               value={result.total ? fmt(((result.success as number) / (result.total as number)) * 100, 1) : "—"}
               unit="%" color="green" />
             <MetricCard label="GPU Eff."
               value={gpuEff.mismatch ? <span title="GPU metrics mismatch">N/A</span> : gpuEff.display}
               unit="tok/s/%" color="purple" />
           </div>

            <div className="panel">
              <div className="section-title">Latency Distribution</div>
              <table className="table" aria-label="Latency Detailed Results">
               <thead><tr><th>Metric</th><th>Value</th></tr></thead>
               <tbody>
                 {([
                   ["Total Requests", (result.total_requested ?? result.total) as number],
                   ["Success", result.success as number], ["Failed", result.failed as number],
                   ["Actual RPS", fmt(result.rps_actual as number | null | undefined, 2)],
                   ["Mean Latency", `${fmt(((result.latency as Record<string, number> | null)?.mean || 0) * 1000, 0)} ms`],
                   ["P50 Latency", `${fmt(((result.latency as Record<string, number> | null)?.p50 || 0) * 1000, 0)} ms`],
                   ["P95 Latency", `${fmt(((result.latency as Record<string, number> | null)?.p95 || 0) * 1000, 0)} ms`],
                   ["P99 Latency", `${fmt(((result.latency as Record<string, number> | null)?.p99 || 0) * 1000, 0)} ms`],
                   ["TTFT Mean", `${fmt(((result.ttft as Record<string, number> | null)?.mean || 0) * 1000, 0)} ms`],
                   ["TTFT P95", `${fmt(((result.ttft as Record<string, number> | null)?.p95 || 0) * 1000, 0)} ms`],
                   ["Total TPS", `${fmt((result.tps as Record<string, number> | null)?.total, 1)} tok/s`],
                   ["GPU Efficiency", gpuEff.mismatch ? <span title="GPU metrics mismatch">N/A</span> : gpuEff.value ? `${gpuEff.display} tok/s/%` : "—"],
                 ] as [string, React.ReactNode][]).map(([k, v]) => (
                   <tr key={k}>
                     <td className="td-muted">{k}</td>
                     <td className="td-accent-mono">{v}</td>
                   </tr>
                 ))}
               </tbody>
             </table>
           </div>

            {latencyData.length > 0 && (
              <Chart data={latencyData} title={ERROR_MESSAGES.LOAD_TEST.REALTIME_LATENCY} height={160} lines={[
                { key: "lat", color: COLORS.red, label: "Latency ms" },
                { key: "tps", color: COLORS.accent, label: "TPS" },
              ]} />
            )}

           {status === "completed" && result && !isMockEnabled && (
             <div className="loadtest-save-row">
               <button className="btn btn-primary" onClick={saveAsBenchmark}
                 disabled={isSaving || saveStatus === "ok"}>
                 {saveStatus === "ok" ? "✓ Saved" : isSaving ? "Saving..." : "⬆ Save as Benchmark"}
               </button>
               {saveStatus === "error" && (
                 <span className="loadtest-save-error">
                   ✗ Save failed
                 </span>
               )}
              </div>
            )}
         </div>
       )}
    </>
  );

  const renderSweepMode = () => (
    <>
      <div className="panel" style={{ padding: '8px 16px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
          <span className="label label-no-mb" style={{ marginRight: '4px' }}>SWEEP PRESETS:</span>
          {SWEEP_PRESETS.map(preset => (
            <button
              key={preset.name}
              className="btn btn-outline"
              title={preset.description}
              onClick={() => applySweepPreset(preset)}
            >
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
                value={sweepConfig[key as keyof SweepConfigState]}
                onChange={e => handleSweepConfigChange(key, type === "number" ? +e.target.value : e.target.value)}
                disabled={sweepStatus === 'running'}
              />
            </div>
          ))}
        </div>
        <div className="loadtest-config-actions">
          <button className="btn btn-primary" onClick={startSweep} disabled={sweepStatus === 'running'}>
            ▶ Start Sweep
          </button>
          <button className="btn btn-danger" onClick={stop} disabled={sweepStatus !== 'running'}>
            ■ Stop
          </button>
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
              <tr>
                <th>Step</th><th>RPS</th><th>P99 Latency</th><th>TPS</th><th>Success %</th><th>Status</th>
              </tr>
            </thead>
            <tbody>
              {sweepSteps.map((step, index) => (
                <tr key={index} data-testid="sweep-step-row" style={step.saturated ? { backgroundColor: 'rgba(255,59,107,0.15)' } : {}}>
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
            <MetricCard label="Optimal RPS" value={sweepResult.optimal_rps ?? 'N/A'} color="green" />
            <MetricCard label="Saturation RPS" value={sweepResult.saturation_point ?? 'None'} color="red" />
            <MetricCard label="Total Steps" value={sweepResult.steps.length} color="cyan" />
            <MetricCard label="Duration" value={`${fmt(sweepResult.total_duration, 1)}s`} color="amber" />
          </div>
          {sweepResult.steps && sweepResult.steps.length > 0 && (
            <SweepChart steps={sweepResult.steps} saturationRps={sweepResult.saturation_point} />
          )}
          {sweepStatus === 'completed' && (
            <div className="loadtest-save-row">
              <button
                className="btn btn-primary"
                onClick={() => saveSweepAsBenchmark(sweepResult)}
                disabled={isSaving || saveStatus === 'ok'}
              >
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
                const hAny = h as Record<string, unknown>;
                const sweepId = hAny.sweep_id as string | undefined;
                return (
                  <tr key={sweepId ?? idx}>
                    <td>{fmt(h.optimal_rps as number | null | undefined, 1) ?? 'N/A'}</td>
                    <td>{Array.isArray(h.steps) ? h.steps.length : '—'}</td>
                    <td>{fmt(h.total_duration, 1)}s</td>
                    <td>
                      {sweepId && (
                        <button
                          className="btn btn-danger"
                          style={{ padding: '2px 8px', fontSize: '12px' }}
                          onClick={() => deleteSweepResult(sweepId)}
                        >
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

  return (
    <div className="flex-col-16">
      <div className="tabs">
        <button className={`tab ${mode === 'normal' ? 'active' : ''}`} onClick={() => setMode('normal')}>Normal Test</button>
        <button className={`tab ${mode === 'sweep' ? 'active' : ''}`} onClick={() => setMode('sweep')}>Sweep Test</button>
      </div>
      {mode === 'normal' ? renderNormalMode() : renderSweepMode()}
    </div>
  );
}

export default LoadTestPage;
