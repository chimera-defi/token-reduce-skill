# Token Reduction Guide

**Benchmarked:** 2026-02-07 with tiktoken on real repo content (642 files, 234 .md)
**Auto-active:** Via local workspace rules or direct helper invocation
**Validated:** `python3 /path/to/quick_validate.py /path/to/token-reduce-skill`
**Scope:** reusable runtime skill package

---

## Quick Reference

| Strategy | Measured Savings | Use |
|----------|-----------------|-----|
| Concise responses | 89% | Always |
| QMD BM25 search | 99% vs naive file reads | Finding which files to read |
| Targeted reads | 33% | Large files |
| Sub-agents | 15-30% | Complex exploration (>5 files) |
| Parallel ops | 20% | Multi-step tasks |

**Removed (benchmarked, not effective):**
- ~~MCP CLI bulk file reads~~ — adds 117% token overhead (JSON wrapping)
- ~~MCP CLI memory~~ — redundant with Claude Code built-in memory (`~/.claude/projects/*/memory/`)
- ~~QMD vector/combined search~~ — 15-175 seconds per query, impractical

---

## Decision Tree (Fastest First)

1. **Unknown location or broad concept?** → `../scripts/token-reduce-paths.sh topic words` first for paths only. If QMD misses, the helper falls back to repo-scoped `rg` in the same command.
2. **Known file/keyword?** → `Grep` tool (or `rg -g`) then targeted read.
3. **Need one ranked excerpt after path kickoff?** → `../scripts/token-reduce-snippet.sh topic words`.
4. **Large file context?** → `Read` with offset/limit (or `head/tail/sed` in Cursor).
5. **No `rg`?** → `git grep` scoped to path.

`rg --files .` is not counted as good discovery here. It is still a broad repo inventory pass.

## Guardrails (Always On)

- Cap tool output to ~120 lines; use head/tail/sed for longer content
- Summarize multi-file reads; never paste full files unless asked
- Avoid full reads for files >300 lines
- Prefer `rg --files -g` before directory_tree
- Use `rg -g` scoped searches; fallback to `git grep` if `rg` missing

---

## 1. Concise Communication (89%)

Bad: "I understand you'd like me to check..."
Good: `[uses Read]` Bug on line 47 — missing return.

**Measured:** 142 tokens → 13 tokens

---

## 2. QMD BM25 Search (99% vs naive)

Find which files to read before loading them into context.

```bash
# One-time setup (2 seconds for 212 md files, no embeddings needed)
qmd collection add /path/to/repo --name my-repo

# Find relevant files (700ms-2.7s, returns paths + scores)
qmd search "topic" -n 5 --files           # path kickoff

# Get ranked snippets only when needed
../scripts/token-reduce-snippet.sh topic words
qmd search "topic" -n 1                    # one ranked excerpt

# Read specific sections of found files
qmd get filename.md -l 50 --from 100       # 748ms

# Multi-file snippet retrieval
qmd multi-get "file1.md,file2.md" -l 30    # 710ms, 373 tokens
```

**Measured:** 52,604 tokens (naive grep+cat 10 files) → 512 tokens (QMD top 5 snippets)

**Skip these modes (too slow):**
- `qmd embed` — 11 min setup, 340MB model download
- `qmd vsearch` — 15-111 seconds per query
- `qmd query` — 105-175 seconds per query, downloads 1.28GB model

**Relevance caveat:** BM25 is keyword-based. It struggles with ambiguous terms (e.g., "token" matches both crypto tokens and LLM tokens). For precise searches, use `grep` directly.

---

## 3. Targeted Reads (33%)

```bash
Read file with offset/limit    # Lines 100-150 only
head -50 file.md               # First 50 lines
tail -100 file.md              # Last 100 lines
```

**Measured:** 4,525 tokens → 2,573 tokens

---

## 4. Sub-Agents (15-30%)

Use `Task(subagent_type="Explore")` for:
- Complex research requiring >5 file reads
- Pattern matching across codebase
- Uncertain where information lives

Agent handles file discovery, reading, and analysis — returns only a summary to the main context.

---

## 5. Parallel Operations (20%)

```
Sequential (3 turns): 3,400 tokens
Parallel (1 turn):    2,700 tokens
```

---

## Anti-Patterns

❌ `find . -name "*.ts" | xargs cat`
✅ `qmd search "workspace actor" -n 5 --files` then targeted reads

❌ `ls -R ideas/`
✅ `rg -n -g 'ideas/**/*.md' 'specforge'`

❌ `rg --files . | head -200`
✅ `../scripts/token-reduce-paths.sh specforge` then targeted reads

- Restating user requests
- Narrating tool usage ("Let me read the file...")
- Reading entire files without line limits
- Re-researching what's already known
- Using MCP CLI for file reads (adds JSON overhead)
- Re-reading the same file in one session unless it changed
- Per-file commentary instead of a single summary

---

## Included Runtime Files

- `../scripts/token-reduce-search.sh` — canonical retrieval helper
- `../scripts/token-reduce-paths.sh` — path-only kickoff wrapper
- `../scripts/token-reduce-snippet.sh` — one-snippet wrapper
- `../scripts/advise-token-reduction.py` — broad Bash-scan blocker
- `../scripts/enforce-glob-scope.py` — broad Glob blocker
- `../scripts/remind-token-reduce.py` — prompt-submit steering hook

**Workspace integrations:** consumer Claude/Codex/workspace instructions can point at this package and wire these runtime files in directly.

---

**Version:** 5.1 (2026-03-19 — standalone runtime package)
**Validation:** `python3 /path/to/quick_validate.py /path/to/token-reduce-skill`
