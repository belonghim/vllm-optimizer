import { useState, useMemo, useEffect } from "react";
import type { SSEState } from "../types";
import { loadPresets, savePreset, deletePreset, isBuiltinPreset } from "../utils/presets";

interface SyntheticConfig {
  distribution: 'uniform' | 'normal';
  min_tokens: number;
  max_tokens: number;
  mean_tokens?: number;
  stddev_tokens?: number;
}

interface LoadTestConfigData {
  endpoint: string;
  model: string;
  total_requests: number;
  concurrency: number;
  rps: number;
  max_tokens: number;
  prompt_template: string;
  temperature: number;
  stream: boolean;
  [key: string]: string | number | boolean;
}

export interface RerunConfig {
  total_requests?: number;
  concurrency?: number;
  rps?: number;
  max_tokens?: number;
  temperature?: number;
  stream?: boolean;
}

interface LoadTestConfigProps {
  config: LoadTestConfigData;
  onChange: (key: string, value: string | number | boolean) => void;
  onSubmit: () => void;
  onStop: () => void;
  isRunning: boolean;
  status: SSEState['status'];
  initialConfig?: RerunConfig | null;
  onInitialConfigApplied?: () => void;
  promptMode?: 'static' | 'synthetic';
  onPromptModeChange?: (mode: 'static' | 'synthetic') => void;
  syntheticConfig?: SyntheticConfig;
  onSyntheticConfigChange?: (key: string, value: string | number) => void;
}

function LoadTestConfig({ config, onChange, onSubmit, onStop, isRunning, status, initialConfig, onInitialConfigApplied, promptMode, onPromptModeChange, syntheticConfig, onSyntheticConfigChange }: LoadTestConfigProps) {
  const [selectedPreset, setSelectedPreset] = useState<string>("");

  useEffect(() => {
    if (!initialConfig) return;
    const fields = ['total_requests', 'concurrency', 'rps', 'max_tokens', 'temperature', 'stream'] as const;
    for (const key of fields) {
      const val = initialConfig[key];
      if (val !== undefined) onChange(key, val);
    }
    onInitialConfigApplied?.();
  }, [initialConfig, onChange, onInitialConfigApplied]);
  const presets = useMemo(() => loadPresets(), []);
  const presetNames = useMemo(() => Object.keys(presets), [presets]);

  const handlePresetSelect = (presetName: string) => {
    if (!presetName) return;
    const preset = presets[presetName];
    if (preset) {
      onChange("total_requests", preset.total_requests);
      onChange("concurrency", preset.concurrency);
      onChange("rps", preset.rps);
      onChange("max_tokens", preset.max_tokens);
      onChange("temperature", preset.temperature);
      onChange("stream", preset.stream);
      setSelectedPreset(presetName);
    }
  };

  const handleSavePreset = () => {
    const name = prompt("Enter preset name:");
    if (name?.trim()) {
      try {
        savePreset(name, {
          total_requests: config.total_requests,
          concurrency: config.concurrency,
          rps: config.rps,
          max_tokens: config.max_tokens,
          temperature: config.temperature,
          stream: config.stream,
        });
        setSelectedPreset(name);
        window.location.reload();
      } catch (e) {
        alert((e as Error).message);
      }
    }
  };

  const handleDeletePreset = () => {
    if (!selectedPreset || isBuiltinPreset(selectedPreset)) return;
    if (confirm(`Delete preset "${selectedPreset}"?`)) {
      try {
        deletePreset(selectedPreset);
        setSelectedPreset("");
        window.location.reload();
      } catch (e) {
        alert((e as Error).message);
      }
    }
  };

  return (
    <div className="panel">
      <div className="section-title">Load Test Settings</div>

      <div style={{ marginBottom: "16px" }}>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: "8px", alignItems: "flex-end" }}>
          <div>
            <label className="label" htmlFor="ltc-preset">Preset</label>
            <select
              id="ltc-preset"
              className="input"
              value={selectedPreset}
              onChange={e => handlePresetSelect(e.target.value)}
            >
              <option value="">-- Select --</option>
              {presetNames.map(name => (
                <option key={name} value={name}>
                  {name}
                </option>
              ))}
            </select>
          </div>
          <button type="button" className="btn btn-primary" onClick={handleSavePreset} style={{ height: "36px" }}>
            💾 Save
          </button>
          <button
            type="button"
            className="btn btn-danger"
            onClick={handleDeletePreset}
            disabled={!selectedPreset || isBuiltinPreset(selectedPreset)}
            style={{ height: "36px" }}
          >
            🗑 Delete
          </button>
        </div>
      </div>
      <div className="grid-form grid-form-compact">
        {([
          ["vLLM Endpoint", "endpoint", "text"],
          ["Model", "model", "text"],
          ["Total Requests", "total_requests", "number"],
          ["Concurrency", "concurrency", "number"],
          ["RPS (0=unlimited)", "rps", "number"],
          ["Max Tokens", "max_tokens", "number"],
        ] as const).map(([label, key, type]) => (
          <div key={key}>
            <label className="label" htmlFor={`ltc-${key}`}>{label}</label>
            <input
              id={`ltc-${key}`}
              className="input"
              type={type}
              value={config[key]}
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

  {(promptMode === 'synthetic') ? (
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
      value={config.prompt_template}
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
            value={config.temperature}
            onChange={e => onChange("temperature", +e.target.value)}
          />
        </div>
      </div>

      <div className="loadtest-stream-toggle">
        <input type="checkbox" id="stream" checked={config.stream}
          onChange={e => onChange("stream", e.target.checked)} />
        <label htmlFor="stream" className="label label-no-mb">
          Streaming Mode (enable TTFT measurement)
        </label>
      </div>

      <div className="loadtest-config-actions">
        <button type="button" className="btn btn-primary" onClick={onSubmit} disabled={isRunning}>
          ▶ Run Load Test
        </button>
        <button type="button" className="btn btn-danger" onClick={onStop} disabled={!isRunning}>
          ■ Stop
        </button>
        <span className={`tag tag-${status}`}>{status.toUpperCase()}</span>
      </div>
    </div>
  );
}

export default LoadTestConfig;
