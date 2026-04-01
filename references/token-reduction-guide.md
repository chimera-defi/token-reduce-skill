# Token Reduction Guide

**Benchmarked:** 2026-02-07 with tiktoken on real repo content (642 files, 234 .md)
**Activation:** via local workspace rules or direct helper invocation
**Validation in this repo:** `uv run --with pyyaml /path/to/quick_validate.py /path/to/token-reduce-skill`
**Local benchmark:** `uv run --with tiktoken /path/to/token-reduce-skill/scripts/benchmark-token-reduce.py`
**Scope:** reusable runtime skill package

---

## Quick Reference

| Strategy | Measured Savings | Use |
|----------|-----------------|-----|
| Concise responses | 89% | Always |
| QMD BM25 search | 99% vs naive file reads | Finding which files to read |
| Targeted reads | 33% | Large files (>300 lines) |
| Sub-agents | 15–30% | >5 files or broad exploration (Claude Code) |
| Parallel ops | 20% | Independent lookups |

Removed from the workflow (benchmarked, not effective):
- ~~MCP CLI bulk file reads~~ — adds 117% token overhead (JSON wrapping)
- ~~MCP CLI memory~~ — redundant with built-in workspace memory
- ~~QMD embed / vsearch / query~~ — 11 min / 15–111s / 105–175s per run, too slow

## Local Benchmark

Current artifact: `references/benchmarks/local-benchmark.json`

| Strategy | Tokens | Savings vs broad inventory | Duration |
|----------|--------|----------------------------|----------|
| `broad_inventory` | `259` | baseline | `8 ms` |
| `guidance_scoped_rg` | `25` | `90.3%` | `8 ms` |
| `qmd_files` | `132` | `49.0%` | `253 ms` |
| `token_reduce_paths_warm` | `132` | `49.0%` | `487 ms` |
| `token_reduce_snippet_warm` | `217` | `16.2%` | `732 ms` |

This repo is intentionally small, so an exact scoped `rg` is cheaper than the helper and one ranked snippet can approach broad inventory cost. Treat `token-reduce-snippet.sh` as a follow-up, not the default first move.
The warm helper now matches raw QMD output exactly, so the wrapper is not adding extra payload above QMD on the steady-state path.
The helper also refreshes the QMD collection when the repo's Markdown fingerprint changes, which avoids stale search results after editing the skill docs.
For a better-fit query like `architecture`, the path helper returned `51` tokens against `265` for broad inventory, which is about `80.8%` savings.

## Claude And Codex Spot Check

Spot-checked locally on `2026-03-20` with better-fit prompts for this repo:

- Claude returned `3/3` correct paths. On `2/3` prompts it blocked exploratory tools and redirected toward `../scripts/token-reduce-paths.sh`, but `claude -p` still showed approval stops before the redirected Bash helper actually ran.
- Codex returned `3/3` correct paths and attempted the helper on `2/3`, but it still showed broad-scan behavior on every run.

Interpret that as better Claude hook coverage and only partial Codex routing improvement: the helper path is getting used more often, but host approval settings and Codex-side routing still matter.

Follow-up maintenance work on `2026-03-27` tightened two weak points:

- `remind-token-reduce.py` now extracts prompt text from multiple payload shapes so Claude hook state is less likely to clear incorrectly.
- `token_reduce_state.py` now falls back to a shared `default` pending key so prompt-submit and pre-tool hooks line up more often across session IDs.

The cleanest recent live proof is a Codex spot check that opened with `./scripts/token-reduce-paths.sh adoption token reduction measure python script` and returned `scripts/measure_token_reduction.py` directly. Treat Claude hook coverage as improved but still worth rechecking after host changes.

## Decision Tree

1. Unknown location or broad concept? Use `../scripts/token-reduce-paths.sh topic words` first.
2. Known file or keyword? Use scoped `rg` or a grep tool, then do a targeted read.
3. Need one excerpt after the path kickoff? Use `../scripts/token-reduce-snippet.sh topic words`.
4. Need more context from a large file? Read only the needed section (`Read` with `offset`/`limit`).
5. Search space still broad after two passes? Ask the user to narrow the scope. In hosts that support an exploration sub-agent, delegation is acceptable.

`rg --files .` is still a broad repo inventory pass and should be treated as a violation.

## Guardrails

- Cap tool output to about 120 lines
- Summarize multi-file reads
- Avoid full reads for files over 300 lines
- Prefer scoped `rg -g`
- Fall back to `git grep` if `rg` is unavailable

## Host Enforcement

This package cannot guarantee skill use on its own. The host must wire:

- instructions that tell the agent when `token-reduce` applies
- a prompt-submit hook that steers the first move to `../scripts/token-reduce-paths.sh`
- pre-tool hooks that block broad Bash scans and broad `Glob` patterns

Skills provide intent. Hooks enforce behavior.

## Maintenance Loop

Future agents maintaining this repo should use the evidence loop, not just edit docs or hooks and stop:

```bash
./scripts/token-reduce-manage.sh validate
./scripts/token-reduce-manage.sh measure
./scripts/token-reduce-manage.sh review
```

Use `./scripts/token-reduce-manage.sh benchmark` when helper output or search behavior changes. Review artifacts live under `artifacts/token-reduction/`.

## Companion Backends

Structural tools like `token-savior` can improve exact symbol lookup and dependency analysis, but they should remain optional accelerators rather than replacing the default helper-first workflow.

Use:
- `../scripts/token-reduce-structural.py --project-root . find-symbol ExactSymbol`
- `../scripts/token-reduce-structural.py --project-root . change-impact ExactSymbol`

Keep using `../scripts/token-reduce-paths.sh` as the default first move for broad or fuzzy discovery.

## 1. Concise Communication (89%)

Bad: "I understand you'd like me to check..."
Good: `Bug on line 47: missing return.`

Measured in the source repo: 142 tokens → 13 tokens

## 2. QMD BM25 Search (99% vs naive)

Use QMD to find which files to read before loading them into context.

```bash
qmd collection add /path/to/repo --name my-repo

qmd search "topic" -n 5 --files
../scripts/token-reduce-snippet.sh topic words
qmd search "topic" -n 1
qmd get filename.md -l 50 --from 100
```

Measured in the source repo: 52,604 tokens (naive grep+cat 10 files) → 512 tokens (QMD top 5 snippets)

Skip these modes:
- `qmd embed`
- `qmd vsearch`
- `qmd query`

BM25 is keyword-based. For ambiguous terms, use precise grep patterns instead.

## 3. Targeted Reads (33%)

```bash
head -50 file.md
tail -100 file.md
sed -n '100,150p' file.md
```

Measured in the source repo: 4,525 tokens → 2,573 tokens

## 4. Parallel Operations (20%)

Use parallel lookups when the queries are independent.

## Anti-Patterns

- `find . -name "*.ts" | xargs cat`
- `ls -R ideas/`
- `rg --files . | head -200`
- Restating user requests
- Narrating tool usage
- Reading entire files without line limits
- Re-reading the same file unless it changed
- Per-file commentary instead of one summary

## Included Runtime Files

- `../scripts/token-reduce-search.sh` — canonical retrieval helper
- `../scripts/token-reduce-paths.sh` — path-only kickoff wrapper
- `../scripts/token-reduce-snippet.sh` — one-snippet wrapper
- `../scripts/enforce-token-reduce-first.py` — unified PreToolUse blocker (Bash/Glob/Grep/Read)
- `../scripts/enforce-glob-scope.py` — broad Glob blocker (legacy, now covered by above)
- `../scripts/remind-token-reduce.py` — prompt-submit steering hook

## Install Examples

### Full stack (recommended)

```bash
git clone https://github.com/chimera-defi/token-reduce-skill tools/token-reduce-skill
./tools/token-reduce-skill/scripts/setup.sh
```

### Claude Code plugin

```bash
claude plugin marketplace add chimera-defi/token-reduce-skill
claude plugin install token-reduce@chimera-defi
```

### Codex

```bash
git clone https://github.com/chimera-defi/token-reduce-skill "$CODEX_HOME/skills/token-reduce"
```

Typical entrypoints:
- `./tools/token-reduce-skill/scripts/token-reduce-paths.sh`
- `./tools/token-reduce-skill/scripts/token-reduce-snippet.sh`
- `./tools/token-reduce-skill/scripts/token-reduce-structural.py`
- `./tools/token-reduce-skill/scripts/enforce-token-reduce-first.py`
- `./tools/token-reduce-skill/scripts/remind-token-reduce.py`

---

**Version:** 5.1 (2026-03-19 — standalone runtime package)
**Note:** this repo preserves benchmark summaries, not the original benchmark harness.
