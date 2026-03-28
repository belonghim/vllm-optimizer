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
  applying_config: "Updating config...",
  restarting: "Restarting InferenceService...",
  waiting_ready: "Waiting for Pod Ready...",
  warmup: "Sending warmup requests...",
  evaluating: "Evaluating performance...",
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
            aria-label={`${percentage}% complete`}
            style={{ width: `${percentage}%` }}
          />
        </div>
      </div>
    )
  );
}
