# token-reduce Architecture

This repo is valuable when an agent does not know where an answer lives yet.
Instead of paying for a broad repo inventory up front, it pushes discovery through a smaller sequence:

1. get candidate paths
2. read one snippet only if needed
3. do targeted follow-up reads

That reduces wasted context and makes host behavior more predictable.

## System Model

`token-reduce` has four layers:

| Layer | What it does | Files |
|------|---------------|-------|
| Guidance | Tells the host when path-first discovery is worth using | `SKILL.md`, `README.md`, `references/token-reduction-guide.md` |
| Retrieval helpers | Return the smallest useful search result first | `scripts/token-reduce-paths.sh`, `scripts/token-reduce-snippet.sh`, `scripts/token-reduce-search.sh` |
| Host enforcement | Blocks broad discovery patterns and pushes the host back to the helper flow | `scripts/remind-token-reduce.py`, `scripts/enforce-token-reduce-first.py`, `.claude/settings.json` |
| Integration surfaces | Make the same workflow usable from different hosts | `.claude-plugin/`, `mcp/server.mjs`, `agents/openai.yaml` |

## Request Flow

For an ambiguous repo question, the intended path is:

1. The host sees a repo-discovery style prompt.
2. A prompt hook adds guidance telling the host to start with `token-reduce-paths.sh`.
3. If the host tries a broad exploratory tool path instead, pre-tool hooks block it.
4. The helper returns candidate files, ideally as a path list only.
5. If the path list is not enough, the host can ask for one ranked snippet.
6. After that, the host should switch to exact-file `Read` or a narrow `Grep`.

The goal is not "never search." The goal is "pay for the cheapest useful search result first."

## Why The Wrapper Exists

Users could call raw QMD or narrow `rg` directly. The wrapper still matters because it bundles:

- a consistent path-first default
- a ranked snippet follow-up
- repo-local QMD collection management
- stale-index refresh when Markdown docs change
- host hooks that push the agent back onto the intended flow

In other words, the value is not just a shell command. It is the workflow plus the enforcement.

## Host-Specific Behavior

### Claude

Claude can be steered and partially enforced with hooks:

- `UserPromptSubmit` adds the path-first reminder
- `PreToolUse` blocks exploratory `Bash`, `Glob`, `Grep`, and pending `Read` paths before the helper runs

This makes Claude much more likely to pivot to the helper, but host approval settings still matter for redirected `Bash` calls.

### Codex

Codex can use the same helper scripts and repo instructions, but it does not have the same Claude hook surface in this repo. That means the helper flow is available and documented, but routing is weaker unless the host adds equivalent enforcement.

### MCP Clients

MCP clients do not need shell glue in the prompt. They can call:

- `token_reduce_paths`
- `token_reduce_snippet`
- `token_reduce_benchmark`
- `token_reduce_install_info`

through `mcp/server.mjs`.

## What The Benchmarks Mean

There are two different benchmark stories in this repo:

- output-size benchmarks: how much text the helper returns compared with broader discovery
- host-behavior checks: whether Claude or Codex actually start with the intended workflow

Those are related, but not identical.
The helper can be efficient while the host still ignores it.

## Limits

- If the exact file is already known, `token-reduce` adds little value.
- On tiny repos, exact scoped `rg` can beat the helper.
- Snippet mode is intentionally more expensive and should be a second step.
- This repo improves discovery workflow; it does not change Codex model internals.

## Telemetry Loop

The repo now has a direct telemetry and self-review loop:

- helper wrappers append repo-local events to `artifacts/token-reduction/events.jsonl`
- session measurement still parses Claude and Codex history for adoption/compliance
- `review_token_reduction.py` converts the latest evidence into prioritized next fixes

That means the skill can do more than claim savings. It can inspect whether it is actually being used, where routing is weak, and which improvements should be made next.

## Read Next

- `README.md`
- `references/token-reduction-guide.md`
- `references/workspace-integration.md`
