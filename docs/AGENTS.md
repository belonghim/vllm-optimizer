---
title: "Agent Orchestration Guidelines"
date: 2026-02-24
updated: 2026-02-25
author: GPS Consultant
tags: [agents, orchestration, openode]
status: draft
aliases: []
---

# Agent Orchestration Guidelines

This note describes the behavior, delegation patterns, and tool usage policies for OpenCode agents working on the vLLM Optimizer project.

## Core Principles

- **No slop**: Code must be indistinguishable from a senior engineer's.
- **Orchestrate, don't work alone**: Delegate to specialized subagents (explore, librarian, oracle, metis, momus) when appropriate.
- **Parallelize**: Independent reads, searches, and agents run simultaneously.
- **Verify before marking complete**: Lint, type checks, and test evidence required.

## Agent Types & When to Use

| Agent | Purpose | Cost |
|-------|---------|------|
| `explore` | Internal codebase grep and pattern discovery | Free |
| `librarian` | External references (docs, OSS examples, web) | Cheap |
| `oracle` | High-IQ consultation (architecture, debugging) | Expensive |
| `metis` | Pre-planning analysis (scope, ambiguities) | Expensive |
| `momus` | Plan and quality review | Expensive |
| Category tasks (`quick`, `deep`, `writing`, etc.) | Task execution with domain-optimized models | Varies |

## Delegation Protocol

Always use the `task()` function with:

- `category` OR `subagent_type` (one of the above)
- `load_skills` — include all relevant skills (user-installed skills have priority)
- `prompt` — must contain all 6 sections: TASK, EXPECTED OUTCOME, REQUIRED TOOLS, MUST DO, MUST NOT DO, CONTEXT
- `run_in_background=true` for parallel exploration; collect results later with `background_output(task_id)`

### Example (quick edit):

```ts
task(
  category="quick",
  load_skills=[],
  prompt="1. TASK: Update backend/main.py to fix import path ...\n2. EXPECTED OUTCOME: ...\n..."
)
```

## Session Continuity

Always store the `session_id` returned from a task. To continue or fix:

```ts
task(session_id="ses_abc123", prompt="Fix: Type error on line 42")
```

Continuing a session preserves full context, saving tokens and avoiding repeated work.

## Tool Usage Discipline

- Use `lsp_diagnostics` before marking a file complete.
- For multi-file edits, batch edits per file in one `edit()` call.
- Avoid `as any` and `@ts-ignore` — fix type errors properly.
- Never commit without explicit user request.
- When in doubt, DELEGATE.

## Common Triggers

- "Look into X" + "create PR" → Full implementation cycle expected.
- External library mentioned → Fire `librarian` immediately.
- 2+ modules involved → Fire `explore` in background.
- Ambiguous request → Consult `metis` before Prometheus.
- Work plan created → Review with `momus` before execution.

## Related

- [[monitoring_runbook|Monitoring Runbook]] — vLLM Prometheus integration runbook.
- `.sisyphus/plans/vllm-monitoring-integration.md` — Master plan for monitoring Tasks 1–9.
- OpenCode system docs: see `/home/user/.config/opencode/AGENTS.md` for full agent spec.
