# graphify Evaluation

This note records whether `safishamsi/graphify` should be integrated into token-reduce.

## Verdict

Do not integrate `graphify` as a token-reduce companion right now.

## Verification

- Source reviewed: `https://github.com/safishamsi/graphify`
- Upstream validation run locally:
  - `cd /tmp/graphify-bench && uv run --with pytest pytest -q`
  - result: `425 passed`
- Benchmarks run on local sibling repos:
  - `/root/.openclaw/workspace/dev/specforge`
  - `/root/.openclaw/workspace/dev/Etc-mono-repo`

## Compatibility Findings

- Path-sensitive false positive in secret filtering:
  - `graphify.detect` currently treats paths containing `token` as sensitive.
  - In this repo path (`.../token-reduce-skill/...`) detection returned `0` files and skipped `106` files.
- CLI/docs mismatch in current package (`0.4.2`):
  - README advertises `graphify path` and `graphify explain`.
  - Installed CLI exposes `query` but not `path`/`explain`.
- Query coverage gaps in code-only graph mode:
  - missed constants (for example `DEFAULT_GUIDED_SPEC_INPUT`)
  - missed some exact symbol lookups (for example `agentRuntimeStatus`)
- Semantic extraction path is heavy for this use case:
  - docs/papers/images need multi-agent semantic extraction
  - this conflicts with token-reduce’s low-overhead default workflow

## Build Cost (AST-only graph generation)

| Repo | Files | Code files | Graph build time | Nodes | Edges |
|------|-------|------------|------------------|-------|-------|
| `specforge` | `254` | `171` | `0.522s` | `661` | `900` |
| `Etc-mono-repo` | `720` | `206` | `1.001s` | `1185` | `1716` |

## Query Benchmark Results

### specforge

| Task | token-reduce | graphify | Outcome |
|------|--------------|----------|---------|
| exact symbol (`buildGuidedSpecMetadata`) | `2799` tokens / `1813.47 ms` / quality hit | `477` tokens / `169.63 ms` / quality hit | graphify better |
| constant (`DEFAULT_GUIDED_SPEC_INPUT`) | `1052` / `1787.35 ms` / quality hit | `56` / `170.53 ms` / quality miss | graphify missed target |
| impact (`buildGuidedSpecMarkdown` ↔ `buildGuidedSpecMetadata`) | `153` / `1778.81 ms` / quality hit | `1003` / `169.99 ms` / quality miss | graphify less relevant and larger |
| broad topic (`workspace membership role updates`) | `311` / `4571.57 ms` / quality hit | `508` / `171.35 ms` / quality hit | mixed; graphify faster, token-reduce smaller |

### Etc-mono-repo

| Task | token-reduce | graphify | Outcome |
|------|--------------|----------|---------|
| exact symbol (`agentRuntimeStatus`) | `179` tokens / `2016.77 ms` / quality hit | `55` / `177.57 ms` / quality miss | graphify missed target |
| hook state topic | `1402` / `262.07 ms` / quality hit | `1089` / `177.25 ms` / quality miss | graphify retrieved unrelated code cluster |
| telemetry overhead topic | `272` / `31107.34 ms` / quality miss | `914` / `181.56 ms` / quality miss | both poor |
| broad architecture topic | `591` / `50730.22 ms` / quality hit | `1039` / `185.96 ms` / quality miss | graphify less relevant and larger |

## Interpretation

- `graphify` can be strong for some exact function-level lookup once a graph is prebuilt.
- It is not consistently reliable for constants, broad discovery, or doc-heavy questions in this workflow.
- Current compatibility gaps and extraction model make it a poor fit for default token-reduce routing.

## Decision

1. Keep token-reduce helper-first routing unchanged.
2. Do not add `graphify` as a default or optional dependency in this package.
3. Re-evaluate only if upstream addresses path-sensitive filtering and query surface consistency (`path`/`explain`), then rerun this benchmark set.

## Applied Mitigation

To reduce dependency side-effects even without integrating graphify, fallback `rg` search now excludes:

- `graphify-out/**`
- `artifacts/token-reduction/events.jsonl`
- `artifacts/token-reduction/snapshots/**`

This prevents graph/cache/event blobs from polluting helper snippets and inflating token cost when fallback search runs.

Post-fix spot check on `specforge` (`buildGuidedSpecMetadata`, path+snippet) dropped helper output from `2799` tokens to `323` tokens while keeping relevant hits.

Also, `Etc-mono-repo` telemetry confirms the top-level overhead concern: helper error rate is `0.0%` but helper latency remains high (`p95 33,731 ms`, `max 42,476 ms`). Review now flags this as `HIGH · latency_overhead`.
