# Shrink plan: token-reduce (2026-11-08)

Before: 16,912 script lines (64 files) + 306 MCP + 8,649 test lines (57 files) + ~5,100 doc lines.
Target: about 250 code lines, about 120 test lines and about 150 doc lines.

The evidence below comes from 30 days of transcripts (3,800 Claude and Codex session files,
2026-10-09 to 2026-11-08), the central hook log `~/.local/share/token-reduce/events.jsonl`
(2026-10-31 onward, 28,469 hook calls) and the per-repo helper logs
(`<repo>/artifacts/token-reduction/events.jsonl`, 211 files). The scan script is not
committed. Counts were re-run by hand.

## 1. Jobs the tool does, with usage evidence

| # | Job | 30-day evidence | Verdict |
|---|-----|-----------------|---------|
| J1 | **Path finder**: give query words, get up to 20 candidate files | 465 Codex calls of bare `token-reduce-paths` (PATH wrapper); about 36 Claude calls; 529 `helper_invocation` events across 211 repos | **Keep. This is the product.** |
| J2 | **Aggregate-root guard**: when run from `$HOME` or `~/workspace`, do a bounded search that skips private dirs (`agent-memory`, `secrets`, `.ssh`, `*holdout*` and the like) | 197 calls from `~/workspace` and 37 from `$HOME` | **Keep.** It stops private files from surfacing fleet-wide. |
| J3 | **Snippet**: paths plus a few `file:line:text` hits | about 6 Claude calls | Keep. It is ~10 lines on top of J1. |
| J4 | `token-reduce-adaptive` (chooses the paths or snippet tier) | 15 Codex calls, 17 events | Keep the name as an alias of `paths`. Drop the tiering logic. |
| J5 | **Symlink-find hint**: a PreToolUse Bash hook. When `find` targets a symlinked dir with no trailing slash, it returns 0 results silently, so the hook adds a context line | Emitted 8 times since 2026-10-31. It is the only hook rule that writes anything to the model. | **Keep.** It prevents silent wrong answers (see memory `find symlink trap`). |
| J6 | Every other hook rule (repeat_broad, read_unbounded, broad_bash, exploratory_grep, catastrophic, grep_no_head_limit, broad_glob, glob_explosion) | 1,545 matches, 0 advised. Since operator ruling 2026-10-28 the hook never blocks, and these rules only write telemetry. | **Drop.** Nobody reads the output (see J7). |
| J7 | Telemetry, measure, review, adoption, release-gate, caliper, cost playbook, benchmarks, review-pass, doctor, dependency-health, settings and setup wizard | `token-reduce-manage.sh` has about 53 calls, almost all inside this repo's own dev sessions (`status` 13, `validate` 2). No timer, cron or other repo reads the logs. | **Drop.** These are tools for maintaining the tool. |
| J8 | qmd semantic backend, plus the 6-hourly cron `qmd-refresh-all.sh` → `qmd-refresh-workspace.sh` | qmd answered 4 of 529 path calls (0.8%). In the other 99%, rg answered after qmd was found missing, missing a collection, or timed out (timeouts reached **237 s**; rg alone answers in 23 ms). Only 1 direct `qmd search` in 30 days. The refresh script updates a fixed list of `repo-*` collections, and its log shows `indexed=0 updated=0`. The `agent-*` memory collections are refreshed by other tooling and are not touched. | **Drop** the backend, the cron line and the refresh scripts. |
| J9 | MCP server (`mcp/server.mjs`), loaded as a skills-dir plugin through `.claude-plugin/plugin.json` | **0 tool calls** in 30 days, yet it starts one `node` process per Claude session | **Drop.** |
| J10 | SessionStart update check | Prints only when behind; `auto_update=false`; deploy is manual | **Drop.** Deploy is the explicit step in §6. |
| J11 | `token-reduce-review` skill | `skillOverrides: off` | Drop. |
| J12 | Skill text (`SKILL.md`) | `token-reduce: name-only`; 2 Skill invocations in 30 days | Keep, trimmed to about 30 lines. |
| J13 | Docs site `docs/`, `references/` (4,774 lines), `llms.txt`, `.claude/*-state.md` (last touched in June) | GitHub Pages is not enabled (API returns 404); no callers | Drop. |

## 2. External contracts (every caller outside the repo)

A host-wide grep (`rg` over `~/.local/bin`, `~/.config`, `~/.claude/{skills,hooks,agents}`, `~/.codex`,
`~/workspace`, `~/.sessions` and crontab) found only these code callers. Everything else is prose in
other repos' AGENTS.md/docs that names `token-reduce-paths`, and keeping that command keeps those docs true.

| Caller | Argv / input it relies on | Output it relies on | Plan |
|---|---|---|---|
| `~/.local/bin/token-reduce-paths` (Codex, agents) | `token-reduce-paths <words...>`, cwd = repo or aggregate root | newline list of paths; `./rel` inside a repo, absolute at aggregate roots; exit 0 | keep; exec new script |
| `~/.local/bin/token-reduce-snippet` | `<words...>` | paths, blank line, `file:line:text` | keep |
| `~/.local/bin/token-reduce-adaptive` | `<words...>` | path list | alias of paths |
| `~/.local/bin/token-reduce-{manage,settings,setup,structural,telemetry-sync,updates}` | any | none parsed | replace with a 2-line pointer that exits 2 |
| `scripts/token-reduce-paths.sh` / `-snippet.sh` (named in CLAUDE.md, AGENTS.md and the skill) | same as above | same | keep as symlinks to the new script |
| `~/.claude/skills/token-reduce` → `.worktrees/main`; `~/.codex/skills/token-reduce` → same | SKILL.md frontmatter | — | keep; trimmed SKILL.md |
| `~/.claude/settings.json` PreToolUse Bash/Glob/Grep/Read → `~/.claude/hooks/token-reduce/enforce-token-reduce-first.py`; PostToolUse Glob → `warn-glob-explosion.py`; SessionStart → `token-reduce-update-check.sh` | hook JSON on stdin | exit 0; optional `hookSpecificOutput.additionalContext` | keep one Bash entry pointing at the new hook; remove the other 5 entries (dated backup) |
| `.claude-plugin/plugin.json` (loaded as a skills-dir plugin; starts the MCP server) | — | — | delete together with `mcp/`, or every session would get a failed MCP server |
| This repo's own `.claude/settings.json` (runs `scripts/enforce-token-reduce-first.py` for Bash, Glob, Grep and Read; stderr not silenced) | — | — | delete in PR 2. The global hook covers this repo. |
| `agents/openai.yaml` (Codex skill card) | names `scripts/token-reduce-paths.sh` | — | keep |
| `paths` output details | `No results found.` + exit 0 on a miss; `--help` (called by Codex) | — | keep both. The `# brain-hint:` first line and the stderr qmd notes go away. |
| crontab `0 */6 * * * ~/.local/bin/qmd-refresh-all.sh` | — | log only | remove the line (crontab backup); archive the wrapper |
| `Etc-mono-repo*` `.claude/settings.json` (3 checkouts) → `skills/token-reduce/scripts/{remind-token-reduce,advise-token-reduction,enforce-glob-scope}.py` | raw invocation | — | 2 of 3 targets are already gone; no session in those repos in 30 days (no project dir). Drop the last shim and record it. |

Running sessions cache their hook config at start. Their old Bash, Glob, Grep and Read wrappers end with `2>/dev/null; exit 0`, so they stay silent and harmless once the old file is moved. The PostToolUse wrapper sends all output to `/dev/null` and is just as safe. The SessionStart script `token-reduce-update-check.sh` is different: it would print a uv error on compact or resume. So it stays in place as a one-line `exit 0` until those sessions roll over.

## 3. Native features that replace code (checked on the installed binaries)

- **Claude Code 2.1.319**: the built-in Grep and Glob tools run ripgrep. They cover J1 and J3 for Claude, which explains why Claude calls the helper only about 36 times a month. The PreToolUse `hookSpecificOutput.additionalContext` field without a permission decision is in use today (the J5 events). After deploy I will re-check it in a fresh `claude -p` session.
- **`skillOverrides`** in `settings.json` already sets the skill to name-only. No reminder hook or prompt injection is needed.
- **rtk** (an existing PreToolUse hook) already compacts Bash output. That covers what the "broad output" telemetry was measuring.
- **ripgrep 14.1.0**: `--files`, `-l`, `--no-config --no-follow --max-depth --max-filesize` and globs cover all search and bounding needs. No qmd and no Python ranking are needed.
- **Codex 0.167.0**: no hook is wired. It uses the PATH command, so it needs nothing more.

## 4. Line budget

| File | Budget | Role |
|---|---|---|
| `scripts/token-reduce.sh` | ≤150 | `paths` / `snippet` / `--help`; dispatches on `$0` basename (`*paths*`, `*snippet*`, `*adaptive*` → paths) |
| `scripts/token-reduce-{paths,snippet,adaptive}.sh` | symlinks | keep the path contract |
| `scripts/symlink-find-hint.py` | ≤50 | J5 hook; stdlib only; fail open; exit 0 always |
| `scripts/deploy.sh` | ≤50 | diff-then-copy hook, rewrite PATH wrappers, print diffs; idempotent |
| `tests/test_e2e.sh` (or one pytest file) | ≤120 | temp git repo + temp HOME; real rg; real hook stdin |
| `SKILL.md`, `README.md`, `AGENTS.md` (rules kept), `CLAUDE.md` | ≈150 total | |

Total code ≤250 lines, against 17,218 today.

**Ranking (J1)**: split the query into words, drop stopwords, keep words of 3+ chars, and OR them into one case-insensitive pattern.
1. Path hits: `rg --files` filtered by the pattern, scored by how many distinct words match the path.
2. Content hits: `rg -c`, scored by match count. They fill any slots left after the path hits.
3. Output the top 20, deduped.

This replaces `rank_paths.py`, the dispatcher, the event-history reranker and the per-repo special cases (the "hook focus" and "benchmark" filters were tuned for this repo only).

**Aggregate mode (J2)**: same rules as today. No symlink following, no rg config, no ignore files, depth 3 under `~/workspace` (1 at `$HOME` plus top-level `*.md`), files of 1 MB or less, the same extension allowlist and private-name excludes plus `*holdout*`, absolute paths, and a stderr note to cd into a repo.

## 5. Dropped and why (summary)

- Telemetry in every form: the central log, per-repo `artifacts/token-reduction/events.jsonl`, payload-key dumps and session state dirs. It had no reader outside this repo's own review scripts.
- All hook rules except J5. They have been non-blocking since 2026-10-28 and only wrote telemetry.
- qmd backend and refresh cron: 0.8% hit rate and multi-minute stalls.
- MCP server and plugin manifest: 0 calls, plus one node process per session.
- Manage, measure, review, release-gate, benchmarks, caliper, cost, adoption, doctor, settings, setup wizard and update-check: dev-only tooling with no external caller.
- `references/`, `docs/`, `llms.txt`, `.claude/*-state.md`, `package.json` and 57 test files that pin removed behavior.
- Kept on disk but no longer written: `~/.config/token-reduce/config.json`, `~/.local/share/token-reduce/`, and the per-repo `artifacts/token-reduction/` and `.claude/token-reduce-state/` dirs. Those dirs sit inside other people's repos, so I leave them alone.

## 6. Migration and rollback

Order matters. The SessionStart wrapper and the cron line both exec files from `.worktrees/main`, so they must be retired before `.worktrees/main` advances past the deletions.

1. **PR 1 (beside the old code):** add `token-reduce.sh`, `symlink-find-hint.py`, `deploy.sh` and the e2e test without deleting anything. Run the existing `validate` and `release-gate` and paste the output in the PR. Gate the new code on real data:
   - **Paths:** compare old and new path lists on 10 real Codex queries, in this repo, a Python repo, `~/workspace`, `$HOME` and a dir with a private name.
   - **Hook replay:** use a few thousand real Bash commands from transcripts plus the `command` fields of per-repo `hook_warn`/`hook_block` events. Run the old hook under a temp HOME and cwd so it writes no telemetry into real repos. The new hook must stay silent on everything except a symlinked-dir `find` without a trailing slash, and must expand `~` and `$HOME`.
2. **Merge PR 1, then deploy, while the old files still exist.**
   - `git -C .worktrees/main checkout --detach origin/main`.
   - Diff, then copy the hook into `~/.claude/hooks/token-reduce/`. Archive the old dir to `~/.claude/hooks/token-reduce.bak-20261108/`. Leave the old file names in place: running sessions still call them, and their wrappers fail open. Set `token-reduce-update-check.sh` to `exit 0`.
   - Diff, then rewrite the `~/.local/bin` wrappers (old ones archived to `~/backups/token-reduce-20261108/bin/`).
   - Edit `~/.claude/settings.json` with Python JSON (backup at `~/.claude/settings.json.bak-token-reduce-20261108`). Remove the Glob, Grep, Read, PostToolUse-Glob and SessionStart entries and repoint Bash.
   - Run `crontab -l > ~/backups/token-reduce-20261108/crontab`, then drop the qmd line.
3. **Live check:** in a fresh `claude -p` session, run a normal Bash call (no output from our hook) and `find ~/.claude/projects -name x` (the hint appears). Run `token-reduce-paths` from Codex's PATH in a real repo and at `~/workspace`.
4. **PR 2:** delete the old files, `.claude-plugin/`, `mcp/` and this repo's `.claude/settings.json`; trim the docs. Strip the AGENTS.md and CLAUDE.md rules that name removed commands (validate, release-gate, measure, review, Headroom, Caliper), and state that exception in the PR body. CI only checks attribution, so the e2e test runs locally and its output goes in the PR. One Claude review (Sonnet) is named in the PR body. Merge on green CI, advance `.worktrees/main` again, and repeat the live check.
5. **Rollback:**
   - `git -C .worktrees/main checkout --detach b3f1f89`.
   - `cp -a ~/.claude/hooks/token-reduce.bak-20261108/. ~/.claude/hooks/token-reduce/`.
   - `cp ~/.claude/settings.json.bak-token-reduce-20261108 ~/.claude/settings.json`.
   - `crontab ~/backups/token-reduce-20261108/crontab`.
   - Restore the wrappers from `~/backups/token-reduce-20261108/bin/`.
   The old code also stays in git history at `b3f1f89`.

## Not touched

The other worktrees of this repo hold other people's work and stay as they are: `.claude/worktrees/agent-ab25df4977bc5deb9`, `~/worktrees/codex-qmd-registration-guard-20261023`, `~/worktrees/token-reduce-aggregate-fallback-1025`, `~/worktrees/token-reduce-home-guard-20261024`, `~/worktrees/token-reduce-qmd-lookup-20261024`, `~/worktrees/tr-enhance-1028b` (+ nested `elegant-bhaskara-af21f8`), `~/worktrees/tr-hygiene-1031`, `~/worktrees/tr-nonblocking-1028`, `~/worktrees/tr-pr-1026` and `~/worktrees/tr-telemetry-1031`. The `Etc-mono-repo*` settings and bus infrastructure also stay as they are.
