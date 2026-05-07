---
name: kimi-delegate
license: MIT
description: |
  Route bounded coding subtasks through a cheap Kimi subagent using a structured delegation envelope,
  fallback routing, and telemetry for continuous improvement.
metadata:
  author: "GPT-5 Codex"
  category: "orchestration"
  version: "0.1.0"
  argument_hint: "[task-or-scope]"
allowed-tools:
  - Bash
  - Read
  - Edit
  - Write
---

# Kimi Delegate Skill

## Description

Use this skill when you want a stronger parent agent to plan and guardrails-check a task, then delegate a narrowly scoped execution subtask to a cheaper Kimi worker.

## Triggers

- The user asks to delegate to Kimi or a cheap subagent.
- The task can be split into a bounded subtask with explicit acceptance criteria.
- You want to reduce parent-agent token usage for search/summarize/draft/check steps.
- You need telemetry on delegation quality, cost behavior, and fallback rates.

## Skip

- Tiny local edits where delegation overhead is larger than direct execution.
- Tasks requiring full-repo/global reasoning without clean scope boundaries.
- Any task where required secrets or sensitive content cannot leave the local execution boundary.

## First Move

1. Build a structured envelope:
   - `./tools/kimi-delegate-skill/scripts/plan_prompt.py --task "..."`
2. Delegate through the runner:
   - `./tools/kimi-delegate-skill/scripts/delegate.py --task "..." --context-file /tmp/context.txt`

## Process

1. Classify task (`search`, `summarize`, `draft`, `review`, `implementation-lite`).
2. Build envelope JSON with goal, scope, constraints, acceptance checks, and output schema.
3. Execute with Kimi using conservative budgets from `config/routing.json`.
4. Validate response schema; retry once if invalid.
5. If Kimi fails (timeout/schema/provider), route via Codex fallback by default.
6. Record telemetry for every call and periodically summarize trends.

## Success Criteria

- Every delegated run has an explicit envelope and acceptance criteria.
- Delegation logs include model, latency, fallback reason, and estimated token savings.
- Fallback is deterministic and visible in telemetry.
- Repo-level instructions include the delegation routing block.

## Usage

```
/kimi-delegate "summarize this failing CI log"
/kimi-delegate "draft migration checklist for auth module"
/kimi-delegate
```

---
Read `references/architecture.md` for architecture and rollout guidance.
