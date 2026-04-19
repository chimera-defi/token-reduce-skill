# token-reduce

![Claude Code](https://img.shields.io/badge/Claude%20Code-plugin-111111)
![Codex](https://img.shields.io/badge/Codex-skill-1f6feb)
![MCP](https://img.shields.io/badge/MCP-server-0a7f5a)
![MIT](https://img.shields.io/badge/license-MIT-lightgrey)

`token-reduce` is an orchestration layer for agent context spending.
It provides built-in routing/enforcement, installs and wires downstream tools, and tells Claude/Codex when to use each tool path.

> Agents: start with [`llms.txt`](./llms.txt) for compact install/usage instructions.

## What It Is

`token-reduce` is not just a prompt style or a single helper script.
It is a high-level token orchestration kit that:

- enforces low-cost discovery first
- auto-routes between path/snippet/structural tiers
- wires tool hooks so wasteful calls are blocked before execution
- integrates a dependency suite and operational benchmarking/review gates

## Dependency Suite (Feature)

`token-reduce` treats dependency integration as a first-class feature.
Instead of manually managing tool-by-tool setup, it installs/wires defaults and exposes conditional tiers explicitly.

### Core orchestrated stack

- [QMD](https://github.com/tobi/qmd): BM25 path/snippet retrieval
- [RTK](https://github.com/rtk-ai/rtk): output compression for executed commands
- token-reduce helpers/hooks: path/snippet/adaptive routing + enforcement

### Conditional companions

- [AXI](https://github.com/kunchenguid/axi) (`gh-axi`, `chrome-devtools-axi`) for GitHub/browser-heavy execution
- [`token-savior`](https://github.com/Mibayy/token-savior) for exact symbol / impact acceleration
- [`context-mode`](https://github.com/mksglu/context-mode) for output-heavy payload sessions
- [`code-review-graph`](https://github.com/tirth8205/code-review-graph) for large-repo structural review tasks
- [`caveman`](https://github.com/JuliusBrussee/caveman) for optional terse output and memory-file compression

### Not in default routing

- `token-optimizer-mcp`, `token-optimizer`, and infra-coupled `claude-context` are intentionally excluded from default routing.
- Legacy graphify-first orchestration is not part of active routing.

## Install And Activation

Quick setup (core stack + hooks + wrappers):

```bash
git clone https://github.com/chimera-defi/token-reduce-skill tools/token-reduce-skill
./tools/token-reduce-skill/scripts/setup.sh
```

What `setup.sh` does automatically:

- installs/configures core tools (`qmd`, `rtk`) when possible
- runs initial QMD indexing for docs+code (`**/*.{md,txt,rst,py,sh,...}`), which can take longer on first run
- wires Claude hooks for prompt steering + pre-tool enforcement
- links global wrappers (`token-reduce-adaptive`, `token-reduce-paths`, `token-reduce-snippet`, `token-reduce-manage`)
- links the Codex skill and companion skills when present

Optional QMD scope overrides:

- `TOKEN_REDUCE_QMD_MASK`: explicit glob mask passed to `qmd collection add`
- `TOKEN_REDUCE_QMD_EXTENSIONS`: comma-separated extension list used to build the default mask
- `TOKEN_REDUCE_QMD_SEARCH_TIMEOUT_SECONDS`: cap runtime `qmd search` latency before falling back to scoped `rg` (default: `8` in runtime, `0` in benchmark/test contexts)

One-command measured activation (core-only default + validate):

```bash
git clone https://github.com/chimera-defi/token-reduce-skill tools/token-reduce-skill
./tools/token-reduce-skill/scripts/token-reduce-manage.sh activate-stack
```

Enable conditional companion install during activation:

```bash
TOKEN_REDUCE_ACTIVATE_EXTENDED_STACK=1 ./tools/token-reduce-skill/scripts/token-reduce-manage.sh activate-stack
```

Direct optional companion install surface:

```bash
TOKEN_REDUCE_INSTALL_EXTENDED_STACK=1 ./tools/token-reduce-skill/scripts/setup.sh
```

## Host Support

### Claude Code

```text
claude plugin marketplace add chimera-defi/token-reduce-skill
claude plugin install token-reduce@chimera-defi
```

### Codex

```bash
git clone https://github.com/chimera-defi/token-reduce-skill "$CODEX_HOME/skills/token-reduce"
```

Codex fresh-context handoff generator:

```bash
./tools/token-reduce-skill/scripts/token-reduce-manage.sh handoff-codex
```

### MCP

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

## Routing Model

Default first move:

```bash
token-reduce-adaptive <topic words>
```

Tier behavior:

- base: `token-reduce-paths`
- promote: `token-reduce-snippet` for clarification/repeat behavior
- promote: `token-reduce-structural` for symbol/impact queries when available
- recommendations: `context-mode` and `code-review-graph` only for matching task classes

Disable adaptive hinting if needed:

```bash
TOKEN_REDUCE_ADAPTIVE_HINT=0
```

## Benchmarks And Regression Guard

### Local benchmark (`references/benchmarks/local-benchmark.json`)

| Strategy | Tokens | vs broad inventory |
|----------|--------|--------------------|
| `broad_inventory` | `1826` | baseline |
| `guidance_scoped_rg` | `391` | `78.6%` saved |
| `qmd_files` | `309` | `83.1%` saved |
| `token_reduce_paths_warm` | `31` | `98.3%` saved |
| `token_reduce_snippet_warm` | `195` | `89.3%` saved |

### Composite benchmark (`references/benchmarks/composite-benchmark.json`)

| Strategy | Tokens | vs broad shell | Status |
|----------|--------|----------------|--------|
| `broad_shell` | `2355` | baseline | `ok` |
| `qmd_only` | `698` | `70.4%` saved | `ok` |
| `token_reduce_only` | `312` | `86.8%` saved | `quality-fail` |
| `token_savior_only` | `488` | `79.3%` saved | `ok` |
| `rtk_only` | `732` | `68.9%` saved | `ok` |
| `composite_stack` | `316` | `86.6%` saved | `ok` |

This confirms the active orchestration stack beats single-tool strategies that also pass quality checks.

### Release gate (anti-regression)

Use this for major change sets:

```bash
./scripts/token-reduce-manage.sh release-gate
```

It gates on:

- composite savings + quality
- adaptive savings + quality (with a small default overhead tolerance of `-2.0%` for benchmark noise)
- profile viability
- runtime reliability (`helper_error_rate`, failure overhead, retry overhead)

## Operational Commands

```bash
./scripts/token-reduce-manage.sh checkpoint
./scripts/token-reduce-manage.sh benchmark
./scripts/token-reduce-manage.sh benchmark-adaptive
./scripts/token-reduce-manage.sh benchmark-composite
./scripts/token-reduce-manage.sh benchmark-profiles
./scripts/token-reduce-manage.sh release-gate
./scripts/token-reduce-manage.sh sync-benchmarks
./scripts/token-reduce-manage.sh test-adaptive
./scripts/token-reduce-manage.sh validate
./scripts/token-reduce-manage.sh measure
./scripts/token-reduce-manage.sh review
./scripts/token-reduce-manage.sh doctor
```

`checkpoint` is the consistent maintenance harness: it runs release gate/validate/tests + local/global measure/review + workspace audit + dry-run telemetry sync and writes checkpoint artifacts under `artifacts/token-reduction/`.
`release-gate` automatically refreshes README benchmark token rows from the generated artifacts; `sync-benchmarks` can be run manually when needed.

Dependency checks:

- core only: `deps-check`, `deps-update`
- conditional companions: `deps-check-conditional`, `deps-update-conditional`

## Caveman Status

`caveman` is integrated as an optional companion, not forced globally.

- enable terse output when requested: `/caveman lite`
- compress memory file when requested: `/caveman:compress CLAUDE.md`

Default token-reduce routing/enforcement works with or without caveman.

## Learn More

- [references/INDEX.md](references/INDEX.md)
- [references/feature-matrix.md](references/feature-matrix.md)
- [references/tier-value-profile.md](references/tier-value-profile.md)
- [references/token-reduction-guide.md](references/token-reduction-guide.md)
- [references/composite-benchmark.md](references/composite-benchmark.md)
- [references/profile-presets.md](references/profile-presets.md)
- [references/prompt-stack-intake-2026-04-18.md](references/prompt-stack-intake-2026-04-18.md)
- [references/meta-learnings-2026-04-18.md](references/meta-learnings-2026-04-18.md)
- [references/meta-learnings-2026-04-19.md](references/meta-learnings-2026-04-19.md)
- [references/agent-setup.md](references/agent-setup.md)
- [references/workspace-integration.md](references/workspace-integration.md)
- [references/codex-handoff.md](references/codex-handoff.md)
- [references/caveman-evaluation.md](references/caveman-evaluation.md)
- [references/axi-evaluation.md](references/axi-evaluation.md)
- [references/token-savior-evaluation.md](references/token-savior-evaluation.md)
