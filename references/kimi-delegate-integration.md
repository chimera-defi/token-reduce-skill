# Kimi Delegate Companion Integration

`kimi-delegate-skill` is a standalone companion repository.

- Source: https://github.com/chimera-defi/kimi-delegate-skill
- Integration script: `scripts/integrate-kimi-delegate.sh`

## Why standalone

- keeps lifecycle/versioning independent from token-reduce
- allows Takopi/OpenClaw/Hermes to consume the same source of truth
- avoids embedding non-core orchestration logic in token-reduce

## Local integration flow

```bash
git clone https://github.com/chimera-defi/kimi-delegate-skill /root/.openclaw/workspace/dev/kimi-delegate-skill
./scripts/integrate-kimi-delegate.sh
```

This links the skill into `~/.agents/skills`, `~/.openclaw/skills`, and `~/.codex/skills` and optionally relinks workspace repos via the standalone installer.
