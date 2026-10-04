"""Regression: runtime `uv run` calls must pass --no-project.

Without --no-project, `uv run python ...` invoked with cwd inside another repo
that has a pyproject.toml resolves that repo as the project and creates or
syncs its .venv and uv.lock — a side effect in someone else's repo. The
token-reduce skill repo has no pyproject.toml, so --no-project never changes
behaviour for the skill itself; inline-script metadata is still honoured.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
RUNTIME_SCRIPTS = (
    "token-reduce-paths.sh",
    "token-reduce-snippet.sh",
    "token-reduce-adaptive.sh",
    "token-reduce-manage.sh",
    # reached from token-reduce-manage.sh (measure, release-gate) without a cd
    "baseline-measurement.sh",
    "release-gate.sh",
)
UV_RUN_RE = re.compile(r"\buv\s+run\b(?!\s+--no-project\b)")


@pytest.mark.parametrize("name", RUNTIME_SCRIPTS)
def test_runtime_scripts_pass_no_project(name: str) -> None:
    offenders = [
        f"{name}:{i}: {ln.strip()}"
        for i, ln in enumerate((SCRIPTS_DIR / name).read_text().splitlines(), 1)
        if not ln.strip().startswith("#") and UV_RUN_RE.search(ln)
    ]
    assert not offenders, "uv run without --no-project:\n" + "\n".join(offenders)


def _foreign_repo(path: Path) -> Path:
    path.mkdir()
    subprocess.run(["git", "-c", "init.defaultBranch=main", "init", "-q", str(path)], check=True)
    (path / "pyproject.toml").write_text(
        '[project]\nname = "foreign"\nversion = "0.0.0"\nrequires-python = ">=3.10"\ndependencies = []\n'
    )
    (path / "mod.py").write_text("def hello():\n    return 1\n")
    return path


@pytest.mark.skipif(shutil.which("uv") is None, reason="uv not installed")
def test_paths_sh_does_not_bootstrap_foreign_project(tmp_path: Path) -> None:
    repo = _foreign_repo(tmp_path / "foreign")
    env = dict(os.environ, UV_CACHE_DIR=str(tmp_path / "uv-cache"))
    out = subprocess.run(
        ["bash", str(SCRIPTS_DIR / "token-reduce-paths.sh"), "hello"],
        cwd=repo, env=env, capture_output=True, text=True, timeout=180,
    )
    assert out.returncode == 0, f"paths.sh failed (rc={out.returncode}): {out.stderr[-2000:]}"
    assert not (repo / ".venv").exists(), "token-reduce-paths.sh created .venv in a foreign repo"
    assert not (repo / "uv.lock").exists(), "token-reduce-paths.sh created uv.lock in a foreign repo"


@pytest.mark.skipif(shutil.which("uv") is None, reason="uv not installed")
def test_no_project_keeps_inline_script_metadata(tmp_path: Path) -> None:
    repo = _foreign_repo(tmp_path / "foreign")
    script = tmp_path / "meta.py"
    script.write_text(
        '# /// script\n# requires-python = ">=3.10"\n# dependencies = []\n# ///\nprint("meta-ok")\n'
    )
    env = dict(os.environ, UV_CACHE_DIR=str(tmp_path / "uv-cache"))
    out = subprocess.run(
        ["uv", "run", "--no-project", str(script)],
        cwd=repo, env=env, capture_output=True, text=True, timeout=120,
    )
    assert out.returncode == 0 and "meta-ok" in out.stdout
    assert not (repo / ".venv").exists()


@pytest.mark.skipif(shutil.which("uv") is None, reason="uv not installed")
def test_no_project_still_enforces_inline_requires_python(tmp_path: Path) -> None:
    """Proves the metadata block is read under --no-project, not ignored."""
    repo = _foreign_repo(tmp_path / "foreign")
    script = tmp_path / "meta_bad.py"
    script.write_text('# /// script\n# requires-python = ">=99"\n# dependencies = []\n# ///\nprint("ran")\n')
    env = dict(os.environ, UV_CACHE_DIR=str(tmp_path / "uv-cache"), UV_OFFLINE="1")
    out = subprocess.run(
        ["uv", "run", "--no-project", str(script)],
        cwd=repo, env=env, capture_output=True, text=True, timeout=120,
    )
    assert out.returncode != 0 and "ran" not in out.stdout
    assert "99" in out.stderr
    assert not (repo / ".venv").exists()
