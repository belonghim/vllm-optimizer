import { useEffect } from "react";

export default function TunerProgressBar({
  isRunning,
  trialsCompleted,
  totalTrials,
  currentPhase
}) {
  // Calculate progress percentage with bounds checking
  const percentage = totalTrials > 0
    ? Math.min(100, Math.round((trialsCompleted / totalTrials) * 100))
    : 0;

  // Phase labels - defined locally to avoid import issues during testing
  const PHASE_LABELS = {
    applying_config: "설정 업데이트 중...",
    restarting: "InferenceService 재시작 중...",
    waiting_ready: "Pod Ready 대기 중...",
    warmup: "Warmup 요청 전송 중...",
    evaluating: "성능 평가 중...",
  };

  // Get phase label if currentPhase is provided
  const phaseLabel = currentPhase && PHASE_LABELS[currentPhase.phase] 
    ? `Trial ${currentPhase.trial_id + 1}: ${PHASE_LABELS[currentPhase.phase]}`
    : currentPhase 
      ? `Trial ${currentPhase.trial_id + 1}: ${currentPhase.phase}`
      : null;

  // Show progress bar when running OR when trials have been completed (to show final state)
  const showProgressBar = isRunning || trialsCompleted > 0;

  return (
    showProgressBar && (
      <div className="tuner-progress-container">
        <div className="tuner-progress-header">
          <span className="tuner-progress-pct">{percentage}%</span>
          {phaseLabel && <span className="tuner-progress-phase">{phaseLabel}</span>}
        </div>
        <div className="progress-bar">
          <div 
            className={`progress-fill${percentage === 100 ? ' progress-fill--completed' : ''}`}
            role="progressbar"
            aria-valuenow={percentage}
            aria-valuemin="0"
            aria-valuemax="100"
            aria-label={`${percentage}% 완료`}
            style={{ width: `${percentage}%` }}
          />
        </div>
      </div>
    )
  );
}