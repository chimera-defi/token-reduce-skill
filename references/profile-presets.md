# Routing Profile Presets

`token-reduce` ships with three formal routing profiles you can apply via settings.

## Profiles

### `minimal-load`

Use when you want the lightest operational footprint and lowest companion/tool churn.

- short behavior lookback (`1` day)
- high snippet-promotion threshold (`0.65`)
- structural tier disabled
- companion recommendations disabled (`context-mode`, `code-review-graph`)

### `balanced`

Default profile. Good general-purpose tradeoff between stability and savings.

- behavior lookback (`3` days)
- snippet threshold (`0.35`)
- structural tier enabled
- companion recommendations enabled

### `max-savings`

Use when maximizing token compression is worth extra complexity.

- long behavior lookback (`7` days)
- aggressive snippet promotion (`0.2`)
- structural tier enabled
- companion recommendations enabled

## Commands

List profiles:

```bash
./scripts/token-reduce-manage.sh settings profile list
```

Show active profile:

```bash
./scripts/token-reduce-manage.sh settings profile show
```

Show a profile preset:

```bash
./scripts/token-reduce-manage.sh settings profile show max-savings
```

Apply a profile:

```bash
./scripts/token-reduce-manage.sh settings profile apply minimal-load
./scripts/token-reduce-manage.sh settings profile apply balanced
./scripts/token-reduce-manage.sh settings profile apply max-savings
```

Benchmark all presets:

```bash
./scripts/token-reduce-manage.sh benchmark-profiles
```

Results are written to:

`references/benchmarks/profile-presets-benchmark.json`
