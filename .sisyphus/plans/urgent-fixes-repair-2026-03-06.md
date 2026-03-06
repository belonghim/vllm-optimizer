# 🛠️ vLLM Optimizer urgent-fixes Repair Plan (2026-03-06)

**생성일**: 2026-03-06
**플랜 ID**: urgent-fixes-repair-2026-03-06
**우선순위**: P0 (블로커)
**예상 기간**: 2-3시간
**원본 플랜**: urgent-fixes-2026-03-06-consolidated

---

## TL;DR

Oracle F1 audit rejected the original implementation due to:
- Missing RBAC (Task 3)
- Corrupted deploy.sh (Task 14)
- Guardrail violation: prod overlay modified (Task 11 side-effect)
- Backend HPA duplication (Task 12)
- Missing evidence for 11 tasks

This repair plan addresses **all critical gaps** and re-validates.

---

## Repair Tasks

- [x] Task R1: Add Missing RBAC RoleBinding (Task 3 fix)

**What to do**:
- Insert `vllm-optimizer-monitoring-view` ClusterRoleBinding into `openshift/base/01-namespace-rbac.yaml` after line 52 (after existing ClusterRoleBinding).

**YAML**:
```yaml
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: vllm-optimizer-monitoring-view
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: cluster-monitoring-view
subjects:
  - kind: ServiceAccount
    name: vllm-optimizer-backend
    namespace: "vllm-optimizer"
```

**Acceptance**:
- [ ] `grep -A12 "vllm-optimizer-monitoring-view" openshift/base/01-namespace-rbac.yaml` shows correct content
- [ ] `oc apply --dry-run=client -f openshift/base/01-namespace-rbac.yaml` succeeds

**Evidence**: `.sisyphus/evidence/urgent-fixes-repair/task-r1-crb.txt`, `task-r1-dryrun.log`

---

- [x] Task R2: Fix deploy.sh Corruption (Task 14 fix)

**What to do**:
- Remove lines 213-214 and 245-246 that contain literal `\n` and `-n ""`.
- Replace with clean, functional rollout monitoring after each `oc apply -k`:

```bash
echo "⏳ Waiting for rollout to complete..."
oc rollout status deployment/vllm-optimizer-backend -n "${NAMESPACE}" --timeout=5m
oc rollout status deployment/vllm-optimizer-frontend -n "${NAMESPACE}" --timeout=5m

echo "⏳ Waiting for pods to be ready..."
oc wait --for=condition=Ready pod -l app=vllm-optimizer-backend -n "${NAMESPACE}" --timeout=300s
oc wait --for=condition=Ready pod -l app=vllm-optimizer-frontend -n "${NAMESPACE}" --timeout=300s

echo "✅ Deployment completed successfully"
```

- Ensure no duplicate inserts; script remains syntactically valid.
- Run `shellcheck deploy.sh` to validate.

**Acceptance**:
- [ ] No literal `\n` in deploy.sh
- [ ] All `-n` parameters use `${NAMESPACE}`, not empty string
- [ ] `shellcheck` reports no errors (or only minor)
- [ ] Script runs with `bash -n` (syntax check) passes

**Evidence**: `.sisyphus/evidence/urgent-fixes-repair/task-r2-deploy-clean.txt`, `task-r2-shellcheck.log`

---

- [x] Task R3: Revert Prod Overlay HPA Patch (Guardrail restore)

**What to do**:
- Remove the HPA patch from `openshift/overlays/prod/kustomization.yaml` lines 55-60.
- Ensure `prod/kustomization.yaml` does NOT modify HPA; HPA should be defined only in base.
- Verify only namespace and replicas patches exist for prod.

**Acceptance**:
- [ ] `grep -n "HorizontalPodAutoscaler" openshift/overlays/prod/kustomization.yaml` returns 0 (no matches)
- [ ] `oc apply -k openshift/overlays/prod --dry-run=client` succeeds

**Evidence**: `.sisyphus/evidence/urgent-fixes-repair/task-r3-prod-clean.txt`, `task-r3-dryrun.log`

---

- [x] Task R4: Fix Backend HPA Duplication (Task 12 fix)

**What to do**:
- Clean up `openshift/base/03-backend.yaml` HPA (lines 133-177):
  - Keep ONE `behavior` section with correct `scaleUp` and `scaleDown`.
  - Keep ONE `metrics` section.
  - Remove duplicate lines 165-177.
- Ensure HPA spec structure:
  - `scaleTargetRef`
  - `minReplicas: 1`, `maxReplicas: 5`
  - `behavior` (with scaleUp/scaleDown)
  - `metrics` (CPU and Memory)

**Acceptance**:
- [ ] `grep -A5 "behavior:" openshift/base/03-backend.yaml` shows one block
- [ ] `grep -c "metrics:" openshift/base/03-backend.yaml` returns 1
- [ ] `oc apply --dry-run=client -f openshift/base/03-backend.yaml` succeeds

**Evidence**: `.sisyphus/evidence/urgent-fixes-repair/task-r4-hpa-clean.txt`, `task-r4-dryrun.log`

---

- [x] Task R5: Generate Missing Evidence for All Tasks

**What to do**:
For each task that lacks evidence, run its QA scenarios and capture outputs:

**Tasks needing evidence**: 1,2,4,5,6,9,10,11,13,14 (and re-run 3,7,8 if needed)

- Create `.sisyphus/evidence/urgent-fixes-repair/` directory.
- For each task, execute its QA scenarios from the plan and save outputs with task-specific filenames.
- Ensure all acceptance criteria are re-verified with evidence.

**Acceptance**:
- [ ] Evidence files present for all 14 tasks (original + repairs)
- [ ] Each evidence file matches its scenario description

**Note**: This task will spawn multiple subcommands; ensure they run in correct order.

---

### Final Re-Verification (F1-F4 repeat)

After repairs, re-run the four verification agents (oracle, code quality, manual QA, scope fidelity) to confirm all issues resolved.

---

## Execution Order

1. R1 (RBAC)
2. R2 (deploy.sh) — depends on R1? No, independent
3. R3 (prod overlay)
4. R4 (HPA cleanup)
5. R5 (evidence generation)
6. Final Re-Verification

---

## Success Criteria

- All original Must Have items implemented correctly
- Zero Must NOT Have violations
- All evidence complete and matching scenarios
- All verification agents return APPROVE
