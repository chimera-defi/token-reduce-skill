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

## What Makes It Different

**vs [RTK](https://github.com/rtk-ai/rtk):** RTK compresses command *output* after it runs — a great complement. token-reduce works upstream: it prevents expensive discovery commands from being issued in the first place. Use both for maximum savings.

**vs raw QMD:** token-reduce wraps QMD — when it's installed the helpers call it automatically; when it isn't, they fall back to scoped `rg`. Either way you call the skill helper, not the underlying tool directly.

**vs just writing better prompts:** Prompts don't block bad tool calls. Hooks do.

## Learn More

- [references/agent-setup.md](references/agent-setup.md) — Claude, Codex, and MCP setup details
- [references/workspace-integration.md](references/workspace-integration.md) — hook wiring for consumer repos
- [references/token-reduction-guide.md](references/token-reduction-guide.md) — benchmark notes and workflow details
- [references/architecture.md](references/architecture.md) — high-level system design

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
