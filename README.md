# token-reduce

![Claude Code](https://img.shields.io/badge/Claude%20Code-plugin-111111)
![Codex](https://img.shields.io/badge/Codex-skill-1f6feb)
![MCP](https://img.shields.io/badge/MCP-server-0a7f5a)
![MIT](https://img.shields.io/badge/license-MIT-lightgrey)

Make Claude Code and Codex last longer.

token-reduce is a workflow skill for AI coding tools. It cuts wasted context before and during implementation, so your agent spends more of its budget writing code and less of it wandering through the repo.

It is built for one goal:

> lower total token burn across a real coding task without making the model less useful

## Why People Install It

- longer Claude Code and Codex sessions before you hit limits
- less context pollution from broad scans and oversized reads
- more budget left for planning, writing code, and fixing bugs
- better odds that the agent stays fast and focused on the actual task

This is not just a search helper.
It is a workflow layer that helps the model discover, narrow, read, and then implement with less waste.

## How It Works

1. Start narrow.
   The agent gets candidate paths before it gets fat snippets or broad inventories.
2. Expand only when needed.
   If the path list is not enough, it can ask for one ranked excerpt.
3. Stay disciplined after discovery.
   Hooks and guidance push the agent away from broad scans and back toward targeted follow-up reads.

That matters because most coding tasks are not “just repo discovery.”
They are discovery plus planning plus editing plus verification.
If you waste context at the front of the task, the whole session gets worse.

## What Makes It Different

`qmd` is a strong search primitive.
RTK is useful for trimming noisy output.

token-reduce sits above both ideas.
It packages the workflow around them:

- it can use QMD under the hood
- it pushes the model toward a cheaper first move
- it adds host-side enforcement so the model actually uses the workflow more often
- it is designed for the full coding loop, not just one search command

## Results

Current local benchmark in this repo:

| Strategy | Tokens | Savings vs broad inventory | Duration |
|----------|--------|----------------------------|----------|
| `broad_inventory` | `259` | baseline | `8 ms` |
| `guidance_scoped_rg` | `25` | `90.3%` | `8 ms` |
| `qmd_files` | `132` | `49.0%` | `253 ms` |
| `token_reduce_paths_warm` | `132` | `49.0%` | `487 ms` |
| `token_reduce_snippet_warm` | `217` | `16.2%` | `732 ms` |

This is a small repo — the helper's savings are proportionally lower than on a large codebase. On the 642-file repo where this skill was developed, QMD BM25 search delivered ~99% fewer tokens than naive multi-file reads.

Routing also improved on the latest spot check:

- Claude: `3/3` correct on better-fit prompts, with exploratory tool paths blocked and redirected on `2/3`
- Codex: `3/3` correct, helper attempted on `2/3`, but routing is still weaker than Claude

Benchmarks and technical notes:

- [references/benchmarks/local-benchmark.json](references/benchmarks/local-benchmark.json)
- [references/benchmarks/script-speed.json](references/benchmarks/script-speed.json)
- [references/token-reduction-guide.md](references/token-reduction-guide.md)

## Install

Claude Code:

```text
/plugin marketplace add https://github.com/chimera-defi/token-reduce-skill
/plugin install token-reduce@chimera-defi
```

Using Codex or MCP, or want the host-specific setup details?
See [references/agent-setup.md](references/agent-setup.md).

## Learn More

- [references/architecture.md](references/architecture.md) for the high-level system design
- [references/agent-setup.md](references/agent-setup.md) for Claude, Codex, and MCP setup
- [references/workspace-integration.md](references/workspace-integration.md) for deeper repo wiring
- [references/token-reduction-guide.md](references/token-reduction-guide.md) for benchmark notes and workflow details

## FAQ

### Is this only for repo discovery?

No.
The point is to reduce total token burn across the whole coding task.
Discovery is where the waste usually starts, so that is where the workflow takes control first.

### Does this replace QMD or RTK?

No.
It can benefit from tools like QMD, and it is compatible with the broader idea behind RTK, but it is trying to solve the workflow problem around those tools, not just ship a single primitive.

### Does this always save tokens?

No.
On tiny repos, an exact scoped `rg` can still be cheapest.
The value is larger on longer sessions, larger repos, fuzzier prompts, and hosts that actually follow the workflow.

### Does this change model internals?

No.
It improves how the host gathers and spends context.
It does not change Codex or Claude model internals.
