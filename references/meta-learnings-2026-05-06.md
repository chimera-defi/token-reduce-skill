# Meta Learnings (2026-05-06)

## Telemetry-Driven Skill Improvement Cycle

This session validated that telemetry can diagnose its own blind spots. The loop:

1. **Evaluate** — run `measure` + `review` to see what the data says
2. **Identify gaps** — find what's missing from the signals (benchmark pollution, no outcome correlation, no post-block tracking)
3. **Instrument** — add the missing telemetry without changing behavior
4. **Re-measure** — confirm the new signals show up and make sense
5. **Decide** — let the new data guide the next round of behavior changes

## Key Telemetry Gaps Discovered

### Benchmark Pollution Dominates Runtime Signal

The 14d window had 201 total events but only 11 runtime (5.5%). Benchmark QMD collection creation (~9s per call) drove the 13s p95 latency, masking real user experience. **Fix**: context-separated `efficiency_by_context` now isolates runtime from benchmark.

### QMD Latency Was a Black Box

We knew total latency was high but couldn't tell if it was collection creation, search, snippet, or fallback. **Fix**: `qmd_latency_breakdown` with p50/p95 per sub-phase. First data: `qmd_ensure_ms` p95 = 5,300ms, `qmd_files_ms` p95 = 4,612ms — together explaining the tail.

### Hook Enforcement Had No Feedback Loop

Hooks blocked broad scans, but we didn't know if agents complied or escaped. **Fix**: `record_block` / `consume_block` state tracking + `post_block_compliance`, `post_block_escape`, `post_block_abandon` events.

### Helper Usage ≠ Helper Quality

We tracked *that* the helper ran but not *whether it helped*. **Fix**: `files_returned_count` + `top_returned_paths` in helper meta, and per-session `discovery_outcome` classification in `measure_token_reduction.py`.

## Decisions Enabled by New Telemetry

| Signal | Current Reading | Decision |
|--------|-----------------|----------|
| Runtime latency p95 | 12,392 ms (dominated by QMD) | Consider lowering `TOKEN_REDUCE_QMD_REFRESH_TTL_SECONDS` or pre-warming collection |
| QMD ensure p95 | 5,300 ms | Collection fingerprinting + add is the expensive phase; TTL tuning helps |
| direct_hit rate | 12.5% | Low; may indicate ranking quality or prompt-steering issues |
| miss rate | 0.0% | Good — helper results are not being ignored for broad scans |
| standoff rate | 0.0% | Good — when helper runs, agents do follow-up discovery |
| post-block compliance | Not yet measured (needs new sessions) | Will reveal hook effectiveness in next window |

## Propagation Process Verified

1. Run `release-gate` → must pass before merging
2. Bump version in `SKILL.md`
3. Commit with `[Agent: <MODEL>]` + `Co-authored-by` trailer
4. Push feature branch, open PR with attribution
5. Run `workspace-install --force-relink` to propagate skill symlink + doc blocks
6. Commit doc-block changes in sibling repos separately (only the files touched by install)
7. Run `workspace-audit` to confirm version/commit drift is zero across siblings

## Guardrails to Keep

- **Never commit local config** (`.claude/token-reduce-config.json`) — it's per-machine
- **Never commit benchmark artifacts blindly** — `release-gate` syncs README rows from artifacts before validation
- **Separate benchmark from runtime in operational decisions** — always check `efficiency_by_context.runtime` before acting on latency
- **Post-block tracking is fragile to hook ordering** — `enforce-token-reduce-first` must run before `remind-token-reduce` consumes block state

## Current Follow-Ups

1. Collect real runtime sessions to populate `post_block_compliance` / `post_block_escape` signals
2. Watch `direct_hit` rate over next 2 weeks; if it stays below 30%, investigate QMD ranking or adaptive tier thresholds
3. Tune `TOKEN_REDUCE_QMD_REFRESH_TTL_SECONDS` if `qmd_ensure_ms` stays above 5s in runtime context
4. Add `companion_recommended` / `companion_accepted` tracking for adaptive router recommendations (context_mode, code_review_graph)
5. Consider adding `estimated_tokens_saved` heuristic once `files_returned_count` and repo size are reliably captured
