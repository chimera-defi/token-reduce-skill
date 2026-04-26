# Tier Value Profile

This document formalizes which dependencies are actively orchestrated, which are conditional, and which are intentionally excluded.

## Evidence Snapshot

From current benchmark artifacts:

- `references/benchmarks/composite-benchmark.json`
- `references/benchmarks/adaptive-tier-benchmark.json`
- `references/benchmarks/profile-presets-benchmark.json`

Key signals:

- composite stack: quality pass with strong savings
- adaptive tiering: quality pass with lower token cost than path-only baseline
- profile presets: `balanced` and `max-savings` pass quality; `minimal-load` fails quality in current set

## Keep (Orchestrated Core)

These are the dependencies we actively orchestrate on top of by default:

| Tier | Dependency / Tool | Why kept |
|---|---|---|
| T0 core | `qmd` + `token-reduce-paths` + `token-reduce-snippet` + hooks | first-move discovery control plane |
| T1 adaptive | `token-reduce-adaptive` | improves quality and reduces token cost vs baseline paths |
| T1 output-control | `rtk` | compresses command output that still needs to run |
| T1 structural (optional but integrated) | `token-reduce-structural` (`token-savior` backend) | high-value exact symbol / impact acceleration |

## Conditional (Not In Core Default)

These are only worth enabling for narrow task classes:

| Tier | Dependency / Tool | Why conditional |
|---|---|---|
| T2 output-heavy companion | `context-mode` | strong for large payload sessions; unnecessary for normal discovery |
| T2 large-repo structural companion | `code-review-graph` | can win on large dependency-heavy repos; can lose on tiny diffs |
| T2 execution-surface companion | `gh-axi`, `chrome-devtools-axi` | turn-count improvement for GitHub/browser workflows only |
| T2 response-style companion | `caveman` | output/memory compression, not discovery routing |

## Excluded From Routing Defaults

| Candidate | Decision | Reason |
|---|---|---|
| `token-optimizer-mcp` | excluded | local discovery benchmark regression / quality issues |
| `token-optimizer` | excluded | overlap + no reproducible win in token-reduce tasks |
| `claude-context` | excluded from local default | infra-coupled; no local default-routing win evidence |
| prompt-template-only repos | excluded from runtime deps | guidance overlap, no runtime backend |
| legacy graphify-first orchestration | removed from active orchestration path | unnecessary complexity/risk for current stack |
| legacy `token-reduce-orchestrate.sh` wrapper | removed | redundant surface once adaptive routing + strict hooks became the canonical path |

## Failure And Token-Overhead Controls

1. Core activation is default; conditional companions are opt-in.
2. Core dependency checks are default; conditional dependency checks are explicit.
3. Major change sets must pass release gate:

```bash
./scripts/token-reduce-manage.sh release-gate
```

4. Keep only change sets that preserve quality and pass release gate criteria.
