# Worktree Deploy Sync — closing the stale-`.worktrees/main` gap

**Why this doc exists.** There are **two independent deploy targets**, and both
lag `origin/main` after a normal PR merge:

1. **The skill content** — `~/.claude/skills/token-reduce -> <repo>/.worktrees/main`
   (a git worktree). Used by the skill and by sibling repos that symlink it.
2. **The per-session hook gate (the important one)** — `~/.claude/settings.json`
   points PreToolUse/UserPromptSubmit at a **separate copy** under
   `~/.claude/hooks/token-reduce/*.py`, written by `scripts/setup.sh`. **This
   copy — not `.worktrees/main` — is what actually gates every session's tool
   calls.** It is a plain `cp`, so it does not track the repo at all.

`.worktrees/main` is a *checked-out working tree*, not a moving pointer at
`origin/main`; and the `~/.claude/hooks/` copy is a snapshot from the last
`setup.sh` run. Merging a PR to `origin/main` therefore does **not** reach live
sessions until **both** are refreshed. `references/skill-propagation-process.md`
assumes all release work happens *inside* `.worktrees/main` (so it stays current
organically) and never mentions the `~/.claude/hooks/` copy at all. When work is
done in a separate worktree and squash-merged — the normal case — nothing
advances either target, and sessions silently run stale hook logic.

> **Root anomaly (flag for operator):** the top-level checkout
> `/home/agents/workspace/token-reduce-skill` is itself on branch `main`, and a
> branch can only be checked out in one worktree. So `.worktrees/main` is *forced*
> into detached HEAD and **will silently re-drift after every merge**. The durable
> fix is to resolve the double-`main` checkout (e.g. keep the top-level on a
> throwaway branch and let `.worktrees/main` own `main`), so a normal
> `git -C .worktrees/main pull` works. Until then the sync below is detached.

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

# 2. Fast-forward to the merged fixes. The worktree MUST stay detached, because
#    the top-level checkout holds the `main` branch (see "Root anomaly" above) —
#    `git switch -C main origin/main` errors with "'main' is already used by
#    worktree". Use --detach:
git fetch origin
git checkout --detach origin/main

# 3. Verify the deployed skill tree is the intended version.
grep -c "except Exception" scripts/enforce-token-reduce-first.py     # fail-open present (>=5)
grep -q is_non_discovery_command scripts/enforce-token-reduce-first.py && echo over-block:present
./scripts/token-reduce-manage.sh validate

# 4. Confirm the symlink still resolves.
readlink -f ~/.claude/skills/token-reduce
```

### Also refresh the per-session hook gate (`~/.claude/hooks/`)

`.worktrees/main` is only the skill content. The hooks that gate tool calls are
the **separate copy** at `~/.claude/hooks/token-reduce/`. Refresh it too:

```bash
# Canonical: re-run the installer (idempotent since #79 — writes the hardened
# fail-open wrapper and copies ALL helper modules).
<repo>/.worktrees/main/scripts/setup.sh

# Or, surgically (what the 2026-08-26 live fix did): copy the entrypoints +
# helpers and confirm ~/.claude/settings.json uses the #70 fail-open wrapper
# (`timeout 20 uv run "$T"; ec=$?; [ "$ec" -eq 2 ] && [ -f "$T" ] && exit 2; exit 0`).
for f in enforce-token-reduce-first.py remind-token-reduce.py token_reduce_state.py \
         token_reduce_telemetry.py token_reduce_config.py command_rewrites.py coverage_patterns.py; do
  cp "<repo>/.worktrees/main/scripts/$f" ~/.claude/hooks/token-reduce/$f
done
```

**Note:** Claude Code caches hook config at **session start**, so a running
session keeps the old behavior — verify a refresh by invoking the deployed hook
as a subprocess, or from a *new* session. The PR #70 `timeout` + `ec==2 && -f`
fail-open wrapper only protects sessions once it is present in *both* the deployed
tree's `.claude/settings.json` and the global `~/.claude/settings.json`.

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
