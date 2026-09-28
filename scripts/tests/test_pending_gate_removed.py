"""Regression test for the PreToolUse enforcer's "pending" first-move
discovery gate removal (operator ruling 2026-09-28).

Nothing sets the pending marker anymore -- the UserPromptSubmit reminder
hook that used to set it was retired in an earlier PR (see
references/worktree-deploy-sync.md) -- so the enforcer's `if pending:`
branches, mark_pending/is_pending/clear_pending, and the "pending gate"
classification code were all dead code and removed.

This file pins the resulting contract with a fresh, dedicated test rather
than relying on the aggregate of rewritten pre-existing tests:

  (a) an ordinary, scoped Grep/Glob/Read/Bash call is allowed with no
      session state at all -- there is nothing left to set up before an
      agent's very first tool call in a session.
  (b) the find-symlink-root guard and a catastrophic scan still block
      (exit 2) -- these safety checks never depended on pending and are
      unaffected by its removal.
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
# (a) ordinary, scoped work is allowed with no state
# --------------------------------------------------------------------------- #


def test_ordinary_compound_bash_allowed_with_no_state(repo: Path) -> None:
    result = _run_hook(_bash_payload("git status && git log -1", "sess-a-bash"), repo)
    assert result.returncode == 0, result.stdout
    assert result.stdout.strip() == ""


def test_scoped_rg_allowed_with_no_state(repo: Path) -> None:
    target = repo / "scripts"
    target.mkdir()
    (target / "x.py").write_text("def foo():\n    pass\n")
    result = _run_hook(_bash_payload("rg -n foo scripts/x.py", "sess-a-rg"), repo)
    assert result.returncode == 0, result.stdout


def test_ordinary_glob_allowed_with_no_state(repo: Path) -> None:
    (repo / "known_file.py").write_text("# known\n")
    payload = {
        "session_id": "sess-a-glob",
        "tool_name": "Glob",
        "tool_input": {"pattern": "known_file.py"},
    }
    result = _run_hook(payload, repo)
    assert result.returncode == 0, result.stdout


def test_ordinary_read_allowed_with_no_state(repo: Path) -> None:
    target = repo / "known_file.py"
    target.write_text("# known\n")
    payload = {
        "session_id": "sess-a-read",
        "tool_name": "Read",
        "tool_input": {"file_path": str(target)},
    }
    result = _run_hook(payload, repo)
    assert result.returncode == 0, result.stdout


def test_ordinary_grep_allowed_with_no_state(repo: Path) -> None:
    target = repo / "known_file.py"
    target.write_text("def foo():\n    pass\n")
    payload = {
        "session_id": "sess-a-grep",
        "tool_name": "Grep",
        "tool_input": {"pattern": "foo", "path": str(target)},
    }
    result = _run_hook(payload, repo)
    assert result.returncode == 0, result.stdout


# --------------------------------------------------------------------------- #
# (b) safety checks that never depended on pending still block
# --------------------------------------------------------------------------- #


def test_find_symlink_root_guard_still_blocks(tmp_path: Path, repo: Path) -> None:
    real_dir = tmp_path / "real_target"
    real_dir.mkdir()
    link = tmp_path / "the_link"
    link.symlink_to(real_dir)

    result = _run_hook(_bash_payload(f"find {link}", "sess-b-symlink"), repo)
    assert result.returncode == 2, result.stdout
    decision = json.loads(result.stdout)
    assert "symlink" in decision["reason"].lower()


def test_catastrophic_scan_still_blocks(repo: Path) -> None:
    result = _run_hook(_bash_payload("find / -name x", "sess-b-catastrophic"), repo)
    assert result.returncode == 2, result.stdout
    decision = json.loads(result.stdout)
    assert decision["decision"] == "block"
    assert "catastrophic" in decision["reason"].lower()
