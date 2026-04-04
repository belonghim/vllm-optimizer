import TunerStatusPanel from "./TunerStatusPanel";
import TunerCurrentConfig from "./TunerCurrentConfig";
import type { TunerStatus, TunerConfig, TunerPhase, ClusterTarget } from "../types";

interface TunerConfigSectionProps {
  isActive: boolean;
  status: TunerStatus;
  config: TunerConfig;
  error: string | null;
  warning: string | null;
  applyStatus: string | null;
  interruptedWarning: string | null;
  autoBenchmark: boolean;
  benchmarkSaved: boolean;
  benchmarkSavedId: number | null;
  currentPhase: TunerPhase | null;
  targetOverride?: ClusterTarget | null;
  onDismissInterrupted: () => void;
  onAutoBenchmarkChange: (v: boolean) => void;
  onTabChange?: (tab: string) => void;
  onConfigChange: (field: string, value: string | number | boolean | number[]) => void;
  onStart: () => void;
  onStop: () => void;
  onApplyBest: () => void;
  onError: (msg: string | null) => void;
  onApplySuccess: () => void;
}

export default function TunerConfigSection({
  isActive, status, config, error, warning, applyStatus, interruptedWarning,
  autoBenchmark, benchmarkSaved, benchmarkSavedId, currentPhase, targetOverride,
  onDismissInterrupted, onAutoBenchmarkChange, onTabChange,
  onConfigChange, onStart, onStop, onApplyBest, onError, onApplySuccess,
}: TunerConfigSectionProps) {
  return (
    <>
      <TunerStatusPanel
        error={error}
        warning={warning}
        applyStatus={applyStatus}
        interruptedWarning={interruptedWarning}
        autoBenchmark={autoBenchmark}
        benchmarkSaved={benchmarkSaved}
        benchmarkSavedId={benchmarkSavedId}
        onDismissInterrupted={onDismissInterrupted}
        onAutoBenchmarkChange={onAutoBenchmarkChange}
        onTabChange={onTabChange}
      />
      <TunerCurrentConfig
        isActive={isActive}
        isRunning={status.running}
        config={config}
        targetOverride={targetOverride}
        onChange={onConfigChange}
        onSubmit={onStart}
        onStop={onStop}
        onApplyBest={onApplyBest}
        hasBest={!!status.best}
        currentPhase={currentPhase}
        trialsCompleted={status.trials_completed}
        onError={onError}
        onApplySuccess={onApplySuccess}
      />
    </>
  );
}
