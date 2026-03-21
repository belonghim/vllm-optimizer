import { useState, useEffect } from "react";
import { useMockData } from "../contexts/MockDataContext";
import { useClusterConfig } from "../contexts/ClusterConfigContext";
import { API, COLORS } from "../constants";
import MetricCard from "../components/MetricCard";
import Chart from "../components/Chart";
import { simulateLoadTest } from "../mockData";
import LoadTestConfig from "../components/LoadTestConfig";
import ErrorAlert from "../components/ErrorAlert";
import { useLoadTestSSE } from "../hooks/useLoadTestSSE";

const fmt = (n, d = 1) => (n == null ? "—" : Number(n).toFixed(d));

function LoadTestPage() {
  const { endpoint: globalEndpoint, inferenceservice, isLoading: globalIsLoading } = useClusterConfig();
  const [config, setConfig] = useState({
    endpoint: "", model: inferenceservice || "auto", total_requests: 200, concurrency: 20,
    rps: 10, max_tokens: 256, prompt_template: "Hello, how are you?",
    temperature: 0.7, stream: true,
  });
  const [isSaving, setIsSaving] = useState(false);
  const [saveStatus, setSaveStatus] = useState(null);
  const { isMockEnabled } = useMockData();
  const { status, setStatus, isReconnecting, retryCount, error, setError,
    result, setResult, progress, setProgress, latencyData, setLatencyData,
    connect, disconnect } = useLoadTestSSE();

  const start = async () => {
    setStatus("running"); setResult(null); setLatencyData([]); setProgress(0);
    setError(null); setSaveStatus(null);
    if (isMockEnabled) {
      simulateLoadTest(config, setProgress, setResult, setStatus, setLatencyData);
      return;
    }
    try {
      const resp = await fetch(`${API}/load_test/start`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify(config),
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const startData = await resp.json();
      if (startData.config?.model) setConfig(c => ({ ...c, model: startData.config.model }));
      connect(config.total_requests);
    } catch (err) {
      setError(`부하 테스트 시작 실패: ${err.message}`); setStatus("error");
    }
  };

  const stop = async () => {
    disconnect();
    await fetch(`${API}/load_test/stop`, { method: "POST" });
    setStatus("stopped");
  };

  const saveAsBenchmark = async () => {
    if (isSaving || !result) return;
    setIsSaving(true); setSaveStatus(null);
    const name = `${config.model}-${Math.floor(Date.now() / 1000)}`;
    try {
      const resp = await fetch(`${API}/benchmark/save`, {
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

  useEffect(() => { return () => disconnect(); }, [isMockEnabled]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!globalIsLoading && globalEndpoint) {
      setConfig(c => ({ ...c, endpoint: c.endpoint || globalEndpoint }));
    }
  }, [globalIsLoading, globalEndpoint]);

  useEffect(() => {
    fetch(`${API}/config`).then(r => r.json()).then(data => {
      setConfig(c => ({
        ...c,
        ...(data.vllm_endpoint ? { endpoint: c.endpoint || data.vllm_endpoint } : {}),
      }));
    }).catch(() => {});
  }, []);

  const handleConfigChange = (key, value) => setConfig(c => ({ ...c, [key]: value }));

  const progressFillStyle = { width: `${progress}%` };

  return (
    <div className="flex-col-16">
      <LoadTestConfig config={config} onChange={handleConfigChange} onSubmit={start}
        onStop={stop} isRunning={status === "running"} status={status} />

      {isReconnecting && status === "running" && (
        <div className="loadtest-reconnect-banner" aria-live="assertive" role="alert">
          ↺ SSE 재연결 중... ({retryCount}/3회 시도)
        </div>
      )}

      <ErrorAlert message={error} className="error-alert--mb8" />

      {status === "running" && (
        <div className="panel" aria-live="polite" aria-label="부하 테스트 진행 상황">
          <div className="loadtest-progress-header">
            <span className="label">진행률</span>
            <span className="loadtest-progress-pct">{progress}%</span>
          </div>
          <div className="progress-bar">
            <div className="progress-fill" style={progressFillStyle} />
          </div>
        </div>
      )}

      {result && (
        <>
          <div className="grid-5 gap-1">
            <MetricCard label="Mean TPS" value={fmt(result.tps?.mean, 1)} unit="tok/s" color="amber" />
            <MetricCard label="TTFT Mean" value={fmt((result.ttft?.mean || 0) * 1000, 0)} unit="ms" color="cyan" />
            <MetricCard label="P99 Latency" value={fmt((result.latency?.p99 || 0) * 1000, 0)} unit="ms" color="red" />
            <MetricCard label="Success Rate"
              value={result.total ? fmt((result.success / result.total) * 100, 1) : "—"}
              unit="%" color="green" />
            <MetricCard label="GPU Eff."
              value={result.metrics_target_matched === false ? (
                <span title="GPU metrics mismatch">N/A</span>
              ) : (
                result.gpu_utilization_avg > 0
                  ? (result.tps.mean / result.gpu_utilization_avg).toFixed(1)
                  : "—"
              )}
              unit="tok/s/%" color="purple" />
          </div>

          <div className="panel">
            <div className="section-title">Latency Distribution</div>
            <table className="table">
              <thead><tr><th>Metric</th><th>Value</th></tr></thead>
              <tbody>
                {[
                  ["Total Requests", result.total_requested ?? result.total],
                  ["Success", result.success], ["Failed", result.failed],
                  ["Actual RPS", fmt(result.rps_actual, 2)],
                  ["Mean Latency", `${fmt((result.latency?.mean || 0) * 1000, 0)} ms`],
                  ["P50 Latency", `${fmt((result.latency?.p50 || 0) * 1000, 0)} ms`],
                  ["P95 Latency", `${fmt((result.latency?.p95 || 0) * 1000, 0)} ms`],
                  ["P99 Latency", `${fmt((result.latency?.p99 || 0) * 1000, 0)} ms`],
                  ["TTFT Mean", `${fmt((result.ttft?.mean || 0) * 1000, 0)} ms`],
                  ["TTFT P95", `${fmt((result.ttft?.p95 || 0) * 1000, 0)} ms`],
                  ["Total TPS", `${fmt(result.tps?.total, 1)} tok/s`],
                  ["GPU Efficiency", result.metrics_target_matched === false ? (
                    <span title="GPU metrics mismatch">N/A</span>
                  ) : (
                    result.gpu_utilization_avg > 0
                      ? `${(result.tps.mean / result.gpu_utilization_avg).toFixed(1)} tok/s/%`
                      : "—"
                  )],
                ].map(([k, v]) => (
                  <tr key={k}>
                    <td className="td-muted">{k}</td>
                    <td className="td-accent-mono">{v}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {latencyData.length > 0 && (
            <Chart data={latencyData} title="실시간 레이턴시 (ms)" height={160} lines={[
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
        </>
      )}
    </div>
  );
}

export default LoadTestPage;
