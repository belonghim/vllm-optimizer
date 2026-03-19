import { useState, useEffect, useCallback } from "react";
import { API, COLORS } from "../constants";
import { useMockData } from "../contexts/MockDataContext";
import { mockTrials } from "../mockData";
import TunerConfigForm from "../components/TunerConfigForm";
import TunerResults from "../components/TunerResults";

function TunerPage() {
  const { isMockEnabled } = useMockData();
  const [error, setError] = useState(null);
  const [status, setStatus] = useState({ running: false, trials_completed: 0 });
  const [trials, setTrials] = useState([]);
  const [importance, setImportance] = useState({});
  const [currentPhase, setCurrentPhase] = useState(null);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [currentConfig, setCurrentConfig] = useState(null);
  const [config, setConfig] = useState({
    objective: "balanced",
    n_trials: 20,
    vllm_endpoint: "",
    max_num_seqs_min: 64, max_num_seqs_max: 512,
    gpu_memory_min: 0.80, gpu_memory_max: 0.95,
    max_model_len_min: 2048, max_model_len_max: 8192,
    max_num_batched_tokens_min: 256, max_num_batched_tokens_max: 2048,
    block_size_options: [8, 16, 32],
    include_swap_space: false,
    swap_space_min: 1.0, swap_space_max: 8.0,
    eval_concurrency: 32,
    eval_rps: 20,
    eval_requests: 200,
  });

  const fetchStatus = useCallback(async () => {
    if (isMockEnabled) {
      setTrials(mockTrials());
      setError(null);
      return;
    }
    try {
      const [s, t, imp] = await Promise.all([
        fetch(`${API}/tuner/status`).then(r => r.json()),
        fetch(`${API}/tuner/trials`).then(r => r.json()),
        fetch(`${API}/tuner/importance`).then(r => r.json()),
      ]);
      setStatus(s); setTrials(t); setImportance(imp);
      setError(null);
    } catch (err) {
      setError(`튜너 조회 실패: ${err.message}`);
    }
  }, [isMockEnabled]);

  useEffect(() => {
    fetchStatus();
    const id = setInterval(fetchStatus, 3000);
    return () => clearInterval(id);
  }, [fetchStatus]);

  useEffect(() => {
    if (!status.running || isMockEnabled) return;
    const es = new EventSource(`${API}/tuner/stream`);
    es.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.type === "phase") {
          setCurrentPhase(data.data);
        }
        if (data.type === "trial_complete" || data.type === "tuning_complete") {
          setCurrentPhase(null);
          fetchStatus();
        }
      } catch (e) {
        console.warn("SSE parse error:", e);
      }
    };
    es.onerror = () => { es.close(); };
    return () => { es.close(); };
  }, [status.running, isMockEnabled, fetchStatus]);

  useEffect(() => {
    if (isMockEnabled) return;
    fetch(`${API}/vllm-config`)
      .then(r => r.json())
      .then(data => { if (data.success) setCurrentConfig(data.data); })
      .catch(() => {});
  }, [isMockEnabled]);

  useEffect(() => {
    fetch(`${API}/config`)
      .then(r => r.json())
      .then(data => {
        if (data.vllm_endpoint) {
          setConfig(c => ({ ...c, vllm_endpoint: c.vllm_endpoint || data.vllm_endpoint }));
        }
      })
      .catch(() => {}); // silently fail — user can type manually
  }, []);

  const handleConfigChange = useCallback((field, value) => {
    setConfig(c => ({ ...c, [field]: value }));
  }, []);

  const start = async () => {
    setError(null);
    try {
      const res = await fetch(`${API}/tuner/start`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify(config),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      if (!data.success) {
        setError(data.message || "튜닝 시작 실패");
        return;
      }
      fetchStatus();
    } catch (err) {
      setError(`튜닝 시작 실패: ${err.message}`);
    }
  };

  const stop = async () => {
    await fetch(`${API}/tuner/stop`, { method: "POST" });
    setCurrentPhase(null);
    fetchStatus();
  };

  const applyBest = async () => {
    try {
      const res = await fetch(`${API}/tuner/apply-best`, { method: "POST" });
      const data = await res.json();
      if (data && data.success) {
        alert("최적 파라미터를 Kubernetes ConfigMap에 적용했습니다.");
      } else {
        alert(`파라미터 적용 실패: ${data?.message || "Unknown error"}`);
      }
    } catch (err) {
      alert(`파라미터 적용 실패: ${err.message}`);
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      {error && (
        <div style={{
          border: `1px solid ${COLORS.red}`,
          color: COLORS.red,
          padding: "10px 16px",
          fontFamily: "'JetBrains Mono', monospace",
          fontSize: 11,
          marginBottom: 16,
          background: "rgba(255,59,107,0.05)",
        }}>
          ⚠ {error}
        </div>
      )}
      <TunerConfigForm
        config={config}
        onChange={handleConfigChange}
        onSubmit={start}
        onStop={stop}
        onApplyBest={applyBest}
        isRunning={status.running}
        hasBest={!!status.best}
        currentConfig={currentConfig}
        currentPhase={currentPhase}
        trialsCompleted={status.trials_completed}
        showAdvanced={showAdvanced}
        onToggleAdvanced={() => setShowAdvanced(v => !v)}
      />
      <TunerResults
        trials={trials}
        bestParams={status.best}
        status={status}
        isRunning={status.running}
        importance={importance}
      />
    </div>
  );
}

export default TunerPage;
