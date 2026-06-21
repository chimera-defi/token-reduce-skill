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

Use Headroom only when `headroom --version` works, `headroom install status` or `/readyz` shows a healthy local proxy, telemetry is disabled, and the task has large tool payloads, repeated log/API/test outputs, or long-session context pressure.

Do not use Headroom as the first move for unknown-path repo discovery. Do not enable `--learn` until memory writes are reviewed against `MEMORY.md`, daily memory, and gbrain policy. If the OpenClaw installer emits obsolete plugin keys such as `startupTimeoutMs` or `gatewayProviderIds`, keep the manually verified config and do not rerun `headroom install apply --providers all`.

Preferred checks:

```bash
headroom install status
curl -fsS http://127.0.0.1:8787/readyz
```

There are two operating modes — pick the one that matches the payload size:

- **Passive proxy/wrap** (default): wrap `claude` or `codex` and let Headroom replay and compress old tool turns in flight. Local benchmarks show ~8% reduction on mixed sessions and 24–33% on tool-result-heavy workloads. Good for steady background pressure.
- **Active MCP compress** (>20k-token tool result): call the `headroom_compress` MCP action directly on large blobs (logs, payloads, transcripts, pytest output, API responses, big pastes) so they get summarized before they hit context. The adaptive router emits `headroom_compress`, `headroom install status`, and `curl -fsS http://127.0.0.1:8787/readyz` as copy-pasteable commands whenever it recommends Headroom, so the caller can run them without translation.

### Trigger cues (copy-paste, no translation)

If you see any of these patterns, run the corresponding command verbatim — no rewriting:

| You see | Run |
|---------|-----|
| Tool result >20k tokens (large API response, pytest output, log dump) | `headroom_compress` (MCP) on that result before reasoning over it |
| Healthcheck unclear | `headroom install status` |
| Proxy may be down | `curl -fsS http://127.0.0.1:8787/readyz` |
| Router already nudged but you ignored it 3+ times | Escalation kicks in (see `scripts/escalation.py`); run `headroom_compress` on the largest pending tool result |

The router emits these as literal commands in its rationale. Don't paraphrase — copy the exact string.

Read `references/headroom-evaluation-2026-06-10.md` for evidence and rollback caveats.

Measure Headroom adoption with `scripts/token-reduce-manage.sh measure` and `scripts/token-reduce-manage.sh review`; reports include `headroom_mentions`, `headroom_command_sessions`, `headroom_command_pct`, and recommendation conversion findings.

## Subagent + gstack Integration

When the helper returns more than five candidate files, or the query has broad-scope cues (`across`, `workspace`, `everywhere`, `all files`), the adaptive router emits `subagent_recommended: true` and a ready-to-copy `Agent(subagent_type="Explore", ...)` snippet. Delegating discovery to a subagent keeps the raw candidate set out of the main context — only the ranked summary returns. Use the emitted snippet directly instead of reading every candidate yourself.

When the query also names sibling repos or workspaces and the `gstack-session-spawn` skill is available, the router additionally emits a `/create-session` suggestion so each sibling repo gets its own dispatch.

If the query intent matches another skill (`review the PR` → `/review`, `fix the bug` → `/investigate`, `brainstorm` → `/brainstorm`), the router surfaces the matching skill in its rationale. Treat that as a routing hint, not an override.

## Brain-First Hint

When `qmd` or `gbrain` is on `PATH`, helper output prepends:

```
brain hits available — run `qmd search "<query>" -n 5 --files` before filesystem scan
```

Check semantic memory before a filesystem walk. If the brain returns relevant hits, you can skip the helper entirely.

## Structural backend (`token-savior`) — optional, exact-symbol only

The structural tier (`scripts/token-reduce-structural.py`) is powered by the optional [`token-savior`](https://github.com/Mibayy/token-savior) package. It is **optional**: install via `uv tool install token-savior` only when you actively need exact-symbol `find-symbol` / `change-impact` queries on a large repo.

- **Do not auto-install.** The router demotes the structural tier to path-only when the backend is missing, and that path-only result is good enough for >90% of discovery tasks.
- **When it helps:** exact symbol you can name (`StakingRouter.submit`), blast-radius / dependency-impact questions, monorepos where rg-only scope is too broad.
- **When to skip it:** vague topic discovery, prose searches, anything where you'd hesitate to type the exact symbol — `qmd search` and the path helper are cheaper.

See `references/tier-value-profile.md` for the full keep/conditional/excluded tier matrix.

## Output-hook over-compression workaround

Some sessions run a global `~/.claude/hooks` PostToolUse hook that compresses tool output and accidentally mangles `pytest` summaries ("No tests collected" or truncated pass/fail lines). This repo has no PostToolUse hook of its own — the offending hook lives outside the repo and is intentionally out of scope per the brief.

Workaround when running tests under a wrapped session:

```bash
uv run --with pytest python -m pytest scripts/tests/ -q > /tmp/pytest.out 2>&1
# then Read /tmp/pytest.out to inspect the full output without compression
```

Redirect to a file and `Read` the file rather than relying on stdout — the file path is not subject to in-flight tool-output compression. Logged as a cross-repo issue in the PR description so the global hook can be hardened separately.

## QMD warm cache (H1)

`scripts/qmd_warm_cache.py` exposes `QmdWarmCache`, a session-scoped read-through cache for QMD collection listings and first-page query results. Cache hits return immediately; misses fall through to the live QMD CLI and seed the cache. TTL is 10 minutes, scoped per session key, persisted under `.claude/token-reduce-state/qmd-cache/`. Target p95 hit latency: <300ms (empirically sub-millisecond in tests).

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

## AI Delegate Call Reduction (via the delegate-skill router)

Delegate *selection* goes through the `delegate-skill` router — do not hand-pick a delegate or hardcode one wrapper. The router maps the task to the right backend and keeps the parent context small (only the result summary returns):

| Task | Router picks | Wrapper |
|------|--------------|---------|
| Browser / UI / screenshot / sandbox | devin | `devin-delegate` |
| Cheap research / review / summarize / draft | kimi | `kimi-delegate` |
| Multi-file refactor / large codebase | grok | `grok-delegate` |
| Local Codex write-mode implementation | spark | `/spark` |
| Unknown scope | kimi to scope, then escalate | `kimi-delegate` |

For owned workspace projects, default to the PR-backed delegation workflow:

1. Keep the parent agent as orchestrator, integrator, and final verifier.
2. Pick the delegate with the `delegate-skill` router, not by hand. See `delegate-skill/SKILL.md` for the full routing table and health checks.
3. Always call the wrapper the router names (`devin-delegate`, `kimi-delegate`, `grok-delegate`, `/spark`) — never raw `devin`, raw `pi --provider kimi-coding`, or backgrounded delegate commands. Wrappers preserve envelope checks, fallback, and telemetry.
4. Give every delegate the workspace path, scope, constraints, acceptance checks, and expected output. Prefer batched questions and file references over pasted code.
5. For non-trivial owned-repo changes, stage only relevant files, run the repo's validation, push a feature branch, and open a PR so the work is backed up off the server.

The call-reduction tips below apply to whichever wrapper the router selects (written here as `<delegate>-delegate`). Orchestrator-to-subagent calls have fixed overhead (envelope, fallback wiring, telemetry). Reduce by:

### 1. Batch — 5 questions per call, not 1

```bash
# BAD: 5 calls × overhead
<delegate>-delegate --task "Check zero-value guard in submit()"
<delegate>-delegate --task "Check oracle replay protection"
...

# GOOD: 1 call, 5 questions, ~70% token savings
<delegate>-delegate --task "Answer CLEAN or FINDING+file:line for each:
Q1. StakingRouter.submit(): zero-value ETH guard?
Q2. reportModuleBeaconBalance: replay protection?
Q3-Q5. ..."
```

### 2. Reference, don't quote

```bash
# BAD (pastes 50 lines into prompt)
<delegate>-delegate --task "Review this: [code block]"

# GOOD (the delegate reads it itself — 30-70% cheaper)
<delegate>-delegate --task "Read OracleAdapter.sol:120-135. Does _validateSlashGuard
enforce a floor? CLEAN or FINDING."
```

### 3. Constrain output format

Append to every task: `"Answer CLEAN or FINDING+file:line. No preamble."` — cuts response tokens 40-60%.

### 4. Pre-compress context before delegating

```bash
./scripts/token-reduce-paths.sh "staking contracts" > /tmp/ctx.txt
<delegate>-delegate --task "..." --context-file /tmp/ctx.txt
```

### 5. Never background with `&` — use Agent tool for parallelism

`<delegate>-delegate ... 2>&1 &` writes to terminal FD, not the task output file.
Use `Agent(description=..., prompt="Use <delegate>-delegate ...")` instead.

### 6. Build the envelope with the wrapper to reduce in-model planning

```bash
# --print-envelope emits the structured plan; no per-skill script paths needed
<delegate>-delegate --print-envelope --task "audit X" > /tmp/envelope.txt
<delegate>-delegate --context-file /tmp/envelope.txt --task "execute the plan above"
```

Details: `references/meta-learnings-2026-05-31.md`
---
Read `references/token-reduction-guide.md` for benchmark notes and integration details.
Read `references/delegate-skill-integration.md` for how token-reduce integrates the delegate-skill router.
Read `references/companion-tools.md` for how to evaluate future companion backends.
Read `references/graphify-evaluation.md` for the graphify companion verdict.
Read `references/caveman-evaluation.md` for the caveman companion verdict.
Read `references/headroom-evaluation-2026-06-10.md` for the Headroom proxy/MCP pilot verdict.
Read `references/axi-evaluation.md` for the AXI companion verdict.
Read `references/prompt-stack-intake-2026-04-18.md` for the 10-dependency prompt-stack intake verdict and evidence.
Read `references/feature-matrix.md` for the complete feature/command/config/telemetry map.
Read `references/meta-learnings-2026-04-18.md` for validated integration lessons and guardrails.
Read `references/meta-learnings-2026-04-19.md` for QMD indexing/routing synchronization lessons and latency/adoption follow-ups.
Read `references/meta-learnings-2026-04-25.md` for telemetry-window interpretation and diagnostics normalization lessons.
Read `references/meta-learnings-2026-05-06.md` for telemetry-driven instrumentation and propagation workflow lessons.
Read `references/meta-learnings-2026-05-20.md` for docs fast-path routing and weekly maintenance automation lessons.
Read `references/tier-value-profile.md` for keep/conditional/excluded dependency-tier decisions.
