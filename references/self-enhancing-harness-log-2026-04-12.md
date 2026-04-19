# Self-Enhancing Harness Log (2026-04-12)

## Request Scope

- Review telemetry and trigger harness improvements.
- Improve long-run learning loop quality (local + sibling repos + remote summary sync).
- Track graphify-layer decision so it can be removed cleanly if it underperforms.

## Changes Applied

1. Added telemetry context support (`runtime` vs `benchmark` / `test` / `synthetic`).
2. Default telemetry summaries/reviews now exclude non-runtime contexts while still reporting excluded counts.
3. Tagged benchmark flows to emit `TOKEN_REDUCE_TELEMETRY_CONTEXT=benchmark`.
4. Updated `self-improve` to include workspace audit snapshot output.
5. Added observed-discovery metrics in measure/review:
   - discovery compliance among observed-discovery sessions
   - helper usage among observed-discovery sessions
6. Extended telemetry sync payload with observed metrics and workspace gap counters.
7. Updated docs (including the then-active graphify tracking note) with new keep/remove gate.

## Files Touched

- `scripts/token_reduce_telemetry.py`
- `scripts/token-reduce-paths.sh`
- `scripts/token-reduce-snippet.sh`
- `scripts/token-reduce-structural.py`
- `scripts/token-reduce-orchestrate.sh` (retired later)
- `scripts/benchmark-composite-stack.py`
- `scripts/token-reduce-manage.sh`
- `scripts/measure_token_reduction.py`
- `scripts/review_token_reduction.py`
- `scripts/token-reduce-telemetry-sync.py`
- `scripts/baseline-measurement.sh`
- `README.md`
- `references/self-improving-harness.md`
- `references/token-reduction-guide.md`
- `references/graphify-orchestration-tracking.md` (retired later)

## Rollback Plan (If Needed)

1. Revert telemetry-context filtering changes in `scripts/token_reduce_telemetry.py`.
2. Revert benchmark context tagging in benchmark/manage scripts.
3. Revert observed-discovery metrics additions in measure/review.
4. Keep graphify disabled (default). This surface was later removed entirely in the 2026-04-19 cleanup pass.

## Verification Checklist

- `./scripts/token-reduce-manage.sh validate`
- `./scripts/token-reduce-manage.sh measure-global`
- `./scripts/token-reduce-manage.sh review-global`
- `./scripts/token-reduce-manage.sh workspace-audit --days 30 --output artifacts/token-reduction/workspace-audit-2026-04-12.json`

## Verification Results

- `validate`: passed (`skill package` + `benchmark artifact`).
- `self-improve`: completed successfully.
- telemetry sync upload: `http 200`.

Global review snapshot (`artifacts/token-reduction/adoption-global-2026-04-12-review.md`):

- health score: `68.3`
- discovery compliance (all sessions): `47.5%`
- discovery compliance (observed sessions): `76.2%`
- helper usage (all sessions): `29.7%`
- helper usage (observed sessions): `47.6%`
- telemetry excluded benchmark/test events: `12`

Workspace audit snapshot (`artifacts/token-reduction/workspace-audit-2026-04-12.json`):

- local skill installed across sibling repos: `14/14` (`100%`)
- token-reduce docs present: `14/14` (`100%`)
- active repos without helper usage: `SharedStake-ui`, `eth2-quickstart`

## Follow-up Actions (User Approved)

1. Strengthened shared workspace routing block template to make first discovery call mandatory and query-word usage explicit.
2. Re-ran `workspace-install` to propagate the tighter block across sibling repos (`12` repos updated with `block-replaced`).
3. Ran `deps-update` and upgraded stale companions:
   - `rtk`: `0.31.0 -> 0.35.0`
   - `chrome-devtools-axi`: `0.1.12 -> 0.1.15`
4. Re-ran global measure/review and workspace audit.
5. Improved workspace audit to include recent repo-local helper telemetry (not only session-log helper calls).
6. Ran helper smoke calls in `SharedStake-ui` and `eth2-quickstart` to verify telemetry-based adoption path.
7. Added rolling baseline reporter and manage command (`rolling-baseline`) for automatic pre/post trend windows.

Post-install audit snapshot (`artifacts/token-reduction/workspace-audit-2026-04-12-post-install.json`):

- install/doc compliance remains `100%` (`14/14`).
- helper-usage gap remains in active repos: `SharedStake-ui`, `eth2-quickstart`.

Post-smoke audit snapshot (`artifacts/token-reduction/workspace-audit-2026-04-12-post-smoke.json`):

- active repos without helper usage: `0`
- repos with helper usage signal (session or telemetry): `13/14`
- telemetry-only usage repos: `10/14`

Rolling baseline artifact (`artifacts/token-reduction/rolling-baseline-2026-04-13.md`):

- helper usage (all sessions): `+0.56`
- helper usage (observed discovery): `+47.6`
- discovery compliance (all sessions): `+0.4`
- discovery compliance (observed discovery): `+76.2`

## 2026-04-19 Cleanup Note

- The experimental `graphify` orchestration tracking surface was fully retired.
- Canonical routing is now `token-reduce-adaptive` + enforced first-move hooks only.
