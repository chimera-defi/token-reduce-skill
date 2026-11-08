# Shrink report: token-reduce (2026-11-08)

Plan and usage evidence: `SHRINK-PLAN.md`. Old code: commit `b3f1f89`. Landed in two PRs: #122 (new code beside old, then deploy) and this one (delete old).

## Line counts (tracked files, symlinks excluded)

| | Before (`b3f1f89`) | After | 
|---|---:|---:|
| Code (scripts, mcp, plugin, web page) | 17,797 | 186 |
| Tests | 8,649 | 67 |
| Docs (`*.md`, llms.txt) | 5,289 | 377 (incl. this report and the plan) |
| Config (json/yaml/txt) | 844 | 22 |
| CI (`.githooks`, workflows; unchanged) | 280 | 280 |
| **Total** | **32,859** | **932** |
| Files | 203 | 21 |

Code after: `token-reduce.sh` 97, `symlink-find-hint.py` 61, `deploy.sh` 28.

## Kept, and why

- **`token-reduce-paths` / `-snippet` / `-adaptive`** (one script, verb from argv or basename). Codex called `token-reduce-paths` 465 times in 30 days; Claude about 40. Now rg only: ranked by how many query words the path matches, then content hits. From `$HOME`/`~/workspace` it does a bounded search with private-name excludes (secrets, agent memory, holdouts, dotfile config dirs). Replay of 40 real queries: 0 timeouts, 0 private paths, p50 0.84 s, max 1.48 s (the old script fell back to rg in 99% of calls and hit 120 s timeouts on large repos).
- **Symlinked-dir `find` hint** (`symlink-find-hint.py`). The only hook rule that ever advised in the 30-day central log. Adds `additionalContext`, never blocks, always exits 0. Replay over 5,521 real Bash commands: 0 non-zero exits, 9 hints, all true positives, p99 54 ms. Handles `~`, `$HOME`, `rtk`/`sudo`/`timeout N` prefixes, `bash -c '...'`, `$(...)`, multi-line commands, and ignores heredoc bodies.
- **`deploy.sh`**: diff-first install of the hook copy and `~/.local/bin` wrappers, with timestamped backups.
- **`tests/test_e2e.sh`**: 35 cases with real rg and real hook stdin in a temp HOME.
- `SKILL.md`, `README.md`, `AGENTS.md` (attribution, commit format, PR rules, delegate block), `CLAUDE.md`, `agents/openai.yaml`, `.githooks`, `.github`.

## Dropped, and why

- **qmd backend, collections refresh and cron line**: answered 0.8% of path calls; the rest fell back to rg after up to 237 s. The 6-hourly refresh reported `indexed=0 updated=0`.
- **MCP server and `.claude-plugin/`**: 0 calls in 30 days; one node process per session.
- **Multi-rule PreToolUse enforcer, Glob/Grep/Read hooks, PostToolUse glob warning, SessionStart update check**: 28,469 hook calls, 1,545 rule matches, nothing advised except the symlink rule kept above.
- **Telemetry, central log, measure/review/improve-adoption, benchmarks, release gate, validate, Caliper/Headroom companions, dashboards (`docs/`)**: no reader outside this repo's own review scripts. The AGENTS.md/CLAUDE.md rules that required running them were removed with them (stated exception to the old "run release-gate before merge" rule).
- **`skills/token-reduce-review`, `references/`, `llms.txt`, `package.json`, `.claude/*` state files and repo `.claude/settings.json`**: documented or wired the removed parts.
- **`remind-token-reduce.py` no-op shim**: the one remaining raw consumer (an unrelated monorepo's `.claude/settings.json`, three checkouts) had no sessions in 30 days, and its other two token-reduce hook targets were already missing. Its UserPromptSubmit hook will now show a non-blocking "file not found" error if a session starts there; fix is to delete those three entries in that repo.

## Deploy (done after #122, by diff, with backups)

- `.worktrees/main` advanced to `origin/main`.
- `~/.claude/hooks/token-reduce/` archived to `token-reduce.bak-20261108/`; new hook copied in; old file names left so already-running sessions keep failing open; `token-reduce-update-check.sh` set to `exit 0`.
- `~/.local/bin` wrappers: paths/snippet/adaptive unchanged; manage, settings, setup, structural, telemetry-sync and updates now print a "was removed" line and exit 2. Old wrappers backed up to `~/backups/token-reduce-20261108/bin/`.
- `~/.claude/settings.json` (global) edited with a dated backup `~/.claude/settings.json.bak-token-reduce-20261108`: removed the Glob/Grep/Read PreToolUse, PostToolUse Glob and SessionStart entries; Bash now runs only the symlink hint. All non-hook keys unchanged.
- Crontab backed up to `~/backups/token-reduce-20261108/crontab`; qmd refresh line removed; its wrapper archived.
- Live check in a fresh `claude -p` session: a normal Bash call passed with no hook output; `find ~/.claude/projects -name ...` received the hint.

Rollback: `SHRINK-PLAN.md` section 6, step 5.

## Decided

- Two PRs: new code beside old first, deploy while old files still existed, then delete.
- `adaptive` kept as an alias of `paths` (Codex called it 15 times).
- Aggregate roots get a bounded search rather than a refusal.
- Hook stays advisory (`additionalContext`), never blocks.
- Removed verbs get exit-2 stubs instead of disappearing, so callers see a pointer.
- Squash-merge, branches kept.
- Review: Claude Sonnet 5.5 subagent (Codex out of quota, Fable paused).

## Left undone / for others

- Stale `skillOverrides` key `token-reduce:token-reduce-review` in the global settings (harmless; no plugin now).
- The monorepo raw hook entries noted above.
- Other worktrees and branches of this repo were not touched: `.claude/worktrees/agent-ab25df4977bc5deb9`, `~/worktrees/codex-qmd-registration-guard-20261023`, `token-reduce-aggregate-fallback-1025`, `token-reduce-home-guard-20261024`, `token-reduce-qmd-lookup-20261024`, `tr-enhance-1028b` (+ nested `elegant-bhaskara-af21f8`), `tr-hygiene-1031`, `tr-nonblocking-1028`, `tr-pr-1026`, `tr-telemetry-1031`. Those working on qmd, telemetry, the enforcer or aggregate fallback are now obsolete against `main`; their owners decide.
- `validate` exited 1 on the old code only because the benchmark artifacts were 65 days stale; moot now.
