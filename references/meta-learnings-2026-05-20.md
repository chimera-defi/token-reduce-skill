# Meta Learnings (2026-05-20)

## What Changed This Cycle

1. Added docs-focused fast-path routing in `token-reduce-search`:
- Queries containing `guide`, `readme`, `docs`, `reference`, `architecture`, or `integration` now short-circuit to scoped `rg` path/content hints.
- This avoids entering slow QMD paths for common documentation lookups.

2. Added recency-aware telemetry interpretation in `review_token_reduction.py`:
- The review still reports 14-day latency tails.
- It now downgrades severity when 1-day runtime latency is healthy, preventing stale outliers from driving current operational decisions.

3. Formalized weekly maintenance automation:
- `scripts/install-token-reduction-cron.sh` now installs weekly jobs for:
  - `token-reduce-manage.sh self-improve`
  - `token-reduce-manage.sh telemetry-sync`
- Output is written to `artifacts/token-reduction/cron-weekly.log`.

4. Expanded delegate-routing policy coverage:
- `AGENTS.md` now includes a mandatory `devin-delegate` wrapper block in the same policy style as `kimi-delegate`.

## Operational Learnings

1. Validate fast paths with benchmark-shaped prompts.
- The adaptive benchmark includes `token reduction guide`; if docs routing regresses, adaptive/profile gates fail quickly.

2. Run adaptive/profile checks before full release-gate when routing changes are involved.
- This catches threshold issues earlier and avoids waiting through long composite/QMD benchmark passes before discovering adaptive gate drift.

3. Treat runtime windows as primary for operational health.
- Use 14-day windows for trend context only.
- Use 1-day runtime windows for “is this currently broken?” decisions.

## Follow-Ups

1. Keep docs-priority matching strict enough to surface `references/token-reduction-guide.md` first for docs queries.
2. Continue monitoring `discovery_compliance_pct_observed` and `prompt_skill_gap`; latency improved, but first-move adoption still has room to improve.
3. Periodically review weekly `self-improve` outputs and tune adaptive/profile thresholds only when repeated weekly regressions appear.
