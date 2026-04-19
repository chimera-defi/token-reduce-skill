# Token Reduction Guide

Current guidance for running token-reduce with adaptive tiers, profile presets, and telemetry-backed validation.

## Current Snapshot

- Last benchmark refresh: 2026-04-18
- Primary local artifacts:
  - `references/benchmarks/local-benchmark.json`
  - `references/benchmarks/composite-benchmark.json`
  - `references/benchmarks/adaptive-tier-benchmark.json`
  - `references/benchmarks/profile-presets-benchmark.json`

## Quick Reference

| Strategy | Measured effect | When |
|---|---|---|
| Concise responses | large response-token reduction | always |
| Path-first discovery (`token-reduce-paths`) | avoids broad inventory overhead | unknown file location |
| Adaptive routing (`token-reduce-adaptive`) | promotes snippet/structural tiers when useful | unknown file location with mixed task types |
| Targeted reads | avoids loading irrelevant file sections | large files |
| RTK companion | compresses command output | output-heavy shell steps |
| token-savior companion | exact symbol / impact wins | exact symbol known |

## Decision Flow

1. Exact file path already known: read only what you need.
2. File path unknown: run `./scripts/token-reduce-adaptive.sh <topic words>`.
3. Adaptive disabled: run `./scripts/token-reduce-paths.sh <topic words>`.
4. Need one excerpt after path list: run `./scripts/token-reduce-snippet.sh <topic words>`.
5. Need exact symbol or impact: run `token-reduce-structural --project-root . find-symbol <symbol>` or `change-impact <symbol>`.
6. Candidate set still broad after two passes: ask user to narrow scope.

`rg --files .`, `find .`, `ls -R`, and `grep -R` are first-move violations when helper routing is available.

## Benchmarks (Current)

### Local helper benchmark

From `references/benchmarks/local-benchmark.json`:

| Strategy | Tokens | Savings vs broad inventory |
|---|---|---|
| `broad_inventory` | `565` | baseline |
| `guidance_scoped_rg` | `197` | `65.1%` |
| `qmd_files` | `328` | `41.9%` |
| `token_reduce_paths_warm` | `328` | `41.9%` |
| `token_reduce_snippet_warm` | `406` | `28.1%` |

### Composite stack benchmark (quality-gated)

From `references/benchmarks/composite-benchmark.json`:

| Strategy | Tokens | Savings vs broad | Status |
|---|---|---|---|
| `broad_shell` | `2407` | `0.0%` | `ok` |
| `qmd_only` | `408` | `83.0%` | `quality-fail` |
| `token_reduce_only` | `623` | `74.1%` | `quality-fail` |
| `token_savior_only` | `483` | `79.9%` | `ok` |
| `rtk_only` | `782` | `67.5%` | `ok` |
| `composite_stack` | `431` | `82.1%` | `ok` |

### Adaptive tier benchmark

From `references/benchmarks/adaptive-tier-benchmark.json`:

- baseline paths tokens: `724`
- adaptive tokens: `563`
- adaptive savings: `22.2%`
- baseline quality: fail
- adaptive quality: pass

### Routing profile benchmark

From `references/benchmarks/profile-presets-benchmark.json`:

- `minimal-load`: lower overhead, no adaptive gain in current set, quality fail
- `balanced`: quality pass with `22.2%` adaptive savings
- `max-savings`: quality pass with `22.2%` adaptive savings

## Routing Profiles

Use profile presets to formalize behavior/load policy:

```bash
./scripts/token-reduce-manage.sh settings profile list
./scripts/token-reduce-manage.sh settings profile show
./scripts/token-reduce-manage.sh settings profile apply balanced
./scripts/token-reduce-manage.sh benchmark-profiles
```

Details: `references/profile-presets.md`.

## Enforcement And Telemetry

### Enforced flow

- prompt steering: `scripts/remind-token-reduce.py`
- broad-scan blocking: `scripts/enforce-token-reduce-first.py`

### Telemetry loop

```bash
./scripts/token-reduce-manage.sh measure
./scripts/token-reduce-manage.sh review
./scripts/token-reduce-manage.sh telemetry
./scripts/token-reduce-manage.sh rolling-baseline
```

Adaptive telemetry also records tier and recommendation metadata (`tier`, behavior ratios, recommendation flags, latency, chars/lines).

## Companion Policy

- Keep companion tools task-scoped unless benchmark and quality evidence support broader routing.
- Keep prompt-template repositories as guidance inputs, not runtime dependencies.
- Re-run intake benchmarks before changing default routing decisions.

Intake method and evidence rules: `references/companion-tools.md`.

## Maintenance Baseline

When routing/hooks/benchmarks change, run:

```bash
./scripts/token-reduce-manage.sh validate
./scripts/token-reduce-manage.sh measure
./scripts/token-reduce-manage.sh review
./scripts/token-reduce-manage.sh release-gate
./scripts/token-reduce-manage.sh deps-check
./scripts/token-reduce-manage.sh deps-check-conditional
```

Optional one-shot pass:

```bash
./scripts/token-reduce-manage.sh self-improve
```

## Related Docs

- `references/feature-matrix.md`
- `references/meta-learnings-2026-04-18.md`
- `references/composite-benchmark.md`
- `references/prompt-stack-intake-2026-04-18.md`
