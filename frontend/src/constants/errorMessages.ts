export const ERROR_MESSAGES = {
  // SlaPage.tsx
  SLA: {
    PROFILE_LOAD_FAILED: "Failed to load SLA profile",
    NO_THRESHOLD_ERROR: "You must enter at least 1 threshold.",
    PROFILE_SAVE_FAILED: "Failed to save SLA profile",
    PROFILE_DELETE_CONFIRM: "Delete this SLA profile?",
    PROFILE_DELETE_FAILED: "Failed to delete SLA profile",
    NO_THRESHOLDS_SET: "No thresholds set",
    EDIT_TITLE: "Edit SLA Profile",
    CREATE_TITLE: "Create New SLA Profile",
    NO_PROFILES: "No profiles registered.",
    SELECT_BENCHMARK: "Select a benchmark from the Benchmark Comparison page",
    NO_EVALUATION_RESULTS: "No evaluation results",
  },

  // TunerPage.tsx
  TUNER: {
    ALL_API_FAILED: "Failed to fetch all tuner APIs (status, trials, importance)",
    PARTIAL_API_FAILED_PREFIX: "Warning: Failed to fetch some tuner information (",
    ERROR_DEFAULT: "An error occurred during tuning.",
    WARNING_DEFAULT: "A tuning warning occurred.",
    SSE_MAX_RETRIES_EXCEEDED: "Tuner SSE connection failed: Maximum retry attempts exceeded.",
    CONFIG_FETCH_FAILED: "Failed to fetch vLLM configuration",
    CONFIG_FETCH_ERROR_PREFIX: "Failed to fetch vLLM configuration: ",
    INTERRUPTED_WARNING: "Previous tuning was interrupted.",
    RESTART_CONFIRM: "vLLM InferenceService will restart. Apply the changed parameters?",
    APPLY_CURRENT_FAILED_PREFIX: "Failed to apply current values: ",
    APPLY_CURRENT_SUCCESS: "Current values applied successfully",
    STORAGE_URI_UPDATE_FAILED_PREFIX: "Failed to update storageUri: ",
    START_FAILED: "Failed to start tuning",
    START_ERROR_PREFIX: "Failed to start tuning: ",
    STOP_FAILED_PREFIX: "Failed to stop tuner: ",
    APPLY_BEST_FAILED_PREFIX: "Failed to apply parameters: ",
    APPLY_BEST_SUCCESS: "Applied optimal parameters to InferenceService.",
    APPLY_CURRENT_VALUES_SUCCESS: "Applied current values to InferenceService.",
    AUTO_BENCHMARK_LABEL: "Auto-save benchmark after completion",
    BENCHMARK_SAVED: "Benchmark saved ✓",
    GOTO_BENCHMARK_BUTTON: "Go to BenchmarkPage",
  },

  // LoadTestPage.tsx
  LOAD_TEST: {
    START_FAILED_PREFIX: "Failed to start load test: ",
    INTERRUPTED_WARNING: "Previous load test was interrupted.",
    REALTIME_LATENCY: "Real-time Latency (ms)",
  },
};
