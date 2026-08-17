"""Regression test for the hook-wedge class described in the 2026-08-17 RCA.

Root cause: ``uv run scripts/<hook>.py`` used a bare relative path. If the
shell's cwd ever drifted away from the repo root, or the target script was
transiently unreachable, ``uv`` itself failed to spawn the script and exited
with code 2 while printing ``error: Failed to spawn: ... No such file or
directory`` to stderr. For ``enforce-token-reduce-first.py`` (a PreToolUse
hook), exit code 2 is *also* the hook's own signal for an intentional block
-- so a vanished/unreachable script was indistinguishable from a deliberate
block, and Claude Code treated every subsequent tool call as blocked with no
in-session recovery.

These tests exercise the *actual* command strings configured in
``.claude/settings.json`` -- not the Python scripts directly -- because the
bug lived in the shell/spawn layer, not in the scripts' internal logic (which
already had try/except fail-open guards around runtime errors).
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SETTINGS_PATH = REPO_ROOT / ".claude" / "settings.json"


def _load_settings() -> dict:
    return json.loads(SETTINGS_PATH.read_text())


def _hook_command(event: str, matcher: str | None, script_name: str) -> str:
    """Pull the live command string for <event>/<matcher> that invokes script_name."""
    settings = _load_settings()
    for entry in settings["hooks"][event]:
        if matcher is not None and entry.get("matcher") != matcher:
            continue
        for hook in entry["hooks"]:
            if script_name in hook["command"]:
                return hook["command"]
    raise AssertionError(f"no {event}/{matcher} hook command references {script_name}")


def _run_shell(
    command: str,
    *,
    cwd: Path,
    project_dir: Path | None,
    stdin: str = "{}",
    state_root: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    if project_dir is not None:
        env["CLAUDE_PROJECT_DIR"] = str(project_dir)
    else:
        env.pop("CLAUDE_PROJECT_DIR", None)
    if state_root is not None:
        # Redirect the script's own state/telemetry writes away from the real
        # repo when project_dir points at REPO_ROOT (TOKEN_REDUCE_REPO_ROOT
        # takes precedence over CLAUDE_PROJECT_DIR inside token_reduce_state.py).
        env["TOKEN_REDUCE_REPO_ROOT"] = str(state_root)
    else:
        env.pop("TOKEN_REDUCE_REPO_ROOT", None)
    return subprocess.run(
        ["sh", "-c", command],
        input=stdin,
        text=True,
        capture_output=True,
        cwd=str(cwd),
        env=env,
        timeout=30,
    )


@pytest.fixture
def scratch_repo(tmp_path: Path) -> Path:
    """A throwaway cwd, distinct from the real repo, to simulate cwd drift."""
    other = tmp_path / "elsewhere"
    other.mkdir()
    return other


def test_remind_hook_fails_open_when_script_is_unreachable(scratch_repo: Path) -> None:
    """CLAUDE_PROJECT_DIR pointing at a repo where the script is missing must not block prompts."""
    command = _hook_command("UserPromptSubmit", None, "remind-token-reduce.py")

    fake_project = scratch_repo / "fake-project"
    (fake_project / "scripts").mkdir(parents=True)
    # Deliberately do NOT create remind-token-reduce.py -- simulates the
    # exact wedge trigger (uv "Failed to spawn").

    result = _run_shell(command, cwd=scratch_repo, project_dir=fake_project, stdin="{}")

    assert result.returncode == 0, (
        f"remind hook must fail open when its script is unreachable, "
        f"got returncode={result.returncode} stderr={result.stderr!r}"
    )


def test_enforce_hook_fails_open_when_script_is_unreachable(scratch_repo: Path) -> None:
    """Same wedge trigger for the PreToolUse hook must not block tool calls."""
    command = _hook_command("PreToolUse", "Bash", "enforce-token-reduce-first.py")

    fake_project = scratch_repo / "fake-project"
    (fake_project / "scripts").mkdir(parents=True)

    payload = json.dumps({"session_id": "s1", "tool_name": "Bash", "tool_input": {"command": "echo hi"}})
    result = _run_shell(command, cwd=scratch_repo, project_dir=fake_project, stdin=payload)

    assert result.returncode == 0, (
        f"enforce hook must fail open (not block) when its script is unreachable, "
        f"got returncode={result.returncode} stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    assert "decision" not in result.stdout


def test_enforce_hook_fails_open_when_script_crashes(scratch_repo: Path) -> None:
    """Deliberately break the script by making it throw (per the RCA's own
    regression-test prescription) -- an uncaught exception must fail open,
    not be mistaken for an intentional block."""
    command = _hook_command("PreToolUse", "Bash", "enforce-token-reduce-first.py")

    fake_project = scratch_repo / "fake-project"
    (fake_project / "scripts").mkdir(parents=True)
    (fake_project / "scripts" / "enforce-token-reduce-first.py").write_text(
        "raise RuntimeError('deliberately broken for the fail-open regression test')\n"
    )

    payload = json.dumps({"session_id": "s1", "tool_name": "Bash", "tool_input": {"command": "echo hi"}})
    result = _run_shell(command, cwd=scratch_repo, project_dir=fake_project, stdin=payload)

    assert result.returncode == 0, (
        f"enforce hook must fail open when the script crashes, "
        f"got returncode={result.returncode} stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    assert "decision" not in result.stdout


def test_remind_hook_fails_open_when_script_crashes(scratch_repo: Path) -> None:
    command = _hook_command("UserPromptSubmit", None, "remind-token-reduce.py")

    fake_project = scratch_repo / "fake-project"
    (fake_project / "scripts").mkdir(parents=True)
    (fake_project / "scripts" / "remind-token-reduce.py").write_text(
        "raise RuntimeError('deliberately broken for the fail-open regression test')\n"
    )

    result = _run_shell(command, cwd=scratch_repo, project_dir=fake_project, stdin="{}")

    assert result.returncode == 0, (
        f"remind hook must fail open when the script crashes, "
        f"got returncode={result.returncode} stderr={result.stderr!r}"
    )


def test_enforce_hook_fails_open_on_cwd_drift_alone(scratch_repo: Path) -> None:
    """Reproduces the exact empirical trigger: cwd != repo root, CLAUDE_PROJECT_DIR unset,
    bare relative path can't resolve -- must not be treated as a block.
    Anchoring on CLAUDE_PROJECT_DIR (with a real value) is what fixes this in practice;
    this test pins the failure-mode side: no CLAUDE_PROJECT_DIR + wrong cwd must still
    fail open rather than block.
    """
    command = _hook_command("PreToolUse", "Bash", "enforce-token-reduce-first.py")
    payload = json.dumps({"session_id": "s1", "tool_name": "Bash", "tool_input": {"command": "echo hi"}})

    result = _run_shell(command, cwd=scratch_repo, project_dir=None, stdin=payload)

    assert result.returncode == 0, (
        f"cwd drift without CLAUDE_PROJECT_DIR must fail open, not block, "
        f"got returncode={result.returncode} stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    assert "decision" not in result.stdout


def test_enforce_hook_still_blocks_a_genuine_catastrophic_command(tmp_path: Path) -> None:
    """Control case: with a real, reachable repo, an actual block must still fire.

    This is the guard against overcorrecting -- proves the fail-open fix didn't
    neuter the enforcement hook itself.
    """
    command = _hook_command("PreToolUse", "Bash", "enforce-token-reduce-first.py")

    # Real checkout of the repo's scripts dir, anchored via CLAUDE_PROJECT_DIR,
    # exercised from an unrelated cwd (also proves path-anchoring fixes cwd drift
    # for the *working* case, not just the failure case).
    payload = json.dumps({"session_id": "s-catastrophic", "tool_name": "Bash", "tool_input": {"command": "find /etc/passwd"}})

    state_root = tmp_path / "state-root"
    state_root.mkdir()
    result = _run_shell(command, cwd=tmp_path, project_dir=REPO_ROOT, stdin=payload, state_root=state_root)

    assert result.returncode == 2, (
        f"genuine catastrophic command must still block, "
        f"got returncode={result.returncode} stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    decision = json.loads(result.stdout)
    assert decision["decision"] == "block"
