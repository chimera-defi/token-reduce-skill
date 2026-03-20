# token-reduce

Path-first repo discovery for Claude Code, Codex, and MCP-compatible clients.

token-reduce exists for one reason: broad repo exploration is cheap to type and expensive in context. This package pushes discovery toward the smallest useful output first, then expands only when the first answer is not enough.

## Token Reduction, First

Measured locally in this repo:

| Strategy | Tokens | Savings vs broad inventory | Duration |
|----------|--------|----------------------------|----------|
| `broad_inventory` | `92` | baseline | `8 ms` |
| `scoped_rg` | `44` | `52.2%` | `12 ms` |
| `token_reduce_paths` | `29` | `68.5%` | `33 ms` |
| `token_reduce_snippet` | `201` | `-118.5%` | `831 ms` |

What that means:

- the default win is the path-first kickoff
- the snippet helper is intentionally a follow-up path, not the default
- the benchmark is reproducible here with `uv run --with tiktoken scripts/benchmark-token-reduce.py`

The local artifact lives at `references/benchmarks/local-benchmark.json`.

This repo also preserves benchmark summaries from the larger source repo where the workflow was developed:

- concise responses: about `89%` fewer tokens
- QMD BM25 search vs naive multi-file reads: about `99%` fewer tokens
- targeted reads vs full reads: about `33%` fewer tokens

## Quickstart

Claude Code:

```text
/plugin marketplace add https://github.com/chimera-defi/token-reduce-skill
/plugin install token-reduce@chimera-defi
```

Codex:

```bash
git clone https://github.com/chimera-defi/token-reduce-skill "$CODEX_HOME/skills/token-reduce"
```

MCP clients:

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

## What You Get

- `scripts/token-reduce-paths.sh`: cheapest path-first discovery kickoff
- `scripts/token-reduce-snippet.sh`: one ranked excerpt after the path list
- `scripts/advise-token-reduction.py`: blocks broad Bash scans
- `scripts/enforce-glob-scope.py`: blocks broad Glob patterns
- `scripts/remind-token-reduce.py`: steers discovery onto the helper flow
- `mcp/server.mjs`: dependency-free MCP server for the same helper surface
- `.claude-plugin/`: Claude plugin packaging for `/plugin` install

## Why It Works

The workflow is intentionally simple:

1. Start with paths, not content.
2. Use QMD BM25 when available.
3. Fall back to scoped `rg`.
4. Add one ranked snippet only if the path list is not enough.
5. Block broad scans before they bloat context.

That is the product. Not a bigger search stack, not more agent narration, not more prompt stuffing.

## Proven Here

What is verifiable in this repo today:

- `SKILL.md` validates with `quick_validate.py`
- the helper scripts run successfully
- the MCP server initializes and exposes working tools
- the benchmark harness runs and writes a local artifact
- the QMD collection refreshes when Markdown files change, so results do not stay stale

Validate locally:

```bash
uv run --with pyyaml /root/.codex/skills/.system/skill-creator/scripts/quick_validate.py .
uv run --with tiktoken scripts/benchmark-token-reduce.py
./scripts/token-reduce-paths.sh "hook broad exploratory bash scans"
./scripts/token-reduce-snippet.sh "token reduction"
```

## Who It Is For

Use this when:

- file location is uncertain
- the repo is large enough that `find .` and `rg --files .` are noisy
- you want the same path-first workflow in Claude Code, Codex, and MCP clients
- you want host-side guardrails around repo exploration

Skip this when:

- the exact file path is already known
- the task is a small local edit
- you are trying to change Codex or Claude Code internals

## Important Boundary

This repo can improve your repo discovery workflow.
It cannot change Codex's own model-side behavior.

It also includes an optional Anthropic-only helper for developers who own their own Anthropic API payloads:

```bash
cat payload.json | node scripts/anthropic-cache-plan.mjs
```

That helper does **not** change Codex behavior and does **not** add caching to Claude Code's built-in sessions. It only helps when you control the Anthropic request payload yourself.

See `references/anthropic-prompt-caching.md` for details.

## Website

The single-page landing page lives in `docs/` and is intended for GitHub Pages or any static host.

## FAQ

### Does this always save tokens?

No. The path-first helper is the cheapest default. On a tiny repo, one ranked snippet can cost more than a plain file inventory.

### Does this require QMD?

No. QMD is preferred when available, but the workflow falls back to scoped `rg`.

### Does this hard-force skill use by itself?

No. Skills are advisory. Reliable behavior comes from repo instructions plus the prompt-submit and pre-tool hooks shipped here.
