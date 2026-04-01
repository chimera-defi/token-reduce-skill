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

**Quickest — full stack (QMD + RTK + hooks wired in one shot):**

```bash
git clone https://github.com/chimera-defi/token-reduce-skill tools/token-reduce-skill
./tools/token-reduce-skill/scripts/setup.sh
```

`setup.sh` installs [QMD](https://github.com/tobi/qmd) (BM25 path search) and [RTK](https://github.com/rtk-ai/rtk) (output compression), wires both sets of hooks into Claude Code globally, and indexes your repo. Re-run any time — it's idempotent.

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
| `broad_inventory` | `259` | baseline |
| `guidance_scoped_rg` | `25` | `90.3%` saved |
| `token_reduce_paths` | `132` | `49.0%` saved |
| `token_reduce_snippet` | `217` | `16.2%` saved |

Reproduce: `uv run --with tiktoken scripts/benchmark-token-reduce.py`

## Telemetry

token-reduce now logs direct helper and hook events under `artifacts/token-reduction/events.jsonl`, measures recent Claude/Codex session compliance, and can generate a self-review report with prioritized next improvements.

Useful commands:

```bash
./scripts/token-reduce-manage.sh benchmark
./scripts/token-reduce-manage.sh measure
./scripts/token-reduce-manage.sh review
./scripts/token-reduce-manage.sh telemetry
./scripts/token-reduce-manage.sh validate
```

Future agents should treat `measure` and `review` as part of the normal maintenance loop, not optional cleanup after the fact.

This is the self-improvement loop:

1. collect helper and hook events
2. measure actual session adoption and compliance
3. generate a review with the next routing, docs, or enforcement fixes
4. rerun after changes

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

## Dependencies And Attribution

token-reduce is intentionally composite. It combines:

- [QMD](https://github.com/tobi/qmd) for BM25 path and snippet retrieval
- [RTK](https://github.com/rtk-ai/rtk) for command-output compression
- [`token-savior`](https://github.com/Mibayy/token-savior) as an optional structural accelerator for exact symbol and dependency questions
- Anthropic prompt-caching guidance as an optional API-layer companion, documented in [references/anthropic-prompt-caching.md](references/anthropic-prompt-caching.md)

Direct runtime dependencies:
- `qmd`
- `rtk`
- the token-reduce helper, hook, telemetry, and MCP runtime in this repo

Optional companions:
- `token-savior`
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
- [scripts/smoke-test-workspace.sh](scripts/smoke-test-workspace.sh) — verify the global helper across local repos

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
