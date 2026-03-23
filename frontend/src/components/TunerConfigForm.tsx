import { useState, useEffect } from "react";
import TunerProgressBar from "./TunerProgressBar";

interface TunerPhase {
  trial_id: number;
  phase: string;
}

interface TunerConfig {
  objective: string;
  n_trials: number;
  vllm_endpoint: string;
  max_num_seqs_min: number;
  max_num_seqs_max: number;
  gpu_memory_min: number;
  gpu_memory_max: number;
  max_model_len_min: number;
  max_model_len_max: number;
  max_num_batched_tokens_min: number;
  max_num_batched_tokens_max: number;
  block_size_options: number[];
  include_swap_space: boolean;
  swap_space_min: number;
  swap_space_max: number;
  eval_concurrency: number;
  eval_rps: number;
  eval_requests: number;
}

interface TunerConfigFormProps {
  config: TunerConfig;
  onChange: (field: string, value: string | number | boolean | number[]) => void;
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
}

const PHASE_LABELS: Record<string, string> = {
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
  storageUri,
  onSaveStorageUri,
  onApplyCurrentValues,
}: TunerConfigFormProps) {
  const [localStorageUri, setLocalStorageUri] = useState(storageUri ?? "");
  const [editedValues, setEditedValues] = useState<Record<string, unknown>>({});

  useEffect(() => {
    setLocalStorageUri(storageUri ?? "");
  }, [storageUri]);

  useEffect(() => {
    setEditedValues({});
  }, [currentConfig]);

  const getInputValue = (key: string): string => {
    if (editedValues[key] !== undefined) return String(editedValues[key]);
    if (!currentConfig) return "";
    const val = currentConfig[key];
    return val !== undefined ? String(val) : "";
  };

  const handleCurrentValChange = (key: string, value: unknown) => {
    setEditedValues(prev => ({ ...prev, [key]: value }));
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
          onChange={e => handleCurrentValChange(key, e.target.checked)}
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
          handleCurrentValChange(key, type === "number" ? +e.target.value : e.target.value)
        }
        style={{ width: "100%" }}
      />
    );
  };

  return (
    <div className="panel">
      <div className="section-title">Bayesian Optimization 설정</div>
      
      <div className="grid-form grid-form-compact" style={{ marginBottom: '20px' }}>
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
      </div>

      <div style={{ overflowX: 'auto', marginBottom: '20px' }}>
        <table className="table tuner-params-table">
          <thead>
            <tr>
              <th style={{ width: '20%' }}>설정명</th>
              <th style={{ width: '15%' }}>현재값</th>
              <th style={{ width: '30%' }}>탐색 범위</th>
              <th style={{ width: '35%' }}>설명</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td title="max_num_seqs">최대 시퀀스 수</td>
              <td className="td-current">{renderCurrentInput("max_num_seqs", "number")}</td>
              <td>
                <div className="flex-row-8">
                  <input className="input" type="number" placeholder="Min" min={1} max={2048} value={config.max_num_seqs_min}
                    onChange={e => onChange("max_num_seqs_min", +e.target.value)} />
                  <input className="input" type="number" placeholder="Max" min={1} max={2048} value={config.max_num_seqs_max}
                    onChange={e => onChange("max_num_seqs_max", +e.target.value)} />
                </div>
              </td>
              <td className="td-desc">동시 처리 가능한 최대 시퀀스 수</td>
            </tr>
            <tr>
              <td title="gpu_memory_utilization">GPU 메모리 비율</td>
              <td className="td-current">{renderCurrentInput("gpu_memory_utilization", "number", { step: "0.01", min: 0, max: 1 })}</td>
              <td>
                <div className="flex-row-8">
                  <input className="input" type="number" step="0.01" placeholder="Min" min={0.5} max={0.99} value={config.gpu_memory_min}
                    onChange={e => onChange("gpu_memory_min", +e.target.value)} />
                  <input className="input" type="number" step="0.01" placeholder="Max" min={0.5} max={0.99} value={config.gpu_memory_max}
                    onChange={e => onChange("gpu_memory_max", +e.target.value)} />
                </div>
              </td>
              <td className="td-desc">GPU 메모리 할당 비율 (0.0~1.0)</td>
            </tr>
            <tr>
              <td title="max_model_len">최대 모델 길이</td>
              <td className="td-current">{renderCurrentInput("max_model_len", "number")}</td>
              <td>
                <div className="flex-row-8">
                  <input className="input" type="number" placeholder="Min" min={256} max={32768} step={256} value={config.max_model_len_min}
                    onChange={e => onChange("max_model_len_min", +e.target.value)} />
                  <input className="input" type="number" placeholder="Max" min={256} max={32768} step={256} value={config.max_model_len_max}
                    onChange={e => onChange("max_model_len_max", +e.target.value)} />
                </div>
              </td>
              <td className="td-desc">모델이 처리할 수 있는 최대 토큰 길이</td>
            </tr>
            <tr>
              <td title="max_num_batched_tokens">최대 배치 토큰 수</td>
              <td className="td-current">{renderCurrentInput("max_num_batched_tokens", "number")}</td>
              <td>
                <div className="flex-row-8">
                  <input className="input" type="number" placeholder="Min" min={256} max={8192} step={256} value={config.max_num_batched_tokens_min}
                    onChange={e => onChange("max_num_batched_tokens_min", +e.target.value)} />
                  <input className="input" type="number" placeholder="Max" min={256} max={8192} step={256} value={config.max_num_batched_tokens_max}
                    onChange={e => onChange("max_num_batched_tokens_max", +e.target.value)} />
                </div>
              </td>
              <td className="td-desc">한 번에 배치 처리할 최대 토큰 수</td>
            </tr>
            <tr>
              <td title="block_size">블록 크기</td>
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
              <td className="td-desc">KV 캐시 블록 크기</td>
            </tr>
            <tr>
              <td title="swap_space">스왑 공간 (GB)</td>
              <td className="td-current">{renderCurrentInput("swap_space", "number", { step: "0.5", min: 0 })}</td>
              <td>
                <div className="flex-col-1">
                  <label className="label-flex label-no-mb" style={{ fontSize: '10px' }}>
                    <input type="checkbox"
                      checked={config.include_swap_space}
                      onChange={e => onChange("include_swap_space", e.target.checked)}
                    />
                    포함
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
              <td className="td-desc">CPU 스왑 공간 크기 (GB)</td>
            </tr>
            <tr>
              <td title="enable_chunked_prefill">Chunked Prefill</td>
              <td className="td-current">{renderCurrentInput("enable_chunked_prefill", "checkbox")}</td>
              <td>—</td>
              <td className="td-desc">Chunked Prefill 활성화 여부</td>
            </tr>
            <tr>
              <td title="enable_enforce_eager">Enforce Eager</td>
              <td className="td-current">{renderCurrentInput("enable_enforce_eager", "checkbox")}</td>
              <td>—</td>
              <td className="td-desc">CUDA Graph 미사용 (Eager 모드 강제)</td>
            </tr>
            <tr>
              <td title="storageUri">모델 스토리지</td>
              <td colSpan={2}>
                <div className="flex-row-8">
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
                    className="btn btn-primary btn-small"
                    onClick={() => onSaveStorageUri(localStorageUri)}
                    disabled={isRunning || localStorageUri === storageUri}
                    style={{ whiteSpace: 'nowrap' }}
                  >
                    저장
                  </button>
                </div>
              </td>
              <td className="td-desc">모델 스토리지 URI</td>
            </tr>
          </tbody>
        </table>
      </div>

      <div className="section-title">평가 설정</div>
      <div className="grid-form grid-form-compact" style={{ marginBottom: '20px' }}>
        <div>
          <label className="label">평가 요청 수</label>
           <input className="input" type="number" aria-label="평가 요청 수" min={10} max={10000} step={10} value={config.eval_requests}
             onChange={e => onChange("eval_requests", +e.target.value)} />
        </div>
        <div>
          <label className="label">평가 동시 요청</label>
           <input className="input" type="number" aria-label="평가 동시 요청" min={1} max={256} value={config.eval_concurrency}
             onChange={e => onChange("eval_concurrency", +e.target.value)} />
        </div>
        <div>
          <label className="label">평가 RPS</label>
           <input className="input" type="number" aria-label="평가 RPS" min={1} max={1000} value={config.eval_rps}
             onChange={e => onChange("eval_rps", +e.target.value)} />
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
        {onApplyCurrentValues && currentConfig && (
          <button
            className="btn btn-secondary"
            onClick={() => onApplyCurrentValues(editedValues)}
            disabled={Object.keys(editedValues).length === 0}
          >
            현재값 적용
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

      {isRunning && currentPhase && (
        <div className="tuner-phase-indicator" aria-live="polite" aria-atomic="true">
          Trial {(currentPhase.trial_id ?? 0) + 1}: {PHASE_LABELS[currentPhase.phase] || currentPhase.phase}
        </div>
      )}
    </div>
  );
}
