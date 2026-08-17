"""record-event is a CLI-friendly alias of the `log` subcommand, added so
shell hook wrappers can record telemetry without importing this module."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from unittest import mock

SCRIPT_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import token_reduce_telemetry

SCRIPT = SCRIPT_DIR / "token_reduce_telemetry.py"


def _events(repo_root: Path) -> list[dict]:
    path = repo_root / "artifacts" / "token-reduction" / "events.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def test_record_event_writes_same_shape_as_log(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--repo-root",
            str(tmp_path),
            "record-event",
            "--event",
            "hook_fail_open",
            "--source",
            "hook",
            "--tool",
            "enforce-token-reduce-first",
            "--status",
            "error",
        ],
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 0, result.stderr

    events = _events(tmp_path)
    assert len(events) == 1
    assert events[0]["event"] == "hook_fail_open"
    assert events[0]["source"] == "hook"
    assert events[0]["tool"] == "enforce-token-reduce-first"
    assert events[0]["status"] == "error"


class TestDefaultRepoRootGuards:
    """record-event (and log/summary) fall back to default_repo_root() when
    --repo-root is omitted. That path must not hang or crash on a stalled
    or missing git binary -- the exact bug class this module's callers
    (the hook scripts) exist to be immune to."""

    def test_timeout_falls_back_instead_of_raising(self) -> None:
        with mock.patch.object(
            token_reduce_telemetry.subprocess,
            "run",
            side_effect=subprocess.TimeoutExpired(cmd="git", timeout=10),
        ):
            result = token_reduce_telemetry.default_repo_root()
        assert isinstance(result, Path)

    def test_missing_git_binary_falls_back_instead_of_raising(self) -> None:
        with mock.patch.object(
            token_reduce_telemetry.subprocess,
            "run",
            side_effect=FileNotFoundError("git not found"),
        ):
            result = token_reduce_telemetry.default_repo_root()
        assert isinstance(result, Path)

    def test_fallback_resolves_to_repo_root_not_a_grandparent(self) -> None:
        # The fallback must land on the actual repo root (scripts/..), not
        # one level further up -- callers use this as the events.jsonl base.
        with mock.patch.object(
            token_reduce_telemetry.subprocess,
            "run",
            side_effect=FileNotFoundError("git not found"),
        ):
            result = token_reduce_telemetry.default_repo_root()
        assert result == SCRIPT_DIR.parent

    def test_record_event_cli_without_repo_root_flag_does_not_hang(self, tmp_path: Path, monkeypatch) -> None:
        # Exercise the actual CLI entry point (argparse default) with a
        # stalled git binary on PATH, not just the Python-level function.
        stub_git = tmp_path / "bin" / "git"
        stub_git.parent.mkdir(parents=True)
        # Absolute path to sleep: the stub's own PATH is restricted to this
        # bin dir, so a bare `sleep` would fail-fast (127) instead of hanging.
        stub_git.write_text(f"#!/bin/sh\nexec {shutil.which('sleep')} 30\n")
        stub_git.chmod(0o755)
        env = {**os.environ, "PATH": str(tmp_path / "bin")}
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "record-event", "--event", "e", "--source", "s"],
            capture_output=True,
            text=True,
            env=env,
            timeout=15,
        )
        assert result.returncode == 0, result.stderr
