import { COLORS } from '../constants';

const PHASE_LABELS = {
  applying_config: "ConfigMap 업데이트 중...",
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
}) {
  return (
    <div style={{ background: COLORS.surface, border: `1px solid ${COLORS.border}`, padding: 20 }}>
      <div className="section-title">Bayesian Optimization 설정</div>
      <div className="grid-form" style={{ gap: 12 }}>
        <div>
          <label className="label">최적화 목표</label>
          <select className="input" value={config.objective}
            onChange={e => onChange("objective", e.target.value)}>
            <option value="tps">최대 처리량 (TPS)</option>
            <option value="latency">최소 레이턴시</option>
            <option value="balanced">균형 (TPS / Latency)</option>
            <option value="pareto">Pareto (TPS + Latency)</option>
          </select>
        </div>
        <div>
          <label className="label">Trial 수</label>
          <input className="input" type="number" value={config.n_trials}
            onChange={e => onChange("n_trials", +e.target.value)} />
        </div>
        <div>
          <label className="label">max_num_seqs 범위</label>
          <div style={{ display: "flex", gap: 8 }}>
            <input className="input" type="number" placeholder="Min" value={config.max_num_seqs_min}
              onChange={e => onChange("max_num_seqs_min", +e.target.value)} />
            <input className="input" type="number" placeholder="Max" value={config.max_num_seqs_max}
              onChange={e => onChange("max_num_seqs_max", +e.target.value)} />
          </div>
        </div>
        <div>
          <label className="label">GPU Memory Util 범위</label>
          <div style={{ display: "flex", gap: 8 }}>
            <input className="input" type="number" step="0.01" placeholder="Min" value={config.gpu_memory_min}
              onChange={e => onChange("gpu_memory_min", +e.target.value)} />
            <input className="input" type="number" step="0.01" placeholder="Max" value={config.gpu_memory_max}
              onChange={e => onChange("gpu_memory_max", +e.target.value)} />
          </div>
        </div>
      </div>

      <div style={{ display: "flex", gap: 8, marginTop: 16, alignItems: "center" }}>
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
        <span style={{ fontSize: 11, color: COLORS.muted }}>
          {trialsCompleted} / {config.n_trials} trials
        </span>
      </div>

      <div style={{ marginTop: 8 }}>
        <button
          className="btn"
          onClick={onToggleAdvanced}
          style={{ fontSize: 11, padding: "4px 12px", background: "none", border: `1px solid ${COLORS.border}`, color: COLORS.muted, cursor: "pointer" }}
        >
          고급 설정 {showAdvanced ? "▲" : "▼"}
        </button>
      </div>

      {showAdvanced && (
        <div style={{ background: COLORS.surface, border: `1px solid ${COLORS.border}`, padding: 16, marginTop: 8 }}>
          {currentConfig && (
            <div style={{ background: "rgba(0,0,0,0.2)", border: `1px solid ${COLORS.border}`, padding: 12, marginBottom: 16, fontSize: 11 }}>
              <div style={{ color: COLORS.muted, marginBottom: 6, fontFamily: "'JetBrains Mono', monospace" }}>현재 vLLM 설정 (ConfigMap)</div>
              <div style={{ display: "flex", flexWrap: "wrap", gap: "4px 16px" }}>
                {Object.entries(currentConfig).map(([k, v]) => (
                  <span key={k} style={{ fontFamily: "'JetBrains Mono', monospace", color: COLORS.text, fontSize: 11 }}>
                    {k}: <span style={{ color: COLORS.accent }}>{String(v) || "(비어있음)"}</span>
                  </span>
                ))}
              </div>
            </div>
          )}
          <div className="grid-form" style={{ gap: 12 }}>
            <div>
              <label className="label">max_model_len 범위</label>
              <div style={{ display: "flex", gap: 8 }}>
                <input className="input" type="number" placeholder="Min" value={config.max_model_len_min}
                  onChange={e => onChange("max_model_len_min", +e.target.value)} />
                <input className="input" type="number" placeholder="Max" value={config.max_model_len_max}
                  onChange={e => onChange("max_model_len_max", +e.target.value)} />
              </div>
            </div>
            <div>
              <label className="label">max_num_batched_tokens 범위</label>
              <div style={{ display: "flex", gap: 8 }}>
                <input className="input" type="number" placeholder="Min" value={config.max_num_batched_tokens_min}
                  onChange={e => onChange("max_num_batched_tokens_min", +e.target.value)} />
                <input className="input" type="number" placeholder="Max" value={config.max_num_batched_tokens_max}
                  onChange={e => onChange("max_num_batched_tokens_max", +e.target.value)} />
              </div>
            </div>
            <div>
              <label className="label">block_size 옵션</label>
              <div style={{ display: "flex", gap: 12 }}>
                {[8, 16, 32].map(size => (
                  <label key={size} style={{ display: "flex", alignItems: "center", gap: 4, fontSize: 12, color: COLORS.text, cursor: "pointer" }}>
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
              <label className="label" style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <input type="checkbox"
                  checked={config.include_swap_space}
                  onChange={e => onChange("include_swap_space", e.target.checked)}
                />
                swap_space 포함
              </label>
              {config.include_swap_space && (
                <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
                  <input className="input" type="number" step="0.5" placeholder="Min GB" value={config.swap_space_min}
                    onChange={e => onChange("swap_space_min", +e.target.value)} />
                  <input className="input" type="number" step="0.5" placeholder="Max GB" value={config.swap_space_max}
                    onChange={e => onChange("swap_space_max", +e.target.value)} />
                </div>
              )}
            </div>
            <div>
              <label className="label">평가 요청 수</label>
              <input className="input" type="number" value={config.eval_requests}
                onChange={e => onChange("eval_requests", +e.target.value)} />
            </div>
            <div>
              <label className="label">평가 동시 요청</label>
              <input className="input" type="number" value={config.eval_concurrency}
                onChange={e => onChange("eval_concurrency", +e.target.value)} />
            </div>
            <div>
              <label className="label">평가 RPS</label>
              <input className="input" type="number" value={config.eval_rps}
                onChange={e => onChange("eval_rps", +e.target.value)} />
            </div>
          </div>
        </div>
      )}

      {isRunning && currentPhase && (
        <div style={{
          marginTop: 12,
          padding: "8px 16px",
          background: "rgba(0,163,255,0.08)",
          border: `1px solid ${COLORS.accent}`,
          fontSize: 12,
          fontFamily: "'JetBrains Mono', monospace",
          color: COLORS.accent,
        }}>
          Trial {(currentPhase.trial_id ?? 0) + 1}: {PHASE_LABELS[currentPhase.phase] || currentPhase.phase}
        </div>
      )}
    </div>
  );
}
