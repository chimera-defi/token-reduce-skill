# Known Issues

## Output-hook over-compression (cross-repo, fix-out-of-scope)

Some sessions run a global `~/.claude/hooks` PostToolUse hook that compresses tool output and accidentally mangles `pytest` summaries ("No tests collected" or truncated pass/fail lines). This repo has no PostToolUse hook of its own — the offending hook lives outside this repo and is intentionally out of scope.

**Workaround** when running tests under a wrapped session:

```bash
uv run --with pytest python -m pytest scripts/tests/ -q > /tmp/pytest.out 2>&1
# then Read /tmp/pytest.out to inspect the full output without compression
```

Redirect to a file and `Read` the file rather than relying on stdout — the file path is not subject to in-flight tool-output compression.

## H3 — Global output-hook hardening (cross-repo, tracking only)

Tracking only. The fix belongs in `~/.claude/hooks/` — the global PostToolUse hook should detect known test-runner output formats (pytest, vitest, jest, go test) and skip compression for them. That change is outside this repo's scope; the orchestrator will surface it to the human for cross-repo tracking.

In this repo, the workaround above is the recommended escape hatch when the global hook is active.
