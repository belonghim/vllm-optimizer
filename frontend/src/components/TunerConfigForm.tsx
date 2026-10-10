import { useState, useEffect } from 'react';
import TunerProgressBar from './TunerProgressBar';
import TunerParamInputs from './TunerParamInputs';
import TunerResourceInputs from './TunerResourceInputs';
import { parseNumberInput } from '../utils/numberInput';
import type { TunerConfig } from '../types';

interface TunerPhase {
  trial_id: number;
  phase: string;
}

export type { TunerConfig } from '../types';

interface TunerConfigFormProps {
  config: TunerConfig;
  maxModelLenLimit?: number | null;
  onChange: (field: string, value: string | number | boolean) => void;
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
  applying_config: 'Updating config...',
  restarting: 'Restarting InferenceService...',
  waiting_ready: 'Waiting for Pod Ready...',
  warmup: 'Sending warmup requests...',
  evaluating: 'Evaluating performance...',
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
  maxModelLenLimit,
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
  const [localStorageUri, setLocalStorageUri] = useState(storageUri ?? '');
  const [editedValues, setEditedValues] = useState<Record<string, unknown>>({});
  const [resourceErrors, setResourceErrors] = useState<Record<string, boolean>>({});

  useEffect(() => {
    setLocalStorageUri(storageUri ?? '');
  }, [storageUri]);

  useEffect(() => {
    setEditedValues({});
  }, []);

  const handleCurrentValChange = (key: string, value: unknown) => {
    setEditedValues((prev) => ({ ...prev, [key]: value }));
  };

  const getResourceValue = (tier: string, key: string): string => {
    return currentResources?.[tier]?.[key] ?? '';
  };

  const handleResourceChange = (resourceKey: string, value: string) => {
    setEditedValues((prev) => ({ ...prev, [resourceKey]: value }));

    let isValid = true;
    if (resourceKey === 'resources.requests.cpu' || resourceKey === 'resources.limits.cpu') {
      isValid = isValidCpu(value);
    } else if (
      resourceKey === 'resources.requests.memory' ||
      resourceKey === 'resources.limits.memory'
    ) {
      isValid = isValidMemory(value);
    } else if (resourceKey === 'resources.limits.nvidia.com/gpu') {
      isValid = isValidGpu(value);
    }

    setResourceErrors((prev) => ({ ...prev, [resourceKey]: !isValid }));
  };

  return (
    <div className="panel">
      <div className="section-title">Service Target</div>
      <p className="td-desc" style={{ marginTop: 0 }}>
        Finds the vLLM settings with the highest TPS for this many concurrent users while P99
        end-to-end latency stays within the SLA.
      </p>
      <div className="grid-form grid-form-compact" style={{ marginBottom: '20px' }}>
        <div>
          <label className="label" htmlFor="tuner-eval-concurrency">
            Concurrent Users
          </label>
          <input
            id="tuner-eval-concurrency"
            className="input"
            type="number"
            min={1}
            max={512}
            value={config.eval_concurrency}
            onChange={(e) =>
              onChange(
                'eval_concurrency',
                parseNumberInput(e.target.value, config.eval_concurrency)
              )
            }
          />
        </div>
        <div>
          <label className="label" htmlFor="tuner-p99-sla">
            P99 Latency SLA (ms)
          </label>
          <input
            id="tuner-p99-sla"
            className="input"
            type="number"
            min={100}
            max={600000}
            step={100}
            value={config.p99_latency_sla_ms}
            onChange={(e) =>
              onChange(
                'p99_latency_sla_ms',
                parseNumberInput(e.target.value, config.p99_latency_sla_ms)
              )
            }
          />
        </div>
        <div>
          <label className="label" htmlFor="tuner-max-tokens">
            Output Tokens / Request
          </label>
          <input
            id="tuner-max-tokens"
            className="input"
            type="number"
            min={1}
            max={8192}
            value={config.max_tokens}
            onChange={(e) =>
              onChange('max_tokens', parseNumberInput(e.target.value, config.max_tokens))
            }
          />
        </div>
        <div>
          <label className="label" htmlFor="tuner-trials">
            Trial Count
          </label>
          <input
            id="tuner-trials"
            className="input"
            type="number"
            min={1}
            max={100}
            value={config.n_trials}
            onChange={(e) =>
              onChange('n_trials', parseNumberInput(e.target.value, config.n_trials))
            }
          />
        </div>
      </div>

      <div className="section-title">Search Space</div>
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
              maxModelLenLimit={maxModelLenLimit}
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
                  <input
                    className="input"
                    type="text"
                    value={localStorageUri}
                    onChange={(e) => setLocalStorageUri(e.target.value)}
                    disabled={isRunning}
                    placeholder="oci://registry/model"
                    aria-label="storageUri"
                  />
                  <button
                    type="button"
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

      <div className="grid-form grid-form-compact" style={{ marginBottom: '12px' }}>
        <div>
          <label className="label" htmlFor="tuner-eval-requests">
            Eval Requests / Trial
          </label>
          <input
            id="tuner-eval-requests"
            className="input"
            type="number"
            min={10}
            max={1000}
            step={10}
            value={config.eval_requests}
            onChange={(e) =>
              onChange('eval_requests', parseNumberInput(e.target.value, config.eval_requests))
            }
          />
        </div>
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '20px' }}>
        <input
          id="tuner-llm-assistant"
          type="checkbox"
          checked={config.enable_llm_assistant ?? true}
          onChange={(e) => onChange('enable_llm_assistant', e.target.checked)}
          disabled={isRunning}
        />
        <label
          className="label"
          htmlFor="tuner-llm-assistant"
          style={{ margin: 0, cursor: isRunning ? 'default' : 'pointer' }}
        >
          Use analyst LLM (ANALYST_ENDPOINT) for warm-start suggestions, failure analysis and the
          final report
        </label>
      </div>

      <div className="tuner-config-actions">
        <button
          type="button"
          className="btn btn-primary"
          onClick={onSubmit}
          disabled={isRunning || (!!maxModelLenLimit && config.max_model_len > maxModelLenLimit)}
        >
          ▶ Start Tuning
        </button>
        <button type="button" className="btn btn-danger" onClick={onStop} disabled={!isRunning}>
          ■ Stop
        </button>
        {hasBest && (
          <button type="button" className="btn btn-green" onClick={onApplyBest}>
            ✓ Apply Best Params
          </button>
        )}
        {onApplyCurrentValues && currentConfig && (
          <button
            type="button"
            className="btn btn-secondary"
            onClick={() => onApplyCurrentValues(editedValues)}
            disabled={
              Object.keys(editedValues).length === 0 || Object.values(resourceErrors).some((e) => e)
            }
          >
            Apply Current Values
          </button>
        )}
        <span className={`tag tag-${isRunning ? 'running' : 'idle'}`}>
          {isRunning ? 'TUNING...' : 'IDLE'}
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
          Trial {(currentPhase.trial_id ?? 0) + 1}:{' '}
          {PHASE_LABELS[currentPhase.phase] || currentPhase.phase}
        </div>
      )}
    </div>
  );
}
