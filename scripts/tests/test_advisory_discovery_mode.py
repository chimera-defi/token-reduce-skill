"""Regression tests for config-backed advisory discovery enforcement.

The setup wizard has long exposed enforcement=advisory. Ordinary discovery
should therefore warn/allow without weakening catastrophic and symlink-root
hard guards.
"""
from __future__ import annotations
import json
import os
import subprocess
import sys
from pathlib import Path
import pytest

SCRIPTS = Path(__file__).resolve().parents[1]
HOOK = SCRIPTS / "enforce-token-reduce-first.py"


def _init_repo(path: Path) -> None:
    subprocess.run(["git", "-c", "init.defaultBranch=main", "init", "-q", str(path)], check=True)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    _init_repo(tmp_path)
    return tmp_path


def _run(payload: dict, repo: Path, *, advisory: bool = True):
    env = os.environ.copy()
    env["TOKEN_REDUCE_REPO_ROOT"] = str(repo)
    env["PYTHONPATH"] = str(SCRIPTS) + os.pathsep + env.get("PYTHONPATH", "")
    env.pop("TOKEN_REDUCE_ENFORCE_MODE", None)  # prod default: warn-only
    if advisory:
        cfg = repo / "token-reduce-config.json"
        cfg.write_text(json.dumps({"enforcement": "advisory"}) + "\n")
        env["TOKEN_REDUCE_CONFIG_PATH"] = str(cfg)
    return subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        cwd=repo,
        env=env,
        timeout=30,
    )


def _bash(command: str, session: str, use_id: str) -> dict:
    return {"session_id": session, "tool_use_id": use_id, "tool_name": "Bash", "tool_input": {"command": command}}


def test_advisory_allows_repeat_broad_bash(repo: Path) -> None:
    first = _run(_bash("tree .", "adv-repeat", "b1"), repo)
    second = _run(_bash("tree .", "adv-repeat", "b2"), repo)
    assert first.returncode == 0
    assert second.returncode == 0
    assert second.stdout == ""


def test_advisory_allows_exploratory_glob_and_grep(repo: Path) -> None:
    glob = _run({"session_id": "adv-glob", "tool_use_id": "g1", "tool_name": "Glob", "tool_input": {"pattern": "**/*.py"}}, repo)
    grep = _run({"session_id": "adv-grep", "tool_use_id": "g2", "tool_name": "Grep", "tool_input": {"pattern": "auth"}}, repo)
    assert glob.returncode == 0
    assert grep.returncode == 0
    assert glob.stdout == ""
    assert grep.stdout == ""


def test_catastrophic_scan_is_warn_only_now(repo: Path) -> None:
    result = _run(_bash("find / -maxdepth 1 -type f", "adv-cat", "c1"), repo)
    assert result.returncode == 0
    assert result.stdout == ""
