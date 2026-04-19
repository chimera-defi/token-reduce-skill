# References Index

Use this index to keep maintenance repeatable and avoid drift.

## Start Here

- `README.md` for install/activation and benchmark snapshots
- `SKILL.md` for runtime behavior and first-move rules
- `references/architecture.md` for routing/enforcement model

## Hard Gates

- Full checkpoint suite:
  - `./scripts/token-reduce-manage.sh checkpoint`
- Major change-set keep/drop gate:
  - `./scripts/token-reduce-manage.sh release-gate`
- Manual README benchmark sync (normally handled by release gate):
  - `./scripts/token-reduce-manage.sh sync-benchmarks`
- Package and artifact validity:
  - `./scripts/token-reduce-manage.sh validate`
- Adaptive routing tests:
  - `./scripts/token-reduce-manage.sh test-adaptive`

## Telemetry And Review

- Repo/local adoption:
  - `./scripts/token-reduce-manage.sh measure`
  - `./scripts/token-reduce-manage.sh review`
- Global/sibling adoption:
  - `./scripts/token-reduce-manage.sh measure-global`
  - `./scripts/token-reduce-manage.sh review-global`
  - `./scripts/token-reduce-manage.sh workspace-audit`
  - `./scripts/token-reduce-manage.sh telemetry-sync --dry-run`

## Dependency Policy

- Tier decisions:
  - `references/tier-value-profile.md`
- Companion intake rubric:
  - `references/companion-tools.md`
- Freshness checks:
  - `./scripts/token-reduce-manage.sh deps-check`
  - `./scripts/token-reduce-manage.sh deps-check-conditional`

## Benchmark Artifacts

- Local helper benchmark:
  - `references/benchmarks/local-benchmark.json`
- Composite stack benchmark:
  - `references/benchmarks/composite-benchmark.json`
- Adaptive routing benchmark:
  - `references/benchmarks/adaptive-tier-benchmark.json`
- Profile preset benchmark:
  - `references/benchmarks/profile-presets-benchmark.json`

## Change Logs And Learnings

- Harness change log:
  - `references/self-enhancing-harness-log-2026-04-12.md`
- Harness operations:
  - `references/self-improving-harness.md`
- Recent meta learnings:
  - `references/meta-learnings-2026-04-18.md`
  - `references/meta-learnings-2026-04-19.md`
