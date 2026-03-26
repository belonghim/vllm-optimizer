import { useState, useEffect, useCallback } from "react";
import { authFetch } from '../utils/authFetch';
import { API } from "../constants";
import { useMockData } from "../contexts/MockDataContext";
import { useClusterConfig } from "../contexts/ClusterConfigContext";
import { mockTrials } from "../mockData";
import type { SSEErrorPayload, SSEWarningPayload } from '../types';
import TunerConfigForm from "../components/TunerConfigForm";
import TunerResults from "../components/TunerResults";
import TunerHistoryPanel from "../components/TunerHistoryPanel";
import ErrorAlert from "../components/ErrorAlert";

interface TunerPhase {
  trial_id: number;
  phase: string;
}

interface TunerStatus {
  running: boolean;
  trials_completed: number;
  best?: {
    tps: number;
    p99_latency: number;
    params?: Record<string, unknown>;
  };
  best_score_history?: number[];
}

interface Trial {
  id: number;
  tps: number;
  p99_latency: number;
  score: number;
  params: Record<string, unknown>;
  status: string;
  is_pareto_optimal?: boolean;
}

interface TunerConfig {
  objective: string;
  n_trials: number;
  vllm_endpoint: string;
  max_num_seqs_min: number;
  max_num_seqs_max: number;
  gpu_memory_min: number;
  gpu_memory_max: number;
  max_model_len_min: number;
  max_model_len_max: number;
  max_num_batched_tokens_min: number;
  max_num_batched_tokens_max: number;
  block_size_options: number[];
  include_swap_space: boolean;
  swap_space_min: number;
  swap_space_max: number;
  eval_concurrency: number;
  eval_rps: number;
  eval_requests: number;
}

interface TunerPageProps {
  isActive: boolean;
  onTabChange?: (tab: string) => void;
  onRunningChange?: (running: boolean) => void;
}

function TunerPage({ isActive, onTabChange, onRunningChange }: TunerPageProps) {
  const { isMockEnabled } = useMockData();
  const { endpoint, namespace, inferenceservice } = useClusterConfig();
  const [error, setError] = useState<string | null>(null);
  const [warning, setWarning] = useState<string | null>(null);
  const [status, setStatus] = useState<TunerStatus>({ running: false, trials_completed: 0 });
  const [trials, setTrials] = useState<Trial[]>([]);
  const [importance, setImportance] = useState<Record<string, number>>({});
  const [currentPhase, setCurrentPhase] = useState<TunerPhase | null>(null);
  const [applyStatus, setApplyStatus] = useState<string | null>(null);
  const [interruptedWarning, setInterruptedWarning] = useState<string | null>(null);
  const [autoBenchmark, setAutoBenchmark] = useState(false);
  const [benchmarkSaved, setBenchmarkSaved] = useState(false);
  const [benchmarkSavedId, setBenchmarkSavedId] = useState<number | null>(null);
  const [currentConfig, setCurrentConfig] = useState<Record<string, unknown> | null>(null);
  const [currentResources, setCurrentResources] = useState<Record<string, Record<string, string>> | null>(null);
  const [storageUri, setStorageUri] = useState<string | null>(null);
  const [config, setConfig] = useState<TunerConfig>({
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

  const fetchStatus = useCallback(async (signal?: AbortSignal) => {
    if (isMockEnabled) {
      setTrials(mockTrials());
      setError(null);
      return;
    }

    const safeFetch = async (url: string) => {
      try {
        const response = await authFetch(url, { signal });
        if (!response.ok) return null;
        return await response.json();
      } catch {
        return null;
      }
    };

    const results = await Promise.allSettled([
      safeFetch(`${API}/tuner/status`),
      safeFetch(`${API}/tuner/trials`),
      safeFetch(`${API}/tuner/importance`),
    ]);

    if (signal?.aborted) return;

    const s = results[0].status === "fulfilled" ? results[0].value : null;
    const t = results[1].status === "fulfilled" ? results[1].value : null;
    const imp = results[2].status === "fulfilled" ? results[2].value : null;

    if (s) setStatus(s);
    if (t) setTrials(t);
    if (imp) setImportance(imp);

    if (!s && !t && !imp) {
      setError("튜너 모든 API 조회 실패 (상태, 시도, 중요도)");
    } else if (!s || !t || !imp) {
      const failed: string[] = [];
      if (!s) failed.push("상태");
      if (!t) failed.push("시도");
      if (!imp) failed.push("중요도");
      setError(`주의: 일부 튜너 정보를 가져오지 못했습니다 (${failed.join(", ")})`);
    } else {
      setError(null);
    }
  }, [isMockEnabled]);

  useEffect(() => {
    if (!isActive) return;

    const controller = new AbortController();
    fetchStatus(controller.signal);
    const id = setInterval(() => fetchStatus(controller.signal), 3000);
    return () => { controller.abort(); clearInterval(id); };
  }, [isActive, fetchStatus]);

  useEffect(() => {
    if (!isActive || !status.running) return;
    if (isMockEnabled) return;

    let retryCount = 0;
    let retryTimer: ReturnType<typeof setTimeout> | null = null;
    let currentEs: EventSource | null = null;

    const openConnection = () => {
      const es = new EventSource(`${API}/tuner/stream`);
      currentEs = es;

      es.onmessage = (event) => {
        retryCount = 0;
        try {
          const data = JSON.parse(event.data as string);
          if (data.type === "phase") {
            setCurrentPhase(data.data);
          }
          if (data.type === "tuning_error") {
            const payload = data.data as SSEErrorPayload | undefined;
            setError(payload?.error ?? "튜닝 중 오류가 발생했습니다.");
            es.close();
            return;
          }
          if (data.type === "tuning_warning") {
            const payload = data.data as SSEWarningPayload | undefined;
            setWarning(payload?.message ?? "튜닝 경고가 발생했습니다.");
            return;
          }
          if (data.type === "benchmark_saved") {
            const benchmarkId = data?.data?.benchmark_id;
            setBenchmarkSaved(true);
            setBenchmarkSavedId(typeof benchmarkId === "number" ? benchmarkId : null);
            return;
          }
          if (data.type === "trial_complete" || data.type === "tuning_complete") {
            setCurrentPhase(null);
            fetchStatus();
          }
        } catch (e) {
          if (import.meta.env.DEV) console.error("[TunerSSE] parse error:", e);
        }
      };

      es.onerror = () => {
        es.close();
        currentEs = null;
        const count = retryCount + 1;
        retryCount = count;
        if (count <= 3) {
          const delay = Math.min(1000 * Math.pow(2, count - 1), 8000);
          retryTimer = setTimeout(() => { openConnection(); }, delay);
        } else {
          setError("튜너 SSE 연결 실패: 최대 재시도 횟수를 초과했습니다.");
        }
      };
    };

    openConnection();

    return () => {
      if (retryTimer !== null) clearTimeout(retryTimer);
      if (currentEs) { currentEs.close(); currentEs = null; }
    };
  }, [isActive, status.running, isMockEnabled, fetchStatus]);

  useEffect(() => {
    if (!isActive) return;
    if (isMockEnabled) return;

    const controller = new AbortController();
    authFetch(`${API}/vllm-config`, { signal: controller.signal })
      .then(r => {
        if (!r.ok) {
          return r.json().then(errData => {
            throw new Error(errData.detail || `HTTP ${r.status}`);
          });
        }
        return r.json();
      })
      .then(data => {
        if (data.success) {
          setCurrentConfig(data.data);
          setStorageUri(data.storageUri ?? null);
          setCurrentResources(data.resources ?? null);
        } else {
          setError(data.message || "vLLM 설정 조회 실패");
        }
      })
      .catch((err: Error) => {
        if (err.name === 'AbortError') return;
        setError(`vLLM 설정 조회 실패: ${err.message}`);
      });
    return () => controller.abort();
  }, [isActive, isMockEnabled, namespace, inferenceservice]);

  useEffect(() => {
    if (!isActive) return;
    if (isMockEnabled) return;

    const controller = new AbortController();
    authFetch(`${API}/status/interrupted`, { signal: controller.signal })
      .then(r => r.json())
      .then(data => {
        if (data.interrupted_runs && data.interrupted_runs.some((r: any) => r.task_type === "tuner")) {
          setInterruptedWarning("이전 튜닝이 비정상 종료되었습니다.");
        }
      })
      .catch(() => {});
    return () => controller.abort();
  }, [isActive, isMockEnabled]);

  useEffect(() => {
    if (endpoint) {
      setConfig(c => ({ ...c, vllm_endpoint: c.vllm_endpoint || endpoint }));
    }
  }, [endpoint]);

  useEffect(() => {
    onRunningChange?.(status.running);
  }, [status.running, onRunningChange]);


  const handleConfigChange = useCallback((field: string, value: string | number | boolean | number[]) => {
    setConfig(c => ({ ...c, [field]: value }));
  }, []);

  const handleApplyCurrentValues = useCallback(async (values: Record<string, unknown>) => {
    const confirmed = window.confirm(
      "vLLM InferenceService가 재시작됩니다. 변경된 파라미터를 적용하시겠습니까?"
    );
    if (!confirmed) return;
    try {
      const dataPayload: Record<string, string> = {};
      const resourcesPayload: Record<string, Record<string, string>> = {};

      for (const [key, val] of Object.entries(values)) {
        if (key.startsWith("resources.")) {
          const parts = key.split(".");
          const tier = parts[1];
          const resKey = parts.slice(2).join(".");
          if (!resourcesPayload[tier]) resourcesPayload[tier] = {};
          resourcesPayload[tier][resKey] = String(val);
        } else {
          dataPayload[key] = String(val);
        }
      }

      const patchBody: Record<string, unknown> = {};
      if (Object.keys(dataPayload).length > 0) patchBody.data = dataPayload;
      if (Object.keys(resourcesPayload).length > 0) patchBody.resources = resourcesPayload;

      const res = await authFetch(`${API}/vllm-config`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(patchBody),
      });
      const data = await res.json();
      if (!res.ok || !data.success) {
        setError(`현재값 적용 실패: ${data.detail || res.status}`);
        return;
      }
      setCurrentConfig(prev => (prev ? { ...prev, ...values } : null));
      setApplyStatus("현재값 적용 완료");
      setTimeout(() => setApplyStatus(null), 3000);
    } catch (err) {
      setError(`현재값 적용 실패: ${(err as Error).message}`);
    }
  }, []);

  const handleSaveStorageUri = useCallback(async (newUri: string) => {
    try {
      const res = await authFetch(`${API}/vllm-config`, {
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
      setError(`storageUri 업데이트 실패: ${(err as Error).message}`);
    }
  }, []);

  const start = async () => {
    setError(null);
    setWarning(null);
    setBenchmarkSaved(false);
    setBenchmarkSavedId(null);
    try {
      const res = await authFetch(`${API}/tuner/start`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ...config,
          auto_benchmark: autoBenchmark,
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
      setError(`튜닝 시작 실패: ${(err as Error).message}`);
    }
  };

  const stop = async () => {
    try {
      await authFetch(`${API}/tuner/stop`, { method: "POST" });
    } catch (err) {
      setError(`튜너 중지 실패: ${(err as Error).message}`);
    }
    setCurrentPhase(null);
    fetchStatus();
  };

  const applyBest = async () => {
    setApplyStatus(null);
    try {
      const res = await authFetch(`${API}/tuner/apply-best`, { method: "POST" });
      const data = await res.json();
      if (data && data.success) {
        setApplyStatus("success");
        setTimeout(() => setApplyStatus(null), 3000);
      } else {
        setError(`파라미터 적용 실패: ${data?.message || "Unknown error"}`);
      }
    } catch (err) {
      setError(`파라미터 적용 실패: ${(err as Error).message}`);
    }
  };

  return (
    <div className="flex-col-16">
      {interruptedWarning && (
        <div style={{display: 'flex', alignItems: 'flex-start', gap: '8px'}}>
          <ErrorAlert message={interruptedWarning} severity="warning" className="error-alert--mb16" />
          <button onClick={() => setInterruptedWarning(null)} style={{background:'none',border:'none',cursor:'pointer',padding:'4px',color:'var(--muted-color)',fontSize:'18px'}}>×</button>
        </div>
      )}
      <ErrorAlert message={error} className="error-alert--mb16" />
      <ErrorAlert message={warning} severity="warning" className="error-alert--mb16" />
      {applyStatus === "success" && (
        <div className="success-msg" role="status">
          최적 파라미터를 InferenceService에 적용했습니다.
        </div>
      )}
      {applyStatus === "현재값 적용 완료" && (
        <div className="success-msg" role="status">
          현재값을 InferenceService에 적용했습니다.
        </div>
      )}
      <label style={{ display: "inline-flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
        <input
          type="checkbox"
          checked={autoBenchmark}
          onChange={(e) => setAutoBenchmark(e.target.checked)}
        />
        완료 후 벤치마크 자동 저장
      </label>
      {benchmarkSaved && (
        <div className="success-msg" role="status" style={{ marginBottom: 8 }}>
          벤치마크 저장됨 ✓{benchmarkSavedId !== null ? ` (ID: ${benchmarkSavedId})` : ""}
        </div>
      )}
      {benchmarkSaved && onTabChange && (
        <button type="button" onClick={() => onTabChange("benchmark")} style={{ marginBottom: 12 }}>
          BenchmarkPage로 이동
        </button>
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
        currentResources={currentResources}
        storageUri={storageUri}
        onSaveStorageUri={handleSaveStorageUri}
        onApplyCurrentValues={handleApplyCurrentValues}
        currentPhase={currentPhase}
        trialsCompleted={status.trials_completed}
      />
      <TunerResults
        trials={trials}
        bestParams={status.best}
        status={status}
        isRunning={status.running}
        importance={importance}
      />
      <TunerHistoryPanel />
    </div>
  );
}

export default TunerPage;
