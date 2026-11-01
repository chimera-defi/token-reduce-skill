import hashlib
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SEARCH = REPO_ROOT / "scripts" / "token-reduce-search.sh"
ADAPTIVE = REPO_ROOT / "scripts" / "token_reduce_adaptive.py"


def _stub(bin_dir: Path, name: str, body: str) -> None:
    path = bin_dir / name
    path.write_text("#!/bin/sh\n" + body)
    path.chmod(0o755)


def _git_repo(path: Path) -> None:
    path.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(path)], check=True)


ROOT_KINDS = ["home", "workspace", "workspace_symlink", "workspace_target_symlink"]
ENTRY_POINTS = ["search", "search_snippets", "paths", "snippet", "adaptive", "adaptive_shell"]
PRIVATE_NAMES = [
    "agent-memory", "secrets", ".ssh", ".gnupg", ".codex", ".claude",
    ".config", ".local", ".cache", "state", "private", "node_modules",
    ".git", "venv", ".venv", "venvs", ".venvs", "env", ".env",
    "virtualenv", ".virtualenv", "worktree-holdout", "worktree-HOLDOUT",
]


def _aggregate_setup(tmp_path, root_kind):
    home = tmp_path / "home"
    workspace = home / "workspace"
    home.mkdir()
    if root_kind == "workspace_target_symlink":
        target = tmp_path / "actual-workspace"
        target.mkdir()
        workspace.symlink_to(target, target_is_directory=True)
    else:
        workspace.mkdir()
    if root_kind == "home":
        root = home
    elif root_kind == "workspace_symlink":
        root = tmp_path / "workspace-link"
        root.symlink_to(workspace, target_is_directory=True)
    else:
        root = workspace
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    calls = tmp_path / "calls"
    real_rg = shutil.which("rg")
    assert real_rg
    for name in ("uv", "qmd"):
        _stub(bin_dir, name, f'echo {name} >> "{calls}"\nexit 99\n')
    _stub(bin_dir, "rg", f'echo "rg:$*" >> "{calls}"\nexec {shlex.quote(real_rg)} "$@"\n')
    env = os.environ.copy()
    env.pop("CLAUDE_PROJECT_DIR", None)
    env.update(HOME=str(home), TOKEN_REDUCE_REPO_ROOT=str(root), PATH=f"{bin_dir}:{env['PATH']}")
    return home, workspace, root, calls, env


def _run_aggregate(entry, root, env, query="needle", extra=(), cwd=None):
    if entry == "adaptive":
        command = [sys.executable, str(ADAPTIVE), "--repo-root", str(root), *extra, query]
    elif entry == "search_snippets":
        command = [str(SEARCH), "--snippets", query]
    else:
        script = SEARCH if entry == "search" else SEARCH.with_name(f"token-reduce-{entry.removesuffix('_shell')}.sh")
        command = [str(script), *extra, query]
    return subprocess.run(command, cwd=cwd or root, env=env, capture_output=True, text=True, timeout=10)


@pytest.mark.parametrize("root_kind", ROOT_KINDS)
@pytest.mark.parametrize("entry", ENTRY_POINTS)
def test_aggregate_home_fallback_before_qmd_or_uv(tmp_path, root_kind, entry):
    home, workspace, root, calls, env = _aggregate_setup(tmp_path, root_kind)
    repo = workspace / "repo1"
    repo.mkdir()
    (repo / "README.md").write_text("needle contents must never be printed")
    (home / "AGENTS.md").write_text("needle home contents")
    (home / "not-home-scope.py").write_text("needle")
    (home / "other" / "nested").mkdir(parents=True)
    (home / "other" / "nested" / "a.md").write_text("needle")
    for name in PRIVATE_NAMES:
        for base in (home, repo):
            directory = base / name
            directory.mkdir()
            (directory / "hidden.md").write_text("needle")
    (repo / "private-alias").symlink_to(home / "agent-memory", target_is_directory=True)
    (repo / "alias.md").symlink_to(home / "secrets" / "hidden.md")
    (home / "alias.md").symlink_to(home / "agent-memory" / "hidden.md")
    before = sorted(str(p) for p in home.rglob("*"))

    result = _run_aggregate(entry, root, env)

    assert result.returncode == 0, result.stderr
    lines = result.stdout.splitlines()
    readme = str((workspace / "repo1" / "README.md").resolve())
    assert readme in lines
    assert set(lines) == {readme, *([str(home / "AGENTS.md")] if root_kind == "home" else [])}
    assert result.stderr.splitlines()[0] == (
        f"[token-reduce-search] aggregate root '{root.resolve()}': bounded fallback "
        "(no QMD, private dirs excluded); narrow with TOKEN_REDUCE_REPO_ROOT=<repo> or cd into it"
    )
    recorded = calls.read_text().splitlines()
    assert len(recorded) == 1
    assert recorded[0].startswith("rg:")
    assert "--max-depth 3" in recorded[0]
    assert "--max-filesize 1M" in recorded[0]
    assert sorted(str(p) for p in home.rglob("*")) == before


@pytest.mark.parametrize("root_kind", ROOT_KINDS)
def test_adaptive_dry_run_aggregate_before_search_subprocesses(tmp_path, root_kind):
    _, _, root, calls, env = _aggregate_setup(tmp_path, root_kind)
    result = _run_aggregate("adaptive", root, env, extra=("--dry-run",))
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["tier"] == "paths"
    assert payload["command"] == [str(SEARCH), "--paths-only", "needle"]
    assert not calls.exists()


@pytest.mark.parametrize("entry", ENTRY_POINTS)
def test_aggregate_no_matches_preserves_rg_status(tmp_path, entry):
    home, workspace, root, calls, env = _aggregate_setup(tmp_path, "home")
    (workspace / "repo1" / "private").mkdir(parents=True)
    (workspace / "repo1" / "private" / "p.md").write_text("needle")
    for name in ("agent-memory", ".codex", "secrets"):
        (home / name).mkdir()
        (home / name / "x.md").write_text("needle")
    result = _run_aggregate(entry, root, env)
    assert result.returncode == 1, result.stderr
    assert result.stdout == ""
    assert len(calls.read_text().splitlines()) == 1


def test_aggregate_depth_size_extensions_and_result_cap(tmp_path):
    _, workspace, root, calls, env = _aggregate_setup(tmp_path, "workspace")
    repo = workspace / "repo1"
    (repo / "deep" / "too-deep").mkdir(parents=True)
    (repo / "deep" / "boundary.md").write_text("boundary")
    (repo / "deep" / "too-deep" / "beyond.md").write_text("boundary")
    for extension in ("md", "toml", "json", "sh", "py", "txt", "csv"):
        (repo / f"source.{extension}").write_text("extension")
    (repo / "large.md").write_text("large-needle" + "x" * (1024 * 1024))
    assert _run_aggregate("search", root, env, "boundary").stdout.splitlines() == [str((workspace / "repo1" / "deep" / "boundary.md").resolve())]
    assert set(_run_aggregate("search", root, env, "extension").stdout.splitlines()) == {
        str((workspace / "repo1" / f"source.{ext}").resolve()) for ext in ("md", "toml", "json", "sh", "py")
    }
    assert _run_aggregate("search", root, env, "large-needle").returncode == 1
    for index in range(1000):
        (repo / f"match-{index}.md").write_text("many-needle")
    result = _run_aggregate("search", root, env, "many-needle")
    assert result.returncode == 0
    assert len(result.stdout.splitlines()) == 20
    assert len(calls.read_text().splitlines()) == 4


def test_home_without_workspace_only_searches_top_level_markdown(tmp_path):
    home, workspace, root, calls, env = _aggregate_setup(tmp_path, "home")
    workspace.rmdir()
    (home / "README.md").write_text("needle")
    (home / "script.py").write_text("needle")
    (home / "large.md").write_text("needle" + "x" * (1024 * 1024))
    (home / "other").mkdir()
    (home / "other" / "nested.md").write_text("needle")
    result = _run_aggregate("search", root, env)
    assert result.returncode == 0
    assert result.stdout.splitlines() == [str(home / "README.md")]
    assert "--max-depth 1" in calls.read_text()


def test_workspace_symlink_to_home_does_not_expand_home_scope(tmp_path):
    home, workspace, root, _, env = _aggregate_setup(tmp_path, "home")
    workspace.rmdir()
    workspace.symlink_to(home, target_is_directory=True)
    (home / "README.md").write_text("needle")
    (home / "script.py").write_text("needle")
    result = _run_aggregate("search", root, env)
    assert result.returncode == 0
    assert result.stdout.splitlines() == [str(home / "README.md")]


@pytest.mark.parametrize("entry", ["search", "adaptive_shell"])
def test_aggregate_detected_from_cwd_and_explicit_adaptive_argument(tmp_path, entry):
    _, workspace, root, calls, env = _aggregate_setup(tmp_path, "workspace")
    (workspace / "README.md").write_text("needle")
    env.pop("TOKEN_REDUCE_REPO_ROOT")
    extra = ("--repo-root", str(root)) if entry == "adaptive_shell" else ()
    result = _run_aggregate(entry, root, env, extra=extra, cwd=REPO_ROOT if extra else root)
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == [str((workspace / "README.md").resolve())]
    assert len(calls.read_text().splitlines()) == 1


def test_aggregate_ignores_rg_config_and_ignore_files(tmp_path):
    _, workspace, root, calls, env = _aggregate_setup(tmp_path, "workspace")
    (workspace / "README.md").write_text("needle")
    config = tmp_path / "rg-config"
    config.write_text("--pre=qmd\n--follow\n")
    env["RIPGREP_CONFIG_PATH"] = str(config)
    (workspace / ".ignore").write_text("*.md\n")
    result = _run_aggregate("search", root, env)
    assert result.returncode == 0
    assert result.stdout.splitlines() == [str((workspace / "README.md").resolve())]
    assert len(calls.read_text().splitlines()) == 1


def test_private_workspace_symlink_is_never_searched(tmp_path):
    home, workspace, root, calls, env = _aggregate_setup(tmp_path, "home")
    workspace.rmdir()
    private = home / "agent-memory"
    private.mkdir()
    (private / "x.md").write_text("needle")
    workspace.symlink_to(private, target_is_directory=True)
    result = _run_aggregate("search", root, env)
    assert result.returncode == 1
    assert result.stdout == ""
    assert not calls.exists()


def test_aggregate_inside_home_git_repo_still_uses_bounded_fallback(tmp_path):
    home, workspace, root, calls, env = _aggregate_setup(tmp_path, "workspace")
    subprocess.run(["git", "init", "-q", str(home)], check=True)
    (workspace / "README.md").write_text("needle")
    result = _run_aggregate("search", root, env)
    assert result.returncode == 0
    assert result.stdout.splitlines() == [str((workspace / "README.md").resolve())]
    assert len(calls.read_text().splitlines()) == 1


def test_collection_show_is_bounded_and_falls_back_inside_repo(tmp_path):
    temp_root = Path(tempfile.mkdtemp(prefix="qmd-eligible-repo-"))
    repo = temp_root / "repo"
    _git_repo(repo)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    calls = tmp_path / "calls"
    _stub(bin_dir, "uv", f'echo "uv:$*" >> "{calls}"\nprintf auto\n')
    _stub(bin_dir, "qmd", f'echo "qmd:$*" >> "{calls}"\nsleep 5\n')
    _stub(bin_dir, "rg", f'echo "rg:$PWD:$*" >> "{calls}"\nexit 1\n')
    env = os.environ.copy()
    env.update(
        HOME=str(tmp_path / "home"),
        TOKEN_REDUCE_REPO_ROOT=str(repo),
        TOKEN_REDUCE_QMD_COLLECTION_CHECK_TIMEOUT_SECONDS="1",
        PATH=f"{bin_dir}:{env['PATH']}",
    )
    start = time.monotonic()

    try:
        result = subprocess.run([str(SEARCH), "--paths-only", "needle"], cwd=repo, env=env, capture_output=True, text=True, timeout=4)

        assert time.monotonic() - start < 4
        assert result.returncode == 0
        recorded = calls.read_text()
        assert "uv:run --no-project" in recorded
        assert "qmd:collection show " in recorded
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
    _stub(bin_dir, "uv", f'echo "uv:$*" >> "{calls}"\nprintf auto\n')
    _stub(bin_dir, "qmd", f'echo "qmd:$*" >> "{calls}"\nif [ "$1 $2" = "collection show" ]; then printf "Collection: {collection}\\n"; exit 0; fi\nif [ "$1" = search ]; then printf "qmd://{collection}/README.md  #abcdef\\n"; exit 0; fi\nexit 1\n')
    _stub(bin_dir, "rg", f'echo "rg:$PWD:$*" >> "{calls}"\nexit 1\n')
    env = os.environ.copy()
    env.update(HOME=str(tmp_path / "home"), TOKEN_REDUCE_REPO_ROOT=str(repo), PATH=f"{bin_dir}:{env['PATH']}")

    try:
        result = subprocess.run([str(SEARCH), "--paths-only", "needle"], cwd=repo, env=env, capture_output=True, text=True, timeout=5)

        assert result.returncode == 0
        recorded = calls.read_text()
        assert "uv:run --no-project" in recorded
        assert f"qmd:collection show {collection}" in recorded
        assert "qmd:search" in recorded
        assert f"qmd://{collection}/README.md" in result.stdout
        assert ":--files " not in recorded
        assert "falling back to rg" not in result.stderr
        assert "bounded fallback" not in result.stderr
    finally:
        shutil.rmtree(temp_root)
