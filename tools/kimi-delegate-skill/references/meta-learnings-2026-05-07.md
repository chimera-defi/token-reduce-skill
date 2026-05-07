# Meta Learnings — 2026-05-07

## What worked

- Using a strong planner + cheap Kimi executor improved structure and reduced parent-context spend.
- Enforcing a JSON delegation envelope prevented vague or overbroad handoffs.
- Local telemetry made fallback and quality regressions visible without external dependencies.
- Workspace propagation via one installer kept repo docs and skill links consistent.

## Guardrails to keep

- Always plan first with explicit acceptance criteria.
- Delegate only bounded subtasks; keep critical path orchestration local.
- Keep fallback deterministic and log reason codes.
- Keep output schema strict to avoid chatty responses.

## Future default for new skills

1. Create skill package with `SKILL.md`, scripts, config, prompts, and telemetry.
2. Add workspace install + audit scripts on day one.
3. Add at least one smoke test and one telemetry summary test.
4. Add rollout checklist + attribution requirements before first PR.
5. Record a meta-learnings file per release increment.
