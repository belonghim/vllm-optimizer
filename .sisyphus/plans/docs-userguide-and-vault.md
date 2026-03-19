# Plan: Dashboard User Guide + Vault Knowledge Organization

**Created**: 2026-03-08
**Status**: ✅ COMPLETED (2026-03-08)
**Scope**: `docs/user-guide.md` (한국어 대시보드 사용자 가이드) + Obsidian vault 지식 정리 (5개 노트 업데이트/생성)

---

## Context & Decisions

### Confirmed Decisions
- User guide 언어: **한국어** (합니다/하십시오체)
- UI 라벨은 화면에 표시된 그대로 (한국어/영어 혼용) 번역하지 않음
- 벤치마크 탭: **비교 전용**으로 문서화 (저장 버튼이 UI에 없음)
- Vault 정리: **포괄적** (기존 3개 업데이트 + 새 2개 생성)
- Learnings 문서: 기존 유지 + 2026-03-08 날짜의 새 섹션 추가 (append)

### Critical Guardrails (from Metis)
- ❌ 벤치마크 "저장" 워크플로우 문서화 금지 (UI 버튼 없음)
- ❌ Temperature를 설정 가능한 필드로 문서화 금지 (form에 없음, state에만 있음)
- ❌ Tuner의 `vllm_endpoint`를 입력 필드로 문서화 금지 (자동 채움, UI 미표시)
- ❌ "CONNECTED" 표시를 실시간 연결 상태로 설명 금지 (하드코딩된 장식 요소)
- ❌ 영어 UI 라벨을 한국어로 번역 금지 (화면 그대로: "P99 Latency", "TPS" 등)
- ⚠️ "Apply Best Params" 경고 포함 필수 — ConfigMap 직접 수정, 되돌리기 불가
- ⚠️ Mock 모드 기본 ON 동작 설명 필수 (localStorage 지속)
- ⚠️ 벤치마크 비교 차트는 2개 이상 선택 시에만 표시됨을 명시

### Scope Boundaries
**IN**: `docs/user-guide.md`, vault 5개 노트 (아래 상세)
**OUT**: 기존 vault 파일명 변경 (wikilink 깨짐 위험), `deliverables/` 수정, `20_AREAS/` 신규 문서, frontend 코드 수정

---

## Wave 1: Dashboard User Guide (docs/user-guide.md)

### Task 1: Create `docs/user-guide.md` — 한국어 대시보드 사용자 가이드
- [x] **File**: `docs/user-guide.md` (신규 생성)
- [x] **Language**: 한국어 (합니다/하십시오체), UI 라벨은 영어 그대로 유지
- [x] **Frontmatter**: `title: "vLLM Optimizer 대시보드 사용자 가이드"`, `date: 2026-03-08`, `updated: 2026-03-08`, `tags: [user-guide, dashboard, vllm]`, `status: published`

**Required Sections (in order):**

1. **개요** — vLLM Optimizer 대시보드의 목적, 4개 탭 소개, 접근 방법 (OpenShift Route URL)
2. **Mock 모드** — 헤더 우측 MOCK 토글 설명, 기본 ON, localStorage 지속, 실제 데이터 보려면 OFF 필요, "CONNECTED" 표시는 장식이며 실제 연결 상태 반영 안함
3. **실시간 모니터링 탭** (`MonitorPage.jsx` 기반):
   - 8개 MetricCard 설명: Tokens / sec (TPS), TTFT Mean, P99 Latency, KV Cache, Running Reqs, Waiting Reqs, GPU Memory, Pods Ready
   - 4개 차트: Throughput (TPS), Latency (TTFT + P99), KV Cache Usage (%), Request Queue (Running + Waiting)
   - 2초 간격 자동 갱신 (API: `GET /api/metrics/latest`, `GET /api/metrics/history?last_n=60`)
   - KPI 해석 가이드: 정상 범위, 주의 필요 신호
4. **부하 테스트 탭** (`LoadTestPage.jsx` 기반):
   - 설정 필드: vLLM Endpoint (자동 채움), Model Name, Total Requests, Concurrency, RPS (0=unlimited), Max Tokens
   - Streaming Mode 체크박스 (TTFT 측정 활성화)
   - ▶ Run Load Test / ■ Stop 버튼
   - 진행률 표시 (progress bar + %)
   - 결과: 4개 MetricCard (Mean TPS, TTFT Mean, P99 Latency, Success Rate)
   - 결과: Latency Distribution 테이블 (Total, Success, Failed, Actual RPS, Mean/P50/P95/P99, TTFT, Total TPS)
   - 실시간 차트: Latency (ms) + TPS
   - SSE 스트림 사용 (`EventSource /api/load_test/stream`)
   - ⚠️ 에러 발생 시 빨간색 경고 메시지 표시
5. **벤치마크 비교 탭** (`BenchmarkPage.jsx` 기반):
   - 저장된 벤치마크 테이블 (Name, Date, TPS, P99 ms, RPS)
   - 체크박스로 벤치마크 선택 (2개 이상 선택 시 비교 차트 표시)
   - 비교 차트: TPS 비교 (bar), P99 Latency 비교 (bar)
   - ⚠️ 저장 기능은 UI에 없음 — 부하 테스트 완료 시 자동 저장되거나 API를 통해 저장
   - "부하 테스트 결과를 저장하면 여기 나타납니다" 안내 메시지 설명
6. **자동 파라미터 튜닝 탭** (`TunerPage.jsx` 기반):
   - 설정: 최적화 목표 (최대 처리량/최소 레이턴시/균형), Trial 수, max_num_seqs 범위 (Min/Max), GPU Memory Util 범위 (Min/Max)
   - ▶ Start Tuning / ■ Stop 버튼
   - ✓ Apply Best Params 버튼 — **⚠️ 경고: Kubernetes ConfigMap을 직접 수정합니다. 되돌리기 기능이 없으므로 신중하게 사용하십시오.**
   - 최적 파라미터 발견 시: Best TPS, P99 Latency MetricCard + 파라미터 테이블
   - Trial 분포 차트: Scatter (TPS vs P99 Latency)
   - 파라미터 중요도 (FAnova): 프로그레스 바 형태로 각 파라미터의 영향도 표시
   - 3초 간격 자동 갱신
7. **자주 묻는 질문 (FAQ)** — 4~5개 항목:
   - "Mock 모드를 끄면 데이터가 안 나옵니다" → MetricsCollector 확인, K8S_DEPLOYMENT_NAME 점검
   - "부하 테스트가 시작되지 않습니다" → vLLM endpoint 확인, 네트워크 접근성
   - "벤치마크 테이블이 비어 있습니다" → 부하 테스트 실행 후 확인
   - "Apply Best Params를 되돌리고 싶습니다" → ConfigMap 수동 복원 필요
   - troubleshooting.md 교차 참조

**Reference files to READ** (for exact UI labels, form fields, API calls):
- `frontend/src/App.jsx` — tab names, header, MockDataSwitch
- `frontend/src/pages/MonitorPage.jsx` — metrics, charts
- `frontend/src/pages/LoadTestPage.jsx` — config form, SSE, results
- `frontend/src/pages/BenchmarkPage.jsx` — table, comparison charts
- `frontend/src/pages/TunerPage.jsx` — tuning config, scatter, importance
- `frontend/src/components/MockDataSwitch.jsx` — mock toggle behavior
- `frontend/src/constants.js` — API base path

**QA**:
- [x] 파일이 100줄 이상인지 확인 → 204줄
- [x] 4개 탭 섹션 모두 존재하는지 확인 (grep "##") → 19개 섹션
- [x] 한국어 내용 20줄 이상 포함 확인 → 전체 한국어 문서
- [x] 금지 내용 없음 확인: "저장.*버튼", "temperature", "CONNECTED.*실시간" → 0 matches
- [x] Mock 모드 섹션 존재 확인 → `## 2. Mock 모드` 섹션 존재

---

## Wave 2: Vault — 기존 문서 업데이트 (3개)

### Task 2: Update `vllm-optimizer-architecture.md` in vault
- [x] **Vault path**: `10_PROJECTS/2026-02_vllm-optimizer/data/vllm-optimizer-architecture.md`
- [x] **Tool**: `mcp_obsidian_patch_note` for targeted updates, or `mcp_obsidian_write_note` with `mode: overwrite` if major rewrite needed
- [x] **Changes**:
  1. Frontmatter `updated:` → `2026-03-08`, `status: draft` → `status: published`
  2. Add **KServe 네이밍 규칙** section after 컴포넌트 설명:
     - InferenceService `llm-ov` → Deployment `llm-ov-predictor` → Pod label `app=isvc.llm-ov-predictor`
     - `K8S_DEPLOYMENT_NAME` env var는 반드시 Deployment 이름 사용
  3. Add **네임스페이스 분리** clarification:
     - Optimizer: `vllm-optimizer-dev` (또는 `vllm-optimizer-prod`)
     - vLLM: `vllm`
  4. Add **MetricsCollector 동적 라벨 셀렉터** note:
     - `Deployment.spec.selector.matchLabels`에서 라벨 셀렉터를 동적으로 읽어옴
     - 하드코딩된 라벨 패턴 사용 안 함
  5. Update architecture diagram to show `vllm` namespace with KServe resources
  6. Update 관련 노트 links if needed
- [x] **QA**: `grep -i "kserve\|llm-ov-predictor"` → 다수 매치, `updated: 2026-03-08` 확인됨

### Task 3: Update `vllm-optimizer-runbook.md` in vault
- [x] **Vault path**: `30_RESOURCES/runbooks/AI/vllm-optimizer-runbook.md`
- [x] **Tool**: `mcp_obsidian_patch_note` for each fix
- [x] **Changes**:
  1. Add proper frontmatter (currently missing YAML `---` delimiters — the frontmatter is embedded in content)
  2. Fix `oc serviceaccounts get-token` → `oc create token` (Troubleshooting section)
  3. Fix deploy script path: `./scripts/deploy.sh` → `./deploy.sh`
  4. Fix namespace: `vllm-optimizer` → `vllm-optimizer-dev` (throughout, for dev context)
  5. Add new troubleshooting entry: **MetricsCollector 올-제로 메트릭**
     - Cause: `K8S_DEPLOYMENT_NAME`이 InferenceService 이름으로 설정됨
     - Fix: KServe Deployment 이름 (`llm-ov-predictor`) 사용
  6. Add new troubleshooting entry: **auto_tuner 후 다른 테스트 skip**
     - Cause: p99 latency 상승 → `skip_if_overloaded` 트리거
     - Fix: 120초 대기 후 vLLM pod 상태 확인
  7. Update `updated:` date in frontmatter to `2026-03-08`
- [x] **QA**: `oc serviceaccounts get-token` → 주석 처리됨(deprecated 안내), `oc create token` → 실제 사용됨, `./deploy.sh` 경로 정확

### Task 4: Append to `learnings.md` in vault
- [x] **Vault path**: `10_PROJECTS/2026-02_vllm-optimizer/data/learnings.md`
- [x] **Tool**: `mcp_obsidian_write_note` with `mode: append`
- [x] **Append content**: New dated section `## 2026-03-08: KServe 배포 수정 및 통합 테스트 안정화`
  - **K8S_DEPLOYMENT_NAME 수정**: `llm-ov` → `llm-ov-predictor` (KServe가 생성하는 Deployment 이름)
  - **MetricsCollector 동적 라벨 셀렉터**: `Deployment.spec.selector.matchLabels`에서 동적으로 읽어옴
  - **skip_if_overloaded 픽스처**: auto_tuner 후 p99 latency 상승 → 120초 대기, Thanos 1분 rate window 롤오버
  - **통합 테스트 8/8 pass**: test_cluster_health, test_load_test_throughput, test_sse_streaming, test_metrics_collection, test_prometheus_metrics, test_metrics_response_time, test_prometheus_scrape_format, test_auto_tuner
  - **docs/ 보강**: architecture.md, deployment.md, troubleshooting.md 추가, monitoring_runbook.md 업데이트
  - **Import 패턴 확인**: `from services.xxx` (bare import), `backend.` 접두사 금지
- [x] **QA**: `2026-03-08` 섹션 존재 확인, 기존 2026-02-24 내용 보존됨

---

## Wave 3: Vault — 새 지식 노트 생성 (2개)

### Task 5: Create `kserve-naming-patterns.md` in vault
- [x] **Vault path**: `10_PROJECTS/2026-02_vllm-optimizer/data/kserve-naming-patterns.md`
- [x] **Tool**: `mcp_obsidian_write_note`
- [x] **Frontmatter**: title, date, updated: 2026-03-08, tags: [kserve, openshift, naming, troubleshooting], status: published
- [x] **Content**:
  1. **KServe 리소스 네이밍 규칙** — InferenceService → Deployment → Pod label → Service 이름 패턴 테이블
  2. **K8S_DEPLOYMENT_NAME 설정** — 반드시 KServe Deployment 이름 사용, ISVC 이름 사용 시 MetricsCollector가 pod를 찾지 못함
  3. **Pod 라벨 셀렉터** — `app=isvc.{name}-predictor` 패턴, MetricsCollector는 Deployment matchLabels에서 동적으로 읽음
  4. **진단 명령어** — `oc get deployment -n vllm`, `oc get pods -n vllm -l app=isvc.llm-ov-predictor`
  5. **관련 노트 링크**: `[[vllm-optimizer-architecture]]`, `[[vllm-optimizer-runbook]]`
- [x] **QA**: 생성 확인. 네이밍 테이블, 진단 명령어, 올-제로 메트릭 플로우 포함

### Task 6: Create `vllm-optimizer-status-2026-03.md` in vault
- [x] **Vault path**: `10_PROJECTS/2026-02_vllm-optimizer/data/vllm-optimizer-status-2026-03.md`
- [x] **Tool**: `mcp_obsidian_write_note`
- [x] **Frontmatter**: title, date, updated: 2026-03-08, tags: [vllm-optimizer, status, project], status: published
- [x] **Content**:
  1. **현재 상태 요약** — 통합 테스트 8/8 pass, MetricsCollector 정상, 대시보드 정상
  2. **배포 환경**:
     - Optimizer namespace: `vllm-optimizer-dev`
     - vLLM namespace: `vllm`
     - Backend image: `quay.io/joopark/vllm-optimizer-backend:dev`
     - Model: `Qwen2.5-Coder-3B-Instruct-int4-ov` (CPU/OpenVINO)
  3. **최근 수정 이력** (2026-03-01 ~ 2026-03-08):
     - K8S_DEPLOYMENT_NAME 수정 (`llm-ov` → `llm-ov-predictor`)
     - MetricsCollector 동적 라벨 셀렉터
     - skip_if_overloaded 120초 대기
     - docs/ 보강 (architecture, deployment, troubleshooting, monitoring_runbook, user-guide)
     - AGENTS.md 업데이트
  4. **알려진 제한사항**:
     - 벤치마크 저장 UI 버튼 없음 (API only)
     - "CONNECTED" 표시가 실제 연결 상태 미반영
     - Temperature 필드가 UI form에 노출되지 않음
     - GPU 메트릭은 CPU 전용 환경에서 0 표시
  5. **관련 노트 링크**: `[[vllm-optimizer-architecture]]`, `[[learnings]]`, `[[kserve-naming-patterns]]`
- [x] **QA**: 생성 확인. 통합테스트 8/8 현황, 알려진 제한사항, 최근 수정이력 포함

---

## Final Verification Wave

### Task 7: Verify all deliverables and commit
- [x] Verify `docs/user-guide.md` exists and passes QA checks → 204줄, 7개 섹션
- [x] Verify vault notes updated/created correctly → 6개 노트 전부 확인
- [x] Git commit for `docs/user-guide.md`: `a0d57a1 docs: add Korean dashboard user guide`
- [x] Push if requested → origin/main 동기화 완료

---

## Execution Summary

| Wave | Tasks | Parallelizable | Est. Time |
|------|-------|----------------|-----------|
| Wave 1 | Task 1 (user-guide.md) | No (single large doc) | 3-4 min |
| Wave 2 | Tasks 2-4 (vault updates) | Yes (all 3 parallel) | 2-3 min |
| Wave 3 | Tasks 5-6 (vault new notes) | Yes (both parallel) | 1-2 min |
| Final | Task 7 (verify + commit) | No | 1 min |
| **Total** | 7 tasks | | **~8 min** |
