import { useState, useMemo, useEffect } from "react";
import type { SSEState } from "../types";
import { loadPresets, savePreset, deletePreset, isBuiltinPreset } from "../utils/presets";
import LoadTestPresetSelector from "./LoadTestPresetSelector";
import LoadTestParamForm from "./LoadTestParamForm";

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
      <LoadTestPresetSelector
        presetNames={presetNames}
        selectedPreset={selectedPreset}
        onSelect={handlePresetSelect}
        onSave={handleSavePreset}
        onDelete={handleDeletePreset}
        canDelete={!!selectedPreset && !isBuiltinPreset(selectedPreset)}
      />
      <LoadTestParamForm
        config={config}
        onChange={onChange}
        promptMode={promptMode}
        onPromptModeChange={onPromptModeChange}
        syntheticConfig={syntheticConfig}
        onSyntheticConfigChange={onSyntheticConfigChange}
      />
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
