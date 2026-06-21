"""End-to-end integration tests for ``enforce-token-reduce-first.py``.

Spawns the hook as a subprocess with a fabricated PreToolUse JSON event
and asserts the hook's stdout / exit code / telemetry against the three
cases the round-2 follow-up brief calls out:

  (a) catastrophic pattern  -> hard block (exit 2, decision=block,
                                policy=catastrophic)
  (b) first broad attempt   -> warn-and-allow (exit 0, no decision,
                                hook_warn telemetry event)
  (c) repeat broad attempt  -> block (exit 2, decision=block,
                                policy=repeat_broad)

We point ``TOKEN_REDUCE_REPO_ROOT`` at a tmpdir-backed git repo so the
hook's state writes (broad-attempt counter, last-block record) and
telemetry events land there instead of polluting the real repo's
``artifacts/token-reduction/events.jsonl``.
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
    # Hook reads git config for repo root but doesn't need commits.
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


def _events(repo_root: Path) -> list[dict]:
    path = repo_root / "artifacts" / "token-reduction" / "events.jsonl"
    if not path.exists():
        return []
    out: list[dict] = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    _init_git_repo(tmp_path)
    return tmp_path


def _bash_payload(command: str, session_id: str = "sess-int-test") -> dict[str, object]:
    return {
        "session_id": session_id,
        "tool_name": "Bash",
        "tool_input": {"command": command},
    }


CATASTROPHIC_CMD = "find /etc/passwd"      # matches catastrophic `find /...` regex
BROAD_CMD = "tree ."                       # broad bash pattern; NOT catastrophic


def test_catastrophic_pattern_hard_blocks(repo: Path) -> None:
    """A `find /...` style scan is catastrophic -> immediate hard block."""
    result = _run_hook(_bash_payload(CATASTROPHIC_CMD), repo)

    assert result.returncode == 2, result.stderr
    decision = json.loads(result.stdout)
    assert decision["decision"] == "block"
    assert "scan" in decision["reason"].lower() or "catastrophic" in decision["reason"].lower()

    events = _events(repo)
    catastrophic_blocks = [
        ev for ev in events
        if ev.get("event") == "hook_block"
        and (ev.get("meta") or {}).get("policy") == "catastrophic"
    ]
    assert catastrophic_blocks, f"no catastrophic hook_block telemetry in {events}"


def test_first_broad_attempt_warns_and_allows(repo: Path) -> None:
    """First broad-but-not-catastrophic attempt -> warn-and-allow (exit 0, no block JSON)."""
    result = _run_hook(_bash_payload(BROAD_CMD, session_id="sess-warn-first"), repo)

    assert result.returncode == 0, (
        f"first broad attempt should be warn-and-allow, got stdout={result.stdout!r}"
    )
    # No decision JSON on the warn-and-allow path
    assert result.stdout.strip() == "" or "decision" not in result.stdout

    events = _events(repo)
    warns = [ev for ev in events if ev.get("event") == "hook_warn"]
    assert warns, f"expected hook_warn telemetry, got events={events}"
    assert (warns[-1].get("meta") or {}).get("attempt_count") == 1


def test_repeat_broad_attempt_blocks(repo: Path) -> None:
    """Two broad attempts in the same session -> second one blocks."""
    session_id = "sess-repeat-broad"

    first = _run_hook(_bash_payload(BROAD_CMD, session_id=session_id), repo)
    assert first.returncode == 0, "first attempt should warn-and-allow"

    second = _run_hook(_bash_payload(BROAD_CMD, session_id=session_id), repo)
    assert second.returncode == 2, (
        f"second broad attempt in same session should block, got stdout={second.stdout!r}"
    )
    decision = json.loads(second.stdout)
    assert decision["decision"] == "block"

    events = _events(repo)
    repeat_blocks = [
        ev for ev in events
        if ev.get("event") == "hook_block"
        and (ev.get("meta") or {}).get("policy") == "repeat_broad"
    ]
    assert repeat_blocks, f"no repeat_broad hook_block telemetry in {events}"
    assert (repeat_blocks[-1].get("meta") or {}).get("attempt_count") == 2
