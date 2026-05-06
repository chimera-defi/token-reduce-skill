# Token-Reduce Skill Propagation Process

One-command reference for propagating token-reduce changes across the workspace.

## Source-of-Truth Repo

- **Upstream**: `https://github.com/chimera-defi/token-reduce-skill`
- **Local worktree**: `/root/.openclaw/workspace/dev/token-reduce-skill/.worktrees/main`
- **Skill symlink**: `/root/.agents/skills/token-reduce` → worktree

## Release Workflow

### 1. Validate

```bash
cd /root/.openclaw/workspace/dev/token-reduce-skill/.worktrees/main
./scripts/token-reduce-manage.sh validate
./scripts/token-reduce-manage.sh release-gate
```

**Must pass** `release_gate_pass: true` before merging. If it fails, fix or document the exception.

### 2. Bump Version

Edit `SKILL.md` metadata.version (semver: feat → minor, fix → patch).

### 3. Commit & Push

```bash
git checkout -b feat/<descriptive-name>
git add -A
git commit -m "type(scope): subject [Agent: <MODEL NAME>]" \
  -m "Co-authored-by: Chimera <chimera_defi@protonmail.com>"
git push -u origin feat/<descriptive-name>
```

### 4. Open PR

```bash
gh pr create --title "type(scope): subject" \
  --body "**Agent:** <model name>
**Co-authored-by:** Chimera <chimera_defi@protonmail.com>

## Summary
...

## Original Request
<paste original request verbatim>" \
  --base main --head feat/<descriptive-name>
```

### 5. Propagate to Sibling Repos

```bash
cd /root/.openclaw/workspace/dev/token-reduce-skill/.worktrees/main
./scripts/token-reduce-manage.sh workspace-install --force-relink
```

This updates symlinks and doc blocks across all sibling repos under `/root/.openclaw/workspace/dev`.

### 6. Commit Sibling Doc Changes

For each repo where `workspace-install` reported `changed: true`, stage **only** the doc file it touched:

```bash
cd /root/.openclaw/workspace/dev/<repo-name>
git add AGENTS.md   # or CLAUDE.md
git diff --cached --stat   # verify only the token-reduce block
git commit -m "chore(docs): add token-reduce routing block [Agent: <MODEL NAME>]" \
  -m "Co-authored-by: Chimera <chimera_defi@protonmail.com>"
```

**Do NOT** `git add -A` in sibling repos — they often have unrelated working changes.

### 7. Verify

```bash
cd /root/.openclaw/workspace/dev/token-reduce-skill/.worktrees/main
./scripts/token-reduce-manage.sh workspace-audit
```

Confirm `skill_version_match: true` and `skill_commit_match: true` across all active repos.

## Attribution Rules (Non-Negotiable)

Per `AGENTS.md`:
- Commit author = active agent model identity
- Commit trailer = `Co-authored-by: Chimera <chimera_defi@protonmail.com>`
- PR body must include `**Agent:** <actual model name>` and `**Co-authored-by:** ...`
- Never use placeholder model names

## Files to Never Commit

- `.claude/token-reduce-config.json` — local per-machine config
- `tools/token-reduce-skill/` — nested mirror directory (workspace-install artifact)
- Any benchmark artifact unless `release-gate` explicitly regenerated and synced it

## Post-Ship Checklist

- [ ] `release-gate` passed
- [ ] Version bumped in `SKILL.md`
- [ ] Commit has `[Agent: ...]` and `Co-authored-by` trailer
- [ ] PR created with attribution and `## Original Request`
- [ ] `workspace-install` ran with `--force-relink`
- [ ] Sibling doc changes committed separately
- [ ] `workspace-audit` confirms zero drift
- [ ] `meta-learnings-YYYY-MM-DD.md` written with lessons
