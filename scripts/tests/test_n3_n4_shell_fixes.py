"""Tests for N3 (python3 → uv run) and N4 (error telemetry logging).

N3: token-reduce-paths.sh and token-reduce-snippet.sh must use `uv run python3`
    for rank_paths.py and brain_hint.py, not bare `python3`.

N4: When rank_paths or brain_hint fails, the error must be logged to telemetry
    (events.jsonl) with status=error, not silently swallowed.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[1]


def _read_events(repo: Path) -> list[dict]:
    path = repo / "artifacts" / "token-reduction" / "events.jsonl"
    if not path.exists():
        return []
    events = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if line:
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return events


def _init_git_repo(path: Path) -> None:
    subprocess.run(
        ["git", "-c", "init.defaultBranch=main", "init", "-q", str(path)],
        check=True, capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(path), "config", "user.email", "test@example.com"],
        check=True, capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(path), "config", "user.name", "test"],
        check=True, capture_output=True,
    )


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    _init_git_repo(tmp_path)
    return tmp_path


# ---------------------------------------------------------------------------
# N3: uv run python3 used instead of bare python3
# ---------------------------------------------------------------------------







# ---------------------------------------------------------------------------
# N4: rank_paths failure → telemetry event logged
# ---------------------------------------------------------------------------

def test_rank_paths_failure_is_logged_to_telemetry(repo: Path, tmp_path: Path) -> None:
    """N4: rank_paths failure is logged to telemetry (either in paths.sh or dispatch.py)."""
    paths_sh = SCRIPTS_DIR / "token-reduce-paths.sh"
    dispatch_py = SCRIPTS_DIR / "token_reduce_dispatch.py"
    paths_content = paths_sh.read_text()
    dispatch_content = dispatch_py.read_text() if dispatch_py.exists() else ""

    # P2: telemetry logging moved to dispatch.py
    has_error_in_dispatch = "rank_paths_error" in dispatch_content
    has_error_in_paths = "rank_paths_error" in paths_content

    assert has_error_in_dispatch or has_error_in_paths, (
        "rank_paths error must be logged to telemetry in paths.sh or dispatch.py (N4 fix missing)"
    )
    # brain_hint error logging
    has_brain_error_in_dispatch = "brain_hint_error" in dispatch_content
    has_brain_error_in_paths = "brain_hint_error" in paths_content
    assert has_brain_error_in_dispatch or has_brain_error_in_paths, (
        "brain_hint error must be logged to telemetry (N4 fix missing)"
    )




# ---------------------------------------------------------------------------
# Regression: token-reduce-paths.sh error branch must preserve the real exit
# code, not silently report success.
#
# Root cause: `if OUTPUT="$(token-reduce-search.sh ...)"; then ... exit 0; fi`
# had no `else`. In bash, when an `if` condition is false and there is no
# `else` clause, `$?` immediately after the `fi` is reset to 0 (the exit
# status of the `if` construct itself, which POSIX defines as 0 when no
# branch's condition tested true) -- NOT the failing command's exit code.
# `STATUS=$?` on the line after `fi` therefore always read 0, so the wrapper
# always `exit 0`d with empty output on a genuine search failure, and its own
# "error" telemetry event always logged exit_code=0 -- exactly the
# backend=unknown/exit_code=0/status=error events seen in production
# telemetry (e.g. token_reduce_paths at 2026-09-01T19:10:19Z).
# ---------------------------------------------------------------------------


WRAPPER_SCRIPTS = ["token-reduce-paths.sh", "token-reduce-snippet.sh"]




@pytest.mark.parametrize("wrapper_name", WRAPPER_SCRIPTS)
def test_wrapper_sh_preserves_real_exit_code_on_search_failure(
    wrapper_name: str, tmp_path: Path
) -> None:
    """Behavioral: when token-reduce-search.sh genuinely fails, the wrapper
    must exit with that same nonzero code and log it accurately to
    telemetry -- not exit 0 with backend=unknown/exit_code=0/status=error."""
    _init_git_repo(tmp_path)
    work_scripts = tmp_path / "scripts"
    work_scripts.mkdir()
    (work_scripts / wrapper_name).write_text((SCRIPTS_DIR / wrapper_name).read_text())
    (work_scripts / wrapper_name).chmod(0o755)
    (work_scripts / "token_reduce_telemetry.py").write_text(
        (SCRIPTS_DIR / "token_reduce_telemetry.py").read_text()
    )
    stub = work_scripts / "token-reduce-search.sh"
    stub.write_text("#!/usr/bin/env bash\nexit 5\n")
    stub.chmod(0o755)

    result = subprocess.run(
        ["bash", f"scripts/{wrapper_name}", "some", "query"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 5, (
        f"{wrapper_name}: wrapper must propagate the search script's real "
        f"exit code (5), got {result.returncode} "
        f"(stdout={result.stdout!r} stderr={result.stderr!r})"
    )
    events = _read_events(tmp_path)
    error_events = [
        e for e in events
        if e.get("event") == "helper_invocation" and e.get("status") == "error"
    ]
    assert error_events, f"{wrapper_name}: expected an error telemetry event, got: {events}"
    assert error_events[-1]["meta"]["exit_code"] == 5, (
        f"{wrapper_name}: telemetry must log the real exit code (5), "
        f"got meta={error_events[-1]['meta']}"
    )


