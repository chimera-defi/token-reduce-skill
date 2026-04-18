# Composite Benchmark

This benchmark answers a practical question:
is the **composite stack** better than using one companion tool by itself?

## Goal

Compare token output across mixed workloads using:

- broad shell only
- QMD only
- token-reduce helper only
- token-savior only
- RTK only
- composite stack (`token-reduce-paths` + `token-savior` exact symbol + RTK output compression)

## Workload Mix

1. fuzzy discovery (`hook enforcement system`)
2. exact symbol lookup (`prompt_requires_helper`)
3. output-heavy scan (`token reduction`)

Each step has a quality gate. If expected signal is missing, the strategy is marked `quality-fail`.

## Latest Result

Artifact: `references/benchmarks/composite-benchmark.json`

| Strategy | Tokens | Savings vs broad | Status |
|----------|--------|------------------|--------|
| `broad_shell` | `1154` | `0.0%` | `ok` |
| `qmd_only` | `312` | `73.0%` | `quality-fail` |
| `token_reduce_only` | `401` | `65.3%` | `quality-fail` |
| `token_savior_only` | `621` | `46.2%` | `ok` |
| `rtk_only` | `627` | `45.7%` | `ok` |
| `composite_stack` | `367` | `68.2%` | `ok` |

Composite stack wins on tokens against every single-tool strategy that passed quality checks in this run:

- `broad_shell`
- `token_savior_only`
- `rtk_only`

## Reproduce

```bash
./scripts/token-reduce-manage.sh benchmark-composite
```

## Notes

- `qmd_only` and `token_reduce_only` were cheaper on raw tokens for some steps but failed exact-symbol quality in this scenario.
- AXI and caveman are not included in this matrix because their primary value is turn-count/interaction style, not this local shell-only retrieval workload.
