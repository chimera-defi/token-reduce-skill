# Feature Matrix (2026-04-18)

This document maps the shipped token-reduce feature set to operational controls and evidence.

## Core Controls

| Feature | Default | How to use | Config knobs | Telemetry signal | Primary evidence |
|---|---|---|---|---|---|
| Path-first discovery | on | `./scripts/token-reduce-paths.sh <topic words>` | n/a | `tool=token_reduce_paths` helper events | `references/benchmarks/local-benchmark.json` |
| Ranked snippet follow-up | on | `./scripts/token-reduce-snippet.sh <topic words>` | n/a | `tool=token_reduce_snippet` helper events | `references/benchmarks/local-benchmark.json` |
| Adaptive tier router | on (`balanced`/`max-savings`) | `./scripts/token-reduce-adaptive.sh <topic words>` | `routing.adaptive_hint`, `routing.behavior_days`, `routing.rapid_repeat_snippet_threshold`, `routing.enable_structural`, `routing.enable_context_mode_recommendations`, `routing.enable_code_review_graph_recommendations` | `tool=token_reduce_adaptive` + `meta.tier`, `meta.context_mode_recommended`, `meta.code_review_graph_recommended`, behavior ratios | `references/benchmarks/adaptive-tier-benchmark.json` |
| Structural symbol/impact tier | on (`balanced`/`max-savings`) | `token-reduce-structural --project-root . find-symbol <symbol>` or `change-impact <symbol>` | `routing.enable_structural` | adaptive tier values: `structural_symbol`, `structural_impact`, `structural_search` | `references/benchmarks/composite-benchmark.json` |
| Pre-tool enforcement | on when hooks installed | `./scripts/setup.sh` (or plugin install) | n/a | hook blocks + compliance rates in `measure`/`review` artifacts | `artifacts/token-reduction/adoption-*.md` |
| Prompt steering reminder | on when hooks installed | `./scripts/setup.sh` (or plugin install) | `TOKEN_REDUCE_ADAPTIVE_HINT=0` to suppress adaptive hint fallback | pending-state and helper-adoption signals | `artifacts/token-reduction/adoption-*.md` |

## Routing Profiles

| Profile | Goal | Behavior window | Snippet threshold | Structural tier | Companion recommendations |
|---|---|---|---|---|---|
| `minimal-load` | Lowest operational load | `1` day | `0.65` | off | off |
| `balanced` | Default quality/savings mix | `3` days | `0.35` | on | on |
| `max-savings` | Aggressive savings | `7` days | `0.2` | on | on |

Commands:

```bash
./scripts/token-reduce-manage.sh settings profile list
./scripts/token-reduce-manage.sh settings profile show
./scripts/token-reduce-manage.sh settings profile apply max-savings
./scripts/token-reduce-manage.sh benchmark-profiles
```

Profile benchmark artifact:

- `references/benchmarks/profile-presets-benchmark.json`

## Companion Integrations

| Companion | Role | Default routing | When to use | Evidence |
|---|---|---|---|---|
| RTK | Command output compression | optional | output-heavy shell commands | `references/benchmarks/composite-benchmark.json` |
| token-savior | Exact symbol / impact lookup | optional | known symbol + dependency/blast-radius questions | `references/token-savior-evaluation.md` |
| context-mode | Output sandboxing/summarization | optional recommendation | huge logs/tests/payload sessions | `references/prompt-stack-intake-2026-04-18.md` |
| code-review-graph | Repo structural graph review | optional recommendation | large dependency-heavy repos | `references/prompt-stack-intake-2026-04-18.md` |
| caveman | Response and memory compression companion | optional | explicit user brevity request | `references/caveman-evaluation.md` |
| AXI (`gh-axi`, `chrome-devtools-axi`) | Lower-turn GitHub/browser execution | optional | GitHub/browser-heavy flows | `references/axi-evaluation.md` |

## Validation And Benchmarking Surface

| Command | Purpose | Output |
|---|---|---|
| `./scripts/token-reduce-manage.sh validate` | package + benchmark artifact validation | terminal pass/fail |
| `./scripts/token-reduce-manage.sh benchmark` | local helper-output benchmark | `references/benchmarks/local-benchmark.json` |
| `./scripts/token-reduce-manage.sh benchmark-adaptive` | adaptive vs baseline-tier comparison | `references/benchmarks/adaptive-tier-benchmark.json` |
| `./scripts/token-reduce-manage.sh benchmark-composite` | quality-gated composite stack benchmark | `references/benchmarks/composite-benchmark.json` |
| `./scripts/token-reduce-manage.sh benchmark-profiles` | profile-level savings/quality benchmark | `references/benchmarks/profile-presets-benchmark.json` |
| `./scripts/token-reduce-manage.sh deps-check` | core dependency health (qmd + rtk) | terminal summary + JSON |
| `./scripts/token-reduce-manage.sh deps-check-conditional` | conditional companion health (AXI/context-mode/code-review-graph) | terminal summary + JSON |
| `./scripts/token-reduce-manage.sh release-gate` | benchmark + README benchmark-row sync + runtime-reliability keep/drop verdict for major change sets | terminal JSON verdict (`release_gate_pass`) |
| `./scripts/token-reduce-manage.sh sync-benchmarks` | manual README benchmark token-row sync from artifacts | terminal JSON summary |
| `./scripts/token-reduce-manage.sh checkpoint` | full consistency harness (release-gate/validate/tests + local/global review + workspace audit + telemetry sync dry-run) | `artifacts/token-reduction/checkpoint-*.{json,md}` |
| `./scripts/token-reduce-manage.sh measure` | local adoption/compliance metrics | `artifacts/token-reduction/adoption-repo-*.{json,md}` |
| `./scripts/token-reduce-manage.sh review` | telemetry-driven recommendation report | `artifacts/token-reduction/adoption-repo-*-review.md` |

## Activation And Handoff

| Workflow | Command | Notes |
|---|---|---|
| One-command stack activation | `./scripts/token-reduce-manage.sh activate-stack` | setup + extended companions + validate |
| Codex fresh-context handoff | `./scripts/token-reduce-manage.sh handoff-codex` | prints ready-to-paste bootstrap block |

## Telemetry Coverage For Adaptive Policy

The current telemetry is sufficient to evaluate tier usefulness and compliance over time:

- helper/tool usage by helper type (`token_reduce_paths`, `token_reduce_snippet`, `token_reduce_adaptive`)
- first-move compliance and helper adoption (`measure` / `review`)
- adaptive decision details (`tier`, recommendation flags, behavior ratios, latency, chars/lines)
- exclusion of synthetic benchmark/test events from runtime summaries by default
