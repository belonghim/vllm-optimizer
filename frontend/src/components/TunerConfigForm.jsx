import { useState, useEffect } from "react";
import { API } from "../constants";
import TunerProgressBar from "./TunerProgressBar";

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
           <input className="input" type="number" aria-label="Trial 수" min={1} max={100} value={config.n_trials}
             onChange={e => onChange("n_trials", +e.target.value)} />
        </div>
        <div>
          <label className="label">max_num_seqs 범위</label>
          <div className="flex-row-8">
             <input className="input" type="number" placeholder="Min" aria-label="max_num_seqs 최솟값" min={1} max={2048} value={config.max_num_seqs_min}
               onChange={e => onChange("max_num_seqs_min", +e.target.value)} />
             <input className="input" type="number" placeholder="Max" aria-label="max_num_seqs 최댓값" min={1} max={2048} value={config.max_num_seqs_max}
               onChange={e => onChange("max_num_seqs_max", +e.target.value)} />
          </div>
        </div>
        <div>
          <label className="label">GPU Memory Util 범위</label>
          <div className="flex-row-8">
             <input className="input" type="number" step="0.01" placeholder="Min" aria-label="GPU Memory Util 최솟값" min={0.5} max={0.99} value={config.gpu_memory_min}
               onChange={e => onChange("gpu_memory_min", +e.target.value)} />
             <input className="input" type="number" step="0.01" placeholder="Max" aria-label="GPU Memory Util 최댓값" min={0.5} max={0.99} value={config.gpu_memory_max}
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
      
      {(isRunning || trialsCompleted > 0) && (
        <TunerProgressBar
          isRunning={isRunning}
          trialsCompleted={trialsCompleted}
          totalTrials={config.n_trials}
          currentPhase={currentPhase}
        />
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
