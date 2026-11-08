# token-reduce

Small helpers that keep agents from scanning whole repos to find one file.

| Piece | What it does |
|---|---|
| `scripts/token-reduce.sh` | `paths` / `snippet`: ranked candidate files for a few query words (rg only) |
| `scripts/token-reduce-{paths,snippet,adaptive}.sh` | symlinks; the name picks the verb (`adaptive` = `paths`) |
| `scripts/symlink-find-hint.py` | Claude Code PreToolUse hook: warns when `find` targets a symlinked dir without a trailing slash, which silently returns nothing |
| `scripts/deploy.sh` | shows diffs (default) or installs (`--apply`) the hook copy and the `~/.local/bin` wrappers |
| `SKILL.md` | the skill text agents see |

## Install / deploy

```bash
ln -s "$PWD" ~/.claude/skills/token-reduce      # once; Codex: ~/.codex/skills/token-reduce
scripts/deploy.sh            # review the diffs
scripts/deploy.sh --apply    # backs up what it replaces to ~/backups/token-reduce-<date>/
```

Then wire the hook once in `~/.claude/settings.json`:

```json
{"matcher": "Bash", "hooks": [{"type": "command",
  "command": "timeout 5 /usr/bin/python3 ~/.claude/hooks/token-reduce/symlink-find-hint.py 2>/dev/null; exit 0"}]}
```

On the live host `~/.claude/skills/token-reduce` points at `.worktrees/main`, a detached checkout. After a merge, run `git -C .worktrees/main checkout --detach origin/main`, then `scripts/deploy.sh --apply`. Running sessions keep their hook config until they restart.

## Test

```bash
bash tests/test_e2e.sh
```

## History

Until 2026-11-08 this repo also held a qmd backend, an MCP server, telemetry, benchmarks and many hook rules (about 17k lines). Usage evidence and the reasons each part was dropped: `SHRINK-PLAN.md` and `SHRINK-REPORT.md`. The old code is at commit `b3f1f89`.
