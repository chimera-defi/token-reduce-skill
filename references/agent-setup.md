# Agent Setup

Host-specific setup and wiring details.
The main `README.md` is user-facing; this file is for integrators.

## Full Setup (recommended)

One command installs QMD (BM25 search), RTK (output compression), optional AXI companion CLIs, and wires hooks:

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
- links local companion skills (`axi`, `caveman`, `compress`) into Codex when available under `~/.agents/skills`
- installs management wrappers for settings, telemetry sync, and update checks

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

- `./tools/token-reduce-skill/scripts/token-reduce-adaptive.sh`
- `./tools/token-reduce-skill/scripts/token-reduce-paths.sh`
- `./tools/token-reduce-skill/scripts/token-reduce-snippet.sh`

For Codex specifically, make the repo-local rule explicit: if the file path is unknown, the first compliant move is `token-reduce-adaptive.sh` (or `token-reduce-paths.sh` when adaptive is disabled). Raw `rg --files` or repo-wide `rg -n` should only happen as follow-up after the helper returns candidate paths.

When updating the skill itself, also run:

```bash
"$CODEX_HOME/skills/token-reduce/scripts/token-reduce-manage.sh" measure
"$CODEX_HOME/skills/token-reduce/scripts/token-reduce-manage.sh" review
```

That keeps the package aligned with the same evidence loop it asks hosts to follow.

If `scripts/setup.sh` has already been run on the machine, the Codex link and the global helper wrappers should already be present.

Optional managed-harness controls:

```bash
token-reduce-manage settings set telemetry.enabled true
token-reduce-manage settings set telemetry.endpoint https://your-endpoint.example/ingest
token-reduce-manage telemetry-sync
token-reduce-manage updates
token-reduce-manage auto-update
token-reduce-manage workspace-auto-update
token-reduce-manage deps-check
token-reduce-manage deps-update
token-reduce-manage deps-check-conditional
token-reduce-manage deps-update-conditional
token-reduce-manage settings profile list
token-reduce-manage settings profile apply max-savings
token-reduce-manage benchmark-profiles
```

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
| Adaptive routing | `token-reduce-adaptive.sh` | Auto-promotes paths/snippet/structural tiers from query intent + behavior |
| Path kickoff | `token-reduce-paths.sh` | QMD BM25 → candidate paths, minimal tokens |
| Snippet follow-up | `token-reduce-snippet.sh` | Adds one ranked excerpt when path-only results are not enough |
| Output compression | RTK (`rtk-rewrite.sh`) | Compresses output of commands that do run |
| Search backend | QMD | BM25 index, fallback to scoped `rg` |
| Optional response/input companion | caveman (`/caveman lite`, `/caveman:compress`) | Extra response brevity and memory-file token reduction |
| Optional interface companion | AXI (`gh-axi`, `chrome-devtools-axi`) | Lower-turn GitHub/browser tool interactions |
| Routing policy presets | `token-reduce-manage settings profile` | Formal `minimal-load` / `balanced` / `max-savings` behavior profiles |

## Read Next

- `references/architecture.md`
- `references/workspace-integration.md`
- `references/token-reduction-guide.md`
