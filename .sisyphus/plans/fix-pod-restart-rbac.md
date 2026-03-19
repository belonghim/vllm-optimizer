# Fix: IS annotation 방식 복원 + RBAC 정리 + 클러스터 E2E 검증

## TL;DR

> **Quick Summary**: auto_tuner의 파드 재기동을 Deployment 직접 패치 → InferenceService `spec.predictor.annotations` 패치 방식으로 복원. 클러스터에서 IS annotation이 Deployment pod template으로 전파되는 것을 확인함(동일 타임스탬프). Deployment patch/status 불필요 RBAC 제거. deploy.sh로 클러스터 배포 후 실제 E2E 검증 수행.
>
> **Deliverables**:
> - auto_tuner.py: `_apply_params`, `_rollback_to_snapshot` → IS annotation 방식 복원
> - auto_tuner.py: `_wait_for_ready` → IS Ready condition polling 복원
> - RBAC: deployments `patch` 제거 (get/list만 유지)
> - test_tuner.py: mock을 CustomObjectsApi 기반으로 복원
> - deploy.sh dev 실행 → 클러스터 배포
> - E2E: 파드 재기동 + IS/Deployment annotation 변경 검증
> - AGENTS.md: E2E 클러스터 검증 필수 규칙 기록
>
> **Estimated Effort**: Medium
> **Critical Path**: T1 → T2 → T3 → T4 → T5

---

## Context

### 클러스터 진단 결과 (2026-03-15)

**IS annotation → Deployment pod template 전파 확인:**
```
IS spec.predictor.annotations["serving.kserve.io/restartedAt"]:       2026-03-07T15:23:37.378705Z
Deployment spec.template.metadata.annotations["serving.kserve.io/restartedAt"]: 2026-03-07T15:23:37.378705Z
```
→ KServe controller가 IS spec.predictor.annotations 변경을 감지하여 Deployment pod template에 전파하고, pod template 변경이 rolling update를 트리거함.

**이전 IS 방식이 실패한 진짜 원인:**
IS 이름 불일치 (`K8S_DEPLOYMENT_NAME="llm-ov-predictor"` → IS는 `"llm-ov"`) 때문에 IS 패치 자체가 404 에러로 실패.
→ `VLLM_IS_NAME` 수정으로 이미 해결됨. IS annotation 방식 자체는 정상 작동.

**현재 Deployment 직접 패치 방식의 문제:**
`read_namespaced_deployment_status` → RBAC에 `deployments/status` 서브리소스 권한 없음 → 403 Forbidden → `_wait_for_ready` 매 폴링 실패 → 300초 타임아웃

### 결정: IS annotation 방식 복원
- IS `spec.predictor.annotations` 패치 → KServe controller가 Deployment pod template 전파 → rolling update 트리거
- `_wait_for_ready`: IS Ready condition polling (기존 검증된 방식)
- Deployment `patch` RBAC 불필요 (IS `patch`만 있으면 됨)
- `_wait_for_ready` 후 Deployment pod template annotation 변경 확인 (IS → Deployment 전파 검증)

---

## Work Objectives

### Must Have
- `_apply_params`: IS `spec.predictor.annotations["serving.kserve.io/restartedAt"]` 패치 (CustomObjectsApi)
- `_rollback_to_snapshot`: 동일 IS annotation 패치
- `_wait_for_ready`: IS Ready condition polling (`get_namespaced_custom_object` → status.conditions)
- RBAC Role (vllm ns): deployments verbs에서 `patch` 제거 → `get`, `list`만 유지
- deploy.sh dev로 클러스터 배포
- E2E: IS annotation 변경 + Deployment pod template 전파 + 파드 UID 변경 확인
- AGENTS.md: E2E 클러스터 검증 필수 규칙

### Must NOT Have
- Deployment 직접 패치 (`patch_namespaced_deployment`) 코드
- `read_namespaced_deployment_status` 호출
- RBAC에 `deployments/status` 서브리소스
- RBAC에 deployments `patch` verb

---

## Execution Strategy

```
Wave 1 (Sequential — 코드 수정):
├── T1: auto_tuner.py IS annotation 방식 복원 + _wait_for_ready IS polling 복원 [deep]
├── T2: test_tuner.py mock 복원 [deep]

Wave 2 (Sequential — RBAC + 배포):
├── T3: RBAC YAML 수정 + AGENTS.md E2E 규칙 기록 [quick]

Wave 3 (Sequential — 배포 + 검증):
├── T4: deploy.sh dev → 클러스터 배포 [quick]
├── T5: E2E 클러스터 검증 [deep]
```

---

## TODOs

- [x] 1. auto_tuner.py IS annotation 방식 복원

  **What to do**:

  **`_apply_params` (line 508~)**: Deployment patch → IS annotation patch로 복원
  ```python
  try:
      name = VLLM_IS_NAME
      restart_body = {
          "spec": {
              "predictor": {
                  "annotations": {
                      "serving.kserve.io/restartedAt": datetime.datetime.now(
                          datetime.timezone.utc
                      ).isoformat()
                  }
              }
          }
      }
      await asyncio.to_thread(
          self._k8s_custom.patch_namespaced_custom_object,
          group="serving.kserve.io",
          version="v1beta1",
          namespace=K8S_NAMESPACE,
          plural="inferenceservices",
          name=name,
          body=restart_body,
      )
      logger.info(f"[AutoTuner] InferenceService '{name}' restarted in '{K8S_NAMESPACE}'.")
  except Exception as e:
      logger.error(f"[AutoTuner] InferenceService restart failed: {e}")
      return {"success": False, "error": f"InferenceService restart failed: {e}"}
  ```

  **`_rollback_to_snapshot` (line 548~)**: 동일하게 IS annotation patch로 복원
  동일한 IS annotation 패치 구조 사용. `VLLM_IS_NAME` 사용.

  **`_wait_for_ready` (line 77~)**: Deployment status polling → IS Ready condition polling으로 복원
  ```python
  async def _wait_for_ready(self, timeout: int = 300, interval: int = 5) -> bool:
      import time as _time
      logger.info(f"[AutoTuner] InferenceService '{VLLM_IS_NAME}' 준비 대기 중...")
      wait_start = _time.monotonic()
      start_time = asyncio.get_event_loop().time()
      result = False
      while asyncio.get_event_loop().time() - start_time < timeout:
          self._poll_count += 1
          try:
              inferenceservice = await asyncio.to_thread(
                  self._k8s_custom.get_namespaced_custom_object,
                  group="serving.kserve.io",
                  version="v1beta1",
                  name=VLLM_IS_NAME,
                  namespace=K8S_NAMESPACE,
                  plural="inferenceservices",
              )
              conditions = (inferenceservice or {}).get("status", {}).get("conditions", [])
              for c in conditions:
                  if c.get("type") == "Ready" and c.get("status") == "True":
                      logger.info(f"[AutoTuner] InferenceService '{VLLM_IS_NAME}' 준비 완료.")
                      result = True
                      break
              if result:
                  break
          except Exception as e:
              logger.warning(f"[AutoTuner] IS 상태 확인 오류: {e}")
          await asyncio.sleep(interval)

      wait_duration = _time.monotonic() - wait_start
      self._wait_durations.append(round(wait_duration, 2))
      self._total_wait_seconds += wait_duration
      if not result:
          logger.error(f"[AutoTuner] InferenceService '{VLLM_IS_NAME}' 시간 초과: {timeout}초.")
      return result
  ```

  **주의**: _wait_for_ready 복원 시, IS Ready가 롤링업데이트 중 잠시 False가 된 후 다시 True가 되는 타이밍을 활용. IS annotation 패치 직후 첫 폴링에서 아직 True(이전 상태)일 수 있으므로, 첫 폴링 전 `await asyncio.sleep(interval)` 한 번 삽입하거나, Ready가 False→True 전환을 감지하는 로직 추가 고려. 단, 기존 코드(2026-03-05 이전)가 이 방식으로 작동했으므로 동일하게 복원.

  **Must NOT do**:
  - `patch_namespaced_deployment` 호출 코드 유지 금지 (완전 제거)
  - `read_namespaced_deployment` / `read_namespaced_deployment_status` 호출 유지 금지
  - `kubectl.kubernetes.io/restartedAt` annotation 사용 금지
  - _evaluate, _suggest_params, _broadcast 변경 금지

  **References**:
  - `backend/services/auto_tuner.py:77-114` — 현재 _wait_for_ready (Deployment status polling → IS polling으로 교체)
  - `backend/services/auto_tuner.py:507-536` — 현재 _apply_params (Deployment patch → IS patch로 교체)
  - `backend/services/auto_tuner.py:543-570` — 현재 _rollback_to_snapshot (Deployment patch → IS patch로 교체)
  - `backend/services/auto_tuner.py:36` — VLLM_IS_NAME 정의 (유지)

  **Commit**: `fix(tuner): restore InferenceService annotation restart — remove Deployment direct patch`

- [x] 2. test_tuner.py mock 복원 — CustomObjectsApi 기반

  **What to do**:
  - mock_k8s_clients fixture: `read_namespaced_deployment`/`read_namespaced_deployment_status` mock 제거, `get_namespaced_custom_object` IS Ready mock 복원
  - test_apply_params_patches_correct_annotation_location: CustomObjectsApi `patch_namespaced_custom_object` 어설션 복원
  - test_wait_for_ready_polls_inferenceservice_status: IS Ready condition polling mock 복원
  - test_wait_for_ready_times_out: IS never-ready mock 복원
  - test_start_reapplies_best_params_at_end: IS patch count 어설션 복원
  - test_apply_params_returns_failure_when_is_patch_throws: CustomObjectsApi side_effect 복원
  - test_rollback_uses_deployment_restart → test_rollback_uses_inferenceservice_annotation으로 변경
  - `python3 -m pytest backend/tests/ -x -q -m "not integration"` → 전체 PASS

  **Commit**: `test(tuner): restore IS annotation mocks for restart tests`

- [x] 3. RBAC 수정 + AGENTS.md E2E 규칙

  **What to do**:

  **RBAC**: `openshift/base/01-namespace-rbac.yaml` ClusterRole `vllm-optimizer-controller`:
  - deployments verbs: `["get","list","watch","patch","update"]` → `["get","list","watch"]` (patch/update 제거)
  - IS patch는 이미 Role에 있음 (변경 없음)

  **AGENTS.md**: `## 금지 사항` 섹션 이전에 E2E 규칙 추가:
  ```markdown
  ### E2E 클러스터 검증 (필수)

  auto_tuner, 부하 테스트, ConfigMap 관련 코드 변경 시 반드시:
  1. `./deploy.sh dev`로 OpenShift 클러스터에 배포
  2. 실제 클러스터에서 기능 정상 동작 확인
  3. 파드 재기동이 필요한 변경은 `oc get pods -n vllm` 으로 파드 교체 확인
  4. 결과를 사용자에게 물어보지 말고 에이전트가 직접 `oc` 명령으로 확인

  코드만 수정하고 클러스터 검증을 생략하면 안 됨. 이전에 RBAC 403 에러가 코드 검증만으로는 발견되지 않아 실패한 사례가 있음.
  ```

  **Commit**: `fix(rbac): remove unnecessary deployments patch permission` + `docs(agents): add mandatory E2E cluster verification rule`

- [x] 4. 클러스터 배포 — deploy.sh dev

  **What to do**:
  - `./deploy.sh dev`로 백엔드 이미지 빌드 + 레지스트리 푸시 + 클러스터 배포
  - RBAC 적용: `oc apply -f openshift/base/01-namespace-rbac.yaml -n vllm-optimizer-dev`
  - 배포 완료 확인: `oc rollout status deployment/vllm-optimizer-backend -n vllm-optimizer-dev`
  - 새 Pod Running 확인: `oc get pods -n vllm-optimizer-dev -l app=vllm-optimizer-backend`

- [x] 5. E2E 클러스터 검증

  **What to do**:
  1. 현재 IS annotation 확인:
     ```bash
     oc get inferenceservice llm-ov -n vllm -o jsonpath='{.spec.predictor.annotations}'
     ```
  2. 현재 vLLM 파드 UID 수집:
     ```bash
     oc get pods -n vllm -l app=isvc.llm-ov-predictor -o jsonpath='{.items[*].metadata.uid}'
     ```
  3. 백엔드 Route URL 확인:
     ```bash
     BACKEND_URL=$(oc get route vllm-optimizer -n vllm-optimizer-dev -o jsonpath='{.spec.host}')
     ```
  4. 1-trial 튜닝 실행:
     ```bash
     curl -X POST https://$BACKEND_URL/api/tuner/start \
       -H 'Content-Type: application/json' \
       -d '{"n_trials": 1, "eval_requests": 5, "warmup_requests": 0, "vllm_endpoint": "http://llm-ov-predictor.vllm.svc.cluster.local:8080"}'
     ```
  5. 튜닝 완료 대기:
     ```bash
     while true; do
       STATUS=$(curl -s https://$BACKEND_URL/api/tuner/status)
       echo "$STATUS" | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'running={d[\"running\"]} trials={d.get(\"trials_completed\",0)}')"
       echo "$STATUS" | python3 -c "import sys,json; sys.exit(0 if not json.load(sys.stdin)['running'] else 1)" && break
       sleep 10
     done
     ```
  6. IS annotation 변경 확인:
     ```bash
     oc get inferenceservice llm-ov -n vllm -o jsonpath='{.spec.predictor.annotations.serving\.kserve\.io/restartedAt}'
     ```
  7. Deployment pod template annotation 전파 확인:
     ```bash
     oc get deployment llm-ov-predictor -n vllm -o jsonpath='{.spec.template.metadata.annotations.serving\.kserve\.io/restartedAt}'
     ```
  8. 파드 UID 변경 확인:
     ```bash
     oc get pods -n vllm -l app=isvc.llm-ov-predictor -o jsonpath='{.items[*].metadata.uid}'
     ```
  9. 백엔드 로그에 403 에러 없음 확인:
     ```bash
     oc logs -l app=vllm-optimizer-backend -n vllm-optimizer-dev --tail=50 | grep -i "403\|forbidden\|error"
     ```

  **성공 기준**:
  - IS annotation 타임스탬프가 변경됨 (이전 `2026-03-07` → 새 값)
  - Deployment pod template annotation과 IS annotation 값 동일
  - 파드 UID가 이전과 다름 (재기동됨)
  - 백엔드 로그에 403/forbidden 에러 없음

---

## Success Criteria

- [x] `python3 -m pytest backend/tests/ -x -q -m "not integration"` → 전체 PASS
- [x] IS annotation 타임스탬프 변경 확인 (클러스터)
- [x] Deployment pod template annotation 전파 확인 (클러스터)
- [x] 파드 UID 변경 확인 (클러스터)
- [x] 백엔드 로그에 403 에러 없음 (클러스터)
- [x] AGENTS.md에 E2E 필수 규칙 기록됨
