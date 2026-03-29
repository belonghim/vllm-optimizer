import ErrorAlert from "./ErrorAlert";
import { ERROR_MESSAGES } from "../constants/errorMessages";

interface TunerStatusPanelProps {
  error: string | null;
  warning: string | null;
  applyStatus: string | null;
  interruptedWarning: string | null;
  autoBenchmark: boolean;
  benchmarkSaved: boolean;
  benchmarkSavedId: number | null;
  onDismissInterrupted: () => void;
  onAutoBenchmarkChange: (checked: boolean) => void;
  onTabChange?: (tab: string) => void;
}

export default function TunerStatusPanel({
  error,
  warning,
  applyStatus,
  interruptedWarning,
  autoBenchmark,
  benchmarkSaved,
  benchmarkSavedId,
  onDismissInterrupted,
  onAutoBenchmarkChange,
  onTabChange,
}: TunerStatusPanelProps) {
  return (
    <>
      {interruptedWarning && (
        <div style={{ display: 'flex', alignItems: 'flex-start', gap: '8px' }}>
          <ErrorAlert message={interruptedWarning} severity="warning" className="error-alert--mb16" />
          <button
            onClick={onDismissInterrupted}
            aria-label="Dismiss tuner interruption warning"
            style={{ background: 'none', border: 'none', cursor: 'pointer', padding: '4px', color: 'var(--muted-color)', fontSize: '18px' }}
          >×</button>
        </div>
      )}
      <ErrorAlert message={error} className="error-alert--mb16" />
      <ErrorAlert message={warning} severity="warning" className="error-alert--mb16" />
      {applyStatus === "success" && (
        <div className="success-msg" role="status">
          {ERROR_MESSAGES.TUNER.APPLY_BEST_SUCCESS}
        </div>
      )}
      {applyStatus === ERROR_MESSAGES.TUNER.APPLY_CURRENT_SUCCESS && (
        <div className="success-msg" role="status">
          {ERROR_MESSAGES.TUNER.APPLY_CURRENT_VALUES_SUCCESS}
        </div>
      )}
      <label style={{ display: "inline-flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
        <input
          type="checkbox"
          checked={autoBenchmark}
          onChange={(e) => onAutoBenchmarkChange(e.target.checked)}
        />
        {ERROR_MESSAGES.TUNER.AUTO_BENCHMARK_LABEL}
      </label>
      {benchmarkSaved && (
        <div className="success-msg" role="status" style={{ marginBottom: 8 }}>
          {ERROR_MESSAGES.TUNER.BENCHMARK_SAVED}{benchmarkSavedId !== null ? ` (ID: ${benchmarkSavedId})` : ""}
        </div>
      )}
      {benchmarkSaved && onTabChange && (
        <button type="button" onClick={() => onTabChange("benchmark")} style={{ marginBottom: 12 }}>
          {ERROR_MESSAGES.TUNER.GOTO_BENCHMARK_BUTTON}
        </button>
      )}
    </>
  );
}
