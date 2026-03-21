import { useState, useEffect, useCallback } from "react";
import { API, COLORS } from "../constants";
import { useMockData } from "../contexts/MockDataContext";
import { useClusterConfig } from "../contexts/ClusterConfigContext";
import { mockTrials } from "../mockData";
import TunerConfigForm from "../components/TunerConfigForm";
import TunerResults from "../components/TunerResults";
import ErrorAlert from "../components/ErrorAlert";

function TunerPage() {
  const { isMockEnabled } = useMockData();
  const { endpoint, namespace, inferenceservice } = useClusterConfig();
  const [error, setError] = useState(null);
  const [status, setStatus] = useState({ running: false, trials_completed: 0 });
  const [trials, setTrials] = useState([]);
  const [importance, setImportance] = useState({});
  const [currentPhase, setCurrentPhase] = useState(null);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [currentConfig, setCurrentConfig] = useState(null);
  const [storageUri, setStorageUri] = useState(null);
  const [config, setConfig] = useState({
    objective: "balanced",
    n_trials: 10,
    vllm_endpoint: "",
    max_num_seqs_min: 64, max_num_seqs_max: 512,
    gpu_memory_min: 0.80, gpu_memory_max: 0.95,
    max_model_len_min: 2048, max_model_len_max: 8192,
    max_num_batched_tokens_min: 256, max_num_batched_tokens_max: 2048,
    block_size_options: [8, 16, 32],
    include_swap_space: false,
    swap_space_min: 1.0, swap_space_max: 8.0,
    eval_concurrency: 16,
    eval_rps: 20,
    eval_requests: 100,
  });

  const fetchStatus = useCallback(async () => {
    if (isMockEnabled) {
      setTrials(mockTrials());
      setError(null);
      return;
    }

    const safeFetch = async (url) => {
      try {
        const response = await fetch(url);
        if (!response.ok) return null;
        return await response.json();
      } catch (err) {
        console.warn(`Fetch failed for ${url}:`, err);
        return null;
      }
    };

    const results = await Promise.allSettled([
      safeFetch(`${API}/tuner/status`),
      safeFetch(`${API}/tuner/trials`),
      safeFetch(`${API}/tuner/importance`),
    ]);

    const s = results[0].status === "fulfilled" ? results[0].value : null;
    const t = results[1].status === "fulfilled" ? results[1].value : null;
    const imp = results[2].status === "fulfilled" ? results[2].value : null;

    if (s) setStatus(s);
    if (t) setTrials(t);
    if (imp) setImportance(imp);

    if (!s && !t && !imp) {
      setError("튜너 모든 API 조회 실패 (상태, 시도, 중요도)");
    } else if (!s || !t || !imp) {
      const failed = [];
      if (!s) failed.push("상태");
      if (!t) failed.push("시도");
      if (!imp) failed.push("중요도");
      setError(`주의: 일부 튜너 정보를 가져오지 못했습니다 (${failed.join(", ")})`);
    } else {
      setError(null);
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
      .then(data => {
        if (data.success) {
          setCurrentConfig(data.data);
          setStorageUri(data.storageUri ?? null);
        }
      })
      .catch(() => {});
  }, [isMockEnabled]);

  useEffect(() => {
    if (endpoint) {
      setConfig(c => ({ ...c, vllm_endpoint: c.vllm_endpoint || endpoint }));
    }
  }, [endpoint]);

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

  const handleSaveStorageUri = useCallback(async (newUri) => {
    try {
      const res = await fetch(`${API}/vllm-config`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ storageUri: newUri }),
      });
      const data = await res.json();
      if (!res.ok || !data.success) {
        setError(`storageUri 업데이트 실패: ${data.detail || res.status}`);
        return;
      }
      setStorageUri(newUri);
    } catch (err) {
      setError(`storageUri 업데이트 실패: ${err.message}`);
    }
  }, []);

  const start = async () => {
    setError(null);
    try {
      const res = await fetch(`${API}/tuner/start`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ...config,
          vllm_endpoint: endpoint || config.vllm_endpoint,
          vllm_namespace: namespace,
          vllm_is_name: inferenceservice,
        }),
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
        alert("최적 파라미터를 InferenceService에 적용했습니다.");
      } else {
        alert(`파라미터 적용 실패: ${data?.message || "Unknown error"}`);
      }
    } catch (err) {
      alert(`파라미터 적용 실패: ${err.message}`);
    }
  };

  return (
    <div className="flex-col-16">
      <ErrorAlert message={error} className="error-alert--mb16" />
      <TunerConfigForm
        config={config}
        onChange={handleConfigChange}
        onSubmit={start}
        onStop={stop}
        onApplyBest={applyBest}
        isRunning={status.running}
        hasBest={!!status.best}
        currentConfig={currentConfig}
        storageUri={storageUri}
        onSaveStorageUri={handleSaveStorageUri}
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
