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

## Token Reduce — Codex Overrides

Canonical token-reduce rules are in `SKILL.md`. The notes below replace or supplement sections that differ in Codex.

### Escalation

There is no `Task(subagent_type)` API in Codex. If the candidate set stays broad after two discovery passes, stop and ask the user to narrow the scope. Do not attempt to spin up sub-agents.

### Python Commands

Use `uv run ...` instead of `python3 ...` or `pip ...`.
For the validator: `uv run --with pyyaml /path/to/quick_validate.py .`

### Skill Self-Maintenance

These narrow-discovery rules apply even when the task is modifying this skill repo itself. Editing `SKILL.md` or a hook does not justify broad repo inventory.

### First Move Discipline

If the user does not already provide the exact file path, the first compliant discovery command is:

```bash
./scripts/token-reduce-paths.sh topic words
```

Use `./scripts/token-reduce-snippet.sh topic words` only if one ranked excerpt is necessary after the path list.

Do not start Codex discovery in this repo with:

- `rg --files`
- raw `rg -n` across the repo
- `find .`
- `ls -R`
- `grep -R`

Scoped `rg` and targeted reads are follow-up tools after the helper returns candidate paths. They are not the initial compliant move when token-reduce is installed.

### Packaging Checks

Before calling the skill package complete, run:

```bash
./scripts/token-reduce-manage.sh validate
```

### Operational Checks

When changing routing, hooks, telemetry, or benchmark logic, also run:

```bash
./scripts/token-reduce-manage.sh measure
./scripts/token-reduce-manage.sh review
```

Treat the review output as the current evidence source for weak adoption, weak routing, or benchmark drift.

For major change sets before release/merge, also run:

```bash
./scripts/token-reduce-manage.sh release-gate
```

Only keep the change set when the gate reports `release_gate_pass: true`, or document the exception explicitly.

### Companion Tool Intake

For additions like alternate search backends, structural indexers, or external MCP servers:

1. verify the external project directly
2. run its tests or validation first
3. benchmark it on representative token-reduce tasks
4. integrate it only if it improves a specific task class without harming the default workflow
5. propagate the decision into docs and validation

<!-- delegate-skill:begin -->
## AI Delegate Routing — MANDATORY

All delegation MUST go through the `delegate-skill` router, which selects the backend and calls its wrapper. Direct `devin`, `pi --provider kimi-coding`, raw `grok`, or backgrounded delegate commands are **prohibited** — they bypass envelope checks, fallback routing, auth detection, timeout scaling, and telemetry.

**Pick the delegate with the router, then call the named wrapper:**

| Task | Wrapper |
|------|---------|
| Browser / UI / screenshot / sandbox | `devin-delegate --task "..."` |
| Cheap research / review / summarize / draft | `kimi-delegate --task "..."` |
| Multi-file refactor / large codebase | `grok-delegate --task "..."` |
| Local Codex write-mode implementation | `/spark` |
| Unknown scope | `kimi-delegate` to scope, then escalate |

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
