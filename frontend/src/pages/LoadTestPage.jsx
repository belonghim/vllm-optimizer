import { useState, useRef, useEffect } from "react";
import { useMockData } from "../contexts/MockDataContext";
import { API, COLORS, font } from "../constants";
import MetricCard from "../components/MetricCard";
import Chart from "../components/Chart";
import { simulateLoadTest } from "../mockData";

const fmt = (n, d = 1) => (n == null ? "—" : Number(n).toFixed(d));

function LoadTestPage() {
  const [config, setConfig] = useState({
    endpoint: "",
    model: "auto",
    total_requests: 200,
    concurrency: 20,
    rps: 10,
    max_tokens: 256,
    prompt_template: "Hello, how are you?",
    temperature: 0.7,
    stream: true,
  });
  const [status, setStatus] = useState("idle");
  const [result, setResult] = useState(null);
  const [progress, setProgress] = useState(0);
  const [latencyData, setLatencyData] = useState([]);
  const { isMockEnabled } = useMockData();
   const [error, setError] = useState(null);
   const [isSaving, setIsSaving] = useState(false);
   const [saveStatus, setSaveStatus] = useState(null);
   const esRef = useRef(null);
   const mockTimerRef = useRef(null);
   const retryCountRef = useRef(0);

   const start = async () => {
     setStatus("running");
     setResult(null);
     setLatencyData([]);
     setProgress(0);
     setError(null);
     setSaveStatus(null);

    if (isMockEnabled) {
      // Mock mode: simulate locally
      simulateLoadTest(config, setProgress, setResult, setStatus, setLatencyData);
      return;
    }

    // Real API mode
    try {
      const resp = await fetch(`${API}/load_test/start`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(config),
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const startData = await resp.json();
      if (startData.config?.model) {
        setConfig(c => ({ ...c, model: startData.config.model }));
      }

      const es = new EventSource(`${API}/load_test/stream`);
      esRef.current = es;
      es.onmessage = (e) => {
        retryCountRef.current = 0;
        let data;
        try {
          data = JSON.parse(e.data);
        } catch (parseErr) {
          return;
        }
        if (data.type === "progress" && data.data) {
          const d = data.data;
          if (d.total != null) {
            setProgress(Math.round((d.total / config.total_requests) * 100));
          }
          setLatencyData(prev => [...prev.slice(-60), {
            t: prev.length,
            lat: d.latency?.mean * 1000 | 0,
            tps: d.tps?.mean | 0
          }]);
          setResult(d);
        }
        if (data.type === "completed") {
          setStatus("completed");
          setProgress(100);
          es.close();
          esRef.current = null;
          setResult(data.data);
        }
      };
      es.onerror = () => {
        if (es.readyState === EventSource.CONNECTING) {
          retryCountRef.current += 1;
          if (retryCountRef.current <= 3) {
            return;
          }
        }
        setError(`SSE 연결 실패: 부하 테스트 스트림에 연결할 수 없습니다. (재시도 ${retryCountRef.current}회 후 실패)`);
        setStatus("error");
        es.close();
        esRef.current = null;
      };
    } catch (err) {
      setError(`부하 테스트 시작 실패: ${err.message}`);
      setStatus("error");
    }
  };

   const stop = async () => {
     if (esRef.current) {
       esRef.current.close();
       esRef.current = null;
     }
     await fetch(`${API}/load_test/stop`, { method: "POST" });
     setStatus("stopped");
   };

   const saveAsBenchmark = async () => {
     if (isSaving || !result) return;
     setIsSaving(true);
     setSaveStatus(null);
     const name = `${config.model} @ ${new Date().toLocaleDateString()}`;
     try {
       const resp = await fetch(`${API}/benchmark/save`, {
         method: "POST",
         headers: { "Content-Type": "application/json" },
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

  useEffect(() => {
    return () => {
      if (esRef.current) {
        esRef.current.close();
        esRef.current = null;
      }
    };
  }, [isMockEnabled]);

  useEffect(() => {
    fetch(`${API}/config`)
      .then(r => r.json())
      .then(data => {
        if (data.vllm_endpoint) {
          setConfig(c => ({ ...c, endpoint: c.endpoint || data.vllm_endpoint }));
        }
      })
      .catch(() => {}); // silently fail — user can type manually
  }, []);

  useEffect(() => {
    fetch(`${API}/config`)
      .then(r => r.json())
      .then(data => {
        if (data.resolved_model_name && data.resolved_model_name !== "auto") {
          setConfig(c => ({ ...c, model: c.model === "auto" ? data.resolved_model_name : c.model }));
        }
      })
      .catch(() => {});
  }, []);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      {/* 설정 */}
      <div style={{ background: COLORS.surface, border: `1px solid ${COLORS.border}`, padding: 20 }}>
        <div className="section-title">부하 테스트 설정</div>
        <div className="grid-form" style={{ gap: 12 }}>
          {
            [
              ["vLLM Endpoint", "endpoint", "text"],
              ["Model Name", "model", "text"],
              ["Total Requests", "total_requests", "number"],
              ["Concurrency", "concurrency", "number"],
              ["RPS (0=unlimited)", "rps", "number"],
              ["Max Tokens", "max_tokens", "number"],
            ].map(([label, key, type]) => (
              <div key={key}>
                <label className="label">{label}</label>
                <input className="input" type={type} value={config[key]}
                  onChange={e => setConfig(c => ({ ...c, [key]: type === "number" ? +e.target.value : e.target.value }))} />
              </div>
            ))}
            <div>
              <label className="label">프롬프트 템플릿</label>
              <textarea
                className="input"
                rows={3}
                style={{ resize: "vertical", fontFamily: "'JetBrains Mono', monospace", fontSize: 11 }}
                value={config.prompt_template}
                onChange={e => setConfig(c => ({ ...c, prompt_template: e.target.value }))}
              />
            </div>
            <div>
              <label className="label">Temperature</label>
              <input className="input" type="number" step="0.1" min="0" max="2"
                value={config.temperature}
                onChange={e => setConfig(c => ({ ...c, temperature: +e.target.value }))} />
            </div>
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 16 }}>
            <input type="checkbox" id="stream" checked={config.stream}
              onChange={e => setConfig(c => ({ ...c, stream: e.target.checked }))} />
            <label htmlFor="stream" className="label" style={{ marginBottom: 0 }}>
              Streaming Mode (TTFT 측정 활성화)
            </label>
          </div>

          <div style={{ display: "flex", gap: 8, marginTop: 16 }}>
            <button className="btn btn-primary" onClick={start} disabled={status === "running"}>
              ▶ Run Load Test
            </button>
            <button className="btn btn-danger" onClick={stop} disabled={status !== "running"}>
              ■ Stop
            </button>
            <span className={`tag tag-${status}`}>{status.toUpperCase()}</span>
          </div>
        </div>

      {error && (
        <div style={{
          border: `1px solid ${COLORS.red}`,
          color: COLORS.red,
          padding: "10px 16px",
          fontFamily: "'JetBrains Mono', monospace",
          fontSize: 11,
          marginBottom: 8,
          background: "rgba(255,59,107,0.05)",
        }}>
          ⚠ {error}
        </div>
      )}

      {/* 진행률 */}
      {status === "running" && (
        <div style={{ background: COLORS.surface, border: `1px solid ${COLORS.border}`, padding: 20 }}>
          <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 8 }}>
            <span className="label">진행률</span>
            <span style={{ fontSize: 11, color: COLORS.accent }}>{progress}%</span>
          </div>
          <div className="progress-bar">
            <div className="progress-fill" style={{ width: `${progress}%` }} />
          </div>
        </div>
      )}

      {/* 결과 */}
      {result && (
        <>
          <div className="grid-4" style={{ gap: 1 }}>
            <MetricCard label="Mean TPS" value={fmt(result.tps?.mean, 1)} unit="tok/s" color="amber" />
            <MetricCard label="TTFT Mean" value={fmt((result.ttft?.mean || 0) * 1000, 0)} unit="ms" color="cyan" />
            <MetricCard label="P99 Latency" value={fmt((result.latency?.p99 || 0) * 1000, 0)} unit="ms" color="red" />
            <MetricCard label="Success Rate"
              value={result.total ? fmt((result.success / result.total) * 100, 1) : "—"}
              unit="%" color="green" />
          </div>

          <div style={{ background: COLORS.surface, border: `1px solid ${COLORS.border}`, padding: 20 }}>
            <div className="section-title">Latency Distribution</div>
            <table className="table">
              <thead>
                <tr>
                  <th>Metric</th><th>Value</th>
                </tr>
              </thead>
              <tbody>
                 {
                   [
                     ["Total Requests", result.total_requested ?? result.total],
                     ["Success", result.success],
                    ["Failed", result.failed],
                    ["Actual RPS", fmt(result.rps_actual, 2)],
                    ["Mean Latency", `${fmt((result.latency?.mean || 0) * 1000, 0)} ms`],
                    ["P50 Latency", `${fmt((result.latency?.p50 || 0) * 1000, 0)} ms`],
                    ["P95 Latency", `${fmt((result.latency?.p95 || 0) * 1000, 0)} ms`],
                    ["P99 Latency", `${fmt((result.latency?.p99 || 0) * 1000, 0)} ms`],
                    ["TTFT Mean", `${fmt((result.ttft?.mean || 0) * 1000, 0)} ms`],
                    ["TTFT P95", `${fmt((result.ttft?.p95 || 0) * 1000, 0)} ms`],
                    ["Total TPS", `${fmt(result.tps?.total, 1)} tok/s`],
                  ].map(([k, v]) => (
                    <tr key={k}>
                      <td style={{ color: COLORS.muted }}>{k}</td>
                      <td style={{ color: COLORS.accent, fontFamily: font.mono }}>{v}</td>
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
             <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 12 }}>
               <button
                 className="btn btn-primary"
                 onClick={saveAsBenchmark}
                 disabled={isSaving || saveStatus === "ok"}
               >
                 {saveStatus === "ok" ? "✓ Saved" : isSaving ? "Saving..." : "⬆ Save as Benchmark"}
               </button>
               {saveStatus === "error" && (
                 <span style={{ color: COLORS.red, fontSize: 11, fontFamily: font.mono }}>
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