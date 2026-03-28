import type { TunerConfig } from "./TunerConfigForm";

interface TunerParamInputsProps {
  config: TunerConfig;
  onChange: (field: string, value: string | number | boolean | number[]) => void;
  editedValues: Record<string, unknown>;
  currentConfig: Record<string, unknown> | null;
  handleChange: (key: string, value: unknown) => void;
}

export default function TunerParamInputs({
  config,
  onChange,
  editedValues,
  currentConfig,
  handleChange,
}: TunerParamInputsProps) {
  const getInputValue = (key: string): string => {
    if (editedValues[key] !== undefined) return String(editedValues[key]);
    if (!currentConfig) return "";
    const val = currentConfig[key];
    return val !== undefined ? String(val) : "";
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
          onChange={e => handleChange(key, e.target.checked)}
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
          handleChange(key, type === "number" ? +e.target.value : e.target.value)
        }
        style={{ width: "100%" }}
      />
    );
  };

  return (
    <>
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
    </>
  );
}
