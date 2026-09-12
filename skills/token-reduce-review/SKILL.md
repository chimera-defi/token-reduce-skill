---
name: token-reduce-review
license: MIT
description: "Use when token-reduce hooks are blocking sessions, search results look silently empty, deployed hook behavior may have drifted from the repo, or a periodic health review of the token-reduce stack is due."
triggers:
  - token-reduce health review
  - hooks are blocking me
  - find returned nothing
  - deployed hooks out of sync
metadata:
  author: "Claude Sonnet 5"
  category: "diagnostics"
  version: "1.0.0"
allowed-tools:
  - Read
  - Bash
---

# token-reduce Review Pass

Report-only diagnostic pass for the token-reduce hook stack. Wraps `scripts/review_pass.py`.

## Run order

```bash
uv run scripts/review_pass.py all --report artifacts/token-reduction/review-pass-<date>.md
```

Or step through individually: `deploy-drift` -> `hook-contract` -> `env-sanity` ->
`adoption-snapshot` -> `inventory-staleness`.

- `deploy-drift` compares hook file hashes across origin/main, `.worktrees/main`,
  and the deployed `~/.claude/hooks/token-reduce/` copy.
- `hook-contract` runs canned regression scenarios against the repo AND deployed
  hook copies and reports a per-copy pass/fail matrix.
- `env-sanity` checks the `~/.claude/projects` symlink-find trap and an rg
  hidden-file demo.
- `adoption-snapshot` summarizes recent hook/telemetry signals.
- `inventory-staleness` flags unwired, long-untouched scripts.

## Reading the report

Every check exits 0 (healthy), 1 (findings), or 2 (tool error). Exit 1 is often
the CORRECT result -- e.g. a fix landed in `scripts/` but was not yet
redeployed. Cross-check findings against `references/worktree-deploy-sync.md`
before assuming something is broken.

This tool and skill are **report-only**: they never write to `~/.claude/hooks/`,
`.worktrees/main`, or `~/.claude/skills/`. Redeploying a fix is a separate,
human-approved step.

## Install (opt-in)

Not installed by default. To enable:

```bash
ln -s "$(pwd)/skills/token-reduce-review" ~/.claude/skills/token-reduce-review
```
