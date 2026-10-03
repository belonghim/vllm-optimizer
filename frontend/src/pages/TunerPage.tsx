import { useState, lazy, Suspense } from 'react';
import { useTunerLogic } from '../hooks/useTunerLogic';
import TunerConfigSection from '../components/TunerConfigSection';
import TunerHistoryPanel from '../components/TunerHistoryPanel';
import TunerWarmupSuggestions from '../components/TunerWarmupSuggestions';
import TunerReport from '../components/TunerReport';
import TunerModelAnalysis from '../components/TunerModelAnalysis';
import LoadingSpinner from '../components/LoadingSpinner';
import TargetSelector from '../components/TargetSelector';
import type { ClusterTarget, SuggestedSearchSpace } from '../types';

// Lazy: keeps recharts out of the Tuner page chunk until tuning results exist
const TunerResults = lazy(() => import('../components/TunerResults'));

interface TunerPageProps {
  isActive: boolean;
  onTabChange?: (tab: string) => void;
  onRunningChange?: (running: boolean) => void;
}

function TunerPage({ isActive, onTabChange, onRunningChange }: TunerPageProps) {
  const [selectedTarget, setSelectedTarget] = useState<ClusterTarget | null>(null);
  const {
    error,
    warning,
    status,
    trials,
    importance,
    currentPhase,
    applyStatus,
    interruptedWarning,
    autoBenchmark,
    benchmarkSaved,
    benchmarkSavedId,
    initialized,
    config,
    setError,
    setInterruptedWarning,
    setAutoBenchmark,
    handleConfigChange,
    handleApplySuccess,
    start,
    stop,
    applyBest,
    warmupSuggestions,
    tuningReport,
  } = useTunerLogic({ isActive, onRunningChange, targetOverride: selectedTarget });

  const applySearchSpace = (space: SuggestedSearchSpace) => {
    handleConfigChange('max_num_seqs_min', space.max_num_seqs_min);
    handleConfigChange('max_num_seqs_max', space.max_num_seqs_max);
    handleConfigChange('max_model_len_min', space.max_model_len_min);
    handleConfigChange('max_model_len_max', space.max_model_len_max);
  };

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
      <TunerModelAnalysis
        isActive={isActive}
        targetOverride={selectedTarget}
        acceleratorMemoryGib={config.accelerator_memory_gib ?? null}
        onAcceleratorMemoryChange={(gib) => handleConfigChange('accelerator_memory_gib', gib)}
        onApplySearchSpace={applySearchSpace}
        disabled={status.running}
      />
      <TunerConfigSection
        key={
          selectedTarget
            ? `${selectedTarget.namespace}/${selectedTarget.inferenceService}`
            : 'default'
        }
        isActive={isActive}
        status={status}
        config={config}
        targetOverride={selectedTarget}
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
      {warmupSuggestions && warmupSuggestions.configurations.length > 0 && (
        <TunerWarmupSuggestions configurations={warmupSuggestions.configurations} />
      )}
      {!initialized ? (
        <LoadingSpinner />
      ) : (
        <>
          <Suspense fallback={<LoadingSpinner />}>
            <TunerResults
              trials={trials}
              bestParams={status.best}
              status={status}
              isRunning={status.running}
              importance={importance}
            />
          </Suspense>
          {tuningReport && (
            <TunerReport markdown={tuningReport.markdown} summary={tuningReport.summary} />
          )}
          <TunerHistoryPanel />
        </>
      )}
    </div>
  );
}

export default TunerPage;
