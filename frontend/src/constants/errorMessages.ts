export const ERROR_MESSAGES = {
  // ClusterConfigBar.tsx
  CLUSTER_CONFIG: {
    AUTO_TUNER_RUNNING: "Auto-tuner 실행 중. CR 타입 변경 불가.",
    CR_TYPE_UPDATE_FAILED: "CR 타입 변경에 실패했습니다.",
    SAVE_FAILED: "설정 저장에 실패했습니다.",
    CONFIGMAP_WARNING: "설정이 메모리에만 적용됨. ConfigMap 업데이트 실패 — Pod 재시작 시 초기화됩니다.",
  },

  // SlaPage.tsx
  SLA: {
    PROFILE_LOAD_FAILED: "SLA 프로필 로드 실패",
    NO_THRESHOLD_ERROR: "최소 1개의 임계값을 입력해야 합니다.",
    PROFILE_SAVE_FAILED: "SLA 프로필 저장 실패",
    PROFILE_DELETE_CONFIRM: "이 SLA 프로필을 삭제하시겠습니까?",
    PROFILE_DELETE_FAILED: "SLA 프로필 삭제 실패",
    NO_THRESHOLDS_SET: "No thresholds set",
    EDIT_TITLE: "SLA 프로필 편집",
    CREATE_TITLE: "새 SLA 프로필 생성",
    NO_PROFILES: "등록된 프로필이 없습니다.",
    SELECT_BENCHMARK: "벤치마크 비교 페이지에서 벤치마크를 선택하세요",
    NO_EVALUATION_RESULTS: "평가 결과 없음",
  },

  // TunerPage.tsx
  TUNER: {
    ALL_API_FAILED: "튜너 모든 API 조회 실패 (상태, 시도, 중요도)",
    PARTIAL_API_FAILED_PREFIX: "주의: 일부 튜너 정보를 가져오지 못했습니다 (",
    ERROR_DEFAULT: "튜닝 중 오류가 발생했습니다.",
    WARNING_DEFAULT: "튜닝 경고가 발생했습니다.",
    SSE_MAX_RETRIES_EXCEEDED: "튜너 SSE 연결 실패: 최대 재시도 횟수를 초과했습니다.",
    CONFIG_FETCH_FAILED: "vLLM 설정 조회 실패",
    CONFIG_FETCH_ERROR_PREFIX: "vLLM 설정 조회 실패: ",
    INTERRUPTED_WARNING: "이전 튜닝이 비정상 종료되었습니다.",
    RESTART_CONFIRM: "vLLM InferenceService가 재시작됩니다. 변경된 파라미터를 적용하시겠습니까?",
    APPLY_CURRENT_FAILED_PREFIX: "현재값 적용 실패: ",
    APPLY_CURRENT_SUCCESS: "현재값 적용 완료",
    STORAGE_URI_UPDATE_FAILED_PREFIX: "storageUri 업데이트 실패: ",
    START_FAILED: "튜닝 시작 실패",
    START_ERROR_PREFIX: "튜닝 시작 실패: ",
    STOP_FAILED_PREFIX: "튜너 중지 실패: ",
    APPLY_BEST_FAILED_PREFIX: "파라미터 적용 실패: ",
    APPLY_BEST_SUCCESS: "최적 파라미터를 InferenceService에 적용했습니다.",
    APPLY_CURRENT_VALUES_SUCCESS: "현재값을 InferenceService에 적용했습니다.",
    AUTO_BENCHMARK_LABEL: "완료 후 벤치마크 자동 저장",
    BENCHMARK_SAVED: "벤치마크 저장됨 ✓",
    GOTO_BENCHMARK_BUTTON: "BenchmarkPage로 이동",
  },

  // LoadTestPage.tsx
  LOAD_TEST: {
    START_FAILED_PREFIX: "부하 테스트 시작 실패: ",
    INTERRUPTED_WARNING: "이전 부하 테스트가 비정상 종료되었습니다.",
    REALTIME_LATENCY: "실시간 레이턴시 (ms)",
  },
};
