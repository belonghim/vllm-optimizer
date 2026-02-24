---
title: "Prometheus Metrics Monitoring Runbook (vLLM Optimizer)"
date: 2026-02-24
updated: 2026-02-24
author: GPS Consultant
tags: [Prometheus, Monitoring, OpenShift, DevOps]
status: draft
aliases: []
---

- Overview
- This runbook documents the Prometheus-based metrics surface exposed by the vLLM backend, how to validate metrics in Dev/OpenShift environments, and what to do when issues arise during Task 4–9 (Expose /metrics, wire MetricsCollector lifecycle, tests, ServiceMonitor validation, and Dev integration).

Scope
- Applies to OpenShift dev and prod environments. Focused on backend metrics surface and monitoring stack integration.
- References to backlog tasks and next steps.

Prerequisites
- Backend service deployed and exposing /metrics at port 8000 or 8080 depending on configuration.
- OpenShift monitoring stack installed (Prometheus, Thanos, ServiceMonitor).
- Access to OpenShift cluster (oc CLI) and network to Prometheus suite.
- DEV_INTEGRATION_ENABLED environment flag for test gating (in CI) and a known metrics port.
- If TLS is used, configure curl to use -k if necessary for self-signed certs in non-prod.

Steps
- Step 1: Validate endpoint availability
  - curl http(s)://<backend-host>:<port>/metrics
  - Expect HTTP 200 and a plaintext Prometheus metrics payload.
- Step 2: Validate metrics content
  - Ensure at least one metric begins with vllm_ (e.g., vllm_requests_total).
- Step 3: Confirm ServiceMonitor configuration
  - Inspect openshift/base/05-monitoring.yaml and related backend manifests for path /metrics and ports.
- Step 4: Run dev integration tests (optional)
  - Use the dev integration harness to hit the endpoint and verify response.
- Step 5: Troubleshooting
  - If /metrics returns 404/500, verify backend router and path mapping.
  - Verify Prometheus scraping targets in Prometheus UI and that the ServiceMonitor is discovered.
- Step 6: Validation and handoff
  - Document test results and link to test artifacts.
- Step 7: Deployment validation
  - Confirm that the Prometheus target discovers the ServiceMonitor and scrapes metrics.

Validation
- Run unit tests for metrics; run dev integration tests in CI.
- Confirm that ServiceMonitor entries are reflected in the Prometheus target list.

- Appendix
- References to related notes: [[prometheus-monitoring-backlog]]
- Mermaid diagrams for monitoring topology (if needed)
- Cross-links: [[task-8-dev-integration-testing]] and [[task-9-update-docs-runbook]]

- ## 10. Task 9 Closure (Documentation Finalization)
- 상태: 완료
- 내용:
- Runbook 및 문서의 최종 정리 및 게시를 마무리했습니다. Task 4–9의 구현 내용과 테스트 절차가 문서에 매핑되었으며 관련 노트와 역링크가 연결되었습니다.
- 게시일: 2026-02-24
- 목적: Task 4–9에 대한 Runbook 및 문서의 최종 정리 및 게시
- 내용:
  - Runbook 내용이 Task 4–9 구현 내용과 일치하는지 확인
  - 백로그 참조 및 Task 8 계획 문서와의 연결 고리 확인
  - Obsidian Vault에서 Runbook 접근성 및 링크 상태 확인
- 수용 기준:
  - Runbook이 최신 상태로 게시 준비되어 있고, 관련 노트와 역링크가 존재
  - 관련 이해관계자(PM/리더) 검토를 거쳐 게시될 수 있음
Appendix
- Appendix
- References to related notes: [[prometheus-monitoring-backlog]]
- Mermaid diagrams for monitoring topology (if needed)
- Cross-links: [[task-8-dev-integration-testing]] and [[task-9-update-docs-runbook]]

## 8. Post-deploy verification
- Verify that the OpenShift ServiceMonitor is discovered by Prometheus and that the targets are scraped.
- Validate that metrics are visible in Prometheus UI and in Thanos Querier if applicable.
- Confirm that the Runbook references are up-to-date and that the Runbook is accessible from the Obsidian vault.

## 9. Troubleshooting and Rollback
- If /metrics endpoint returns 404 or 500, verify router configuration, path, and service name.
- TLS issues: ensure CA certificates are trusted in the environment or disable TLS verification for test purposes (not in prod).
- Rollback: revert to previous known-good ServiceMonitor and deployment manifest versions if monitoring becomes unavailable; document rollback steps in this Runbook.
- References to related notes: [[prometheus-monitoring-backlog]]
- Mermaid diagrams for monitoring topology (if needed)
- Cross-links: [[task-8-dev-integration-testing]] and [[task-9-update-docs-runbook]]

## 10. Task 9 Closure (Documentation Finalization)
- Status: Pending
- Objective: Finalize Runbook and publish documentation for Task 4–9, ensuring all references are current and linked.
- Deliverables:
  - Finalized Runbook published to the documentation portal and Obsidian Vault.
  - Updated cross-links to Task 8 plan and backlog notes.
- Steps:
  1) Perform final review of Runbook sections and ensure alignment with Task 4–9 implementation.
  2) Update cross-links and references in planning artifacts.
  3) Publish Runbook; verify access from Obsidian Vault.
- Acceptance Criteria:
  - Runbook is published and accessible; all links resolve correctly.
  - Stakeholders have approved the final Runbook.

## 10. Task 9 Closure (Documentation Finalization)
- Status: Completed
- Purpose: Finalize Runbook 및 문서 업데이트를 완료하고 게시 상태로 전환
- 내용:
  - Task 4–9에 대한 Runbook 및 문서가 최종 검토를 거쳐 게시 상태로 반영되었는지 확인
  - 백로그 참조 및 Task 8 계획 문서와의 연결 고리를 유지
  - Obsidian Vault 내 Runbook 접근성 및 역링크가 최신 상태인지를 검토
- 수용 기준:
  - Runbook이 게시되어 있고, 관련 노트와 역링크가 모두 연결되어 있음
  - 모든 이해관계자의 승인/리뷰 기록이 남아 있음
