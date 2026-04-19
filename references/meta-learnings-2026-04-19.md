# Meta Learnings (2026-04-19)

## What Broke And Why

1. QMD was effectively doc-only.
   Setup and runtime used `**/*.md`, so code/symbol lookup quality regressed and users perceived helper failures.
2. Setup/runtime/benchmark drift hid the real behavior.
   Different QMD masks across scripts caused misleading benchmark outcomes and quality flags.
3. Symbol-like queries are a BM25 edge case.
   Underscore-heavy identifiers (for example `prompt_requires_helper`) do not rank reliably via plain BM25 query text.
4. Mirror/benchmark noise can dominate top results.
   Nested `tools/token-reduce-skill`, benchmark artifacts, and generated telemetry files inflate path output and latency.

## What Held Up After Fixes

1. Shared index scope removed major false negatives.
   A unified extension list (`qmd-file-extensions.txt`) improved QMD quality on code queries.
2. Gate-driven validation prevented regressions.
   Running `validate`, `test-adaptive`, and `release-gate` before push kept routing/quality aligned with savings.
3. Noise filtering improved practical relevance.
   Excluding benchmark/artifact mirror paths from helper output reduced token waste and improved composite savings.
4. Adaptive tiering still won under quality checks.
   Final gate run preserved quality and passed savings thresholds with `release_gate_pass: true`.

## Operational Rules To Keep

1. Treat QMD mask policy as a single source of truth.
   Setup, runtime search, and benchmark harnesses must read the same scope definition.
2. Keep symbol routing explicit.
   Let adaptive structural routing own exact-symbol tasks; path-only helpers should stay lightweight.
3. Re-run workspace audit + telemetry after major routing changes.
   Measure local (`measure`/`review`) and global (`measure-global`/`review-global`) before release.
4. Keep dependency health current before publishing.
   Run `deps-check-conditional` and apply updates to avoid stale companion behavior.

## Current Follow-Ups

1. Improve global helper adoption (`helper_sessions_pct_observed_discovery` still below desired level).
2. Tighten hook coverage where broad scans still appear in global history.
3. Keep watching helper latency tails (QMD refresh/search dominates p95).

## Addendum (2026-04-19, gap-closure pass)

1. Telemetry attribution mattered as much as routing.
   Sessions using structural/adaptive/orchestrate helpers were undercounted as "no helper", masking real adoption.
2. Reminder quality affects compliance.
   A generic hint is weaker than a prompt-specific kickoff command; injecting concrete query words improves first-action helper behavior.
3. Broad-scan patterns needed stricter coverage.
   Blocking only `rg --files .` missed other `rg --files` forms and `fd` usage; broader regexes close those escapes.
4. Sibling telemetry validated install consistency but behavior variance.
   Workspace audit shows version/commit sync is stable; remaining gaps are primarily usage patterns, not deployment drift.
5. QMD fingerprint checks needed a freshness window.
   Recomputing full-repo fingerprints on every helper call drives latency spikes; a short stamp TTL keeps repeated calls fast without sacrificing correctness.
6. Broad `rg` detection needed semantic parsing.
   Regex-only broad-scan blocking misses `rg` forms that recurse from repo root; token-aware path parsing catches these while still allowing exact-file `rg`.
