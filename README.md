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

## What's New (2026-06-21)

PR #41 (Tracks A–L) added the following modules and behaviors. Entry points are listed for each so you can jump straight to the code.

- **`scripts/rank_paths.py`** — query-aware re-ranker for path-only helper output. Applied automatically in `scripts/token-reduce-paths.sh` (toggle off with `TOKEN_REDUCE_DISABLE_RANK=1`). Reads `artifacts/token-reduction/events.jsonl` to bias toward paths that previously satisfied the same query.
- **`scripts/cost_ledger.py`** — per-source token-savings ledger consumed by `review_token_reduction.py` and the operational benchmark report. F2 back-compat aliases (`avg_helper_tokens`, `avg_broad_tokens`) are annotated `# DELETE-BY: 2026-09-21`.
- **`scripts/escalation.py`** — closed-loop escalation kicks in when the router has been ignored ≥3 times in a session. Used by `enforce-token-reduce-first.py` and `token_reduce_adaptive.py`.
- **`scripts/coverage_patterns.py`** — advisory broad-pattern detection (unscoped `rg`, whole-dir `cat`, python `glob.glob`/`os.walk`, `xargs cat`). Folded into the enforce hook's warn-first/block-on-repeat policy.
- **`scripts/qmd_warm_cache.py`** — session-scoped read-through cache for QMD collection listings and first-page results. 10-min TTL, persisted under `.claude/token-reduce-state/qmd-cache/`.
- **`scripts/brain_hint.py`** — standalone `qmd`/`gbrain` discovery hint helper. Kept import-light (no `token_reduce_adaptive` import) so shell helpers pay no cold-start tax.
- **`scripts/command_rewrites.py`** — rewrite suggestions and `is_catastrophic` / `estimate_output_tokens` classifiers powering the enforce hook's block messages.

Enforcement gate is now **warn-first / block-on-repeat** (Track B): the first broad attempt in a session emits a `hook_warn` event and passes through; the second blocks. Catastrophic patterns (root-filesystem `find /`, full `rg --files .`) always hard-block on the first attempt.

## Dependency Suite (Feature)

`token-reduce` treats dependency integration as a first-class feature.
Instead of manually managing tool-by-tool setup, it installs/wires defaults and exposes conditional tiers explicitly.

### Core orchestrated stack

- [QMD](https://github.com/tobi/qmd): BM25 path/snippet retrieval
- [RTK](https://github.com/rtk-ai/rtk): output compression for executed commands
- token-reduce helpers/hooks: path/snippet/adaptive routing + enforcement

### Conditional companions

- [AXI](https://github.com/kunchenguid/axi) (`gh-axi`, `chrome-devtools-axi`) for GitHub/browser-heavy execution
- [`delegate-skill`](https://github.com/chimera-defi/delegate-skill) router for planner-first delegation — routes to devin (browser/sandbox), kimi (cheap research/review), grok (large codebase), or spark (local Codex write-mode) (standalone repo integration)
- [`token-savior`](https://github.com/Mibayy/token-savior) for exact symbol / impact acceleration
- [`context-mode`](https://github.com/mksglu/context-mode) for output-heavy payload sessions
- [`headroom`](https://github.com/chopratejas/headroom) as an optional pilot proxy/MCP layer for large tool-result and long-session context pressure; token-reduce remains the master router
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
- `TOKEN_REDUCE_QMD_REFRESH_TTL_SECONDS`: controls how often collection fingerprints are recomputed before refresh checks (default runtime: `900`)
- `TOKEN_REDUCE_QMD_SEARCH_TIMEOUT_SECONDS`: cap runtime `qmd search` latency before falling back to scoped `rg` (default: `8` in runtime, `0` in benchmark/test contexts)

Standalone companion integration (`delegate-skill` router — devin / kimi / grok / spark):

```bash
git clone https://github.com/chimera-defi/delegate-skill "$HOME/.claude/skills/delegate-skill"
./tools/token-reduce-skill/scripts/integrate-delegate-skill.sh
```

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

```bash
git clone https://github.com/chimera-defi/token-reduce-skill tools/token-reduce-skill
./tools/token-reduce-skill/scripts/setup.sh
```

The skill is then available as `/token-reduce` in any Claude Code session rooted in the repo.

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

#### Available MCP Tools

| Tool | Description |
|------|-------------|
| `token_reduce_paths` | Return the smallest useful candidate path list for a repo query |
| `token_reduce_snippet` | Return a path-first result plus one ranked excerpt |
| `token_reduce_benchmark` | Run the local token-reduction benchmark and return the summary table |
| `token_reduce_measure` | Measure recent token-reduce adoption and write fresh repo-local artifacts |
| `token_reduce_self_review` | Generate a telemetry-driven self-review with prioritised next improvements |
| `token_reduce_setup` | Return plugin and MCP install instructions for this repo |
| `token_reduce_full_setup` | Run one-command full setup (installs QMD + RTK, wires hook layers, indexes repo) |
| `anthropic_cache_plan` | Annotate Anthropic API payloads with `cache_control` and estimate repeated-call savings |

## Routing Model

Default first move:

```bash
token-reduce-adaptive <topic words>
```

Tier behavior:

- base: `token-reduce-paths`
- promote: `token-reduce-snippet` for clarification/repeat behavior
- promote: `token-reduce-structural` for symbol/impact queries when available
- recommendations: `context-mode`, `headroom`, and `code-review-graph` only for matching task classes

Disable adaptive hinting if needed:

```bash
TOKEN_REDUCE_ADAPTIVE_HINT=0
```

## Benchmarks And Regression Guard

### Local benchmark (`references/benchmarks/local-benchmark.json`)

| Strategy | Tokens | vs broad inventory |
|----------|--------|--------------------|
| `broad_inventory` | `1225` | baseline |
| `guidance_scoped_rg` | `221` | `78.5%` saved |
| `qmd_files` | `226` | `76.6%` saved |
| `token_reduce_paths_warm` | `228` | `76.2%` saved |
| `token_reduce_snippet_warm` | `354` | `63.7%` saved |

### Composite benchmark (`references/benchmarks/composite-benchmark.json`)

| Strategy | Tokens | vs broad shell | Status |
|----------|--------|----------------|--------|
| `broad_shell` | `1599` | baseline | `ok` |
| `qmd_only` | `680` | `57.5%` saved | `ok` |
| `token_reduce_only` | `389` | `75.7%` saved | `quality-fail` |
| `token_savior_only` | `213` | `86.7%` saved | `quality-fail` |
| `rtk_only` | `788` | `50.7%` saved | `ok` |
| `composite_stack` | `338` | `78.9%` saved | `quality-fail` |

This reports the current potential token-savings ceiling and flags quality failures honestly; do not treat quality-failing strategies as release-ready wins.

### Honest outcome reporting (anti-gaming)

Benchmark savings above are **potential ceiling** metrics only.
For realistic outcomes, run composite telemetry:

```bash
./scripts/token-reduce-manage.sh composite
```

The report now separates:

- `potential_savings_pct` from quality-passing composite benchmark artifacts
- `realized_savings_estimate_pct` discounted by observed helper usage + discovery compliance
- reliability penalties (error/retry overhead + latency)
- telemetry confidence (sample size + logging coverage quality)
- telemetry windows (`1d` and `14d`) so current behavior is not hidden by stale history

This prevents claiming benchmark-only wins when adoption/compliance or runtime stability are weak.

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
./scripts/token-reduce-manage.sh composite
./scripts/token-reduce-manage.sh doctor
```

`checkpoint` is the consistent maintenance harness: it runs release gate/validate/tests + local/global measure/review + workspace audit + dry-run telemetry sync and writes checkpoint artifacts under `artifacts/token-reduction/`.
`release-gate` automatically refreshes README benchmark token rows from the generated artifacts; `sync-benchmarks` can be run manually when needed.

Weekly automation (telemetry pull + skill improvement pass):

```bash
./scripts/install-token-reduction-cron.sh
```

This installs Monday cron entries for:

- `token-reduce-manage.sh self-improve`
- `token-reduce-manage.sh telemetry-sync`

Dependency checks:

- core only: `deps-check`, `deps-update`
- conditional companions: `deps-check-conditional`, `deps-update-conditional`

## Headroom Status

`headroom` is a conditional pilot companion for large tool-result payloads and long sessions where old tool output keeps inflating context.

- check health first: `headroom install status` or `curl -fsS http://127.0.0.1:8787/readyz`
- use selected wrapped sessions before global routing: `headroom wrap codex` or `headroom wrap claude`
- keep telemetry disabled and do not enable `--learn` until memory writes are reviewed
- measure adoption with `./scripts/token-reduce-manage.sh measure` and `review`; reports include `headroom_mentions`, `headroom_command_sessions`, `headroom_command_pct`, and recommendation conversion findings

Two operating modes:

- **passive proxy/wrap** (default): wrapping `claude`/`codex` lets Headroom replay and compress old tool turns in flight. Local benchmarks show ~8% reduction on mixed sessions and 24–33% on tool-result-heavy workloads.
- **active MCP `headroom_compress`** (>20k-token tool results): call the `headroom_compress` MCP action directly on large blobs (logs, payloads, transcripts, pytest output, API responses, big pastes). The adaptive router emits `headroom_compress`, `headroom install status`, and `curl -fsS http://127.0.0.1:8787/readyz` as ready-to-run commands whenever Headroom is recommended.

Default discovery still starts with token-reduce helpers. Headroom is for context pressure after the cheapest discovery and command-output paths are in place.

## Caveman Status

`caveman` is integrated as an optional companion, not forced globally.

- enable terse output when requested: `/caveman lite`
- compress memory file when requested: `/caveman:compress CLAUDE.md`

Default token-reduce routing/enforcement works with or without caveman.

## Learn More

- [references/INDEX.md](references/INDEX.md)
- [references/companion-tools.md](references/companion-tools.md)
- [references/delegate-skill-integration.md](references/delegate-skill-integration.md)
- [references/feature-matrix.md](references/feature-matrix.md)
- [references/tier-value-profile.md](references/tier-value-profile.md)
- [references/headroom-evaluation-2026-06-10.md](references/headroom-evaluation-2026-06-10.md)
- [references/token-reduction-guide.md](references/token-reduction-guide.md)
- [references/composite-benchmark.md](references/composite-benchmark.md)
- [references/profile-presets.md](references/profile-presets.md)
- [references/prompt-stack-intake-2026-04-18.md](references/prompt-stack-intake-2026-04-18.md)
- [references/meta-learnings-2026-04-18.md](references/meta-learnings-2026-04-18.md)
- [references/meta-learnings-2026-04-19.md](references/meta-learnings-2026-04-19.md)
- [references/meta-learnings-2026-04-25.md](references/meta-learnings-2026-04-25.md)
- [references/meta-learnings-2026-05-06.md](references/meta-learnings-2026-05-06.md)
- [references/meta-learnings-2026-05-20.md](references/meta-learnings-2026-05-20.md)
- [references/agent-setup.md](references/agent-setup.md)
- [references/workspace-integration.md](references/workspace-integration.md)
- [references/codex-handoff.md](references/codex-handoff.md)
- [references/caveman-evaluation.md](references/caveman-evaluation.md)
- [references/axi-evaluation.md](references/axi-evaluation.md)
- [references/token-savior-evaluation.md](references/token-savior-evaluation.md)
