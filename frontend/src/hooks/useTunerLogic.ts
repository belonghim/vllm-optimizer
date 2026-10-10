import { useState, useEffect, useCallback, useRef } from 'react';
import toast from 'react-hot-toast';
import { useSSE } from './useSSE';
import { authFetch } from '../utils/authFetch';
import { API } from '../constants';
import { ERROR_MESSAGES } from '../constants/errorMessages';
import { useClusterConfig } from '../contexts/ClusterConfigContext';
import { buildDefaultEndpoint } from '../utils/endpointUtils';
import type {
  SSEErrorPayload,
  SSEWarningPayload,
  TunerPhase,
  TunerStatus,
  TunerTrial,
  TunerTrialFailure,
  TunerTrialFailureDiagnosis,
  TunerConfig,
  ClusterTarget,
  TuningWarmupSuggestionsPayload,
  TuningFailureExplanationPayload,
  TuningReportPayload,
} from '../types';

const DEFAULT_CONFIG: TunerConfig = {
  n_trials: 10,
  vllm_endpoint: '',
  eval_concurrency: 16,
  p99_latency_sla_ms: 10000,
  max_tokens: 256,
  max_model_len: 8192,
  max_num_seqs_min: 64,
  max_num_seqs_max: 512,
  gpu_memory_min: 0.8,
  gpu_memory_max: 0.95,
  max_num_batched_tokens_min: 256,
  max_num_batched_tokens_max: 2048,
  eval_requests: 100,
  enable_llm_assistant: true,
};

function asNumber(value: unknown, fallback: number): number {
  return typeof value === 'number' && !Number.isNaN(value) ? value : fallback;
}

function asString(value: unknown, fallback: string): string {
  return typeof value === 'string' ? value : fallback;
}

function toFailureDiagnosis(value: unknown): TunerTrialFailureDiagnosis | null {
  if (typeof value !== 'object' || value === null) return null;
  const diagnosis = value as Record<string, unknown>;
  if (typeof diagnosis.code !== 'string') return null;
  return {
    code: diagnosis.code,
    title: asString(diagnosis.title, diagnosis.code),
    fix: asString(diagnosis.fix, ''),
  };
}

function toTunerTrialFailure(value: unknown): TunerTrialFailure | null {
  if (typeof value !== 'object' || value === null) return null;
  const failure = value as Record<string, unknown>;
  const diagnoses = Array.isArray(failure.diagnoses)
    ? failure.diagnoses
        .map(toFailureDiagnosis)
        .filter((diagnosis): diagnosis is TunerTrialFailureDiagnosis => diagnosis !== null)
    : [];
  return { reason: asString(failure.reason, ''), diagnoses };
}

function toTunerTrial(value: unknown): TunerTrial | null {
  if (typeof value !== 'object' || value === null) return null;
  const trial = value as Partial<TunerTrial>;
  if (typeof trial.id !== 'number') return null;
  return {
    ...trial,
    id: trial.id,
    tps: asNumber(trial.tps, 0),
    p99_latency: asNumber(trial.p99_latency, 0),
    score: asNumber(trial.score, 0),
    params: typeof trial.params === 'object' && trial.params !== null ? trial.params : {},
    status: asString(trial.status, 'unknown'),
    failure: toTunerTrialFailure(trial.failure),
  };
}

function toTunerTrials(value: unknown): TunerTrial[] {
  if (!Array.isArray(value)) return [];
  return value.map(toTunerTrial).filter((trial): trial is TunerTrial => trial !== null);
}

export function useTunerLogic({
  isActive,
  onRunningChange,
  targetOverride,
}: {
  isActive: boolean;
  onRunningChange?: (running: boolean) => void;
  targetOverride?: ClusterTarget | null;
}) {
  const { endpoint, namespace, inferenceservice, crType } = useClusterConfig();
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
  const [initialized, setInitialized] = useState(false);
  const [warmupSuggestions, setWarmupSuggestions] = useState<TuningWarmupSuggestionsPayload | null>(
    null
  );
  const [tuningReport, setTuningReport] = useState<TuningReportPayload | null>(null);
  const userEditedRef = useRef<Record<string, boolean>>({});
  const lastTargetOverrideRef = useRef<ClusterTarget | null | undefined>(undefined);
  const [config, setConfig] = useState<TunerConfig>(DEFAULT_CONFIG);

  const fetchStatus = useCallback(async (signal?: AbortSignal) => {
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
    const s = results[0].status === 'fulfilled' ? results[0].value : null;
    const t = results[1].status === 'fulfilled' ? results[1].value : null;
    const imp = results[2].status === 'fulfilled' ? results[2].value : null;
    if (s) setStatus(s);
    if (t) setTrials(toTunerTrials(t));
    if (imp) setImportance(imp);
    if (!s && !t && !imp) {
      setError(ERROR_MESSAGES.TUNER.ALL_API_FAILED);
    } else if (!s || !t || !imp) {
      const failed: string[] = [];
      if (!s) failed.push('status');
      if (!t) failed.push('trials');
      if (!imp) failed.push('importance');
      setError(`${ERROR_MESSAGES.TUNER.PARTIAL_API_FAILED_PREFIX}${failed.join(', ')})`);
    } else {
      setError(null);
    }
  }, []);

  useEffect(() => {
    if (!isActive) return;
    const controller = new AbortController();
    (async () => {
      await fetchStatus(controller.signal);
      if (!controller.signal.aborted) setInitialized(true);
    })();
    const id = setInterval(() => fetchStatus(controller.signal), 3000);
    return () => {
      controller.abort();
      clearInterval(id);
    };
  }, [isActive, fetchStatus]);

  const tunerSSEUrl = isActive && status.running && !error ? `${API}/tuner/stream` : null;

  useSSE(
    tunerSSEUrl,
    {
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
        setBenchmarkSavedId(typeof d?.benchmark_id === 'number' ? d.benchmark_id : null);
      },
      trial_complete: () => {
        setCurrentPhase(null);
        fetchStatus();
      },
      tuning_complete: () => {
        setCurrentPhase(null);
        fetchStatus();
      },
      tuning_warmup_suggestions: (data) => {
        setWarmupSuggestions(data as TuningWarmupSuggestionsPayload | null);
      },
      tuning_failure_explanation: (data) => {
        const payload = data as TuningFailureExplanationPayload | undefined;
        if (!payload) return;
        toast.error(`Trial ${payload.trial_id} [${payload.reason}]: ${payload.explanation}`, {
          duration: 10000,
          style: { maxWidth: '480px', fontSize: '12px' },
        });
      },
      tuning_report: (data) => {
        setTuningReport(data as TuningReportPayload | null);
      },
    },
    { reconnect: true, onError: () => setError(ERROR_MESSAGES.TUNER.SSE_MAX_RETRIES_EXCEEDED) }
  );

  useEffect(() => {
    if (!isActive) return;
    const controller = new AbortController();
    authFetch(`${API}/status/interrupted`, { signal: controller.signal })
      .then((r) => r.json())
      .then((data) => {
        if (
          data.interrupted_runs &&
          data.interrupted_runs.some((r: { task_type: string }) => r.task_type === 'tuner')
        ) {
          setInterruptedWarning(ERROR_MESSAGES.TUNER.INTERRUPTED_WARNING);
        }
      })
      .catch((error) => {
        console.warn('Failed to check interrupted status:', error);
      });
    return () => controller.abort();
  }, [isActive]);

  useEffect(() => {
    const targetChanged = lastTargetOverrideRef.current !== targetOverride;
    if (!targetChanged && Object.keys(userEditedRef.current).length > 0) return;
    lastTargetOverrideRef.current = targetOverride;
    userEditedRef.current = {};
    const newEndpoint = targetOverride
      ? buildDefaultEndpoint(
          targetOverride.crType,
          targetOverride.namespace,
          targetOverride.inferenceService
        )
      : endpoint;
    setConfig({ ...DEFAULT_CONFIG, vllm_endpoint: newEndpoint || '' });
  }, [targetOverride, endpoint]);

  useEffect(() => {
    onRunningChange?.(status.running);
  }, [status.running, onRunningChange]);

  const handleConfigChange = useCallback(
    (field: string, value: string | number | boolean | null) => {
      setConfig((c) => ({ ...c, [field]: value }));
      userEditedRef.current[field] = true;
    },
    []
  );

  const handleApplySuccess = useCallback(() => {
    setApplyStatus(ERROR_MESSAGES.TUNER.APPLY_CURRENT_SUCCESS);
    setTimeout(() => setApplyStatus(null), 3000);
  }, []);

  const start = async () => {
    setError(null);
    setWarning(null);
    setBenchmarkSaved(false);
    setBenchmarkSavedId(null);
    setWarmupSuggestions(null);
    setTuningReport(null);
    try {
      const targetNs = targetOverride?.namespace || namespace;
      const targetIsName = targetOverride?.inferenceService || inferenceservice;
      const targetCrType = targetOverride?.crType || crType;
      const resolvedEndpoint = targetOverride
        ? buildDefaultEndpoint(targetCrType, targetNs, targetIsName)
        : endpoint || config.vllm_endpoint;
      const payload: Record<string, unknown> = {
        ...config,
        auto_benchmark: autoBenchmark,
        vllm_endpoint: resolvedEndpoint,
        vllm_namespace: targetNs,
        vllm_is_name: targetIsName,
        vllm_cr_type: targetCrType,
      };
      const res = await authFetch(`${API}/tuner/start`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => null);
        throw new Error(body?.detail?.error || `HTTP ${res.status}`);
      }
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
      await authFetch(`${API}/tuner/stop`, { method: 'POST' });
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
      const res = await authFetch(`${API}/tuner/apply-best`, { method: 'POST' });
      const data = await res.json();
      if (data?.success) {
        setApplyStatus('success');
        setTimeout(() => setApplyStatus(null), 3000);
      } else
        setError(
          `${ERROR_MESSAGES.TUNER.APPLY_BEST_FAILED_PREFIX}${data?.message || 'Unknown error'}`
        );
    } catch (err) {
      console.error('Failed to apply best parameters:', err);
      setError(`${ERROR_MESSAGES.TUNER.APPLY_BEST_FAILED_PREFIX}${(err as Error).message}`);
    }
  };

  return {
    error,
    warning,
    status,
    trials,
    importance,
    currentPhase,
    applyStatus,
    interruptedWarning,
    autoBenchmark,
    benchmarkSaved,
    benchmarkSavedId,
    initialized,
    config,
    setError,
    setInterruptedWarning,
    setAutoBenchmark,
    handleConfigChange,
    handleApplySuccess,
    start,
    stop,
    applyBest,
    warmupSuggestions,
    tuningReport,
  };
}
