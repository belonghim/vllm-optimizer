import { useState, useEffect } from "react";
import { API } from "../constants";

const PHASE_LABELS = {
  applying_config: "설정 업데이트 중...",
  restarting: "InferenceService 재시작 중...",
  waiting_ready: "Pod Ready 대기 중...",
  warmup: "Warmup 요청 전송 중...",
  evaluating: "성능 평가 중...",
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
  showAdvanced,
  onToggleAdvanced,
  storageUri,
  onSaveStorageUri,
}) {
  const [localStorageUri, setLocalStorageUri] = useState(storageUri ?? "");
  const [showVllmSettings, setShowVllmSettings] = useState(false);
  const [vllmSettings, setVllmSettings] = useState({
    vllm_endpoint: "",
    vllm_namespace: "",
    vllm_is_name: "",
  });
  const [vllmSettingsOriginal, setVllmSettingsOriginal] = useState({
    vllm_endpoint: "",
    vllm_namespace: "",
    vllm_is_name: "",
  });
  const [vllmSettingsMessage, setVllmSettingsMessage] = useState(null);
  const [vllmSettingsSaving, setVllmSettingsSaving] = useState(false);

  // Load vLLM settings on mount
  useEffect(() => {
    fetch(`${API}/config`)
      .then(r => r.json())
      .then(data => {
        const settings = {
          vllm_endpoint: data.vllm_endpoint || "",
          vllm_namespace: data.vllm_namespace || "",
          vllm_is_name: data.vllm_is_name || "",
        };
        setVllmSettings(settings);
        setVllmSettingsOriginal(settings);
      })
      .catch(() => {});
  }, []);

  const handleVllmSettingChange = (field, value) => {
    setVllmSettings(prev => ({ ...prev, [field]: value }));
    setVllmSettingsMessage(null);
  };

  const handleSaveVllmSettings = async () => {
    setVllmSettingsSaving(true);
    setVllmSettingsMessage(null);
    try {
      const res = await fetch(`${API}/config`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(vllmSettings),
      });
      const data = await res.json();
      if (!res.ok) {
        setVllmSettingsMessage({ type: "error", text: data.detail || `HTTP ${res.status}` });
        return;
      }
      setVllmSettingsOriginal({ ...vllmSettings });
      setVllmSettingsMessage({ type: "success", text: "설정이 저장되었습니다." });
      // Also update parent config's vllm_endpoint
      if (vllmSettings.vllm_endpoint) {
        onChange("vllm_endpoint", vllmSettings.vllm_endpoint);
      }
    } catch (err) {
      setVllmSettingsMessage({ type: "error", text: `저장 실패: ${err.message}` });
    } finally {
      setVllmSettingsSaving(false);
    }
  };

  const vllmSettingsChanged =
    vllmSettings.vllm_endpoint !== vllmSettingsOriginal.vllm_endpoint ||
    vllmSettings.vllm_namespace !== vllmSettingsOriginal.vllm_namespace ||
    vllmSettings.vllm_is_name !== vllmSettingsOriginal.vllm_is_name;

  useEffect(() => {
    setLocalStorageUri(storageUri ?? "");
  }, [storageUri]);

  return (
    <div className="panel">
      <div className="section-title">Bayesian Optimization 설정</div>
      <div className="grid-form grid-form-compact">
        <div>
          <label className="label">최적화 목표</label>
          <select className="input" aria-label="최적화 목표" value={config.objective}
            onChange={e => onChange("objective", e.target.value)}>
            <option value="tps">최대 처리량 (TPS)</option>
            <option value="latency">최소 레이턴시</option>
            <option value="balanced">균형 (TPS / Latency)</option>
            <option value="pareto">Pareto (TPS + Latency)</option>
          </select>
        </div>
        <div>
          <label className="label">Trial 수</label>
          <input className="input" type="number" aria-label="Trial 수" value={config.n_trials}
            onChange={e => onChange("n_trials", +e.target.value)} />
        </div>
        <div>
          <label className="label">max_num_seqs 범위</label>
          <div className="flex-row-8">
            <input className="input" type="number" placeholder="Min" aria-label="max_num_seqs 최솟값" value={config.max_num_seqs_min}
              onChange={e => onChange("max_num_seqs_min", +e.target.value)} />
            <input className="input" type="number" placeholder="Max" aria-label="max_num_seqs 최댓값" value={config.max_num_seqs_max}
              onChange={e => onChange("max_num_seqs_max", +e.target.value)} />
          </div>
        </div>
        <div>
          <label className="label">GPU Memory Util 범위</label>
          <div className="flex-row-8">
            <input className="input" type="number" step="0.01" placeholder="Min" aria-label="GPU Memory Util 최솟값" value={config.gpu_memory_min}
              onChange={e => onChange("gpu_memory_min", +e.target.value)} />
            <input className="input" type="number" step="0.01" placeholder="Max" aria-label="GPU Memory Util 최댓값" value={config.gpu_memory_max}
              onChange={e => onChange("gpu_memory_max", +e.target.value)} />
          </div>
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
        <span className={`tag tag-${isRunning ? "running" : "idle"}`}>
          {isRunning ? "TUNING..." : "IDLE"}
        </span>
        <span className="tuner-trials-count">
          {trialsCompleted} / {config.n_trials} trials
        </span>
      </div>

      <div className="tuner-advanced-toggle-wrap">
        <button
          className="btn btn-advanced"
          onClick={() => setShowVllmSettings(v => !v)}
        >
          vLLM 설정 {showVllmSettings ? "▲" : "▼"}
        </button>
      </div>

      {showVllmSettings && (
        <div className="tuner-advanced-panel">
          <div className="grid-form grid-form-compact">
            <div>
              <label className="label">vLLM Endpoint</label>
              <input
                className="input"
                type="text"
                value={vllmSettings.vllm_endpoint}
                onChange={e => handleVllmSettingChange("vllm_endpoint", e.target.value)}
                placeholder="http://llm-ov-predictor.vllm.svc.cluster.local:8080"
                aria-label="vLLM Endpoint"
              />
            </div>
            <div>
              <label className="label">Namespace</label>
              <input
                className="input"
                type="text"
                value={vllmSettings.vllm_namespace}
                onChange={e => handleVllmSettingChange("vllm_namespace", e.target.value)}
                placeholder="vllm"
                aria-label="vLLM Namespace"
              />
            </div>
            <div>
              <label className="label">InferenceService Name</label>
              <input
                className="input"
                type="text"
                value={vllmSettings.vllm_is_name}
                onChange={e => handleVllmSettingChange("vllm_is_name", e.target.value)}
                placeholder="llm-ov"
                aria-label="InferenceService Name"
              />
            </div>
          </div>
          <div className="tuner-vllm-settings-actions">
            <button
              className="btn btn-primary"
              onClick={handleSaveVllmSettings}
              disabled={vllmSettingsSaving || !vllmSettingsChanged}
            >
              {vllmSettingsSaving ? "저장 중..." : "저장"}
            </button>
            {vllmSettingsMessage && (
              <span className={`tuner-vllm-settings-msg tuner-vllm-settings-msg--${vllmSettingsMessage.type}`}>
                {vllmSettingsMessage.text}
              </span>
            )}
          </div>
        </div>
      )}

      <div className="tuner-advanced-toggle-wrap">
        <button
          className="btn btn-advanced"
          onClick={onToggleAdvanced}
        >
          고급 설정 {showAdvanced ? "▲" : "▼"}
        </button>
      </div>

      {showAdvanced && (
        <div className="tuner-advanced-panel">
          {currentConfig && (
            <div className="tuner-current-config-box">
              <div className="tuner-config-key-label">현재 vLLM 설정</div>
              <div className="tuner-config-pairs">
                {Object.entries(currentConfig).map(([k, v]) => (
                  <span key={k} className="tuner-config-pair">
                    {k}: <span className="tuner-config-pair-val">{String(v) || "(비어있음)"}</span>
                  </span>
                ))}
              </div>
              {/* storageUri 표시/수정 */}
              <div className="tuner-storageuri-row">
                <span className="tuner-config-key-label">storageUri</span>
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
                  className="btn btn-primary"
                  onClick={() => onSaveStorageUri(localStorageUri)}
                  disabled={isRunning || localStorageUri === storageUri}
                >
                  저장
                </button>
              </div>
            </div>
          )}
          <div className="grid-form grid-form-compact">
            <div>
              <label className="label">max_model_len 범위</label>
              <div className="flex-row-8">
                <input className="input" type="number" placeholder="Min" aria-label="max_model_len 최솟값" value={config.max_model_len_min}
                  onChange={e => onChange("max_model_len_min", +e.target.value)} />
                <input className="input" type="number" placeholder="Max" aria-label="max_model_len 최댓값" value={config.max_model_len_max}
                  onChange={e => onChange("max_model_len_max", +e.target.value)} />
              </div>
            </div>
            <div>
              <label className="label">max_num_batched_tokens 범위</label>
              <div className="flex-row-8">
                <input className="input" type="number" placeholder="Min" aria-label="max_num_batched_tokens 최솟값" value={config.max_num_batched_tokens_min}
                  onChange={e => onChange("max_num_batched_tokens_min", +e.target.value)} />
                <input className="input" type="number" placeholder="Max" aria-label="max_num_batched_tokens 최댓값" value={config.max_num_batched_tokens_max}
                  onChange={e => onChange("max_num_batched_tokens_max", +e.target.value)} />
              </div>
            </div>
            <div>
              <label className="label">block_size 옵션</label>
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
            </div>
            <div>
              <label className="label label-flex">
                <input type="checkbox"
                  checked={config.include_swap_space}
                  onChange={e => onChange("include_swap_space", e.target.checked)}
                />
                swap_space 포함
              </label>
              {config.include_swap_space && (
                <div className="tuner-swap-space-row">
                  <input className="input" type="number" step="0.5" placeholder="Min GB" aria-label="swap_space 최솟값 (GB)" value={config.swap_space_min}
                    onChange={e => onChange("swap_space_min", +e.target.value)} />
                  <input className="input" type="number" step="0.5" placeholder="Max GB" aria-label="swap_space 최댓값 (GB)" value={config.swap_space_max}
                    onChange={e => onChange("swap_space_max", +e.target.value)} />
                </div>
              )}
            </div>
            <div>
              <label className="label">평가 요청 수</label>
              <input className="input" type="number" aria-label="평가 요청 수" value={config.eval_requests}
                onChange={e => onChange("eval_requests", +e.target.value)} />
            </div>
            <div>
              <label className="label">평가 동시 요청</label>
              <input className="input" type="number" aria-label="평가 동시 요청" value={config.eval_concurrency}
                onChange={e => onChange("eval_concurrency", +e.target.value)} />
            </div>
            <div>
              <label className="label">평가 RPS</label>
              <input className="input" type="number" aria-label="평가 RPS" value={config.eval_rps}
                onChange={e => onChange("eval_rps", +e.target.value)} />
            </div>
          </div>
        </div>
      )}

      {isRunning && currentPhase && (
        <div className="tuner-phase-indicator" aria-live="polite" aria-atomic="true">
          Trial {(currentPhase.trial_id ?? 0) + 1}: {PHASE_LABELS[currentPhase.phase] || currentPhase.phase}
        </div>
      )}
    </div>
  );
}
