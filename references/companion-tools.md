# Companion Tool Intake

Use this when evaluating additions like structural indexers, alternate search backends, new MCP servers, or agent-native CLI companions.
Also use it for response-style or memory-compression companions (for example caveman).

## Rule

Do not replace the core token-reduce workflow just because a tool claims better token numbers in isolation.

## Intake Checklist

0. Verify the exact user-provided source URL/repo is reachable.
   - If it is not reachable (`404`/permission denied), mark the candidate as failed at source level.
   - Do not silently substitute a different owner/repo without recording that mapping explicitly.
1. Verify the external project directly.
2. Run its own tests or validation surface first.
3. Check license compatibility before default integration (MIT-core skills should not silently depend on restrictive/noncommercial companions).
4. Benchmark it on representative token-reduce tasks:
   - exact symbol lookup
   - constant lookup
   - broad topic discovery
   - impact analysis
5. Measure both output size and latency.
6. For style/memory companions, also measure:
   - output-token effect (response verbosity)
   - session-input effect (always-loaded memory files like `CLAUDE.md`)
   - fidelity checks (code/URLs/headings/commands preserved)
7. For CLI-interface companions (for example AXI-style tools), also measure:
   - turn count on real execution tasks
   - retry/error rate for common mutations
   - whether outputs are concise by default without lossy truncation
8. Decide whether it is:
   - replacement
   - optional accelerator
   - not worth integrating
9. Propagate the verdict into:
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
- If the tool is clearly better only for response brevity or memory-file compression, integrate it as an optional style/input companion.
- If the tool is clearly better only for specific operational surfaces (for example GitHub/browser), integrate it as an optional interface companion and keep core discovery defaults unchanged.
- If it degrades broad topic discovery or adds heavy runtime/install cost, do not make it the default first move.
- If it cannot beat token-reduce on real repo tasks, document the result and reject it.

## Meta Learning

Future additions should enter through the same benchmark-and-adapter path:
- benchmark first
- adapter second
- docs and validation third
