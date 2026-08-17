"""record-event is a CLI-friendly alias of the `log` subcommand, added so
shell hook wrappers can record telemetry without importing this module."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "token_reduce_telemetry.py"


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
