# Meta Learnings (2026-04-18)

These are the implementation lessons from validating the tiered token-reduce stack and companion intake work.

## What Held Up Under Benchmarking

1. Quality gates changed the winner.
   Raw token counts alone were misleading; some lowest-token paths failed exact-symbol quality checks. The quality-gated composite/adaptive paths were safer defaults.
2. Adaptive routing improved practical outcomes.
   In the current benchmark set, adaptive routing reduced token volume and restored exact-symbol quality compared with path-only baseline.
3. Profiled routing made tradeoffs explicit.
   `minimal-load` reduced complexity but missed quality in the tested set; `balanced` and `max-savings` preserved quality with higher savings.
4. Companion value is task-class specific.
   - `context-mode`: strong on output-heavy payloads.
   - `code-review-graph`: strong on larger dependency-rich repos; overhead risk on tiny diffs.
   - `token-savior`: strong on exact symbol/impact queries.

## What Did Not Generalize

1. A single universal backend did not win every task class.
   Forcing one backend across fuzzy discovery, exact symbol, and output-heavy scenarios caused regressions.
2. Prompt-template-only repos were not runtime dependencies.
   Prompt packs informed guidance style but did not justify adding runtime complexity.
3. Claimed savings from external repos required local re-validation.
   Integration decisions changed after running local tests and representative benchmarks.

## Operational Rules We Should Keep

1. Do not promote a tier/tool without benchmark + quality evidence in this repo.
2. Keep token-reduce helper-first discipline as the control plane; companions remain conditional accelerators.
3. Treat telemetry as a routing feedback loop, not just usage counters.
4. Keep profile presets formal and benchmarkable (`minimal-load`, `balanced`, `max-savings`).
5. Keep activation and handoff reproducible with one command (`activate-stack`, `handoff-codex`).

## Known Risks To Watch

1. Duplicate mirror content in `tools/token-reduce-skill` can inflate search output in local benchmarks.
2. Structural tiers depend on companion availability; fallback behavior must stay deterministic.
3. Recommendation flags (`context-mode`, `code-review-graph`) can over-suggest if intent terms are too broad; keep thresholds and heuristics under review.

## Next Validation Checkpoints

1. Run `token-reduce-manage.sh release-gate` before merging major change sets.
2. Re-run `measure` and `review` after hook or hinting changes.
3. Re-run intake benchmarks before changing default companion routing decisions.
