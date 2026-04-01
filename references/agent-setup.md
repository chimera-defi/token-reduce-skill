# Agent Setup

Host-specific setup and wiring details.
The main `README.md` is user-facing; this file is for integrators.

## Full Setup (recommended)

One command installs QMD (BM25 search) and RTK (output compression) and wires both:

```bash
./scripts/setup.sh
```

Or from a fresh clone of the skill into a consumer repo:

```bash
./tools/token-reduce-skill/scripts/setup.sh
```

It also:
- links global helper commands into `~/.local/bin`
- links the Codex skill into `$CODEX_HOME/skills/token-reduce`

## Claude Code

### Plugin Install

```text
claude plugin marketplace add chimera-defi/token-reduce-skill
claude plugin install token-reduce@chimera-defi
```

The plugin wires the token-reduce enforcement hooks automatically.
For RTK output compression on top, run `scripts/setup.sh` or `rtk init -g` separately.

### Repo-Level Hook Wiring

See `references/workspace-integration.md` for the full settings.json template, including both token-reduce hooks and the RTK rewrite hook.

## Codex

```bash
git clone https://github.com/chimera-defi/token-reduce-skill "$CODEX_HOME/skills/token-reduce"
```

Then run:

```bash
"$CODEX_HOME/skills/token-reduce/scripts/setup.sh"
"$CODEX_HOME/skills/token-reduce/scripts/token-reduce-manage.sh" validate
```

Point repo instructions at:

- `./tools/token-reduce-skill/scripts/token-reduce-paths.sh`
- `./tools/token-reduce-skill/scripts/token-reduce-snippet.sh`

For Codex specifically, make the repo-local rule explicit: if the file path is unknown, the first compliant move is `token-reduce-paths.sh`. Raw `rg --files` or repo-wide `rg -n` should only happen as follow-up after the helper returns candidate paths.

When updating the skill itself, also run:

```bash
"$CODEX_HOME/skills/token-reduce/scripts/token-reduce-manage.sh" measure
"$CODEX_HOME/skills/token-reduce/scripts/token-reduce-manage.sh" review
```

That keeps the package aligned with the same evidence loop it asks hosts to follow.

If `scripts/setup.sh` has already been run on the machine, the Codex link and the global helper wrappers should already be present.

## MCP

```json
{
  "mcpServers": {
    "token-reduce-mcp": {
      "command": "node",
      "args": ["/absolute/path/to/token-reduce-skill/mcp/server.mjs"]
    }
  }
}
```

## What Each Layer Does

| Layer | Tool | What it does |
|-------|------|--------------|
| Discovery guardrails | `enforce-token-reduce-first.py` | Blocks broad scans before they happen |
| Prompt steering | `remind-token-reduce.py` | Routes discovery prompts to helpers |
| Path kickoff | `token-reduce-paths.sh` | QMD BM25 → candidate paths, minimal tokens |
| Output compression | RTK (`rtk-rewrite.sh`) | Compresses output of commands that do run |
| Search backend | QMD | BM25 index, fallback to scoped `rg` |

## Read Next

- `references/architecture.md`
- `references/workspace-integration.md`
- `references/token-reduction-guide.md`
