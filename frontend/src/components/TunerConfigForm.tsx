import { useState, useEffect } from "react";
import TunerProgressBar from "./TunerProgressBar";
import TunerParamInputs from "./TunerParamInputs";
import TunerResourceInputs from "./TunerResourceInputs";

interface TunerPhase {
  trial_id: number;
  phase: string;
}

export interface TunerConfig {
  objective: string;
  evaluation_mode: "single" | "sweep";
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

interface TunerConfigFormProps {
  config: TunerConfig;
  onChange: (field: string, value: string | number | boolean | number[]) => void;
  onSubmit: () => void;
  onStop: () => void;
  onApplyBest: () => void;
  isRunning: boolean;
  hasBest: boolean;
  currentConfig: Record<string, unknown> | null;
  currentPhase: TunerPhase | null;
  trialsCompleted: number;
  storageUri: string | null;
  onSaveStorageUri: (uri: string) => void;
  onApplyCurrentValues?: (values: Record<string, unknown>) => void;
  currentResources?: Record<string, Record<string, string>> | null;
  extraArgs?: string[];
}

const PHASE_LABELS: Record<string, string> = {
  applying_config: "Updating config...",
  restarting: "Restarting InferenceService...",
  waiting_ready: "Waiting for Pod Ready...",
  warmup: "Sending warmup requests...",
  evaluating: "Evaluating performance...",
};

function isValidCpu(v: string): boolean {
  if (!v) return true;
  return /^\d+(\.\d+)?$/.test(v) || /^\d+m$/.test(v);
}

function isValidMemory(v: string): boolean {
  if (!v) return true;
  return /^\d+(\.\d+)?(Gi|Mi)$/.test(v);
}

function isValidGpu(v: string): boolean {
  if (!v) return true;
  return /^\d+$/.test(v);
}

export default function TunerConfigForm({
  config,
  onChange,
  onSubmit,
  onStop,
  onApplyBest,
  isRunning,
  hasBest,
  currentConfig,
  currentPhase,
  trialsCompleted,
  storageUri,
  onSaveStorageUri,
  onApplyCurrentValues,
  currentResources,
  extraArgs,
}: TunerConfigFormProps) {
  const [localStorageUri, setLocalStorageUri] = useState(storageUri ?? "");
  const [editedValues, setEditedValues] = useState<Record<string, unknown>>({});
  const [resourceErrors, setResourceErrors] = useState<Record<string, boolean>>({});

  useEffect(() => {
    setLocalStorageUri(storageUri ?? "");
  }, [storageUri]);

  useEffect(() => {
    setEditedValues({});
  }, [currentConfig]);

  const handleCurrentValChange = (key: string, value: unknown) => {
    setEditedValues(prev => ({ ...prev, [key]: value }));
  };

  const getResourceValue = (tier: string, key: string): string => {
    return currentResources?.[tier]?.[key] ?? "";
  };

  const handleResourceChange = (resourceKey: string, value: string) => {
    setEditedValues(prev => ({ ...prev, [resourceKey]: value }));

    let isValid = true;
    if (resourceKey === "resources.requests.cpu" || resourceKey === "resources.limits.cpu") {
      isValid = isValidCpu(value);
    } else if (resourceKey === "resources.requests.memory" || resourceKey === "resources.limits.memory") {
      isValid = isValidMemory(value);
    } else if (resourceKey === "resources.limits.nvidia.com/gpu") {
      isValid = isValidGpu(value);
    }

    setResourceErrors(prev => ({ ...prev, [resourceKey]: !isValid }));
  };

  return (
    <div className="panel">
      <div className="section-title">Bayesian Optimization Settings</div>

      <div className="grid-form grid-form-compact" style={{ marginBottom: '20px' }}>
        <div>
          <label className="label">Optimization Objective</label>
          <select className="input" aria-label="Optimization Objective" value={config.objective}
            onChange={e => onChange("objective", e.target.value)}>
            <option value="tps">Max Throughput (TPS)</option>
            <option value="latency">Min Latency</option>
            <option value="balanced">Balanced (TPS / Latency)</option>
            <option value="pareto">Pareto (TPS + Latency)</option>
          </select>
        </div>
        <div>
          <label className="label">Trial Count</label>
          <input className="input" type="number" aria-label="Trial Count" min={1} max={100} value={config.n_trials}
            onChange={e => onChange("n_trials", +e.target.value)} />
        </div>
        <div>
          <label className="label">Eval Mode</label>
          <select className="input" aria-label="Eval Mode" value={config.evaluation_mode}
            onChange={e => onChange("evaluation_mode", e.target.value as "single" | "sweep")}>
            <option value="single">Single (basic load test)</option>
            <option value="sweep">Sweep (optimal RPS based)</option>
          </select>
        </div>
      </div>

      <div style={{ overflowX: 'auto', marginBottom: '20px' }}>
        <table className="table tuner-params-table">
          <thead>
            <tr>
              <th style={{ width: '20%' }}>Parameter</th>
              <th style={{ width: '15%' }}>Current Value</th>
              <th style={{ width: '30%' }}>Search Range</th>
              <th style={{ width: '35%' }}>Description</th>
            </tr>
          </thead>
          <tbody>
            <TunerParamInputs
              config={config}
              onChange={onChange}
              editedValues={editedValues}
              currentConfig={currentConfig}
              handleChange={handleCurrentValChange}
            />
            <TunerResourceInputs
              editedValues={editedValues}
              getResourceValue={getResourceValue}
              handleResourceChange={handleResourceChange}
              resourceErrors={resourceErrors}
            />
            {extraArgs && extraArgs.length > 0 && (
              <tr>
                <td title="Other vLLM args not in tuning scope">extra_args</td>
                <td colSpan={2}>
                  <code style={{ fontSize: '11px', wordBreak: 'break-all' }}>
                    {extraArgs.join(' ')}
                  </code>
                </td>
                <td className="td-desc">vLLM args outside tuning scope</td>
              </tr>
            )}
            <tr>
              <td title="Model storage URI">storageUri</td>
              <td colSpan={2}>
                <div className="flex-row-8">
                  <input className="input" type="text" value={localStorageUri}
                    onChange={e => setLocalStorageUri(e.target.value)}
                    disabled={isRunning} placeholder="oci://registry/model" aria-label="storageUri" />
                  <button className="btn btn-primary btn-small"
                    onClick={() => onSaveStorageUri(localStorageUri)}
                    disabled={isRunning || localStorageUri === storageUri}
                    style={{ whiteSpace: 'nowrap' }}>
                    Save
                  </button>
                </div>
              </td>
              <td className="td-desc">Model storage URI</td>
            </tr>
          </tbody>
        </table>
      </div>

      <div className="section-title">Evaluation Settings</div>
      <div className="grid-form grid-form-compact" style={{ marginBottom: '20px' }}>
        <div>
          <label className="label">Eval Request Count</label>
          <input className="input" type="number" aria-label="Eval Request Count" min={10} max={10000} step={10}
            value={config.eval_requests} onChange={e => onChange("eval_requests", +e.target.value)} />
        </div>
        <div>
          <label className="label">Eval Concurrency</label>
          <input className="input" type="number" aria-label="Eval Concurrency" min={1} max={256}
            value={config.eval_concurrency} onChange={e => onChange("eval_concurrency", +e.target.value)} />
        </div>
        <div>
          <label className="label">Eval RPS</label>
          <input className="input" type="number" aria-label="Eval RPS" min={1} max={1000}
            value={config.eval_rps} onChange={e => onChange("eval_rps", +e.target.value)} />
        </div>
      </div>

      <div className="tuner-config-actions">
        <button className="btn btn-primary" onClick={onSubmit} disabled={isRunning}>
          ▶ Start Tuning
        </button>
        <button className="btn btn-danger" onClick={onStop} disabled={!isRunning}>
          ■ Stop
        </button>
        {hasBest && (
          <button className="btn btn-green" onClick={onApplyBest}>
            ✓ Apply Best Params
          </button>
        )}
        {onApplyCurrentValues && currentConfig && (
          <button className="btn btn-secondary"
            onClick={() => onApplyCurrentValues(editedValues)}
            disabled={Object.keys(editedValues).length === 0 || Object.values(resourceErrors).some(e => e)}>
            Apply Current Values
          </button>
        )}
        <span className={`tag tag-${isRunning ? "running" : "idle"}`}>
          {isRunning ? "TUNING..." : "IDLE"}
        </span>
        <span className="tuner-trials-count">
          {trialsCompleted} / {config.n_trials} trials
        </span>
      </div>

      {(isRunning || trialsCompleted > 0) && (
        <TunerProgressBar
          isRunning={isRunning}
          trialsCompleted={trialsCompleted}
          totalTrials={config.n_trials}
          currentPhase={currentPhase}
        />
      )}

      {isRunning && currentPhase && (
        <div className="tuner-phase-indicator" aria-live="polite" aria-atomic="true">
          Trial {(currentPhase.trial_id ?? 0) + 1}: {PHASE_LABELS[currentPhase.phase] || currentPhase.phase}
        </div>
      )}
    </div>
  );
}
