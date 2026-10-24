import hashlib
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SEARCH = REPO_ROOT / "scripts" / "token-reduce-search.sh"


def _stub(bin_dir: Path, name: str, body: str) -> None:
    path = bin_dir / name
    path.write_text("#!/bin/sh\n" + body)
    path.chmod(0o755)


def _git_repo(path: Path) -> None:
    path.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(path)], check=True)


@pytest.mark.parametrize("root_kind", ["home", "workspace", "workspace_symlink"])
def test_aggregate_home_refuses_before_qmd_or_rg(tmp_path, root_kind):
    home = tmp_path / "home"
    (home / "workspace").mkdir(parents=True)
    if root_kind == "home":
        root = home
    elif root_kind == "workspace":
        root = home / "workspace"
    else:
        root = tmp_path / "workspace-link"
        root.symlink_to(home / "workspace", target_is_directory=True)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    calls = tmp_path / "calls"
    _stub(bin_dir, "uv", f'echo uv >> "{calls}"\nexit 0\n')
    _stub(bin_dir, "qmd", f'echo qmd >> "{calls}"\nexit 0\n')
    _stub(bin_dir, "rg", f'echo rg >> "{calls}"\nexit 0\n')
    env = os.environ.copy()
    env.update(HOME=str(home), TOKEN_REDUCE_REPO_ROOT=str(root), PATH=f"{bin_dir}:{env['PATH']}")

    result = subprocess.run([str(SEARCH), "--paths-only", "needle"], env=env, capture_output=True, text=True)

    assert result.returncode == 2
    assert "refusing aggregate root" in result.stderr
    assert "TOKEN_REDUCE_REPO_ROOT" in result.stderr
    assert not calls.exists()


def test_collection_list_is_bounded_and_falls_back_inside_repo(tmp_path):
    temp_root = Path(tempfile.mkdtemp(prefix="qmd-eligible-repo-"))
    repo = temp_root / "repo"
    _git_repo(repo)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    calls = tmp_path / "calls"
    _stub(bin_dir, "uv", 'printf auto\n')
    _stub(bin_dir, "qmd", f'echo "qmd:$*" >> "{calls}"\nsleep 5\n')
    _stub(bin_dir, "rg", f'echo "rg:$PWD:$*" >> "{calls}"\nexit 1\n')
    env = os.environ.copy()
    env.update(
        HOME=str(tmp_path / "home"),
        TOKEN_REDUCE_REPO_ROOT=str(repo),
        TOKEN_REDUCE_QMD_COLLECTION_LIST_TIMEOUT_SECONDS="1",
        PATH=f"{bin_dir}:{env['PATH']}",
    )
    start = time.monotonic()

    try:
        result = subprocess.run([str(SEARCH), "--paths-only", "needle"], cwd=repo, env=env, capture_output=True, text=True, timeout=4)

        assert time.monotonic() - start < 4
        assert result.returncode == 0
        recorded = calls.read_text()
        assert "qmd:collection list" in recorded
        assert f"rg:{repo}:" in recorded
        assert str(tmp_path) not in recorded.replace(str(repo), "")
    finally:
        shutil.rmtree(temp_root)


def test_registered_collection_still_uses_qmd(tmp_path):
    temp_root = Path(tempfile.mkdtemp(prefix="qmd-eligible-repo-"))
    repo = temp_root / "repo"
    _git_repo(repo)
    collection = "repo-" + hashlib.sha1(str(repo).encode()).hexdigest()[:12]
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    calls = tmp_path / "calls"
    _stub(bin_dir, "uv", 'printf auto\n')
    _stub(bin_dir, "qmd", f'echo "qmd:$*" >> "{calls}"\nif [ "$1" = collection ]; then printf "{collection}  /tmp/docs\\n"; exit 0; fi\nexit 1\n')
    _stub(bin_dir, "rg", f'echo "rg:$PWD:$*" >> "{calls}"\nexit 1\n')
    env = os.environ.copy()
    env.update(HOME=str(tmp_path / "home"), TOKEN_REDUCE_REPO_ROOT=str(repo), PATH=f"{bin_dir}:{env['PATH']}")

    try:
        result = subprocess.run([str(SEARCH), "--paths-only", "needle"], cwd=repo, env=env, capture_output=True, text=True, timeout=5)

        assert result.returncode == 0
        recorded = calls.read_text()
        assert "qmd:collection list" in recorded
        assert "qmd:search" in recorded
        assert f"rg:{repo}:" in recorded
    finally:
        shutil.rmtree(temp_root)


def test_large_collection_list_completes_without_early_pipe_close(tmp_path):
    temp_root = Path(tempfile.mkdtemp(prefix="qmd-eligible-repo-"))
    repo = temp_root / "repo"
    _git_repo(repo)
    collection = "repo-" + hashlib.sha1(str(repo).encode()).hexdigest()[:12]
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    calls = tmp_path / "calls"
    _stub(bin_dir, "uv", 'printf auto\n')
    _stub(
        bin_dir,
        "qmd",
        f'if [ "$1" = collection ]; then printf "{collection}  /tmp/docs\\n"; i=0; while [ "$i" -lt 12000 ]; do printf "collection-%s /tmp/docs\\n" "$i"; i=$((i+1)); done; exit 0; fi\necho "qmd:$*" >> "{calls}"\nprintf "qmd://{collection}/README.md  #abcdef\\n"\n',
    )
    _stub(bin_dir, "rg", f'echo "rg:$PWD:$*" >> "{calls}"\nexit 1\n')
    env = os.environ.copy()
    env.update(HOME=str(tmp_path / "home"), TOKEN_REDUCE_REPO_ROOT=str(repo), PATH=f"{bin_dir}:{env['PATH']}")

    try:
        result = subprocess.run([str(SEARCH), "--paths-only", "needle"], cwd=repo, env=env, capture_output=True, text=True, timeout=5)

        assert result.returncode == 0
        assert f"qmd://{collection}/README.md" in result.stdout
        recorded = calls.read_text()
        assert "qmd:search" in recorded
        assert ":--files " not in recorded
        assert "falling back to rg" not in result.stderr
    finally:
        shutil.rmtree(temp_root)
