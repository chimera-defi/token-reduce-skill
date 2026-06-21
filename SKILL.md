---
name: token-reduce
license: MIT
description: "Reduce repo context cost with QMD/helper discovery, scoped rg, targeted reads, concise summaries, and AI-delegate call batching."
triggers:
  - reduce context
  - token-reduce
  - find where code lives
  - large repo discovery
metadata:
  author: "GPT-5 Codex"
  category: "productivity"
  version: "5.6.1"
  argument_hint: "[file-or-directory]"
allowed-tools:
  - Read
  - Grep
  - Glob
  - Bash
---

# Token Reduction Skill

## Description

Use targeted retrieval and short summaries when paths are unknown, the repo is large, or the task spans multiple files. Skip exact-path tiny edits.

## Triggers

- The user asks to review, explore, search for context, or find where something lives.
- The user asks to validate, check, verify, improve, fix, or update a skill, hook, script, or file.
- The user's request implies the skill is not being used correctly or needs to work better.
- You do not know the exact file path yet.
- The task spans several files or areas of the repo.
- Broad scans or full-file reads would likely waste context.
- When maintaining this skill itself, the same narrow-discovery rules apply.

## Setup (First Invocation)

On first invocation in a new repo, if no config exists at `~/.claude/token-reduce-config.json`,
run `token-reduce-manage.sh setup` (or `token-reduce-manage.sh setup --non-interactive` in CI)
and relay the choices to the user via AskUserQuestion. Skip if config already exists.

## First Move

- If file location is unknown, start with one standalone discovery command:
  - `scripts/token-reduce-paths.sh topic words`
  - `scripts/token-reduce-snippet.sh topic words`
- If the exact symbol is already known and `token-savior` is installed, you may use:
  - `uv run python scripts/token-reduce-structural.py --project-root . find-symbol ExactSymbol`
  - `uv run python scripts/token-reduce-structural.py --project-root . change-impact ExactSymbol`
- Prefer `scripts/token-reduce-paths.sh` for the initial path-only kickoff.
- Prefer the structural helper only for exact symbol or dependency questions; do not use it as the default for vague repo discovery.
- Use `scripts/token-reduce-snippet.sh` only when the path list is not enough.
- Do not treat raw `qmd search` or raw `rg` as the first compliant move when the helper is available; those belong inside the helper workflow or as a narrow follow-up after helper output.
- Do not chain discovery commands with `||`, `&&`, `find`, `ls`, or extra fallback shell logic.
- Do not treat `rg --files .` as compliant discovery.
- Do not start with `find .`, `ls -R`, `grep -R`, or broad `Glob` patterns such as `**/*`.
- After two failed discovery attempts or once the candidate set exceeds 5 files, stop expanding and ask the user to narrow the scope.

## Heuristics

| Strategy | Measured Savings | When |
|----------|-----------------|------|
| Concise responses | 89% | Always |
| QMD BM25 search | 71–83% vs broad file listing (local/composite benchmarks); much higher vs reading file contents naively | Finding which files to read |
| Targeted reads | 33% | Large files |
| Parallel calls | 20% | Independent lookups |
| Caveman-style output profile (optional companion) | 20–65% output token reduction in upstream caveman benchmarks | When the user explicitly asks for extra brevity |
| AXI companion tools (optional) | Fewer turns in upstream AXI studies for GitHub/browser tasks | When work is primarily GitHub or browser automation |
| AI delegate router (`delegate-skill`) | Offload bounded side work while parent agent keeps critical-path orchestration and verification | Let the router pick the delegate: devin (browser/sandbox), kimi (cheap research/review), grok (large codebase), spark (local Codex write-mode) |
| Adaptive tier router | Auto-promotes/demotes helper tier from behavior and query intent; recommends context-mode, Headroom, or code-review-graph when matching companions are installed | Default first move when path is unknown (`token-reduce-adaptive`) |
| Context Mode companion (optional) | Up to ~98% reduction in output-heavy fixture comparisons | When tasks are dominated by huge tool payloads (logs, test output, API dumps) |
| Headroom companion (optional pilot) | 24-33% saved in local tool-result smoke tests; live proxy/MCP can reduce long-session tool context | When large tool results or old turns keep inflating the context and a verified Headroom proxy is already available |
| code-review-graph companion (optional) | 6x–10x token wins on larger-repo token-efficiency samples; can lose on tiny single-file diffs | Large monorepo review, dependency blast-radius, architecture impact tasks |

## Process

1. Check QMD once per session:
   ```bash
   command -v qmd >/dev/null 2>&1 && qmd collection list 2>/dev/null | head -1
   ```
   If unavailable, use scoped `rg`.
2. If you know the file or keyword, use a scoped grep first, then read only the needed lines.
3. If you need an auto-routed kickoff, use `scripts/token-reduce-adaptive.sh topic words`.
4. If you need a low-token path-only kickoff, use `scripts/token-reduce-paths.sh topic words`.
5. If you need one ranked excerpt after the kickoff, use `scripts/token-reduce-snippet.sh topic words`.
6. If a file is large, read only the relevant section.
7. If the search space stays broad, stop expanding and ask the user to narrow it.
8. For GitHub/browser-heavy execution, prefer `gh-axi` or `chrome-devtools-axi` over higher-overhead interfaces when available.
9. When routing behavior should be formally constrained, apply a profile (`minimal-load`, `balanced`, `max-savings`) via `token-reduce-manage.sh settings profile apply <name>`.

## Headroom Companion (Pilot)

Token-reduce remains the master router. Use helper-first discovery, scoped reads, QMD, RTK, and structural helpers before adding a proxy layer.

Use Headroom only when `headroom install status` or `/readyz` shows a healthy local proxy, telemetry is disabled, and the task has large tool payloads, repeated log/API/test outputs, or long-session context pressure. Do not use Headroom as the first move for unknown-path repo discovery. Do not enable `--learn` until memory writes are reviewed.

Two modes — pick based on payload size:

- **Passive proxy/wrap**: `headroom wrap claude` or `headroom wrap codex` — compresses old tool turns in flight. 24–33% reduction on tool-result-heavy workloads.
- **Active MCP compress** (>20k-token result): call `headroom_compress` directly on large blobs before reasoning over them.

| You see | Run |
|---------|-----|
| Tool result >20k tokens | `headroom_compress` (MCP) on that result |
| Healthcheck unclear | `headroom install status` |
| Proxy may be down | `curl -fsS http://127.0.0.1:8787/readyz` |
| Router nudged 3+ times, ignored | Run `headroom_compress` on largest pending result |

See `references/headroom-evaluation-2026-06-10.md` for evidence and rollback caveats.

## Subagent / gstack / Brain-First Hints

The adaptive router emits a subagent snippet when results >5 files or the query has broad-scope cues, a `/create-session` hint when sibling repos are named (with `gstack-session-spawn` installed), and a stderr brain-hint pointing at `qmd search` / `gbrain search` when either is on PATH. See: `references/subagent-and-brain-integration.md`.

## Structural backend (`token-savior`)

Optional, exact-symbol only — do not auto-install. Run `uv tool install token-savior` only when you need `find-symbol` / `change-impact` on a known symbol; the path helper covers >90% of discovery without it. See: `references/token-savior-evaluation.md` and `references/tier-value-profile.md`.

## Output-hook over-compression workaround

If a global PostToolUse hook compresses `pytest` output, redirect to a file and `Read` it: `pytest ... > /tmp/pytest.out 2>&1`. See: `references/known-issues.md`.

## QMD warm cache (H1)

Session-scoped read-through cache for QMD collection listings and first-page results (`scripts/qmd_warm_cache.py`, 10-min TTL, persisted under `.claude/token-reduce-state/qmd-cache/`). See: `references/architecture.md`.

## Output Brevity Profile (Companion)

When the user asks for tighter responses, apply a caveman-inspired **lite** profile:

- remove pleasantries, hedging, and filler
- keep technical terms exact
- keep code blocks, commands, and error text exact
- prefer short, direct statements over narrative framing

Do not force this style when clarity or safety would degrade. This is optional, not the default for every user.

## Success Criteria

- Discovery starts with QMD BM25 or scoped `rg`, not recursive shell scans.
- `scripts/token-reduce-search.sh` uses repo-scoped QMD first, then scoped `rg`.
- `rg --files .` and similar broad inventory commands are treated as violations.
- Reads stay targeted.
- Final summaries cite only the minimum files needed.
- Repo-level instructions and hooks point at the same first-move workflow.
- Owned-workspace changes that are more than trivial end on a feature branch with a PR for review and backup.

## QMD / GBrain note

Semantic QMD and GBrain memory are optional. Stay on BM25 (`qmd search`) for cheap discovery; switch to `qmd embed` + `qmd vsearch` only when the user asks or BM25 misses. Use GBrain for durable project memory, QMD for current-repo discovery — they do not share vectors. Full setup notes in `references/feature-matrix.md`.

## AI Delegate Call Reduction

Route delegation through the `delegate-skill` router (never hand-pick a delegate or call raw wrappers). Six tactics — batch, reference don't quote, constrain output, pre-compress context, never `&`, build envelope with `--print-envelope` — typically cut delegate token cost 40-70%. See: `references/delegate-call-reduction.md` for the full routing table, examples, and rules.

---
See `references/INDEX.md` for the full reference index.
