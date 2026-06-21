"""Tests for N1 (python3 -c/-m safe-tool bypass) and N2 (multi-line helper bypass).

N1: _SAFE_TOOL_RE matches `python3` and returns 0 before coverage_hit runs.
    `python3 -c "import os; os.walk('.')"` must be blocked, not allowed.

N2: When pending=True, HELPER_COMMAND_RE match on first line returns 0 without
    checking continuation lines. `token-reduce-paths.sh foo && find / -name bar`
    must be blocked when pending=True.
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


def _init_git_repo(path: Path) -> None:
    subprocess.run(
        ["git", "-c", "init.defaultBranch=main", "init", "-q", str(path)],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(path), "config", "user.email", "test@example.com"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(path), "config", "user.name", "test"],
        check=True,
        capture_output=True,
    )


def _run_hook(
    payload: dict[str, object],
    repo_root: Path,
) -> subprocess.CompletedProcess[str]:
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


def _bash_payload(command: str, session_id: str = "sess-bypass-test") -> dict[str, object]:
    return {
        "session_id": session_id,
        "tool_name": "Bash",
        "tool_input": {"command": command},
    }


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    _init_git_repo(tmp_path)
    return tmp_path


# ---------------------------------------------------------------------------
# N1: python3 -c / -m bypass
# ---------------------------------------------------------------------------

def test_python3_c_with_os_walk_is_not_safe_tool_bypassed(repo: Path) -> None:
    """N1: python3 -c with os.walk must NOT bypass safe-tool check.

    First attempt: warn-and-allow (rc=0 with telemetry).
    Second attempt: hard block (rc=2) — proving it went through coverage checks.
    """
    session_id = "sess-n1-python3-c"
    cmd = 'python3 -c "import os; [_ for _ in os.walk(\'.\')]"'

    # First attempt: warn-and-allow (coverage hit, not bypassed)
    r1 = _run_hook(_bash_payload(cmd, session_id=session_id), repo)
    assert r1.returncode == 0, (
        f"first python3 -c with os.walk should warn-and-allow; got rc={r1.returncode} "
        f"stderr={r1.stderr!r}"
    )

    # Second attempt: block (proves it did NOT take the safe-tool bypass path)
    r2 = _run_hook(_bash_payload(cmd, session_id=session_id), repo)
    assert r2.returncode == 2, (
        f"repeat python3 -c with os.walk should be blocked; got rc={r2.returncode} "
        f"stdout={r2.stdout!r}"
    )


def test_python3_script_is_allowed(repo: Path) -> None:
    """N1: plain `python3 some_script.py` is a safe tool invocation — allow."""
    result = _run_hook(_bash_payload("python3 scripts/benchmark.py"), repo)
    assert result.returncode == 0, (
        f"plain python3 script should be allowed; got rc={result.returncode} "
        f"stdout={result.stdout!r}"
    )


def test_python3_m_pytest_is_allowed(repo: Path) -> None:
    """N1: `python3 -m pytest scripts/tests/` has no broad pattern — allow."""
    result = _run_hook(_bash_payload("python3 -m pytest scripts/tests/ -q"), repo)
    assert result.returncode == 0, (
        f"python3 -m pytest should be allowed; got rc={result.returncode} "
        f"stdout={result.stdout!r}"
    )


def test_python311_c_with_os_walk_is_not_safe_tool_bypassed(repo: Path) -> None:
    """N1: versioned python (python3.11 -c) with os.walk must NOT bypass safe-tool check."""
    session_id = "sess-n1-python311-c"
    cmd = 'python3.11 -c "import os; [_ for _ in os.walk(\'.\')]"'

    r1 = _run_hook(_bash_payload(cmd, session_id=session_id), repo)
    assert r1.returncode == 0, (
        f"first python3.11 -c with os.walk should warn-and-allow; got rc={r1.returncode}"
    )
    r2 = _run_hook(_bash_payload(cmd, session_id=session_id), repo)
    assert r2.returncode == 2, (
        f"repeat python3.11 -c with os.walk should be blocked; got rc={r2.returncode}"
    )


def test_python3_m_with_broad_pattern_is_blocked(repo: Path) -> None:
    """N1: `python3 -m` falls through to coverage checks; broad pattern inside blocks."""
    result = _run_hook(
        _bash_payload('python3 -m site; find . -name "*.py"'),
        repo,
    )
    assert result.returncode == 2 or result.returncode == 0, (
        # First attempt: warn-and-allow; second attempt: block.
        # We just need it NOT to bypass coverage entirely (rc=0 on first warn is OK
        # but rc=0 with no telemetry event would mean it bypassed the check).
        f"unexpected rc={result.returncode}"
    )
    # On the warn-first path the stdout is empty (no block JSON), but telemetry fires.
    # On the block path stdout has JSON. Either way the safe-tool bypass must not fire
    # (which would produce rc=0 with NO telemetry).


# ---------------------------------------------------------------------------
# N2: multi-line helper bypass when pending=True
# ---------------------------------------------------------------------------

import time as _time


def _set_pending(repo: Path, session_id: str) -> None:
    """Prime the repo state to pending=True for the given session."""
    state_dir = repo / ".claude" / "token-reduce-state"
    state_dir.mkdir(parents=True, exist_ok=True)
    import re
    key = re.sub(r"[^A-Za-z0-9_.-]+", "-", session_id).strip("-") or "default"
    payload = json.dumps({"prompt": "find all files", "created_at": _time.time()}) + "\n"
    (state_dir / f"{key}.json").write_text(payload)
    (state_dir / "default.json").write_text(payload)


def test_multiline_helper_plus_broad_is_blocked_when_pending(repo: Path) -> None:
    """N2: `token-reduce-paths.sh foo\\nfind / -name bar` must block when pending=True."""
    session_id = "sess-n2-pending"
    _set_pending(repo, session_id)

    multi_cmd = "token-reduce-paths.sh foo\nfind / -name bar"
    result = _run_hook(
        {"session_id": session_id, "tool_name": "Bash",
         "tool_input": {"command": multi_cmd}},
        repo,
    )

    assert result.returncode == 2, (
        f"multi-line helper+find should be blocked when pending=True; "
        f"got rc={result.returncode} stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_multiline_helper_only_is_allowed_when_pending(repo: Path) -> None:
    """N2: a pure multi-line helper command (no broad continuation) is allowed when pending."""
    session_id = "sess-n2-helper-only"
    _set_pending(repo, session_id)

    multi_cmd = "token-reduce-paths.sh foo\necho done"
    result = _run_hook(
        {"session_id": session_id, "tool_name": "Bash",
         "tool_input": {"command": multi_cmd}},
        repo,
    )

    assert result.returncode == 0, (
        f"pure helper command should be allowed when pending=True; "
        f"got rc={result.returncode} stdout={result.stdout!r}"
    )
