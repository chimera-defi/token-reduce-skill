# Worktree Deploy Sync — closing the stale-`.worktrees/main` gap

**Why this doc exists.** Live Claude/Codex sessions execute the skill through a
symlink chain:

```
~/.claude/skills/token-reduce  ->  <repo>/.worktrees/main   (a git worktree)
```

`.worktrees/main` is a *checked-out working tree*, not a moving pointer at
`origin/main`. Merging a PR to `origin/main` therefore does **not** reach live
sessions until that worktree is fast-forwarded. `references/skill-propagation-process.md`
documents the release + sibling-propagation flow, but assumes all release work
happens *inside* `.worktrees/main` (so it stays current organically). When work
is instead done in a separate worktree and squash-merged on GitHub — the normal
case — **nothing advances `.worktrees/main`**, and it silently runs stale hook
logic. This is the missing step.

## Detecting drift

```bash
cd <repo>/.worktrees/main
git rev-parse --abbrev-ref HEAD          # 'HEAD' == detached (bad sign)
git fetch origin --quiet
git log --oneline -1                      # deployed commit
git log --oneline -1 origin/main          # what should be deployed
git status --short                        # any uncommitted local edits?
```

If the deployed commit != `origin/main`, live sessions are stale.

## Safe sync procedure

`.worktrees/main` may be **detached** and may carry **uncommitted local edits**.
Do not blind-`reset`; preserve the local state as evidence first.

```bash
cd <repo>/.worktrees/main

# 1. Preserve any uncommitted local edits (diff them first; land anything worth
#    keeping via a normal PR, then discard the rest). Never commit-over them blind.
git stash push -u -m "pre-sync-$(date +%Y%m%dT%H%M%SZ) local worktree edits"

# 2. Re-attach to main and fast-forward to the merged fixes.
git fetch origin
git switch -C main origin/main            # re-attaches a detached HEAD onto main

# 3. Verify the deployed hooks are the intended version.
grep -n "except Exception" scripts/enforce-token-reduce-first.py | head   # fail-open present
./scripts/token-reduce-manage.sh validate

# 4. Confirm the symlink still resolves.
readlink -f ~/.claude/skills/token-reduce
```

The primary wedge guard (`.claude/settings.json`, PR #70's `timeout` +
`${CLAUDE_PROJECT_DIR}` anchor + `ec==2 && -f` fail-open wrapper) only protects
live sessions **after** this sync — it lives in the deployed tree.

## Consumer coordination (do this together with the sync)

Sibling repos symlink `~/.claude/skills/token-reduce`, so they pick up the sync
automatically — but their **own** `.claude/settings.json` hook wiring can break
if it references a script that a forward-sync deletes. Known case:

- The `Etc-mono-repo*` variants wire `PreToolUse/Glob -> enforce-glob-scope.py`
  **invoked raw** (no `uv run`, no `timeout`, no `ec==2 && -f` guard).
- `enforce-glob-scope.py` was removed from `main` as dead code. After a
  forward-sync it no longer exists → that hook invocation fails on a missing
  script every Glob call.

Before/with a forward-sync, for each consumer:

```bash
grep -rn "enforce-glob-scope\|enforce-token-reduce-first" <consumer>/.claude/settings.json
```

If a removed script is referenced, either drop that hook entry or re-point it,
**and** adopt the #70 wrapper form (`timeout 20 uv run "$T"; ec=$?;
[ "$ec" -eq 2 ] && [ -f "$T" ] && exit 2; exit 0`) so a missing/renamed script
fails open instead of erroring on every tool call.

## Root-cause summary

The drift is structural, not a one-off: there is no automated step that syncs
`.worktrees/main` after a GitHub merge, and its detached-HEAD + local-edit state
blocks a naive `git pull`. Options to make it durable (pick one):

1. A `token-reduce-manage.sh deploy-sync` subcommand that runs the safe procedure
   above (stash-guard + `switch -C main origin/main` + validate).
2. A post-merge CI/webhook that fast-forwards the worktree.
3. Always doing release work directly in `.worktrees/main` (the original assumed
   model) — brittle, since external-worktree PRs are the norm.
