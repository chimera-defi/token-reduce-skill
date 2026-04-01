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

### Companion Tool Intake

For additions like alternate search backends, structural indexers, or external MCP servers:

1. verify the external project directly
2. run its tests or validation first
3. benchmark it on representative token-reduce tasks
4. integrate it only if it improves a specific task class without harming the default workflow
5. propagate the decision into docs and validation
