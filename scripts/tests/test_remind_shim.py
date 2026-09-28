"""scripts/remind-token-reduce.py was retired 2026-09-28 (operator ruling: 93%
of its firings were on harness-generated turns, and the PreToolUse enforcer's
own false-positive tightening made the separate reminder redundant -- see
references/worktree-deploy-sync.md).

The file itself stays in place as an inert shim ONLY because Etc-mono-repo's
`.claude/settings.json` invokes it raw (no `uv run`, no fail-open wrapper) via
a symlinked copy of this skill's `scripts/` directory. These tests pin that
contract directly at the Python level: for any stdin (valid JSON, garbage, or
empty), the shim must exit 0 and print nothing.
"""
from __future__ import annotations

import stat
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
SHIM = SCRIPTS_DIR / "remind-token-reduce.py"


def _run(stdin: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SHIM)],
        input=stdin,
        text=True,
        capture_output=True,
        timeout=30,
    )


def test_shim_file_is_executable() -> None:
    mode = SHIM.stat().st_mode
    assert mode & stat.S_IXUSR, f"{SHIM} must stay executable for a raw (no `uv run`) consumer invocation"


@pytest.mark.parametrize(
    "stdin",
    [
        '{"session_id": "s1", "prompt": "where is the auth hook defined in this repo"}',
        "not valid json at all {{{",
        "",
    ],
    ids=["valid-json", "garbage", "empty"],
)
def test_shim_exits_zero_and_silent(stdin: str) -> None:
    result = _run(stdin)
    assert result.returncode == 0, (
        f"shim must always exit 0, got returncode={result.returncode} stderr={result.stderr!r}"
    )
    assert result.stdout == "", f"shim must print nothing to stdout, got {result.stdout!r}"
