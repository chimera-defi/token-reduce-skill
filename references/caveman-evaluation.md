# caveman Evaluation

This note records whether `JuliusBrussee/caveman` should be integrated into token-reduce.

## Verdict

Integrate it as an **optional companion** for output brevity and memory-file compression.
Do **not** make it a required dependency or the default discovery path.

## Verification

- Source reviewed: `https://github.com/JuliusBrussee/caveman`
- Local validation run (from upstream test corpus):
  - `uv run --with tiktoken /tmp/caveman-bench/caveman-compress/scripts/benchmark.py`
  - result:
    - `claude-md-preferences.md`: `843 -> 421` (`50.1%` saved), valid
    - `claude-md-project.md`: `1615 -> 1100` (`31.9%` saved), valid
    - `mixed-with-code.md`: `1417 -> 1087` (`23.3%` saved), valid
    - `project-notes.md`: `1437 -> 847` (`41.1%` saved), valid
    - `todo-list.md`: `880 -> 646` (`26.6%` saved), valid
- Upstream benchmark harness surface checked:
  - `uv run --with anthropic /tmp/caveman-bench/benchmarks/run.py --dry-run --trials 1`
  - result: harness loads prompts and run plan cleanly without API calls in dry-run mode

## Why

- `caveman` addresses two token classes token-reduce does not directly optimize:
  - output verbosity (response-side tokens)
  - always-loaded memory files (input-side session overhead)
- token-reduce still owns:
  - first-move discovery discipline
  - hook enforcement against broad scans
  - targeted retrieval and fallback behavior

## Recommended Consumption Model

Use caveman only as an opt-in layer:

- response brevity: `/caveman lite` for tighter responses without extreme style drift
- memory compression: `/caveman:compress CLAUDE.md` for repeated-session input savings

Keep default token-reduce behavior unchanged:

- first move remains `./scripts/token-reduce-paths.sh topic words`
- no caveman dependency required for setup or core routing

## Integration Plan

1. Document caveman as an optional companion in `README.md`, `SKILL.md`, and `llms.txt`.
2. Keep attribution explicit alongside QMD and RTK.
3. Preserve companion-tool intake discipline in `references/companion-tools.md`.
4. Re-benchmark if we add any direct runtime adapter in this repo.
