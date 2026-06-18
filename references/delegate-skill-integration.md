# Delegate Skill Router Integration

`delegate-skill` is the single entry point token-reduce uses for AI delegation. It is a
standalone companion repository that routes a task to the right backend and calls its
wrapper — token-reduce no longer wires individual delegate skills directly.

- Source: https://github.com/chimera-defi/delegate-skill
- Local skill: `~/.claude/skills/delegate-skill/SKILL.md`
- Integration script: `scripts/integrate-delegate-skill.sh`

## What it wraps

| Task | Router picks | Wrapper |
|------|--------------|---------|
| Browser / UI / screenshot / sandbox | devin | `devin-delegate` |
| Cheap research / review / summarize / draft | kimi | `kimi-delegate` |
| Multi-file refactor / large codebase | grok | `grok-delegate` |
| Local Codex write-mode implementation | spark | `/spark` |
| Unknown scope | kimi to scope, then escalate | `kimi-delegate` |

`delegate-skill/setup.sh` installs and links all four wrappers and injects the global
routing block. Always call the wrapper the router names — never raw `devin`,
raw `pi --provider kimi-coding`, raw `grok`, or backgrounded delegate commands; the
wrappers preserve envelope checks, fallback, auth detection, timeout scaling, and telemetry.

## Why standalone

- keeps lifecycle/versioning independent from token-reduce
- lets Takopi/OpenClaw/Hermes consume the same routing source of truth
- avoids embedding non-core orchestration logic in token-reduce

## Local integration flow

```bash
git clone https://github.com/chimera-defi/delegate-skill "$HOME/.claude/skills/delegate-skill"
./scripts/integrate-delegate-skill.sh
```

`integrate-delegate-skill.sh` locates the delegate-skill repo (override with
`DELEGATE_SKILL_REPO`) and runs its `setup.sh`. token-reduce's own `setup.sh` calls this
automatically unless `TOKEN_REDUCE_SETUP_DELEGATE_SKILL=0`
(legacy alias: `TOKEN_REDUCE_SETUP_KIMI_DELEGATE=0`).

## Health check

```bash
devin-delegate --check
kimi-delegate --check
grok-delegate --check
```
