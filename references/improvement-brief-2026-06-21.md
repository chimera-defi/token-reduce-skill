# Token-Reduce Improvement — Master Brief (2026-06-21)

You are an Opus session spawned by a Sonnet orchestrator to execute this brief
inside the `token-reduce-skill` repo. The orchestrator already did discovery and
plan iteration with the human. **Your job: build it.** The orchestrator will
review your PR before handoff to the human.

## Hard guardrails (do not violate)

- Work on the feature branch you were spawned on (already a session/* branch).
- Open **one** PR against `main`. **DO NOT merge. DO NOT force-push. DO NOT push to `main`.**
- Stay inside this repo (`token-reduce-skill`). Do not touch `~/.claude/skills/*`,
  other workspace repos, or gstack tooling.
- **TDD**: every track is a test commit first (watch it fail), then impl commit.
  Run the suite with `python3 -m pytest scripts/tests/ -q`. If output looks
  truncated (the output hook can mangle it), redirect to a file and Read it.
- Commit per logical unit. Conventional commit message + `[Agent: <name>]`
  attribution trailer (this repo's CI checks format + attribution).
- No secrets, no runtime junk (`__pycache__`, `artifacts/*.jsonl`, symlinks).
- Use `token-reduce` for your own discovery. Dogfood the skill.

## Context (verified by orchestrator)

- Current global telemetry: 185 sessions / 27 runtime events / 14d, health 84.8.
- Broad scans still attempted in **79 sessions** — gate leakage.
- Discovery **direct_hit only 14.6%** — the *real* lever; ranking quality
  matters more than enforcement.
- Helper p95 2237ms (qmd_ensure 1213ms dominates).
- Headroom: mentioned 18.0%, used 0.5%; router fired it only 2× in 183 sessions.
- Caveman converts mention→use at 6% — the model to copy.

## Reframe (core insight from plan iteration)

The gate is potentially **negative-EV**: a blocked broad command costs tokens on
the failed attempt + verbose block message + retry decision. If that exceeds
helper savings, enforcement hurts. So:

- Make mistakes cheap and the helper rewarding, not enforce harder.
- Ranking quality is the real prize — agents reach for the helper organically
  when the first 3 paths are right.
- Hard-block only catastrophic patterns; soften everything else to advisory.

## Master plan — 8 tracks, single PR, TDD, no deferrals

### Track A — Ranking quality (highest ROI)

Target: direct_hit 14.6% → 50%+.

- **A1**. Git-recency weighting (log-decay over 90d) in `token_reduce_paths.sh` /
  the path-ranking helper. Recent commits float to top.
- **A2**. Symbol-match boost: if query token matches a defined function/class
  name in a candidate file, boost it.
- **A3**. Path-relevance demotion: tests/fixtures/vendored demoted unless query
  mentions them.
- **A4**. Query expansion: split multi-word queries into individual terms +
  bigrams, prune stopwords.
- **A5**. Click-through learning: telemetry adds `file_read_after_helper` event;
  per-repo cache uses it as a prior for identical/similar queries.

Tests: representative queries with expected top-3 paths. Add a fixture corpus
under `scripts/tests/fixtures/ranking/`.

### Track B — Gate → Guide (kill token bloat from failed commands)

- **B1**. Auto-rewrite suggestions in block messages: `find . -name "*.py"` →
  message includes ready-to-copy `rg -g '*.py' --files`.
- **B2**. One-line block messages. Current multi-paragraph is part of the cost.
- **B3**. **Tighter-variant policy** (human-approved):
  - Hard block always: `find /`, `ls -R /`, `rg --files .` at repo root.
  - First broad attempt in a session: **warn + measure**, allow command through.
  - Repeat broad attempt in same session: **block** with the warn-history
    referenced.
  - Use `token_reduce_state` session-key tracking; add a "broad_attempt_count"
    counter.
- **B4**. Cost-aware telemetry: log token cost of `block → retry` chains vs
  helper-direct; surface in review as "enforcement cost".
- **B5**. Pre-flight estimate on borderline commands: append "estimated output:
  ~Xk tokens; cheaper: `<helper>`" without blocking.

### Track C — Coverage (close 79 leakage sessions, advisory not block)

- **C1**. New detection patterns in **both** `enforce-token-reduce-first.py`
  and `measure_token_reduction.py` (keep them in sync — this is the key bug):
  - Unscoped `rg <pattern>` (no `-g`, no path arg).
  - `cat/head/tail/wc <dir>/*` whole-dir reads.
  - Python `glob.glob`/`os.walk` invocations via `python -c`.
  - `xargs cat` chains.
  - These fire **advisory** (per B3), counted toward measure.

### Track D — Headroom + companion funnels (brief #1, #8)

- **D1**. Actionable headroom: router emits exact commands —
  `headroom_compress`, `headroom install status`, `curl -fsS http://127.0.0.1:8787/readyz` —
  not prose.
- **D2**. Widen triggers: `tool_result`, `transcript`, `log dump`, `pytest output`,
  `api response`, `paste`. Keep plain-query control returning
  `headroom_recommended: false`. Test matrix.
- **D3**. Doc clarity in SKILL.md + README.md: passive proxy auto-compresses
  ~8%; use active MCP `headroom_compress` for big one-shot tool results
  (>20k tokens).
- **D4**. Per-companion conversion funnel in `review_token_reduction.py`:
  mention → recommended → used → estimated savings, for headroom, caveman,
  context_mode, code_review_graph, axi. New review section.

### Track E — Subagent + gstack integration

- **E1**. Subagent-dispatch recommendation: when helper returns >5 candidates
  OR query has broad-scope cues ("across the workspace", "everywhere",
  "all files"), router emits `subagent_recommended: true` with a ready-to-copy
  `Agent(subagent_type=Explore, ...)` snippet. SKILL.md adds the pattern with
  rationale (keeps raw candidate set out of main context).
- **E2**. gbrain-first hint: if `qmd` or `gbrain` CLIs are available, helper
  output prepends one line: `brain hits available — run \`qmd search "<query>"\`
  or check gbrain before filesystem scan`.
- **E3**. session-spawn escalation: if `gstack-session-spawn` skill is
  detectable (skill name in available-skills listing — Opus has it) AND scope
  is multi-repo (cues: "across workspace", "all sibling repos"), router emits
  a `/create-session` suggestion.
- **E4**. Sibling-skill routing: if query intent matches a different skill
  (e.g., "review PR" → `/review`, "fix bug" → `/investigate`), surface the
  skill name with one-line rationale.

### Track F — Cost ledger (with vs without measurement)

- **F1**. Per-session estimated tokens saved when helper ran vs estimated
  tokens spent on broad-scan sessions. Use existing benchmark coefficients
  in `references/benchmarks/`.
- **F2**. Per-source aggregate (claude/codex): avg context size, helper-used
  vs broad-scan. New review section "Context Impact".

### Track G — Closed-loop tuning

- **G1**. Behavior-profile escalation: if a session ignores recommendation N
  times (track via `helper_recommended_ignored` event), escalate to stronger
  nudge or trigger auto-compress (route through headroom_compress).
- **G2**. Mention→use lift: SKILL.md adds caveman-style concrete trigger cues
  + ready-to-copy examples right at the recommendation point.

### Track H — Brief leftovers (no deferrals)

- **H1**. Warm/persist QMD index across helper invocations. Cache the qmd
  collection list + first-page results per session. Target p95 <300ms.
- **H2**. Explicit `token_savior` gating decision documented in SKILL.md +
  references/: "optional, install via `uv tool install token-savior`; only
  needed for exact-symbol change-impact queries". Don't auto-install.
- **H3**. Fix output-hook over-compression of pytest output ("No tests
  collected" mangling). Find the hook (likely in `scripts/` or `~/.claude/`
  via a local detection — DO NOT modify global `~/.claude/hooks` since brief
  forbids touching outside this repo; **fix the repo-local interception**
  only). Preserve pass/fail summaries. If the offending hook is global and
  unreachable from this repo, document the workaround (redirect output to
  file, Read the file) in SKILL.md and skip the hook fix — log this as a
  cross-repo issue in the PR description.

## Execution order

Ranking first (A), then B/C together (gate softening + coverage), then D
(headroom), then E (subagent + gstack), then F (cost ledger — depends on
events from earlier tracks), G (escalation — depends on behavior profile),
H last.

## Delegation guidance

Use the `delegate-skill` router (per repo's `SKILL.md` lines 165–238) for
bounded side work. **Do not hand-pick a delegate.** Suggested routing:

- **Heavy ranking algorithm work** → `spark` (local Codex write-mode).
- **Repeated cross-file edits across `enforce-token-reduce-first.py` +
  `measure_token_reduction.py`** → `grok-delegate` (multi-file refactor).
- **Independent review of a track's diff before commit** → `kimi-delegate`
  with constrained format ("CLEAN or FINDING+file:line").
- **Sandbox verification of helper latency changes** → `devin-delegate` only
  if needed; prefer local pytest.

Batch delegate questions (5 per call, not 1 each). Reference, don't quote.
Constrain output: "Answer CLEAN or FINDING+file:line. No preamble."

## Deliverable

One PR against `main` with:
- All 8 tracks implemented.
- All new + existing tests green (`python3 -m pytest scripts/tests/ -q`).
- PR description with:
  - Per-track summary of changes.
  - Before/after telemetry where measurable (especially direct_hit, broad-scan
    count, headroom conversion).
  - Any items where the implementation diverged from this brief and why.
  - Anything blocked by cross-repo constraints (e.g., H3 if the hook is
    global).

**STOP at the PR. Do not merge. Do not force-push. Do not push to `main`.**

## Reporting back

When the PR is open, post a short status to the orchestrator (Sonnet) via
whatever channel was used to spawn you (tmux session output is captured;
orchestrator will poll). Include the PR URL and a one-line summary of what's
covered vs deferred. Orchestrator reviews, then hands back to human.
