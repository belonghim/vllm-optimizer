import { useState, useEffect, useCallback } from "react";
import { authFetch } from '../utils/authFetch';
import { API } from "../constants";
import { ERROR_MESSAGES } from "../constants/errorMessages";
import { useMockData } from "../contexts/MockDataContext";
import { useClusterConfig } from "../contexts/ClusterConfigContext";
import TunerConfigForm from "./TunerConfigForm";
import type { TunerPhase, TunerConfig } from "../types";

interface TunerCurrentConfigProps {
  isActive: boolean;
  isRunning: boolean;
  config: TunerConfig;
  onChange: (field: string, value: string | number | boolean | number[]) => void;
  onSubmit: () => void;
  onStop: () => void;
  onApplyBest: () => void;
  hasBest: boolean;
  currentPhase: TunerPhase | null;
  trialsCompleted: number;
  onError: (msg: string | null) => void;
  onApplySuccess: () => void;
}

export default function TunerCurrentConfig({
  isActive,
  isRunning,
  config,
  onChange,
  onSubmit,
  onStop,
  onApplyBest,
  hasBest,
  currentPhase,
  trialsCompleted,
  onError,
  onApplySuccess,
}: TunerCurrentConfigProps) {
  const { isMockEnabled } = useMockData();
  const { namespace, inferenceservice } = useClusterConfig();
  const [currentConfig, setCurrentConfig] = useState<Record<string, unknown> | null>(null);
  const [currentResources, setCurrentResources] = useState<Record<string, Record<string, string>> | null>(null);
  const [storageUri, setStorageUri] = useState<string | null>(null);
  const [extraArgs, setExtraArgs] = useState<string[]>([]);

  useEffect(() => {
    if (!isActive) return;
    if (isMockEnabled) return;

    const controller = new AbortController();
    authFetch(`${API}/vllm-config`, { signal: controller.signal })
      .then(r => {
        if (!r.ok) {
          return r.json().then(errData => {
            throw new Error(errData.detail || `HTTP ${r.status}`);
          });
        }
        return r.json();
      })
      .then(data => {
        if (data.success) {
          setCurrentConfig(data.data);
          setStorageUri(data.storageUri ?? null);
          setCurrentResources(data.resources ?? null);
          setExtraArgs(data.extraArgs ?? []);
        } else {
          onError(data.message || ERROR_MESSAGES.TUNER.CONFIG_FETCH_FAILED);
        }
      })
      .catch((err: Error) => {
        if (err.name === 'AbortError') return;
        console.error('Failed to fetch vLLM config:', err);
        onError(`${ERROR_MESSAGES.TUNER.CONFIG_FETCH_ERROR_PREFIX}${err.message}`);
      });
    return () => controller.abort();
  }, [isActive, isMockEnabled, namespace, inferenceservice, onError]);

  const handleApplyCurrentValues = useCallback(async (values: Record<string, unknown>) => {
    const confirmed = window.confirm(ERROR_MESSAGES.TUNER.RESTART_CONFIRM);
    if (!confirmed) return;
    try {
      const dataPayload: Record<string, string> = {};
      const resourcesPayload: Record<string, Record<string, string>> = {};

      for (const [key, val] of Object.entries(values)) {
        if (key.startsWith("resources.")) {
          const parts = key.split(".");
          const tier = parts[1];
          const resKey = parts.slice(2).join(".");
          if (!resourcesPayload[tier]) resourcesPayload[tier] = {};
          resourcesPayload[tier][resKey] = String(val);
        } else {
          dataPayload[key] = String(val);
        }
      }

      const patchBody: Record<string, unknown> = {};
      if (Object.keys(dataPayload).length > 0) patchBody.data = dataPayload;
      if (Object.keys(resourcesPayload).length > 0) patchBody.resources = resourcesPayload;

      const res = await authFetch(`${API}/vllm-config`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(patchBody),
      });
      const data = await res.json();
      if (!res.ok || !data.success) {
        onError(`${ERROR_MESSAGES.TUNER.APPLY_CURRENT_FAILED_PREFIX}${data.detail || res.status}`);
        return;
      }
      setCurrentConfig(prev => (prev ? { ...prev, ...values } : null));
      onApplySuccess();
    } catch (err) {
      console.error('Failed to apply current values:', err);
      onError(`${ERROR_MESSAGES.TUNER.APPLY_CURRENT_FAILED_PREFIX}${(err as Error).message}`);
    }
  }, [onError, onApplySuccess]);

  const handleSaveStorageUri = useCallback(async (newUri: string) => {
    try {
      const res = await authFetch(`${API}/vllm-config`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ storageUri: newUri }),
      });
      const data = await res.json();
      if (!res.ok || !data.success) {
        onError(`${ERROR_MESSAGES.TUNER.STORAGE_URI_UPDATE_FAILED_PREFIX}${data.detail || res.status}`);
        return;
      }
      setStorageUri(newUri);
    } catch (err) {
      console.error('Failed to save storage URI:', err);
      onError(`${ERROR_MESSAGES.TUNER.STORAGE_URI_UPDATE_FAILED_PREFIX}${(err as Error).message}`);
    }
  }, [onError]);

  return (
    <TunerConfigForm
      config={config}
      onChange={onChange}
      onSubmit={onSubmit}
      onStop={onStop}
      onApplyBest={onApplyBest}
      isRunning={isRunning}
      hasBest={hasBest}
      currentConfig={currentConfig}
      currentResources={currentResources}
      storageUri={storageUri}
      onSaveStorageUri={handleSaveStorageUri}
      onApplyCurrentValues={handleApplyCurrentValues}
      currentPhase={currentPhase}
      trialsCompleted={trialsCompleted}
      extraArgs={extraArgs}
    />
  );
}
