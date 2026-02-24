---
title: "Monitoring Runbook - Prometheus integration with vLLM"
date: 2026-02-24
updated: 2026-02-24
author: GPS Consultant
tags: ["monitoring","prometheus","runbook"]
status: draft
aliases: []
---

Executive summary
- This Runbook describes how to verify, monitor, and operate the Prometheus based monitoring for vLLM on OpenShift.

Scope
- Task 4-9: Expose metrics, start collector, test, and document.

Procedures
- Check /metrics endpoint is exposed and returns Prometheus text format
- Validate Prometheus data collection via MetricsCollector in startup
- Validate ServiceMonitor scrapes the metrics endpoint
- Validate dev environment test coverage and CI tests
- Runbook validation steps with rollback

Validation / Verification
- Run unit tests for metrics endpoint
- Run dev integration tests
- Validate OpenShift monitoring config
- Confirm logs indicate metrics collection

References
- OpenShift monitoring docs
- Prometheus text format
