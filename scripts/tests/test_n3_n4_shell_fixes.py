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

def test_paths_sh_uses_uv_run_for_rank_paths() -> None:
    """N3: token-reduce-paths.sh must call `uv run python3` for rank_paths.py."""
    paths_sh = SCRIPTS_DIR / "token-reduce-paths.sh"
    lines = paths_sh.read_text().splitlines()
    # Find lines that invoke rank_paths.py (not file-existence checks like -s/-f/-r)
    rank_lines = [
        ln for ln in lines
        if "rank_paths.py" in ln
        and not ln.strip().startswith("#")
        and "-s " not in ln and "-f " not in ln and "-r " not in ln
    ]
    assert rank_lines, "No rank_paths.py invocation found in token-reduce-paths.sh"
    for ln in rank_lines:
        assert "uv run" in ln, (
            f"token-reduce-paths.sh invokes rank_paths.py without `uv run`: {ln!r}"
        )


def test_paths_sh_uses_uv_run_for_brain_hint() -> None:
    """N3: brain_hint is invoked via uv run (either in paths.sh or dispatch.py)."""
    paths_sh = SCRIPTS_DIR / "token-reduce-paths.sh"
    dispatch_py = SCRIPTS_DIR / "token_reduce_dispatch.py"
    paths_content = paths_sh.read_text()
    dispatch_content = dispatch_py.read_text() if dispatch_py.exists() else ""
    # P2: dispatch.py took over brain_hint; paths.sh delegates to dispatch via uv run
    has_dispatch = "token_reduce_dispatch.py" in paths_content and "uv run" in paths_content
    has_brain_in_dispatch = "brain_hint" in dispatch_content
    has_brain_direct = any(
        "brain_hint.py" in ln and "uv run" in ln
        for ln in paths_content.splitlines()
        if not ln.strip().startswith("#")
    )
    assert has_dispatch or has_brain_direct, (
        "paths.sh must either invoke dispatch.py via uv run or call brain_hint.py directly via uv run"
    )
    if has_dispatch:
        assert has_brain_in_dispatch, (
            "dispatch.py is used but doesn't invoke brain_hint — N3/P2 incomplete"
        )


def test_snippet_sh_uses_uv_run_for_brain_hint() -> None:
    """N3: token-reduce-snippet.sh must call `uv run python3` for brain_hint.py."""
    snippet_sh = SCRIPTS_DIR / "token-reduce-snippet.sh"
    lines = snippet_sh.read_text().splitlines()
    brain_lines = [ln for ln in lines if "brain_hint.py" in ln and not ln.strip().startswith("#")]
    assert brain_lines, "No brain_hint.py invocation found in token-reduce-snippet.sh"
    for ln in brain_lines:
        assert "uv run" in ln, (
            f"token-reduce-snippet.sh invokes brain_hint.py without `uv run`: {ln!r}"
        )


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


def test_brain_hint_error_logged_in_snippet_sh() -> None:
    """N4: token-reduce-snippet.sh must log brain_hint_error on failure."""
    snippet_sh = SCRIPTS_DIR / "token-reduce-snippet.sh"
    content = snippet_sh.read_text()
    assert "brain_hint_error" in content, (
        "token-reduce-snippet.sh must log brain_hint_error event to telemetry (N4 fix missing)"
    )
    assert "2>/dev/null || true" not in content or "brain_hint" not in content.split("2>/dev/null || true")[0].split("\n")[-1], (
        "token-reduce-snippet.sh still uses 2>/dev/null for brain_hint (N4 fix missing)"
    )


def test_snippet_sh_brain_rc_can_capture_nonzero() -> None:
    """N4 behavioral: snippet.sh must NOT use `|| true` inside $() for brain_hint.

    The pattern `BRAIN_HINT=$(cmd || true)` forces rc=0 even on failure, making
    the error-telemetry branch unreachable. The fix moves `|| _BRAIN_RC=$?` outside.
    """
    snippet_sh = SCRIPTS_DIR / "token-reduce-snippet.sh"
    content = snippet_sh.read_text()
    lines = content.splitlines()
    brain_hint_assign_lines = [
        ln for ln in lines
        if "brain_hint.py" in ln and "BRAIN_HINT=" in ln
    ]
    for ln in brain_hint_assign_lines:
        # The bad pattern: `|| true` inside the command substitution $()
        # Extract content inside $(...) if present
        inside_subshell = ln
        if "$(" in ln:
            start = ln.index("$(") + 2
            # find matching close paren (simple heuristic)
            inside_subshell = ln[start:]
        assert "|| true" not in inside_subshell, (
            f"snippet.sh has `|| true` inside $() for brain_hint — N4 fix regressed: {ln!r}"
        )
