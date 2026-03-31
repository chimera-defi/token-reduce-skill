# Companion Tool Intake

Use this when evaluating additions like structural indexers, alternate search backends, or new MCP servers.

## Rule

Do not replace the core token-reduce workflow just because a tool claims better token numbers in isolation.

## Intake Checklist

1. Verify the external project directly.
2. Run its own tests or validation surface first.
3. Benchmark it on representative token-reduce tasks:
   - exact symbol lookup
   - constant lookup
   - broad topic discovery
   - impact analysis
4. Measure both output size and latency.
5. Decide whether it is:
   - replacement
   - optional accelerator
   - not worth integrating
6. Propagate the verdict into:
   - `README.md`
   - `SKILL.md`
   - a dedicated evaluation note under `references/`
   - any validation rules that should enforce the new contract

## Evidence Standard

Do not integrate a companion tool on intuition alone.

- Keep at least one exact-match task, one fuzzy discovery task, and one impact-analysis task in the benchmark set.
- Record concrete numbers, not just "felt better" claims.
- Prefer tools that improve a narrow task class without making the default install or first move worse.

## Default Decision Heuristic

- If the tool is clearly better only for exact symbol / dependency questions, integrate it as an optional structural accelerator.
- If it degrades broad topic discovery or adds heavy runtime/install cost, do not make it the default first move.
- If it cannot beat token-reduce on real repo tasks, document the result and reject it.

## Meta Learning

Future additions should enter through the same benchmark-and-adapter path:
- benchmark first
- adapter second
- docs and validation third
