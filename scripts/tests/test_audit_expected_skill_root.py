"""Regression test for the expected_skill_root false-positive bug.

Root cause: `build_rows()` computed `expected_root` as
`Path(__file__).resolve().parents[1]` -- i.e. wherever the currently-running
copy of `audit_workspace_skills.py` happens to live -- rather than the
actual canonical install location every repo symlinks to
(`~/.claude/skills/token-reduce`). Any invocation from a copy other than the
one every repo points at (a Claude Code session-scoped worktree under
`~/.claude/worktrees/<session>`, a stale top-level checkout, etc.) makes
every single repo in the workspace spuriously fail the `wrong_skill_root`
check, even when they're all correctly symlinked to the real canonical
target. Verified live: running from a session worktree reported
`expected_skill.root` as the session worktree itself and
`repos_symlinked_to_expected_skill_root: 0` / `wrong_skill_root` for 62
repos that were, on manual inspection, all correctly symlinked to
`.worktrees/main`.
"""
from __future__ import annotations

import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from audit_workspace_skills import resolve_expected_skill_root  # noqa: E402


def test_prefers_global_skill_symlink_target(tmp_path: Path) -> None:
    """When ~/.claude/skills/token-reduce exists, it's the expected root --
    not wherever the audit script itself happens to be running from."""
    fake_home = tmp_path / "home"
    canonical_repo = tmp_path / "workspace" / "token-reduce-skill" / ".worktrees" / "main"
    canonical_repo.mkdir(parents=True)
    skills_dir = fake_home / ".claude" / "skills"
    skills_dir.mkdir(parents=True)
    (skills_dir / "token-reduce").symlink_to(canonical_repo)

    result = resolve_expected_skill_root(home=fake_home)

    assert result == canonical_repo.resolve()
    # Specifically NOT the audit script's own location (the historical bug).
    assert result != Path(__file__).resolve().parents[1].resolve()


def test_falls_back_when_global_symlink_missing(tmp_path: Path) -> None:
    """No global install (e.g. a bare test env) -- fall back to the
    script's own repo root rather than crashing."""
    fake_home = tmp_path / "home-no-skill"
    fake_home.mkdir()

    result = resolve_expected_skill_root(home=fake_home)

    assert result == SCRIPT_DIR.parent.resolve()


def test_falls_back_when_symlink_is_broken(tmp_path: Path) -> None:
    """A dangling symlink (target deleted) must not crash the audit --
    fall back same as a missing install."""
    fake_home = tmp_path / "home-broken-skill"
    skills_dir = fake_home / ".claude" / "skills"
    skills_dir.mkdir(parents=True)
    (skills_dir / "token-reduce").symlink_to(tmp_path / "does-not-exist")

    result = resolve_expected_skill_root(home=fake_home)

    assert result == SCRIPT_DIR.parent.resolve()
