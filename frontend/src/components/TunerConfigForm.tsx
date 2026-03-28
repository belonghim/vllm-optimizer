import { useState, useEffect } from "react";
import TunerProgressBar from "./TunerProgressBar";

interface TunerPhase {
  trial_id: number;
  phase: string;
}

interface TunerConfig {
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

  useEffect(() => {
    setLocalStorageUri(storageUri ?? "");
  }, [storageUri]);

  useEffect(() => {
    setEditedValues({});
  }, [currentConfig]);

  const getInputValue = (key: string): string => {
    if (editedValues[key] !== undefined) return String(editedValues[key]);
    if (!currentConfig) return "";
    const val = currentConfig[key];
    return val !== undefined ? String(val) : "";
  };

  const handleCurrentValChange = (key: string, value: unknown) => {
    setEditedValues(prev => ({ ...prev, [key]: value }));
  };

  const getResourceValue = (tier: string, key: string): string => {
    return currentResources?.[tier]?.[key] ?? "";
  };

  const handleResourceChange = (resourceKey: string, value: string) => {
    setEditedValues(prev => ({ ...prev, [resourceKey]: value }));
  };

  const renderCurrentInput = (
    key: string,
    type: "number" | "text" | "checkbox" = "number",
    extras?: { step?: string; min?: number; max?: number }
  ) => {
    if (!currentConfig) return <span>—</span>;

    if (type === "checkbox") {
      const val = getInputValue(key);
      const isChecked = val.toLowerCase() === "true" || val === "1";
      return (
        <input
          type="checkbox"
          checked={isChecked}
          onChange={e => handleCurrentValChange(key, e.target.checked)}
        />
      );
    }

    return (
      <input
        className="input"
        type={type}
        step={extras?.step}
        min={extras?.min}
        max={extras?.max}
        value={getInputValue(key)}
        onChange={e =>
          handleCurrentValChange(key, type === "number" ? +e.target.value : e.target.value)
        }
        style={{ width: "100%" }}
      />
    );
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
          <select
            className="input"
            aria-label="Eval Mode"
            value={config.evaluation_mode}
            onChange={e => onChange("evaluation_mode", e.target.value as "single" | "sweep")}
          >
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
            <tr>
              <td title="Maximum number of sequences">max_num_seqs</td>
              <td className="td-current">{renderCurrentInput("max_num_seqs", "number")}</td>
              <td>
                <div className="flex-row-8">
                  <input className="input" type="number" placeholder="Min" min={1} max={2048} value={config.max_num_seqs_min}
                    onChange={e => onChange("max_num_seqs_min", +e.target.value)} />
                  <input className="input" type="number" placeholder="Max" min={1} max={2048} value={config.max_num_seqs_max}
                    onChange={e => onChange("max_num_seqs_max", +e.target.value)} />
                </div>
              </td>
              <td className="td-desc">Max concurrent sequences per iteration</td>
            </tr>
            <tr>
              <td title="GPU memory utilization fraction (0.0–1.0)">gpu_memory_utilization</td>
              <td className="td-current">{renderCurrentInput("gpu_memory_utilization", "number", { step: "0.01", min: 0, max: 1 })}</td>
              <td>
                <div className="flex-row-8">
                  <input className="input" type="number" step="0.01" placeholder="Min" min={0.5} max={0.99} value={config.gpu_memory_min}
                    onChange={e => onChange("gpu_memory_min", +e.target.value)} />
                  <input className="input" type="number" step="0.01" placeholder="Max" min={0.5} max={0.99} value={config.gpu_memory_max}
                    onChange={e => onChange("gpu_memory_max", +e.target.value)} />
                </div>
              </td>
              <td className="td-desc">GPU memory allocation fraction (0.0–1.0)</td>
            </tr>
            <tr>
              <td title="Maximum sequence length the model can handle">max_model_len</td>
              <td className="td-current">{renderCurrentInput("max_model_len", "number")}</td>
              <td>
                <div className="flex-row-8">
                  <input className="input" type="number" placeholder="Min" min={256} max={32768} step={256} value={config.max_model_len_min}
                    onChange={e => onChange("max_model_len_min", +e.target.value)} />
                  <input className="input" type="number" placeholder="Max" min={256} max={32768} step={256} value={config.max_model_len_max}
                    onChange={e => onChange("max_model_len_max", +e.target.value)} />
                </div>
              </td>
              <td className="td-desc">Maximum token length the model can process</td>
            </tr>
            <tr>
              <td title="Maximum number of tokens in a batch">max_num_batched_tokens</td>
              <td className="td-current">{renderCurrentInput("max_num_batched_tokens", "number")}</td>
              <td>
                <div className="flex-row-8">
                  <input className="input" type="number" placeholder="Min" min={256} max={8192} step={256} value={config.max_num_batched_tokens_min}
                    onChange={e => onChange("max_num_batched_tokens_min", +e.target.value)} />
                  <input className="input" type="number" placeholder="Max" min={256} max={8192} step={256} value={config.max_num_batched_tokens_max}
                    onChange={e => onChange("max_num_batched_tokens_max", +e.target.value)} />
                </div>
              </td>
              <td className="td-desc">Maximum tokens to process in one batch</td>
            </tr>
            <tr>
              <td title="KV cache block size">block_size</td>
              <td className="td-current">{renderCurrentInput("block_size", "number")}</td>
              <td>
                <div className="flex-row-12">
                  {[8, 16, 32].map(size => (
                    <label key={size} className="tuner-block-size-label">
                      <input type="checkbox"
                        checked={config.block_size_options.includes(size)}
                        onChange={e => {
                          const next = e.target.checked
                            ? [...config.block_size_options, size].sort((a, b) => a - b)
                            : config.block_size_options.filter(s => s !== size);
                          onChange("block_size_options", next);
                        }}
                      />
                      {size}
                    </label>
                  ))}
                </div>
              </td>
              <td className="td-desc">KV cache block size</td>
            </tr>
            <tr>
              <td title="CPU swap space in GB">swap_space</td>
              <td className="td-current">{renderCurrentInput("swap_space", "number", { step: "0.5", min: 0 })}</td>
              <td>
                <div className="flex-col-1">
                  <label className="label-flex label-no-mb" style={{ fontSize: '10px' }}>
                    <input type="checkbox"
                      checked={config.include_swap_space}
                      onChange={e => onChange("include_swap_space", e.target.checked)}
                    />
                    Include
                  </label>
                  {config.include_swap_space && (
                    <div className="flex-row-8" style={{ marginTop: '4px' }}>
                      <input className="input" type="number" step="0.5" placeholder="Min GB" min={0} max={64} value={config.swap_space_min}
                        onChange={e => onChange("swap_space_min", +e.target.value)} />
                      <input className="input" type="number" step="0.5" placeholder="Max GB" min={0} max={64} value={config.swap_space_max}
                        onChange={e => onChange("swap_space_max", +e.target.value)} />
                    </div>
                  )}
                </div>
              </td>
              <td className="td-desc">CPU swap space size (GB)</td>
            </tr>
            <tr>
              <td title="enable_chunked_prefill">Chunked Prefill</td>
              <td className="td-current">{renderCurrentInput("enable_chunked_prefill", "checkbox")}</td>
              <td>—</td>
              <td className="td-desc">Enable chunked prefill</td>
            </tr>
            <tr>
              <td title="enable_enforce_eager">Enforce Eager</td>
              <td className="td-current">{renderCurrentInput("enable_enforce_eager", "checkbox")}</td>
              <td>—</td>
              <td className="td-desc">Disable CUDA graph (force eager mode)</td>
            </tr>
            <tr>
              <td title="resources.requests.cpu">CPU Requests</td>
              <td className="td-current">
                <input type="text" value={editedValues["resources.requests.cpu"] as string ?? getResourceValue("requests", "cpu")}
                       onChange={e => handleResourceChange("resources.requests.cpu", e.target.value)}
                       placeholder="e.g. 4, 500m" />
              </td>
              <td>—</td>
              <td className="td-desc">CPU request (e.g. 4, 500m)</td>
            </tr>
            <tr>
              <td title="resources.limits.cpu">CPU Limits</td>
              <td className="td-current">
                <input type="text" value={editedValues["resources.limits.cpu"] as string ?? getResourceValue("limits", "cpu")}
                       onChange={e => handleResourceChange("resources.limits.cpu", e.target.value)}
                       placeholder="e.g. 8, 1000m" />
              </td>
              <td>—</td>
              <td className="td-desc">CPU limit (e.g. 8, 1000m)</td>
            </tr>
            <tr>
              <td title="resources.requests.memory">Memory Requests</td>
              <td className="td-current">
                <input type="text" value={editedValues["resources.requests.memory"] as string ?? getResourceValue("requests", "memory")}
                       onChange={e => handleResourceChange("resources.requests.memory", e.target.value)}
                       placeholder="e.g. 8Gi, 512Mi" />
              </td>
              <td>—</td>
              <td className="td-desc">Memory request (e.g. 8Gi, 512Mi)</td>
            </tr>
            <tr>
              <td title="resources.limits.memory">Memory Limits</td>
              <td className="td-current">
                <input type="text" value={editedValues["resources.limits.memory"] as string ?? getResourceValue("limits", "memory")}
                       onChange={e => handleResourceChange("resources.limits.memory", e.target.value)}
                       placeholder="e.g. 16Gi" />
              </td>
              <td>—</td>
              <td className="td-desc">Memory limit (e.g. 16Gi)</td>
            </tr>
            <tr>
              <td title="resources.limits.nvidia.com/gpu">GPU Limits</td>
              <td className="td-current">
                <input type="number" min={0} step={1}
                       value={editedValues["resources.limits.nvidia.com/gpu"] as string ?? getResourceValue("limits", "nvidia.com/gpu")}
                       onChange={e => handleResourceChange("resources.limits.nvidia.com/gpu", e.target.value)}
                       placeholder="0" />
              </td>
              <td>—</td>
              <td className="td-desc">GPU count</td>
            </tr>
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
                   <input
                     className="input"
                     type="text"
                     value={localStorageUri}
                     onChange={e => setLocalStorageUri(e.target.value)}
                     disabled={isRunning}
                     placeholder="oci://registry/model"
                     aria-label="storageUri"
                   />
                   <button
                     className="btn btn-primary btn-small"
                     onClick={() => onSaveStorageUri(localStorageUri)}
                     disabled={isRunning || localStorageUri === storageUri}
                     style={{ whiteSpace: 'nowrap' }}
                   >
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
           <input className="input" type="number" aria-label="Eval Request Count" min={10} max={10000} step={10} value={config.eval_requests}
             onChange={e => onChange("eval_requests", +e.target.value)} />
        </div>
        <div>
          <label className="label">Eval Concurrency</label>
           <input className="input" type="number" aria-label="Eval Concurrency" min={1} max={256} value={config.eval_concurrency}
             onChange={e => onChange("eval_concurrency", +e.target.value)} />
        </div>
        <div>
          <label className="label">Eval RPS</label>
           <input className="input" type="number" aria-label="Eval RPS" min={1} max={1000} value={config.eval_rps}
             onChange={e => onChange("eval_rps", +e.target.value)} />
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
          <button
            className="btn btn-secondary"
            onClick={() => onApplyCurrentValues(editedValues)}
            disabled={Object.keys(editedValues).length === 0}
          >
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
