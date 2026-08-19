"""Coverage for scripts/token-reduce-adaptive.sh hardening: uv bypass to
python3, outer timeout, and fail-open when neither runner nor the target
script is available.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "token-reduce-adaptive.sh"


def _make_bindir(tmp_path: Path, tools: list[str]) -> Path:
    """A PATH dir containing only symlinks to the given tool names."""
    bindir = tmp_path / "bin"
    bindir.mkdir()
    for name in tools:
        real = shutil.which(name)
        if real:
            (bindir / name).symlink_to(real)
    return bindir


def _run(args: list[str], *, path: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PATH"] = path
    return subprocess.run(
        ["bash", str(SCRIPT), *args],
        capture_output=True,
        text=True,
        cwd=str(cwd),
        env=env,
        timeout=30,
    )


def test_still_works_with_real_uv(tmp_path: Path) -> None:
    result = _run(["--dry-run", "state", "ttl", "seconds"], path=os.environ["PATH"], cwd=tmp_path)
    assert result.returncode == 0, result.stderr
    assert '"tier"' in result.stdout


def test_falls_back_to_python3_when_uv_missing(tmp_path: Path) -> None:
    # Build a PATH with a python3 shim but no uv.
    bindir = _make_bindir(tmp_path, ["python3", "bash", "timeout", "env", "dirname"])
    result = _run(["--dry-run", "state", "ttl", "seconds"], path=str(bindir), cwd=tmp_path)
    assert result.returncode == 0, result.stderr
    assert '"tier"' in result.stdout


def test_fails_open_when_neither_uv_nor_python3_available(tmp_path: Path) -> None:
    bindir = _make_bindir(tmp_path, ["bash", "timeout", "env", "dirname"])
    result = _run(["state", "ttl"], path=str(bindir), cwd=tmp_path)
    assert result.returncode == 0, (
        f"must fail open when no runner is available, got rc={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    assert "skipping helper" in result.stderr
