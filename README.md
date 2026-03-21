# token-reduce

![Claude Code](https://img.shields.io/badge/Claude%20Code-plugin-111111)
![Codex](https://img.shields.io/badge/Codex-skill-1f6feb)
![MCP](https://img.shields.io/badge/MCP-server-0a7f5a)
![MIT](https://img.shields.io/badge/license-MIT-lightgrey)

Make Claude Code and Codex last longer.

token-reduce keeps discovery and reading lean so your agent spends its budget writing code instead of wandering through the repo.

## Install

**Claude Code** (2 commands):

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

**Generic / self-hosted** (1 command):

```bash
git clone https://github.com/chimera-defi/token-reduce-skill tools/token-reduce-skill
```

Then point your repo instructions at `tools/token-reduce-skill/scripts/token-reduce-paths.sh`.

For hook wiring and deeper setup see [references/agent-setup.md](references/agent-setup.md).

## Results

Current local benchmark in this repo:

| Strategy | Tokens | Savings vs broad inventory | Duration |
|----------|--------|----------------------------|----------|
| `broad_inventory` | `259` | baseline | `8 ms` |
| `guidance_scoped_rg` | `25` | `90.3%` | `8 ms` |
| `qmd_files` | `132` | `49.0%` | `253 ms` |
| `token_reduce_paths_warm` | `132` | `49.0%` | `487 ms` |
| `token_reduce_snippet_warm` | `217` | `16.2%` | `732 ms` |

This is a small repo — savings scale up on larger codebases. On the 642-file repo where this skill was developed, QMD BM25 search delivered ~99% fewer tokens than naive multi-file reads.

Routing spot check:

- Claude: `3/3` correct, exploratory tools blocked and redirected on `2/3`
- Codex: `3/3` correct, helper attempted on `2/3`

Reproduce: `uv run --with tiktoken scripts/benchmark-token-reduce.py`

## How It Works

1. **Start narrow.** Agent gets candidate paths before snippets or broad inventories.
2. **Expand only when needed.** One ranked excerpt if the path list isn't enough.
3. **Stay disciplined.** Hooks push the agent away from broad scans after discovery.

Discovery is where context waste usually starts. Fixing the front of the task makes the whole session better.

## What Makes It Different

`qmd` is a strong BM25 search primitive. token-reduce wraps it — when QMD is installed the helpers call it automatically; when it isn't, they fall back to scoped `rg`. Either way you interact with the skill, not the underlying tool.

Beyond search, token-reduce adds host-side enforcement (hooks that block broad scans before they happen) and is designed for the full coding loop, not just one search command.

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

**Does this always save tokens?**
No. On tiny repos a scoped `rg` can be cheaper. Value scales with session length, repo size, and prompt fuzziness.

**Does this change model internals?**
No. It improves how the host gathers and spends context.
