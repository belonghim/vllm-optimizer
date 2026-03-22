interface TunerPhase {
  trial_id: number;
  phase: string;
}

interface TunerProgressBarProps {
  isRunning: boolean;
  trialsCompleted: number;
  totalTrials: number;
  currentPhase: TunerPhase | null;
}

const PHASE_LABELS: Record<string, string> = {
  applying_config: "설정 업데이트 중...",
  restarting: "InferenceService 재시작 중...",
  waiting_ready: "Pod Ready 대기 중...",
  warmup: "Warmup 요청 전송 중...",
  evaluating: "성능 평가 중...",
};

export default function TunerProgressBar({
  isRunning,
  trialsCompleted,
  totalTrials,
  currentPhase
}: TunerProgressBarProps) {
  const percentage = totalTrials > 0
    ? Math.min(100, Math.round((trialsCompleted / totalTrials) * 100))
    : 0;

  const phaseLabel = currentPhase && PHASE_LABELS[currentPhase.phase]
    ? `Trial ${currentPhase.trial_id + 1}: ${PHASE_LABELS[currentPhase.phase]}`
    : currentPhase
      ? `Trial ${currentPhase.trial_id + 1}: ${currentPhase.phase}`
      : null;

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
            aria-valuemin={0}
            aria-valuemax={100}
            aria-label={`${percentage}% 완료`}
            style={{ width: `${percentage}%` }}
          />
        </div>
      </div>
    )
  );
}
