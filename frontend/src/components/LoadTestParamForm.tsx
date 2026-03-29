import { memo } from "react";

interface SyntheticConfig {
  distribution: 'uniform' | 'normal';
  min_tokens: number;
  max_tokens: number;
  mean_tokens?: number;
  stddev_tokens?: number;
}

interface LoadTestParamFormProps {
  config: Record<string, string | number | boolean>;
  onChange: (key: string, value: string | number | boolean) => void;
  promptMode?: 'static' | 'synthetic';
  onPromptModeChange?: (mode: 'static' | 'synthetic') => void;
  syntheticConfig?: SyntheticConfig;
  onSyntheticConfigChange?: (key: string, value: string | number) => void;
}

const PARAM_FIELDS = [
  ["vLLM Endpoint", "endpoint", "text"],
  ["Model", "model", "text"],
  ["Total Requests", "total_requests", "number"],
  ["Concurrency", "concurrency", "number"],
  ["RPS (0=unlimited)", "rps", "number"],
  ["Max Tokens", "max_tokens", "number"],
] as const;

const LoadTestParamForm = memo(function LoadTestParamForm({ config, onChange, promptMode, onPromptModeChange, syntheticConfig, onSyntheticConfigChange }: LoadTestParamFormProps) {
  return (
    <div className="grid-form grid-form-compact">
      {PARAM_FIELDS.map(([label, key, type]) => (
        <div key={key}>
          <label className="label" htmlFor={`ltc-${key}`}>{label}</label>
          <input
            id={`ltc-${key}`}
            className="input"
            type={type}
            value={config[key] as string | number}
            placeholder={key === "model" ? "auto (auto-detect)" : undefined}
            onChange={e => onChange(key, type === "number" ? +e.target.value : e.target.value)}
          />
        </div>
      ))}
      <div>
        <div className="label">Prompt Mode</div>
        <div style={{ display: 'flex', gap: '8px', marginBottom: '8px' }}>
          <button
            type="button"
            className={promptMode === 'synthetic' ? 'btn btn-outline' : 'btn btn-primary'}
            style={{ fontSize: '13px', padding: '4px 12px' }}
            onClick={() => onPromptModeChange?.('static')}
          >
            Direct Input
          </button>
          <button
            type="button"
            className={promptMode === 'synthetic' ? 'btn btn-primary' : 'btn btn-outline'}
            style={{ fontSize: '13px', padding: '4px 12px' }}
            onClick={() => onPromptModeChange?.('synthetic')}
          >
            Synthetic
          </button>
        </div>
        {promptMode === 'synthetic' ? (
          <div style={{ border: '1px solid var(--border)', borderRadius: '6px', padding: '12px' }}>
            <div style={{ marginBottom: '8px' }}>
              <label className="label" htmlFor="ltc-syn-distribution">Distribution</label>
              <select
                id="ltc-syn-distribution"
                className="input"
                value={syntheticConfig?.distribution ?? 'uniform'}
                onChange={e => onSyntheticConfigChange?.('distribution', e.target.value)}
              >
                <option value="uniform">Uniform</option>
                <option value="normal">Normal</option>
              </select>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px' }}>
              <div>
                <label className="label" htmlFor="ltc-syn-min">Min Tokens</label>
                <input id="ltc-syn-min" className="input" type="number" min={1} value={syntheticConfig?.min_tokens ?? 50}
                  onChange={e => onSyntheticConfigChange?.('min_tokens', +e.target.value)} />
              </div>
              <div>
                <label className="label" htmlFor="ltc-syn-max">Max Tokens</label>
                <input id="ltc-syn-max" className="input" type="number" min={1} value={syntheticConfig?.max_tokens ?? 500}
                  onChange={e => onSyntheticConfigChange?.('max_tokens', +e.target.value)} />
              </div>
              {syntheticConfig?.distribution === 'normal' && (
                <>
                  <div>
                    <label className="label" htmlFor="ltc-syn-mean">Mean Tokens</label>
                    <input id="ltc-syn-mean" className="input" type="number" min={1} value={syntheticConfig?.mean_tokens ?? 200}
                      onChange={e => onSyntheticConfigChange?.('mean_tokens', +e.target.value)} />
                  </div>
                  <div>
                    <label className="label" htmlFor="ltc-syn-std">Std Dev</label>
                    <input id="ltc-syn-std" className="input" type="number" min={1} value={syntheticConfig?.stddev_tokens ?? 50}
                      onChange={e => onSyntheticConfigChange?.('stddev_tokens', +e.target.value)} />
                  </div>
                </>
              )}
            </div>
          </div>
        ) : (
          <textarea
            className="input loadtest-config-textarea"
            aria-label="Prompt template"
            rows={3}
            value={config.prompt_template as string}
            onChange={e => onChange("prompt_template", e.target.value)}
          />
        )}
      </div>
      <div>
        <label className="label" htmlFor="ltc-temperature">Temperature</label>
        <input
          id="ltc-temperature"
          className="input"
          type="number"
          step="0.1"
          min="0"
          max="2"
          value={config.temperature as number}
          onChange={e => onChange("temperature", +e.target.value)}
        />
      </div>
    </div>
  );
});

export default LoadTestParamForm;
