"""Opus 5.5 guidance regression tests.

Guidance (operator-supplied, takes precedence over the pre-existing
token-reduce ritual-first-move posture): a hook must not block ordinary
targeted work -- reading a known file, a specific grep, git/gh commands,
running tests -- and broad-discovery/audit prompts should be steered toward
delegating to a subagent (Agent tool) rather than only toward a CLI helper.

These tests exercise:

  1. Targeted Bash (git/gh/pytest) is never blocked on a session's first
     tool call, pending or not.
  2. Targeted Read/Grep/Glob on a known, exact path is never blocked, even
     while a broad-discovery prompt has set the session's "pending" marker
     (the F10 fix: Glob/Grep previously got a blanket block while pending,
     unlike Read, which already had this exemption).
  3. Genuinely broad/exploratory Glob/Grep still blocks while pending --
     control, proving the F10 fix narrows the gate rather than removing it.
  4. The UserPromptSubmit reminder concretely surfaces the subagent-delegation
     path (Agent/Explore) for a broad-discovery-looking prompt, not just the
     CLI helper.
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
REMIND_HOOK = SCRIPTS_DIR / "remind-token-reduce.py"
sys.path.insert(0, str(SCRIPTS_DIR))

from token_reduce_state import mark_pending, session_key  # noqa: E402


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


def _make_pending(repo_root: Path, session_id: str) -> None:
    key = session_key({"session_id": session_id})
    mark_pending(repo_root, key, "where is the auth hook defined in this repo")


def _bash_payload(command: str, session_id: str) -> dict:
    return {"session_id": session_id, "tool_name": "Bash", "tool_input": {"command": command}}


# --------------------------------------------------------------------------- #
# 1. Targeted Bash (git/gh/tests) never blocked, first call, pending or not.
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
def test_targeted_bash_not_blocked_on_first_call_non_pending(repo: Path, command: str) -> None:
    session_id = f"sess-targeted-nonpending-{hash(command)}"
    result = _run_hook(_bash_payload(command, session_id), repo)
    assert result.returncode == 0, (
        f"targeted command must not be blocked: {command!r}\n"
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    assert "decision" not in result.stdout


@pytest.mark.parametrize("command", TARGETED_BASH_COMMANDS)
def test_targeted_bash_not_blocked_while_pending(repo: Path, command: str) -> None:
    session_id = f"sess-targeted-pending-{hash(command)}"
    _make_pending(repo, session_id)
    result = _run_hook(_bash_payload(command, session_id), repo)
    assert result.returncode == 0, (
        f"targeted git/gh/test command must not be gated by a pending discovery "
        f"marker: {command!r}\nstdout={result.stdout!r} stderr={result.stderr!r}"
    )
    assert "decision" not in result.stdout


# --------------------------------------------------------------------------- #
# 2. Targeted Read/Grep/Glob on a known path not blocked while pending (F10).
# --------------------------------------------------------------------------- #


def test_targeted_read_absolute_path_not_blocked_while_pending(repo: Path) -> None:
    target = repo / "known_file.py"
    target.write_text("# known file\n")
    session_id = "sess-read-pending"
    _make_pending(repo, session_id)

    payload = {
        "session_id": session_id,
        "tool_name": "Read",
        "tool_input": {"file_path": str(target)},
    }
    result = _run_hook(payload, repo)
    assert result.returncode == 0, result.stdout


def test_targeted_grep_on_known_file_not_blocked_while_pending(repo: Path) -> None:
    """F10: before the fix, ANY Grep call was unconditionally blocked while
    pending, even one scoped to a single, existing file path."""
    target = repo / "known_file.py"
    target.write_text("def auth():\n    pass\n")
    session_id = "sess-grep-pending"
    _make_pending(repo, session_id)

    payload = {
        "session_id": session_id,
        "tool_name": "Grep",
        "tool_input": {"pattern": "auth", "path": str(target)},
    }
    result = _run_hook(payload, repo)
    assert result.returncode == 0, (
        f"a Grep scoped to one known file must not be gated while pending, "
        f"got stdout={result.stdout!r}"
    )


def test_targeted_glob_exact_pattern_not_blocked_while_pending(repo: Path) -> None:
    """F10: before the fix, ANY Glob call was unconditionally blocked while
    pending, even an exact (non-wildcard) filename."""
    session_id = "sess-glob-pending"
    _make_pending(repo, session_id)

    payload = {
        "session_id": session_id,
        "tool_name": "Glob",
        "tool_input": {"pattern": "known_file.py"},
    }
    result = _run_hook(payload, repo)
    assert result.returncode == 0, (
        f"a Glob with an exact, non-wildcard pattern must not be gated while "
        f"pending, got stdout={result.stdout!r}"
    )


# --------------------------------------------------------------------------- #
# 3. Control: genuinely broad/exploratory Glob/Grep still block while pending.
# --------------------------------------------------------------------------- #


def test_broad_glob_still_blocks_while_pending(repo: Path) -> None:
    session_id = "sess-glob-broad-pending"
    _make_pending(repo, session_id)
    payload = {
        "session_id": session_id,
        "tool_name": "Glob",
        "tool_input": {"pattern": "**/*.py"},
    }
    result = _run_hook(payload, repo)
    assert result.returncode == 2, "a genuinely broad Glob must still gate while pending"


def test_exploratory_grep_no_path_still_blocks_while_pending(repo: Path) -> None:
    session_id = "sess-grep-broad-pending"
    _make_pending(repo, session_id)
    payload = {
        "session_id": session_id,
        "tool_name": "Grep",
        "tool_input": {"pattern": "auth"},
    }
    result = _run_hook(payload, repo)
    assert result.returncode == 2, "an exploratory Grep with no path must still gate while pending"


# --------------------------------------------------------------------------- #
# 4. Reminder hook surfaces the subagent-delegation path concretely.
# --------------------------------------------------------------------------- #


def _run_remind_hook(payload: dict, repo_root: Path) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["TOKEN_REDUCE_REPO_ROOT"] = str(repo_root)
    env["PYTHONPATH"] = str(SCRIPTS_DIR) + os.pathsep + env.get("PYTHONPATH", "")
    return subprocess.run(
        [sys.executable, str(REMIND_HOOK)],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        env=env,
        cwd=str(repo_root),
        timeout=30,
    )


def test_broad_discovery_prompt_reminder_mentions_subagent(repo: Path) -> None:
    payload = {
        "session_id": "sess-remind-subagent",
        "prompt": "review the entire repo and find where the auth hook is defined",
    }
    result = _run_remind_hook(payload, repo)
    assert result.returncode == 0, result.stdout

    body = json.loads(result.stdout)
    message = body.get("systemMessage", "")
    assert "Agent(" in message, f"reminder should name the Agent tool: {message!r}"
    assert "Explore" in message, f"reminder should name the Explore subagent: {message!r}"
    assert "subagent" in message.lower()
    # No ritual "MUST be a Bash discovery call" framing.
    assert "MUST be a Bash" not in message


def test_non_discovery_prompt_gets_no_reminder(repo: Path) -> None:
    payload = {
        "session_id": "sess-remind-none",
        "prompt": "fix the typo on line 42 of scripts/foo.py",
    }
    result = _run_remind_hook(payload, repo)
    assert result.returncode == 0, result.stdout
    assert result.stdout.strip() == "" or "systemMessage" not in result.stdout
