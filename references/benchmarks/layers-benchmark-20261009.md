# Layer on/off benchmark — 2026-10-09 (this host)

Reproduce: `uv run --no-project --with tiktoken scripts/benchmark-layers.py`.
Tokens are tiktoken cl100k counts of the output an agent would read (a proxy, not Claude's tokenizer).
Fixed cases: 6 read-only commands x 2 repos (this repo, SharedStake-ui); 9 topic searches on this repo.

| Layer | Off (tokens) | On (tokens) | Effect | Decision |
|---|---|---|---|---|
| rtk | 155,873 | 43,340 | -72.2%, same exit codes, +~27 ms/cmd | keep on (raise: nothing to add) |
| search, rg fallback | naive `rg -n` 238,115 | 935 | -99.6%, 8/9 top-5 hits, ~0.45 s/query | default path |
| search, qmd (forced on) | naive 238,115 | 1,477 | 8/9 top-5 hits (same as rg), +56% tokens vs rg (1,477 vs 948), ~4.8 s/query (10x) | **off** on this host (`layers.search_qmd=off`): no quality gain on a ~150-file repo, slower and larger |
| memory hint | - | 9 | one line per search | keep |
| context audit | - | 515 | one report per load, 0.3 s | keep (cost trivial; savings not attributable) |
| headroom (live proxy, 0.39.1->0.40.0) | 16.0M in | 478k removed | -3.0% tokens, $2.51 measured saved vs $26.87 provider-cache discount | keep on; savings are small, cache hits dominate |

Left alone: headroom_retrieve, mcp_trim (no per-case data yet), memory (cost is 28 tokens).
Caveat: qmd may still win on very large repos or fuzzy/semantic queries; not measured here.
Caveat: nothing here measures task success end to end; search quality is top-5 file hit on known targets.
