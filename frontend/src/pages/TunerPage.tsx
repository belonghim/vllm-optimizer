import { useState, useEffect, useCallback } from "react";
import { useSSE } from "../hooks/useSSE";
import { authFetch } from '../utils/authFetch';
import { API } from "../constants";
import { ERROR_MESSAGES } from "../constants/errorMessages";
import { useMockData } from "../contexts/MockDataContext";
import { useClusterConfig } from "../contexts/ClusterConfigContext";
import { mockTrials } from "../mockData";
import type { SSEErrorPayload, SSEWarningPayload } from '../types';
import type { TunerPhase, TunerStatus, TunerTrial, TunerConfig } from "../types";
import TunerStatusPanel from "../components/TunerStatusPanel";
import TunerCurrentConfig from "../components/TunerCurrentConfig";
import TunerResults from "../components/TunerResults";
import TunerHistoryPanel from "../components/TunerHistoryPanel";

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
  const [trials, setTrials] = useState<TunerTrial[]>([]);
  const [importance, setImportance] = useState<Record<string, number>>({});
  const [currentPhase, setCurrentPhase] = useState<TunerPhase | null>(null);
  const [applyStatus, setApplyStatus] = useState<string | null>(null);
  const [interruptedWarning, setInterruptedWarning] = useState<string | null>(null);
  const [autoBenchmark, setAutoBenchmark] = useState(false);
  const [benchmarkSaved, setBenchmarkSaved] = useState(false);
  const [benchmarkSavedId, setBenchmarkSavedId] = useState<number | null>(null);
  const [config, setConfig] = useState<TunerConfig>({
    objective: "balanced",
    evaluation_mode: "single",
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
      setTrials(
        mockTrials().map((trial) => ({
          ...trial,
          params: { ...trial.params },
        }))
      );
      setError(null);
      return;
    }

    const safeFetch = async (url: string) => {
      try {
        const response = await authFetch(url, { signal });
        if (!response.ok) return null;
        return await response.json();
      } catch (e) {
        console.error(`Failed to fetch tuner data from ${url}`, e);
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
      setError(ERROR_MESSAGES.TUNER.ALL_API_FAILED);
    } else if (!s || !t || !imp) {
      const failed: string[] = [];
      if (!s) failed.push("status");
      if (!t) failed.push("trials");
      if (!imp) failed.push("importance");
      setError(`${ERROR_MESSAGES.TUNER.PARTIAL_API_FAILED_PREFIX}${failed.join(", ")})`);
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

  const tunerSSEUrl = isActive && status.running && !isMockEnabled && !error
    ? `${API}/tuner/stream`
    : null;

  useSSE(tunerSSEUrl, {
    phase: (data) => setCurrentPhase(data as TunerPhase | null),
    tuning_error: (data) => {
      const payload = data as SSEErrorPayload | undefined;
      setError(payload?.error ?? ERROR_MESSAGES.TUNER.ERROR_DEFAULT);
    },
    tuning_warning: (data) => {
      const payload = data as SSEWarningPayload | undefined;
      setWarning(payload?.message ?? ERROR_MESSAGES.TUNER.WARNING_DEFAULT);
    },
    benchmark_saved: (data) => {
      const d = data as { benchmark_id?: unknown } | null;
      setBenchmarkSaved(true);
      setBenchmarkSavedId(typeof d?.benchmark_id === "number" ? d.benchmark_id : null);
    },
    trial_complete: () => { setCurrentPhase(null); fetchStatus(); },
    tuning_complete: () => { setCurrentPhase(null); fetchStatus(); },
  }, {
    reconnect: true,
    onError: () => setError(ERROR_MESSAGES.TUNER.SSE_MAX_RETRIES_EXCEEDED),
  });

  useEffect(() => {
    if (!isActive) return;
    if (isMockEnabled) return;

    const controller = new AbortController();
    authFetch(`${API}/status/interrupted`, { signal: controller.signal })
      .then(r => r.json())
      .then(data => {
        if (data.interrupted_runs && data.interrupted_runs.some((r: { task_type: string }) => r.task_type === "tuner")) {
          setInterruptedWarning(ERROR_MESSAGES.TUNER.INTERRUPTED_WARNING);
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

  const handleApplySuccess = useCallback(() => {
    setApplyStatus(ERROR_MESSAGES.TUNER.APPLY_CURRENT_SUCCESS);
    setTimeout(() => setApplyStatus(null), 3000);
  }, []);

  const start = async () => {
    setError(null);
    setWarning(null);
    setBenchmarkSaved(false);
    setBenchmarkSavedId(null);
    try {
      const resolvedEndpoint = endpoint || config.vllm_endpoint;
      const payload: Record<string, unknown> = {
        ...config,
        auto_benchmark: autoBenchmark,
        vllm_endpoint: resolvedEndpoint,
        vllm_namespace: namespace,
        vllm_is_name: inferenceservice,
      };

      if (config.evaluation_mode === "sweep") {
        const baseRps = Math.max(1, config.eval_rps);
        const sweepStep = Math.max(1, Math.floor(baseRps / 2));
        payload.sweep_config = {
          endpoint: resolvedEndpoint,
          model: "auto",
          rps_start: Math.max(1, baseRps - sweepStep),
          rps_end: baseRps + sweepStep,
          rps_step: sweepStep,
          requests_per_step: Math.max(1, config.eval_requests),
          concurrency: Math.max(1, config.eval_concurrency),
        };
      }

      const res = await authFetch(`${API}/tuner/start`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      if (!data.success) {
        setError(data.message || ERROR_MESSAGES.TUNER.START_FAILED);
        return;
      }
      fetchStatus();
    } catch (err) {
      console.error('Failed to start tuner:', err);
      setError(`${ERROR_MESSAGES.TUNER.START_ERROR_PREFIX}${(err as Error).message}`);
    }
  };

  const stop = async () => {
    try {
      await authFetch(`${API}/tuner/stop`, { method: "POST" });
    } catch (err) {
      console.error('Failed to stop tuner:', err);
      setError(`${ERROR_MESSAGES.TUNER.STOP_FAILED_PREFIX}${(err as Error).message}`);
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
        setError(`${ERROR_MESSAGES.TUNER.APPLY_BEST_FAILED_PREFIX}${data?.message || "Unknown error"}`);
      }
    } catch (err) {
      console.error('Failed to apply best parameters:', err);
      setError(`${ERROR_MESSAGES.TUNER.APPLY_BEST_FAILED_PREFIX}${(err as Error).message}`);
    }
  };

  return (
    <div className="flex-col-16">
      <TunerStatusPanel
        error={error}
        warning={warning}
        applyStatus={applyStatus}
        interruptedWarning={interruptedWarning}
        autoBenchmark={autoBenchmark}
        benchmarkSaved={benchmarkSaved}
        benchmarkSavedId={benchmarkSavedId}
        onDismissInterrupted={() => setInterruptedWarning(null)}
        onAutoBenchmarkChange={setAutoBenchmark}
        onTabChange={onTabChange}
      />
      <TunerCurrentConfig
        isActive={isActive}
        isRunning={status.running}
        config={config}
        onChange={handleConfigChange}
        onSubmit={start}
        onStop={stop}
        onApplyBest={applyBest}
        hasBest={!!status.best}
        currentPhase={currentPhase}
        trialsCompleted={status.trials_completed}
        onError={setError}
        onApplySuccess={handleApplySuccess}
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
