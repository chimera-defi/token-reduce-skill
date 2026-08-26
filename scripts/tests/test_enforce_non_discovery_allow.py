"""Over-blocking regression tests for ``enforce-token-reduce-first.py``.

When a repo-discovery prompt is *pending*, the hook blocks every Bash command
except the discovery helper. That over-blocks command shapes that never touch
the repo at all -- tmux/session control, message relays, and wait/poll loops.
The operator reported these exact cases being blocked (each demanding a fresh
``token-reduce-adaptive`` call) even though none of them is a repo scan:

  1. ``tmux capture-pane -p -t <session>``      (read-only pane inspection)
  2. ``session-handoff send <session> --file``  (relaying a message)
  3. ``until [ -s file ]; do sleep 2; done``    (a wait/poll loop)
  4. tmux control (send-keys, list-sessions)
  5. while/poll loops

These must pass the gate without a discovery call. Genuine repo scans (find .,
exploratory rg) must STILL block while pending -- that's the control that proves
the gate isn't neutered.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

HOOK = Path(__file__).resolve().parents[1] / "enforce-token-reduce-first.py"
SCRIPTS_DIR = HOOK.parent
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


def _run_hook(command: str, repo_root: Path, session_id: str) -> subprocess.CompletedProcess[str]:
    payload = {"session_id": session_id, "tool_name": "Bash", "tool_input": {"command": command}}
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


NON_DISCOVERY_COMMANDS = [
    "tmux capture-pane -p -t worker-3",
    "tmux send-keys -t worker-3 C-c",
    "tmux list-sessions",
    "session-handoff send worker-3 --file /tmp/handoff-note.md",
    "until [ -s /tmp/result.json ]; do sleep 2; done",
    "while ! test -f /tmp/done.flag; do sleep 5; done",
    "sleep 10",
]


@pytest.mark.parametrize("command", NON_DISCOVERY_COMMANDS)
def test_non_discovery_command_passes_pending_gate(repo: Path, command: str) -> None:
    session_id = "sess-nondiscovery"
    _make_pending(repo, session_id)

    result = _run_hook(command, repo, session_id)

    assert result.returncode == 0, (
        f"non-discovery command must NOT be gated while pending: {command!r}\n"
        f"got returncode={result.returncode} stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    assert "decision" not in result.stdout, (
        f"non-discovery command must not emit a block decision: {command!r} -> {result.stdout!r}"
    )


GENUINE_DISCOVERY_COMMANDS = [
    "find .",
    "rg pattern .",
    "grep -R foo .",
]


@pytest.mark.parametrize("command", GENUINE_DISCOVERY_COMMANDS)
def test_genuine_discovery_still_blocks_while_pending(repo: Path, command: str) -> None:
    """Control: real repo scans must STILL block while pending. Proves the
    over-blocking fix didn't neuter the discovery gate."""
    session_id = "sess-discovery-control"
    _make_pending(repo, session_id)

    result = _run_hook(command, repo, session_id)

    assert result.returncode == 2, (
        f"genuine discovery scan must still block while pending: {command!r}\n"
        f"got returncode={result.returncode} stdout={result.stdout!r}"
    )
    decision = json.loads(result.stdout)
    assert decision["decision"] == "block"


def test_tmux_command_hiding_a_scan_still_blocks(repo: Path) -> None:
    """A repo scan smuggled into a tmux/session command must NOT pass -- the
    non-discovery allowance is disqualified by any embedded scan pattern."""
    session_id = "sess-smuggle"
    _make_pending(repo, session_id)

    # `find /` on its own line inside a compound command is a real scan.
    command = "tmux new-session -d 'x'\nfind . -name '*.py'"
    result = _run_hook(command, repo, session_id)

    assert result.returncode == 2, (
        f"a command containing a real scan must still block, got "
        f"returncode={result.returncode} stdout={result.stdout!r}"
    )
