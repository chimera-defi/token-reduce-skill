# token-reduce

![Claude Code](https://img.shields.io/badge/Claude%20Code-plugin-111111)
![Codex](https://img.shields.io/badge/Codex-skill-1f6feb)
![MCP](https://img.shields.io/badge/MCP-server-0a7f5a)
![MIT](https://img.shields.io/badge/license-MIT-lightgrey)

Make Claude Code and Codex last longer by keeping discovery lean.

Most context waste in a coding session happens at the front — the agent scans the whole repo before it writes a single line. token-reduce fixes that: it guides the agent to the smallest useful context first, then expands only when needed.

> **Agents:** read [`llms.txt`](./llms.txt) for a self-contained install + usage guide.

## Agent Install

Paste this into your agent chat and it will install itself:

```
Read https://raw.githubusercontent.com/chimera-defi/token-reduce-skill/main/llms.txt and follow the install instructions.
```

That's it. The agent reads `llms.txt`, runs `setup.sh`, and starts enforcing lean discovery automatically.

---

## Manual Install

**Quickest — full stack (QMD + RTK + hooks + AXI companions wired in one shot):**

```bash
git clone https://github.com/chimera-defi/token-reduce-skill tools/token-reduce-skill
./tools/token-reduce-skill/scripts/setup.sh
```

`setup.sh` installs [QMD](https://github.com/tobi/qmd) (BM25 path search), [RTK](https://github.com/rtk-ai/rtk) (output compression), and AXI companion CLIs (`gh-axi`, `chrome-devtools-axi`), wires hooks into Claude Code globally, indexes your repo, and prompts telemetry opt-in during install. Re-run any time — it's idempotent.

It also:
- links `token-reduce-paths`, `token-reduce-snippet`, and related wrappers into `~/.local/bin`
- links the Codex skill into `$CODEX_HOME/skills/token-reduce`

---

**Claude Code plugin** (2 commands):

```text
claude plugin marketplace add chimera-defi/token-reduce-skill
claude plugin install token-reduce@chimera-defi
```

**Codex** (1 command):

```bash
git clone https://github.com/chimera-defi/token-reduce-skill "$CODEX_HOME/skills/token-reduce"
```

**MCP** (add to your MCP config):

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

For hook wiring details see [references/agent-setup.md](references/agent-setup.md).

## How It Works

```
Without token-reduce:                 With token-reduce:

Agent  --"find auth logic"-->         Agent  --"find auth logic"-->
  broad scan: rg --files .              token-reduce-paths.sh "auth"
  cat 8 files into context              QMD BM25 → 2 candidate paths
  ~52,000 tokens                        targeted read of those 2 files
                                        ~500 tokens   (99% less)
```

1. **Start narrow.** Helpers return candidate paths before any file content lands in context.
2. **Expand only when needed.** One ranked excerpt if the path list isn't enough.
3. **Stay disciplined.** Hooks block broad scans before they happen — not after.

## Results

Savings from the source repo (642 files) where this skill was developed:

| Strategy | Measured Savings |
|----------|-----------------|
| Concise responses | ~89% fewer tokens |
| QMD BM25 path kickoff vs naive multi-file reads | ~99% fewer tokens |
| Targeted reads vs full-file reads | ~33% fewer tokens |

Local benchmark in this repo (small — scales up on larger codebases):

| Strategy | Tokens | vs broad inventory |
|----------|--------|--------------------|
| `broad_inventory` | `346` | baseline |
| `guidance_scoped_rg` | `92` | `73.4%` saved |
| `qmd_files` | `146` | `57.8%` saved |
| `token_reduce_paths_warm` | `146` | `57.8%` saved |
| `token_reduce_snippet_warm` | `233` | `32.7%` saved |

Reproduce: `uv run --with tiktoken scripts/benchmark-token-reduce.py`

Composite benchmark in this repo (quality-gated mixed workload):

| Strategy | Tokens | vs broad shell | Status |
|----------|--------|----------------|--------|
| `broad_shell` | `1033` | baseline | `ok` |
| `qmd_only` | `313` | `69.7%` saved | `quality-fail` |
| `token_reduce_only` | `374` | `63.8%` saved | `quality-fail` |
| `token_savior_only` | `621` | `39.9%` saved | `ok` |
| `rtk_only` | `595` | `42.4%` saved | `ok` |
| `composite_stack` | `340` | `67.1%` saved | `ok` |

In this run, `composite_stack` beat every single-tool strategy that also passed quality checks (`broad_shell`, `token_savior_only`, `rtk_only`).
See [references/composite-benchmark.md](references/composite-benchmark.md) for methodology and caveats.

## Telemetry

token-reduce now supports a composite telemetry loop:

- direct helper and hook events (`artifacts/token-reduction/events.jsonl`)
- Claude/Codex session adoption + discovery-compliance measurement
- RTK companion inputs (gain/discover/session/hook-audit) for downstream output-compression signal
- install/wiring health checks (binary availability + Claude/Codex hook binding)

Telemetry upload remains **opt-in** for install-level improvement tracking.

Useful commands:

```bash
./scripts/token-reduce-manage.sh benchmark
./scripts/token-reduce-manage.sh composite
./scripts/token-reduce-manage.sh benchmark-composite
./scripts/token-reduce-manage.sh deps-check
./scripts/token-reduce-manage.sh deps-update
./scripts/token-reduce-manage.sh measure
./scripts/token-reduce-manage.sh measure-global
./scripts/token-reduce-manage.sh review
./scripts/token-reduce-manage.sh review-global
./scripts/token-reduce-manage.sh telemetry
./scripts/token-reduce-manage.sh doctor
./scripts/token-reduce-manage.sh settings show
./scripts/token-reduce-manage.sh settings onboard
./scripts/token-reduce-manage.sh settings set telemetry.enabled true
./scripts/token-reduce-manage.sh settings set telemetry.endpoint https://example.com/ingest
./scripts/token-reduce-manage.sh telemetry-sync
./scripts/token-reduce-manage.sh updates
./scripts/token-reduce-manage.sh auto-update
./scripts/token-reduce-manage.sh self-improve
./scripts/token-reduce-manage.sh workspace-audit
./scripts/token-reduce-manage.sh validate
```

Future agents should treat `measure` and `review` as part of the normal maintenance loop, not optional cleanup after the fact.

This is the self-improvement loop:

1. collect helper and hook events
2. run composite telemetry to include RTK + wiring health input
3. measure actual session adoption and compliance
4. generate a review with the next routing, docs, or enforcement fixes
5. rerun after changes

Recent telemetry also reports optional companion adoption, including caveman command activation and AXI tool usage rates.

### Opt-In Telemetry

Telemetry upload is disabled by default. When enabled, token-reduce sends anonymized summary metrics only (no file contents):

- helper/adoption/compliance percentages
- 14-day event counts
- workspace-level adoption summary

Enable and configure:

```bash
./scripts/token-reduce-manage.sh settings onboard
./scripts/token-reduce-manage.sh settings set telemetry.enabled true
./scripts/token-reduce-manage.sh settings set telemetry.endpoint https://your-endpoint.example/ingest
./scripts/token-reduce-manage.sh settings set telemetry.api_key your-shared-key
./scripts/token-reduce-manage.sh settings set telemetry.signing_secret your-hmac-secret
./scripts/token-reduce-manage.sh telemetry-sync
```

Receive metrics (local ingest service example):

```bash
uv run scripts/token-reduce-telemetry-receiver.py --host 0.0.0.0 --port 8787 --path /ingest --api-key your-shared-key --signing-secret your-hmac-secret
./scripts/token-reduce-manage.sh settings set telemetry.endpoint http://127.0.0.1:8787/ingest
./scripts/token-reduce-manage.sh telemetry-sync
```

### Updates And Auto-Update

token-reduce can check for new commits and optionally fast-forward itself when safe:

```bash
./scripts/token-reduce-manage.sh updates
./scripts/token-reduce-manage.sh settings set updates.auto_update true
./scripts/token-reduce-manage.sh auto-update
./scripts/token-reduce-manage.sh deps-check
./scripts/token-reduce-manage.sh deps-update
./scripts/token-reduce-manage.sh doctor
```

`auto-update` only runs when the worktree is clean and can fast-forward.

## Optional Structural Accelerator

`token-reduce` can also consume [`token-savior`](https://github.com/Mibayy/token-savior) as an optional companion for exact symbol lookup and change-impact questions.

Install it only if you want the structural helper:

```bash
git clone https://github.com/Mibayy/token-savior /tmp/token-savior-bench
cd /tmp/token-savior-bench
uv sync --extra mcp
```

Use it only when the exact symbol is already known:

```bash
uv run python scripts/token-reduce-structural.py --project-root . find-symbol discovery_hint
uv run python scripts/token-reduce-structural.py --project-root . change-impact prompt_requires_helper
```

Do not use it as the default first move for vague repo discovery. For that, keep using:

```bash
./scripts/token-reduce-paths.sh topic words
```

Measured in this repo: `token-savior` cut exact symbol lookup from `234` tokens to `56`, but broad-topic search quality was worse even when raw output was shorter. See [references/token-savior-evaluation.md](references/token-savior-evaluation.md).

## Optional Brevity + Memory Companion

`token-reduce` can also pair with [`caveman`](https://github.com/JuliusBrussee/caveman) for two optional layers outside helper routing:

- output-side compression (`/caveman lite|full|ultra`) when you explicitly want terse agent responses
- input-side memory compression (`/caveman:compress CLAUDE.md`) to shrink always-loaded memory files

Use this as a companion, not a replacement:

- `token-reduce` still owns discovery discipline, hook enforcement, and targeted file-context routing
- `caveman` is for response style and memory-file compression workflows

See [references/caveman-evaluation.md](references/caveman-evaluation.md) for integration verdict and evidence.

## Optional AXI Companion (Agent-Native Tool Interfaces)

`token-reduce` can also pair with [AXI](https://github.com/kunchenguid/axi) companion CLIs to reduce turns/retries when tasks are GitHub- or browser-heavy:

- `gh-axi` for GitHub operations
- `chrome-devtools-axi` for browser automation

These tools are optional and do not replace token-reduce helper-first routing.
Use them when the task is clearly in their domain; keep discovery kickoff discipline unchanged.

See [references/axi-evaluation.md](references/axi-evaluation.md) for validation notes and integration policy.

## Dependencies And Attribution

token-reduce is intentionally composite. It combines:

- [QMD](https://github.com/tobi/qmd) for BM25 path and snippet retrieval
- [RTK](https://github.com/rtk-ai/rtk) for command-output compression
- [`token-savior`](https://github.com/Mibayy/token-savior) as an optional structural accelerator for exact symbol and dependency questions
- [`caveman`](https://github.com/JuliusBrussee/caveman) as an optional response-style and memory-compression companion
- [AXI](https://github.com/kunchenguid/axi) plus `gh-axi` and `chrome-devtools-axi` as optional agent-native tool companions for GitHub/browser workflows
- Anthropic prompt-caching guidance as an optional API-layer companion, documented in [references/anthropic-prompt-caching.md](references/anthropic-prompt-caching.md)

Direct runtime dependencies:
- `qmd`
- `rtk`
- the token-reduce helper, hook, telemetry, and MCP runtime in this repo

Optional companions:
- `token-savior`
- `caveman`
- `gh-axi` / `chrome-devtools-axi`
- Anthropic API prompt-caching workflows

The design goal is explicit:
- token-reduce remains the reliable control plane
- companion tools stay behind task-specific routing rules
- no single dependency replaces the helper-first workflow by default

## What Makes It Different

**vs [RTK](https://github.com/rtk-ai/rtk):** RTK compresses command *output* after it runs — a great complement. token-reduce works upstream: it prevents expensive discovery commands from being issued in the first place. Use both for maximum savings.

**vs raw QMD:** token-reduce wraps QMD — when it's installed the helpers call it automatically; when it isn't, they fall back to scoped `rg`. Either way you call the skill helper, not the underlying tool directly.

**vs just writing better prompts:** Prompts don't block bad tool calls. Hooks do.

## Learn More

- [references/agent-setup.md](references/agent-setup.md) — Claude, Codex, and MCP setup details
- [references/workspace-integration.md](references/workspace-integration.md) — hook wiring for consumer repos
- [references/token-reduction-guide.md](references/token-reduction-guide.md) — benchmark notes and workflow details
- [references/architecture.md](references/architecture.md) — high-level system design
- [references/companion-tools.md](references/companion-tools.md) — how companion tools are evaluated
- [references/token-savior-evaluation.md](references/token-savior-evaluation.md) — measured integration verdict
- [references/caveman-evaluation.md](references/caveman-evaluation.md) — optional output + memory companion verdict
- [references/axi-evaluation.md](references/axi-evaluation.md) — optional AXI companion verdict
- [references/composite-benchmark.md](references/composite-benchmark.md) — quality-gated composite vs single-tool benchmark
- [references/self-improving-harness.md](references/self-improving-harness.md) — opt-in telemetry, updates, and self-improve loop
- [scripts/smoke-test-workspace.sh](scripts/smoke-test-workspace.sh) — verify the global helper across local repos
- [scripts/audit_workspace_skills.py](scripts/audit_workspace_skills.py) — verify install/adoption signals across sibling repos

## FAQ

**Is this only for repo discovery?**
No. Discovery is where waste usually starts, but the workflow covers the full coding loop.

**Does this replace QMD?**
For day-to-day use, yes — you call the skill helpers, not `qmd` directly. QMD is an optional dependency that improves search quality; the skill falls back to `rg` if it isn't installed.

**Does this replace RTK?**
No — they're complementary. [RTK](https://github.com/rtk-ai/rtk) trims the output of commands that run. token-reduce prevents costly commands from running at all. Running both gives you savings at both ends.

**Does this always save tokens?**
No. On tiny repos a scoped `rg` can be cheaper. Value scales with session length, repo size, and prompt fuzziness.

**Does this change model internals?**
No. It improves how the host gathers and spends context.
