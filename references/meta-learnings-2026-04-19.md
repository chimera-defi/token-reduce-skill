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
