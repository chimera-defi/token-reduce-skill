"""Opus 5.5 guidance regression tests.

Guidance (operator-supplied, takes precedence over the pre-existing
token-reduce ritual-first-move posture): a hook must not block ordinary
targeted work -- reading a known file, a specific grep, git/gh commands,
running tests -- and broad-discovery/audit prompts should be steered toward
delegating to a subagent (Agent tool) rather than only toward a CLI helper.

These tests exercise:

  1. Targeted Bash (git/gh/pytest) is never blocked on a session's first
     tool call.
  2. Targeted Read/Grep/Glob on a known, exact path is never blocked.
  3. Genuinely broad/exploratory Glob/Grep still blocks -- control, proving
     targeted-vs-exploratory classification narrows the gate rather than
     removing it.

(A former section 4 exercised the UserPromptSubmit reminder hook's
subagent-delegation wording. That hook was retired 2026-09-28 -- see
references/worktree-deploy-sync.md -- and removed along with its tests.

The PreToolUse enforcer's "pending" first-move discovery gate -- which used
to apply a stricter, no-warn-grace variant of this classification while a
session had a pending discovery marker -- was removed in the same pass as
dead code, since nothing set the marker once the reminder hook was retired.
The targeted-vs-exploratory classification below is now simply the hook's
only behavior, not one exempted from a gate; the former "_while_pending"
test variants are gone along with the marker they set up.)
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
HOOK = SCRIPTS_DIR / "enforce-token-reduce-first.py"
sys.path.insert(0, str(SCRIPTS_DIR))


def _init_git_repo(path: Path) -> None:
    for args in (
        ["git", "-c", "init.defaultBranch=main", "init", "-q", str(path)],
        ["git", "-C", str(path), "config", "user.email", "test@example.com"],
        ["git", "-C", str(path), "config", "user.name", "test"],
    ):
        subprocess.run(args, check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    _init_git_repo(tmp_path)
    return tmp_path


def _run_hook(payload: dict, repo_root: Path) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["TOKEN_REDUCE_REPO_ROOT"] = str(repo_root)
    env["PYTHONPATH"] = str(SCRIPTS_DIR) + os.pathsep + env.get("PYTHONPATH", "")
    return subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        env=env,
        cwd=str(repo_root),
        timeout=30,
    )


def _bash_payload(command: str, session_id: str) -> dict:
    return {"session_id": session_id, "tool_name": "Bash", "tool_input": {"command": command}}


# --------------------------------------------------------------------------- #
# 1. Targeted Bash (git/gh/tests) never blocked, first call, no state.
# --------------------------------------------------------------------------- #

TARGETED_BASH_COMMANDS = [
    "git status",
    "git diff HEAD~1",
    "git log -5 --oneline",
    "gh pr list --state open",
    "gh pr view 42",
    "pytest scripts/tests/test_rg_exploratory_parsing.py -q",
    "python3 -m pytest scripts/tests/ -q",
]


@pytest.mark.parametrize("command", TARGETED_BASH_COMMANDS)
def test_targeted_bash_not_blocked_on_first_call(repo: Path, command: str) -> None:
    session_id = f"sess-targeted-{hash(command)}"
    result = _run_hook(_bash_payload(command, session_id), repo)
    assert result.returncode == 0, (
        f"targeted command must not be blocked: {command!r}\n"
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    assert "decision" not in result.stdout


# --------------------------------------------------------------------------- #
# 2. Targeted Read/Grep/Glob on a known path not blocked.
# --------------------------------------------------------------------------- #


def test_targeted_read_absolute_path_not_blocked(repo: Path) -> None:
    target = repo / "known_file.py"
    target.write_text("# known file\n")
    session_id = "sess-read"

    payload = {
        "session_id": session_id,
        "tool_name": "Read",
        "tool_input": {"file_path": str(target)},
    }
    result = _run_hook(payload, repo)
    assert result.returncode == 0, result.stdout


def test_targeted_grep_on_known_file_not_blocked(repo: Path) -> None:
    target = repo / "known_file.py"
    target.write_text("def auth():\n    pass\n")
    session_id = "sess-grep"

    payload = {
        "session_id": session_id,
        "tool_name": "Grep",
        "tool_input": {"pattern": "auth", "path": str(target)},
    }
    result = _run_hook(payload, repo)
    assert result.returncode == 0, (
        f"a Grep scoped to one known file must not be gated, got stdout={result.stdout!r}"
    )


def test_targeted_glob_exact_pattern_not_blocked(repo: Path) -> None:
    session_id = "sess-glob"

    payload = {
        "session_id": session_id,
        "tool_name": "Glob",
        "tool_input": {"pattern": "known_file.py"},
    }
    result = _run_hook(payload, repo)
    assert result.returncode == 0, (
        f"a Glob with an exact, non-wildcard pattern must not be gated, got stdout={result.stdout!r}"
    )


# --------------------------------------------------------------------------- #
# 3. Control: genuinely broad/exploratory Glob/Grep still block.
# --------------------------------------------------------------------------- #


def test_broad_glob_still_blocks(repo: Path) -> None:
    session_id = "sess-glob-broad"
    payload = {
        "session_id": session_id,
        "tool_name": "Glob",
        "tool_input": {"pattern": "**/*.py"},
    }
    result = _run_hook(payload, repo)
    assert result.returncode == 2, "a genuinely broad Glob must still gate"


def test_exploratory_grep_no_path_still_blocks(repo: Path) -> None:
    session_id = "sess-grep-broad"
    payload = {
        "session_id": session_id,
        "tool_name": "Grep",
        "tool_input": {"pattern": "auth"},
    }
    result = _run_hook(payload, repo)
    assert result.returncode == 2, "an exploratory Grep with no path must still gate"
