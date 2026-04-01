# token-savior Evaluation

This note records whether `Mibayy/token-savior` should be integrated into token-reduce.

## Verdict

Integrate it as an optional structural accelerator, not as a replacement for token-reduce.

## Verification

- Source reviewed: `https://github.com/Mibayy/token-savior`
- Upstream tests run locally:
  - `cd /tmp/token-savior-bench && uv run --with pytest --with mcp pytest -q`
  - result: `416 passed`
- Local benchmark run:
  - `uv run --with tiktoken scripts/benchmark-companion-tools.py --repo-root . --token-savior-repo /tmp/token-savior-bench`

## Why

- It is materially better for exact symbol lookup and structural impact questions.
- It is not better as a general first-move discovery system for broad topic or fuzzy repo navigation.
- token-reduce still owns:
  - repo-agnostic kickoff discipline
  - hook enforcement
  - broad-topic search fallback
  - no-extra-dependency default workflow

## Measured Results

Benchmarked in this repo on four representative tasks:

| Task | token-reduce | token-savior | Outcome |
|------|--------------|--------------|---------|
| exact symbol lookup (`discovery_hint`) | `234` tokens / `1398.56 ms` | `56` tokens / `196.31 ms` | token-savior clearly wins |
| constant lookup (`STATE_TTL_SECONDS`) | `35` tokens / `573.36 ms` | `231` tokens / `195.68 ms` | token-reduce stays cheaper |
| impact analysis (`prompt_requires_helper`) | `25` tokens / `570.61 ms` | `82` tokens / `191.76 ms` | token-savior adds meaningful structure; keep as optional |
| broad topic search (`hook enforcement system`) | `1230` tokens / `286.48 ms` | `106` tokens / `250.77 ms` | token-savior output was cheaper but low-relevance |

Interpretation:

- `token-savior` is the better backend when the symbol is already known and the user needs exact structure or dependency answers.
- `token-savior` should not replace `token-reduce-paths.sh` for ambiguous repo exploration, because its broad text search can surface benchmark/eval noise instead of the canonical implementation files.
- For some simple constant lookups, `token-reduce` remains the cheapest path because the existing helper returns only a path hint or tiny fallback.

## Recommended Consumption Model

Use `scripts/token-reduce-structural.py` only when:
- the exact symbol/class/function name is already known
- the user asks "what depends on X" or "what breaks if I change X"

Do not use it as the default kickoff for vague prompts like "find the auth flow" or "explore the hook system".

## Integration Plan

1. Keep `token-reduce-paths.sh` and `token-reduce-snippet.sh` as the default discovery workflow.
2. Route exact symbol and dependency questions through `scripts/token-reduce-structural.py`.
3. Treat `token-savior` as an optional install, not a required dependency.
4. Reuse the benchmark harness before adopting future companion tools.
