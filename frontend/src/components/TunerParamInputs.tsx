import type { TunerConfig } from './TunerConfigForm';
import { parseNumberInput } from '../utils/numberInput';

interface TunerParamInputsProps {
  config: TunerConfig;
  onChange: (field: string, value: string | number | boolean) => void;
  editedValues: Record<string, unknown>;
  currentConfig: Record<string, unknown> | null;
  handleChange: (key: string, value: unknown) => void;
  maxModelLenLimit?: number | null;
}

export default function TunerParamInputs({
  config,
  onChange,
  editedValues,
  currentConfig,
  handleChange,
  maxModelLenLimit,
}: TunerParamInputsProps) {
  const modelLenTooLong = !!maxModelLenLimit && config.max_model_len > maxModelLenLimit;
  const getInputValue = (key: string): string => {
    if (editedValues[key] !== undefined) return String(editedValues[key]);
    if (!currentConfig) return '';
    const val = currentConfig[key];
    return val !== undefined ? String(val) : '';
  };

  const renderCurrentInput = (
    key: string,
    type: 'number' | 'text' = 'number',
    extras?: { step?: string; min?: number; max?: number }
  ) => {
    if (!currentConfig) return <span>—</span>;

    const id = `tuner-current-${key}`;

    return (
      <label htmlFor={id} style={{ width: '100%', display: 'block' }}>
        <input
          id={id}
          className="input"
          type={type}
          step={extras?.step}
          min={extras?.min}
          max={extras?.max}
          value={getInputValue(key)}
          onChange={(e) =>
            handleChange(
              key,
              type === 'number'
                ? parseNumberInput(e.target.value, Number(getInputValue(key)) || 0)
                : e.target.value
            )
          }
          style={{ width: '100%' }}
          aria-label={`Current ${key}`}
        />
      </label>
    );
  };

  return (
    <>
      <tr>
        <td title="Maximum number of sequences">max_num_seqs</td>
        <td className="td-current">{renderCurrentInput('max_num_seqs', 'number')}</td>
        <td>
          <div className="flex-row-8">
            <input
              id="tuner-param-max_num_seqs_min"
              className="input"
              type="number"
              placeholder="Min"
              min={1}
              max={2048}
              value={config.max_num_seqs_min}
              onChange={(e) =>
                onChange(
                  'max_num_seqs_min',
                  parseNumberInput(e.target.value, config.max_num_seqs_min)
                )
              }
              aria-label="max_num_seqs min"
            />
            <input
              id="tuner-param-max_num_seqs_max"
              className="input"
              type="number"
              placeholder="Max"
              min={1}
              max={2048}
              value={config.max_num_seqs_max}
              onChange={(e) =>
                onChange(
                  'max_num_seqs_max',
                  parseNumberInput(e.target.value, config.max_num_seqs_max)
                )
              }
              aria-label="max_num_seqs max"
            />
          </div>
        </td>
        <td className="td-desc">Max concurrent sequences per iteration</td>
      </tr>
      <tr>
        <td title="GPU memory utilization fraction (0.0–1.0)">gpu_memory_utilization</td>
        <td className="td-current">
          {renderCurrentInput('gpu_memory_utilization', 'number', { step: '0.01', min: 0, max: 1 })}
        </td>
        <td>
          <div className="flex-row-8">
            <input
              id="tuner-param-gpu_memory_min"
              className="input"
              type="number"
              step="0.01"
              placeholder="Min"
              min={0.5}
              max={0.99}
              value={config.gpu_memory_min}
              onChange={(e) =>
                onChange('gpu_memory_min', parseNumberInput(e.target.value, config.gpu_memory_min))
              }
              aria-label="gpu_memory_utilization min"
            />
            <input
              id="tuner-param-gpu_memory_max"
              className="input"
              type="number"
              step="0.01"
              placeholder="Max"
              min={0.5}
              max={0.99}
              value={config.gpu_memory_max}
              onChange={(e) =>
                onChange('gpu_memory_max', parseNumberInput(e.target.value, config.gpu_memory_max))
              }
              aria-label="gpu_memory_utilization max"
            />
          </div>
        </td>
        <td className="td-desc">GPU memory allocation fraction (0.0–1.0)</td>
      </tr>
      <tr>
        <td title="Context length the service must support — fixed during tuning">max_model_len</td>
        <td className="td-current">{renderCurrentInput('max_model_len', 'number')}</td>
        <td>
          <input
            id="tuner-param-max_model_len"
            className="input"
            type="number"
            min={256}
            max={maxModelLenLimit ?? undefined}
            step={256}
            value={config.max_model_len}
            onChange={(e) =>
              onChange('max_model_len', parseNumberInput(e.target.value, config.max_model_len))
            }
            aria-label="max_model_len"
            aria-invalid={modelLenTooLong}
          />
        </td>
        <td className="td-desc">
          Fixed (not searched)
          {maxModelLenLimit ? ` · model limit ${maxModelLenLimit}` : ''}
          {modelLenTooLong && (
            <span style={{ color: 'var(--red-color)' }}> — exceeds the model limit</span>
          )}
        </td>
      </tr>
      <tr>
        <td title="Maximum number of tokens in a batch">max_num_batched_tokens</td>
        <td className="td-current">{renderCurrentInput('max_num_batched_tokens', 'number')}</td>
        <td>
          <div className="flex-row-8">
            <input
              id="tuner-param-max_num_batched_tokens_min"
              className="input"
              type="number"
              placeholder="Min"
              min={256}
              max={8192}
              step={256}
              value={config.max_num_batched_tokens_min}
              onChange={(e) =>
                onChange(
                  'max_num_batched_tokens_min',
                  parseNumberInput(e.target.value, config.max_num_batched_tokens_min)
                )
              }
              aria-label="max_num_batched_tokens min"
            />
            <input
              id="tuner-param-max_num_batched_tokens_max"
              className="input"
              type="number"
              placeholder="Max"
              min={256}
              max={8192}
              step={256}
              value={config.max_num_batched_tokens_max}
              onChange={(e) =>
                onChange(
                  'max_num_batched_tokens_max',
                  parseNumberInput(e.target.value, config.max_num_batched_tokens_max)
                )
              }
              aria-label="max_num_batched_tokens max"
            />
          </div>
        </td>
        <td className="td-desc">Maximum tokens to process in one batch</td>
      </tr>
    </>
  );
}
