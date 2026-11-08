# Agent Rules

## Attribution

- Commit author: the AI model that made the change
- Commit trailer: `Co-authored-by: Chimera <chimera_defi@protonmail.com>`
- PR body must include:
  - `**Agent:** <model name>`
  - `**Co-authored-by:** Chimera <chimera_defi@protonmail.com>`
  - `## Original Request`

## Commit Format

Use:

```text
type(scope): subject [Agent: <MODEL NAME>]
```

Example:

```text
docs(repo): add standalone install examples [Agent: GPT-5 Codex]
```

Allowed types:

- `feat`
- `fix`
- `docs`
- `style`
- `refactor`
- `perf`
- `test`
- `build`
- `ci`
- `chore`
- `revert`

## Local Hook

Install the commit hook path once per clone:

```bash
git config core.hooksPath .githooks
```

## PR Guidance

- Title should describe the change, not the prompt.
- Keep the PR summary factual and short.
- Include the original request verbatim in `## Original Request`.

## Token Reduce — Codex Notes

Canonical usage is in `SKILL.md`. In Codex there is no subagent API: if the candidate set stays broad after two discovery passes, ask the user to narrow the scope.

If the path is unknown, start discovery with `./scripts/token-reduce-paths.sh topic words` (or `token-reduce-snippet.sh` for one ranked excerpt), then use scoped `rg` and targeted reads. Do not start with `rg --files`, repo-wide `rg -n`, `find .`, `ls -R` or `grep -R`. This applies when editing this repo too.

Before merging, run `bash tests/test_e2e.sh` and paste its result in the PR. The old `validate`, `release-gate`, `measure`, `review`, Headroom and Caliper rules were removed with the 2026-11-08 shrink (see `SHRINK-REPORT.md`).

<!-- delegate-skill:begin -->
## AI Delegate Routing — MANDATORY

All delegation MUST go through the `delegate-skill` router, which selects the backend and calls its wrapper. Direct `devin`, raw `grok`, or backgrounded delegate commands are **prohibited** — they bypass envelope checks, fallback routing, auth detection, timeout scaling, and telemetry.

**Pick the delegate with the router, then call the named wrapper:**

| Task | Wrapper |
|------|---------|
| Browser / UI / screenshot / sandbox | `devin-delegate --task "..."` |
| Cheap research / review / summarize / draft | Haiku-high read-only subagent, or Codex `gpt-6.1-sol` low |
| Builds / implementation | `codex exec -m gpt-6.1-sol -c model_reasoning_effort=high` |
| Multi-file refactor / large codebase | `grok-delegate --task "..."` |
| Local Codex write-mode implementation | `/spark` |
| Unknown scope | `devin-delegate --task "..."` |

- **Interactive envelope builder:** `<delegate>-delegate --interactive`
- **Print envelope only:** `<delegate>-delegate --print-envelope --task "..."`

**Why this matters:**
- Structured envelopes prevent vague handoffs
- Provider fallback keeps execution moving when a delegate fails
- Auto-scaling timeouts and auth detection prevent silent hangs
- Telemetry enables continuous improvement

**Bypassing the wrapper will be detected and reported.**

- Keep delegation scoped and include acceptance criteria.
- If a delegate asks for clarification, resolve with Codex guidance first and Claude second before asking a human.
- Inspect telemetry regularly (`<delegate>-delegate --stats`).

See `~/.claude/skills/delegate-skill/SKILL.md` for the full routing table and health checks.
<!-- delegate-skill:end -->

<!-- SHARED_ATTRIBUTION_RULES_START -->
## Shared Attribution & Meta Learnings

- Commit author should be the active agent model identity.
- Commit trailer must include: `Co-authored-by: Chimera <chimera_defi@protonmail.com>`.
- PR description must include:
  - `**Agent:** <actual model name>`
  - `**Co-authored-by:** Chimera <chimera_defi@protonmail.com>`
- Never use placeholder model names; record the actual model used.
- Never push directly to `main`/`master`; use a feature branch and PR.
- Keep one task per PR for clear review and rollback.
- Verify before claiming complete: run relevant tests/lint/checks or explicitly note what was not run.
<!-- SHARED_ATTRIBUTION_RULES_END -->
