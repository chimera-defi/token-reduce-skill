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
