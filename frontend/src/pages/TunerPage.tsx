import { useState } from "react";
import { useTunerLogic } from "../hooks/useTunerLogic";
import TunerConfigSection from "../components/TunerConfigSection";
import TunerResults from "../components/TunerResults";
import TunerHistoryPanel from "../components/TunerHistoryPanel";
import LoadingSpinner from "../components/LoadingSpinner";
import TargetSelector from "../components/TargetSelector";
import type { ClusterTarget } from "../types";

interface TunerPageProps {
  isActive: boolean;
  onTabChange?: (tab: string) => void;
  onRunningChange?: (running: boolean) => void;
}

function TunerPage({ isActive, onTabChange, onRunningChange }: TunerPageProps) {
  const [selectedTarget, setSelectedTarget] = useState<ClusterTarget | null>(null);
  const {
    error, warning, status, trials, importance, currentPhase, applyStatus,
    interruptedWarning, autoBenchmark, benchmarkSaved, benchmarkSavedId,
    initialized, config, setError, setInterruptedWarning, setAutoBenchmark,
    handleConfigChange, handleApplySuccess, start, stop, applyBest,
  } = useTunerLogic({ isActive, onRunningChange, targetOverride: selectedTarget });

  return (
    <div className="flex-col-16">
      <div className="tuner-target-selector">
        <span className="tuner-target-label">Target:</span>
        <TargetSelector
          value={selectedTarget}
          onChange={setSelectedTarget}
          data-testid="tuner-target-selector"
        />
      </div>
      <TunerConfigSection
        isActive={isActive}
        status={status}
        config={config}
        error={error}
        warning={warning}
        applyStatus={applyStatus}
        interruptedWarning={interruptedWarning}
        autoBenchmark={autoBenchmark}
        benchmarkSaved={benchmarkSaved}
        benchmarkSavedId={benchmarkSavedId}
        currentPhase={currentPhase}
        onDismissInterrupted={() => setInterruptedWarning(null)}
        onAutoBenchmarkChange={setAutoBenchmark}
        onTabChange={onTabChange}
        onConfigChange={handleConfigChange}
        onStart={start}
        onStop={stop}
        onApplyBest={applyBest}
        onError={setError}
        onApplySuccess={handleApplySuccess}
      />
      {!initialized ? (
        <LoadingSpinner />
      ) : (
        <>
          <TunerResults
            trials={trials}
            bestParams={status.best}
            status={status}
            isRunning={status.running}
            importance={importance}
          />
          <TunerHistoryPanel />
        </>
      )}
    </div>
  );
}

export default TunerPage;
