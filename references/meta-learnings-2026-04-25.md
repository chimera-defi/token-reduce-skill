# Meta Learnings — 2026-04-25

## What We Learned

1. Aggregate telemetry windows can hide current-state improvements.
- 14-day runtime aggregates remained low after logging fixes because legacy events still dominated the sample.
- Adding `telemetry_windows` (`1d`, `14d`) made trend direction explicit and reduced false regression alarms.

2. High helper latency was partly observability debt.
- Prior events lacked backend and exit-code coverage across some helper tiers, making p95 attribution noisy.
- Standardizing helper telemetry fields (`backend`, `latency_ms`, `exit_code`, `lines`, `chars`) exposed where latency actually comes from.

3. QMD refresh behavior needs conservative default cadence and better diagnostics.
- Missing stamp bootstrap could trigger unnecessary refresh behavior in some environments.
- Increasing runtime `QMD_REFRESH_TTL_SECONDS` default to `900` and emitting search diagnostics reduced avoidable refresh pressure and made latency causes visible.

4. Benchmark potential and realized fleet outcomes must stay separate.
- Composite benchmark potential remained high (~86%), while realized estimates were much lower due routing/adoption and confidence constraints.
- The composite report now computes potential vs realized vs confidence explicitly to prevent benchmark-only claims.

## Changes Added

- `token-reduce-search` diagnostics exported to wrappers:
  - backend, collection action, qmd status, ensure/search/snippet/fallback timing.
- Structural + adaptive helper telemetry normalized:
  - latency + exit code + backend for structural; backend + exit code for adaptive.
- Composite reporting model:
  - potential benchmark savings,
  - realized estimate,
  - conservative/optimistic bands,
  - honesty flags,
  - factor decomposition.
- Review/report trend visibility:
  - 1-day vs 14-day telemetry windows surfaced in review output.

## Operational Follow-ups

1. Keep collecting runtime events so 14-day logging quality converges toward the improved 1-day window.
2. Continue reducing qmd search p95 by tuning indexing scope/TTL per repo size.
3. Promote backend attribution above 80% by ensuring any remaining helper paths emit backend tags.
