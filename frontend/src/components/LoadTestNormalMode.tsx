import { useState, useEffect, useCallback, useRef } from "react";
import type { ReactNode } from "react";
import { authFetch } from '../utils/authFetch';
import { useMockData } from "../contexts/MockDataContext";
import { useClusterConfig } from "../contexts/ClusterConfigContext";
import { API, LOAD_TEST_PRESETS } from "../constants";
import { ERROR_MESSAGES } from "../constants/errorMessages";
import { useThemeColors } from "../contexts/ThemeContext";
import { fmt } from "../utils/format";
import MetricCard from "./MetricCard";
import Chart from "./Chart";
import { simulateLoadTest } from "../mockData";
import LoadTestConfig, { type RerunConfig } from "./LoadTestConfig";
import ErrorAlert from "./ErrorAlert";
import { useLoadTestSSE } from "../hooks/useLoadTestSSE";
import { calcGpuEfficiency } from "../utils/metrics";

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

interface LoadTestNormalModeProps {
  isActive: boolean;
  pendingConfig?: RerunConfig | null;
  onConfigConsumed?: () => void;
  onRunningChange?: (running: boolean) => void;
  onEndpointChange?: (endpoint: string) => void;
  onModelChange?: (model: string) => void;
  targetEndpoint?: string;
  targetModel?: string;
}

function LoadTestNormalMode({ isActive, pendingConfig, onConfigConsumed, onRunningChange, onEndpointChange, onModelChange, targetEndpoint, targetModel }: LoadTestNormalModeProps) {
  const { COLORS } = useThemeColors();
  const { endpoint: globalEndpoint, isLoading: globalIsLoading, resolvedModelName } = useClusterConfig();
  const { isMockEnabled } = useMockData();
  const [config, setConfig] = useState<LoadTestConfigState>({
    endpoint: "", model: resolvedModelName || "auto", total_requests: 200, concurrency: 20,
    rps: 10, max_tokens: 256, prompt_template: "Hello, how are you?",
    temperature: 0.7, stream: true,
  });
  const [isSaving, setIsSaving] = useState(false);
  const [saveStatus, setSaveStatus] = useState<string | null>(null);
  const [interruptedWarning, setInterruptedWarning] = useState<string | null>(null);
  const [promptMode, setPromptMode] = useState<'static' | 'synthetic'>('static');
  const [syntheticConfig, setSyntheticConfig] = useState({
    distribution: 'uniform' as 'uniform' | 'normal',
    min_tokens: 50,
    max_tokens: 500,
    mean_tokens: 200,
    stddev_tokens: 50,
  });
  const { status, setStatus, isReconnecting, retryCount, error, setError,
    result, setResult, progress, setProgress, latencyData, setLatencyData,
    connect, disconnect } = useLoadTestSSE();
  const disconnectRef = useRef<typeof disconnect | undefined>(undefined);

  useEffect(() => { disconnectRef.current = disconnect; }, [disconnect]);

  useEffect(() => {
    onRunningChange?.(status === 'running');
  }, [status, onRunningChange]);

  useEffect(() => {
    onEndpointChange?.(config.endpoint);
  }, [config.endpoint, onEndpointChange]);

  useEffect(() => {
    onModelChange?.(config.model);
  }, [config.model, onModelChange]);

  useEffect(() => { return () => { disconnectRef.current?.(); }; }, [isMockEnabled]);

  useEffect(() => {
    if (!isActive) return;
    const endpointToUse = targetEndpoint || globalEndpoint;
    if (!globalIsLoading && endpointToUse) {
      setConfig(c => ({ ...c, endpoint: endpointToUse }));
    }
  }, [isActive, globalIsLoading, globalEndpoint, targetEndpoint]);

  useEffect(() => {
    if (!isActive) return;
    if (!globalIsLoading && resolvedModelName) {
      setConfig(c => ({ ...c, model: resolvedModelName }));
    }
  }, [isActive, globalIsLoading, resolvedModelName]);

  useEffect(() => {
    if (!isActive) return;
    if (targetModel) {
      setConfig(c => ({ ...c, model: targetModel }));
    }
  }, [isActive, targetModel]);

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
      .catch((error) => { console.warn('Failed to check interrupted status:', error); });
    return () => controller.abort();
  }, [isActive, isMockEnabled]);

  const handleConfigChange = useCallback((key: string, value: string | number | boolean) => setConfig(c => ({ ...c, [key]: value })), []);
  const handleSyntheticConfigChange = (key: string, value: string | number) => setSyntheticConfig(prev => ({ ...prev, [key]: value }));

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

  const start = async () => {
    setStatus("running"); setResult(null); setLatencyData([]); setProgress(0);
    setError(null); setSaveStatus(null);
    if (isMockEnabled) {
      simulateLoadTest(
        config,
        setProgress,
        (mockResult) => setResult({ ...mockResult }),
        (mockStatus) => {
          if (mockStatus === "idle" || mockStatus === "running" || mockStatus === "completed" || mockStatus === "error" || mockStatus === "stopped") {
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
    try {
      disconnect();
      await authFetch(`${API}/load_test/stop`, { method: "POST" });
      setStatus("stopped");
    } catch (err) {
      console.error('Failed to stop load test:', err);
      setError(`Failed to stop load test: ${(err as Error).message}`);
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
     } catch (e) {
       console.error('Failed to save load test result as benchmark', e);
       setSaveStatus("error");
     } finally {
       setIsSaving(false);
     }
   };

  const progressFillStyle = { width: `${progress}%` };
  const gpuEff = result ? calcGpuEfficiency(result) : null;

  return (
    <>
      <div className="panel" style={{ padding: '8px 16px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
          <span className="label label-no-mb" style={{ marginRight: '4px' }}>PRESETS:</span>
          {LOAD_TEST_PRESETS.map(preset => (
            <button key={preset.name} className="btn btn-outline" title={preset.description} onClick={() => applyPreset(preset)}>
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
          <button aria-label="Dismiss interrupted load test warning" onClick={() => setInterruptedWarning(null)} style={{background:'none',border:'none',cursor:'pointer',padding:'4px',color:'var(--muted-color)',fontSize:'18px'}}>×</button>
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
                ] as [string, ReactNode][]).map(([k, v]) => (
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
              <button className="btn btn-primary" onClick={() => saveAsBenchmark().catch((e) => console.error("Failed to save as benchmark:", e))} disabled={isSaving || saveStatus === "ok"}>
                {saveStatus === "ok" ? "✓ Saved" : isSaving ? "Saving..." : "⬆ Save as Benchmark"}
              </button>
              {saveStatus === "error" && <span className="loadtest-save-error">✗ Save failed</span>}
            </div>
          )}
        </div>
      )}
    </>
  );
}

export default LoadTestNormalMode;
