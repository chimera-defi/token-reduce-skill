# Claude Guidance

Use `token-reduce` before broad repo discovery. If the path is unknown, start with:

```bash
./scripts/token-reduce-paths.sh topic words
```

Use scoped `rg` and targeted reads after the helper returns candidate paths. Do not start with `find .`, `ls -R`, `grep -R`, `rg --files .`, or broad glob patterns.

## Headroom Companion

Use Headroom more aggressively for large tool-result payloads, repeated logs/API responses, and long-running sessions where old tool output keeps inflating context.

- Verify health first: `headroom install status` or `curl -fsS http://127.0.0.1:8787/readyz`.
- Prefer selected wrapped sessions: `headroom wrap claude` or `headroom wrap codex`.
- Keep telemetry disabled.
- Do not enable `--learn` until memory writes are reviewed against memory policy.
- Do not use Headroom as the first move for unknown-path discovery; token-reduce remains the master router.

Measure adoption with:

```bash
./scripts/token-reduce-manage.sh measure
./scripts/token-reduce-manage.sh review
```

The adoption report includes `headroom_mentions`, `headroom_command_sessions`, `headroom_command_pct`, and recommendation conversion findings.
