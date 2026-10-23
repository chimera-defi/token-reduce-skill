"""Tests for 2026-06-30 gate fixes.

Fix 1 (token-reduce-search.sh): trailing-newline while-read bug — three sites in
symbol_like_pattern(), path_pattern(), content_pattern() use `while IFS= read -r token`
without `|| [[ -n "$token" ]]`, silently dropping the last token when the process
substitution emits no trailing newline.

Fix 2 (benchmark-composite-stack.py): composite_stack hard-requires token-reduce-structural
and rtk; when token-savior is not installed the entire strategy is skipped and the
composite_gate fails.  The fix makes those tools optional with rg fallbacks.
"""
from __future__ import annotations

import importlib.util
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _init_git_repo(path: Path) -> None:
    subprocess.run(
        ["git", "-c", "init.defaultBranch=main", "init", "-q", str(path)],
        check=True,
        capture_output=True,
    )
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


def _path_without(tool: str) -> str:
    """Return PATH with directories that contain `tool` removed."""
    dirs = os.environ.get("PATH", "").split(":")
    return ":".join(d for d in dirs if d and not (Path(d) / tool).exists())


def _qmd_stub(tmp_path: Path) -> tuple[Path, Path]:
    """Create a QMD executable that records calls without touching a real index."""
    bindir = tmp_path / "bin"
    bindir.mkdir(parents=True, exist_ok=True)
    log = tmp_path / "qmd-calls.log"
    qmd = bindir / "qmd"
    qmd.write_text(
        "#!/usr/bin/env bash\n"
        "printf '%s\\n' \"$*\" >> \"$QMD_TEST_LOG\"\n"
        "if [[ \"$1 $2\" == 'collection list' ]]; then printf '%s\\n' \"${QMD_TEST_COLLECTIONS:-}\"; exit 0; fi\n"
        "if [[ \"$1\" == search ]]; then printf 'No results found.\\n'; fi\n"
        "exit 0\n"
    )
    qmd.chmod(0o755)
    uv = bindir / "uv"
    uv.write_text(
        "#!/usr/bin/env bash\n"
        "case \"$*\" in\n"
        "  *token_reduce_layers.py*) printf '%s\\n' \"${TOKEN_REDUCE_LAYER_SEARCH_QMD:-auto}\" ;;\n"
        "esac\n"
        "exit 0\n"
    )
    uv.chmod(0o755)
    return bindir, log


def _run_search_with_qmd(
    cwd: Path,
    stub_dir: Path,
    log: Path,
    *,
    repo_root: Path | None = None,
    home: Path | None = None,
    wrapper: bool = False,
    collections: str = "",
    refresh_ttl: str | None = None,
) -> subprocess.CompletedProcess[str]:
    env = {
        **os.environ,
        "PATH": f"{stub_dir}:{_path_without('uv')}",
        "QMD_TEST_LOG": str(log),
        "TOKEN_REDUCE_LAYER_SEARCH_QMD": "auto",
        "TOKEN_REDUCE_TELEMETRY_CONTEXT": "test",
        "QMD_TEST_COLLECTIONS": collections,
    }
    if repo_root is not None:
        env["TOKEN_REDUCE_REPO_ROOT"] = str(repo_root)
    if home is not None:
        env["HOME"] = str(home)
    if refresh_ttl is not None:
        env["TOKEN_REDUCE_QMD_REFRESH_TTL_SECONDS"] = refresh_ttl
    script = SCRIPTS_DIR / ("token-reduce-paths.sh" if wrapper else "token-reduce-search.sh")
    args = ["bash", str(script), "needle"] if wrapper else ["bash", str(script), "--paths-only", "needle"]
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True, env=env, timeout=30)


def _load_bcs():
    spec = importlib.util.spec_from_file_location(
        "benchmark_composite_stack",
        SCRIPTS_DIR / "benchmark-composite-stack.py",
    )
    module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    # Python 3.14 dataclasses needs the module in sys.modules before exec_module
    # so that string annotations on @dataclass fields resolve correctly.
    sys.modules["benchmark_composite_stack"] = module
    try:
        spec.loader.exec_module(module)  # type: ignore[union-attr]
    except Exception:
        del sys.modules["benchmark_composite_stack"]
        raise
    return module


# ---------------------------------------------------------------------------
# Fix 1 — while-read trailing-newline bug (token-reduce-search.sh)
# ---------------------------------------------------------------------------

def test_while_read_includes_last_underscore_token(tmp_path: Path) -> None:
    """Behavioral: last underscore-token in query must appear in output.

    printf '%s' emits no trailing newline; tr ... '\\n' therefore leaves the
    final token without a newline.  Without `|| [[ -n "$token" ]]`, the while-read
    loop's implicit `read` returns non-zero on EOF and the token is dropped.

    Setup: only a file matching the *last* token (beta_needle) exists — no file
    matches the first token (alpha_chunk).  Expect the file to be returned.
    """
    _init_git_repo(tmp_path)
    (tmp_path / "beta_needle.sh").write_text("# stub\n")

    env = {
        **os.environ,
        "PATH": _path_without("qmd"),
        "TOKEN_REDUCE_TELEMETRY_CONTEXT": "test",
    }
    result = subprocess.run(
        [
            "bash",
            str(SCRIPTS_DIR / "token-reduce-search.sh"),
            "--paths-only",
            "alpha_chunk beta_needle",
        ],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )

    assert "beta_needle" in result.stdout, (
        "Last token 'beta_needle' absent from output — trailing-newline while-read bug "
        "not fixed (missing `|| [[ -n \"$token\" ]]`).\n"
        f"stdout: {result.stdout!r}\nstderr: {result.stderr!r}"
    )






# ---------------------------------------------------------------------------
# QMD collection root eligibility
# ---------------------------------------------------------------------------

def test_search_does_not_register_non_git_directory(tmp_path: Path) -> None:
    """Non-Git cwd falls back to rg without creating a QMD collection or stamp."""
    with tempfile.TemporaryDirectory(prefix="token-reduce-nonrepo-") as raw_root:
        root = Path(raw_root)
        (root / "needle.txt").write_text("needle\n")
        stub_dir, log = _qmd_stub(tmp_path)

        result = _run_search_with_qmd(root, stub_dir, log)

        assert result.returncode == 0, result.stderr
        assert "needle.txt" in result.stdout
        assert not log.exists() or log.read_text() == ""
        assert not (root / "artifacts").exists()


def test_search_does_not_register_git_pytest_fixture(tmp_path: Path) -> None:
    """A Git-initialized pytest temporary tree still stays out of QMD."""
    _init_git_repo(tmp_path)
    (tmp_path / "needle.txt").write_text("needle\n")
    stub_dir, log = _qmd_stub(tmp_path / "qmd-stub")

    result = _run_search_with_qmd(tmp_path, stub_dir, log)

    assert result.returncode == 0, result.stderr
    assert "needle.txt" in result.stdout
    assert not log.exists() or log.read_text() == ""
    assert not (tmp_path / "artifacts").exists()


def test_search_does_not_register_nested_alternate_pytest_root(tmp_path: Path) -> None:
    """A pytest-of-* path component stays excluded below any temp parent."""
    with tempfile.TemporaryDirectory(prefix="token-reduce-custom-root-") as raw_parent:
        root = Path(raw_parent) / "pytest-of-alternate" / "session" / "repo"
        root.mkdir(parents=True)
        _init_git_repo(root)
        (root / "needle.txt").write_text("needle\n")
        stub_dir, log = _qmd_stub(tmp_path / "qmd-stub")

        result = _run_search_with_qmd(root, stub_dir, log)

        assert result.returncode == 0, result.stderr
        assert "needle.txt" in result.stdout
        assert not log.exists() or log.read_text() == ""
        assert not (root / "artifacts").exists()


@pytest.mark.parametrize("aggregate", ["home", "workspace"])
def test_paths_wrapper_honors_aggregate_root_override(
    aggregate: str, tmp_path: Path
) -> None:
    """The wrapper propagates root overrides and skips aggregate QMD indexing."""
    with tempfile.TemporaryDirectory(prefix="token-reduce-root-override-") as raw_root:
        sandbox = Path(raw_root)
        home = sandbox / "home"
        root = home if aggregate == "home" else home / "workspace"
        root.mkdir(parents=True)
        repo = sandbox / "valid-repo"
        repo.mkdir()
        _init_git_repo(repo)
        (repo / "needle.txt").write_text("needle\n")
        stub_dir, log = _qmd_stub(tmp_path / "qmd-stub")

        result = _run_search_with_qmd(
            repo, stub_dir, log, repo_root=root, home=home, wrapper=True
        )

        assert result.returncode == 0, result.stderr
        assert not log.exists() or log.read_text() == ""
        assert not (root / "artifacts").exists()


def test_search_missing_qmd_collection_falls_back_without_registration(tmp_path: Path) -> None:
    """An unregistered Git checkout uses rg without QMD collection mutation."""
    with tempfile.TemporaryDirectory(prefix="token-reduce-valid-repo-") as raw_root:
        root = Path(raw_root)
        _init_git_repo(root)
        (root / "needle.txt").write_text("needle\n")
        stub_dir, log = _qmd_stub(tmp_path)

        result = _run_search_with_qmd(root, stub_dir, log)

        assert result.returncode == 0, result.stderr
        assert "needle.txt" in result.stdout
        calls = log.read_text().splitlines()
        assert calls == ["collection list"]
        assert not (root / "artifacts").exists()


def test_search_existing_collection_fingerprint_change_is_read_only(tmp_path: Path) -> None:
    """A stale fingerprint never removes/re-adds an existing QMD collection."""
    with tempfile.TemporaryDirectory(prefix="token-reduce-existing-repo-") as raw_root:
        root = Path(raw_root)
        _init_git_repo(root)
        (root / "needle.txt").write_text("needle\n")
        collection = f"repo-{hashlib.sha1(str(root).encode()).hexdigest()[:12]}"
        stamp = root / "artifacts" / f"qmd-{collection}.stamp"
        stamp.parent.mkdir(parents=True)
        stamp.write_text("old-fingerprint")
        stub_dir, log = _qmd_stub(tmp_path)

        result = _run_search_with_qmd(
            root,
            stub_dir,
            log,
            collections=f"{collection} {root}",
            refresh_ttl="0",
        )

        assert result.returncode == 0, result.stderr
        calls = log.read_text().splitlines()
        assert "collection list" in calls
        assert any(call.startswith("search needle") for call in calls)
        assert not any(call.startswith(("collection add", "collection remove", "update")) for call in calls)
        assert stamp.read_text() == "old-fingerprint"


def test_search_keeps_qmd_for_linked_git_worktree(tmp_path: Path) -> None:
    """A linked worktree uses an existing QMD collection without mutation."""
    with tempfile.TemporaryDirectory(prefix="token-reduce-linked-control-") as raw_root:
        sandbox = Path(raw_root)
        source = sandbox / "source"
        linked = sandbox / "linked"
        source.mkdir()
        _init_git_repo(source)
        (source / "needle.txt").write_text("needle\n")
        subprocess.run(
            ["git", "-C", str(source), "add", "needle.txt"],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(source), "commit", "-m", "fixture"],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(source), "worktree", "add", "--detach", str(linked)],
            check=True,
            capture_output=True,
        )
        collection = f"repo-{hashlib.sha1(str(linked).encode()).hexdigest()[:12]}"
        stub_dir, log = _qmd_stub(tmp_path)

        result = _run_search_with_qmd(linked, stub_dir, log, collections=f"{collection} {linked}")

        assert result.returncode == 0, result.stderr
        calls = log.read_text().splitlines()
        assert "collection list" in calls
        assert any(call.startswith("search needle") for call in calls)
        assert not any(call.startswith(("collection add", "collection remove", "update")) for call in calls)
        assert not (linked / "artifacts").exists()


def test_setup_never_auto_registers_qmd_collection() -> None:
    """Setup may inspect registration but cannot mutate the shared QMD index."""
    setup_source = (SCRIPTS_DIR / "setup.sh").read_text()
    assert "qmd collection list" in setup_source
    assert "qmd collection add" not in setup_source
    assert "qmd collection remove" not in setup_source


# ---------------------------------------------------------------------------
# Fix 2 — composite_stack token-savior fallback (benchmark-composite-stack.py)
# ---------------------------------------------------------------------------

def test_composite_stack_available_without_token_savior(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Behavioral: composite_stack must appear available=True when token-savior absent.

    Before fix: composite_stack has hard requirements on token-reduce-structural and
    rtk → strategy is skipped (available=False) when token-savior is not installed.
    After fix: requirements only include tools with guaranteed rg fallbacks.
    """
    bcs = _load_bcs()

    monkeypatch.setattr(bcs, "OUTPUT_PATH", tmp_path / "out.json")

    orig_which = bcs.shutil.which

    def patched_which(tool: str) -> str | None:
        if tool in ("token-reduce-structural", "rtk"):
            return None
        if tool == "token-reduce-paths":
            return "/usr/bin/true"
        return orig_which(tool)

    monkeypatch.setattr(bcs.shutil, "which", patched_which)
    # _token_savior_functional() uses importlib.util.find_spec, not shutil.which
    monkeypatch.setattr(bcs, "_token_savior_functional", lambda: False)

    def fake_run_cmd(command: str, expected_substrings: list) -> object:
        return bcs.StepResult(
            label="",
            command=command,
            exit_code=0,
            duration_ms=1,
            bytes=100,
            lines=5,
            tokens=20,
            quality_pass=True,
            quality_note="ok",
            stdout_preview="mocked",
        )

    monkeypatch.setattr(bcs, "run_cmd", fake_run_cmd)
    monkeypatch.setattr(bcs, "ensure_qmd_collection", lambda: False)

    bcs.main()

    result = json.loads((tmp_path / "out.json").read_text())
    composite = next(
        (b for b in result["benchmarks"] if b["name"] == "composite_stack"), None
    )
    assert composite is not None, "composite_stack row missing from benchmark output"
    assert composite["available"], (
        "composite_stack must be available=True even without token-savior — "
        "token-reduce-structural and rtk must not be hard requirements."
    )
    qmd_only = next(b for b in result["benchmarks"] if b["name"] == "qmd_only")
    assert not qmd_only["available"]
    assert "not registered" in qmd_only["skipped_reason"]


@pytest.mark.parametrize("listed,registered", [("", False), ("repo-test /tmp/repo\n", True)])
def test_benchmark_qmd_registration_check_is_read_only(
    monkeypatch: pytest.MonkeyPatch,
    listed: str,
    registered: bool,
) -> None:
    bcs = _load_bcs()
    calls: list[list[str]] = []
    monkeypatch.setattr(bcs, "QMD_COLLECTION", "repo-test")
    monkeypatch.setattr(bcs.shutil, "which", lambda tool: "/fake/qmd" if tool == "qmd" else None)

    def fake_run(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        assert kwargs["capture_output"] is True
        assert kwargs["check"] is False
        return subprocess.CompletedProcess(argv, 0, stdout=listed, stderr="")

    monkeypatch.setattr(bcs.subprocess, "run", fake_run)
    assert bcs.ensure_qmd_collection() is registered
    assert calls == [["/fake/qmd", "collection", "list"]]



def test_while_read_includes_last_token_without_underscore(tmp_path: Path) -> None:
    """Behavioral: last word token in path_pattern() word-fallback must not be dropped.

    When a query has no underscore-containing tokens, symbol_like_pattern() returns
    exit 1 and path_pattern() falls through to its own while-read word-tokenizer loop
    (the second of the three bug sites).  Use a pure-word query so that code path runs.
    """
    _init_git_repo(tmp_path)
    # File matches only the *last* word of the query (not the first).
    (tmp_path / "zebra.sh").write_text("# stub\n")

    env = {
        **os.environ,
        "PATH": _path_without("qmd"),
        "TOKEN_REDUCE_TELEMETRY_CONTEXT": "test",
    }
    result = subprocess.run(
        [
            "bash",
            str(SCRIPTS_DIR / "token-reduce-search.sh"),
            "--paths-only",
            # No underscore → symbol_like_pattern() fails → word-tokenizer runs.
            # 'mango' is first token (≥4 chars); 'zebra' is last (≥4 chars).
            # Without fix: printf '%s' emits no trailing newline, zebra is dropped.
            "mango zebra",
        ],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )

    assert "zebra" in result.stdout, (
        "Last word token 'zebra' absent — trailing-newline bug in path_pattern() "
        "word-tokenizer fallback (second while-read site).\n"
        f"stdout: {result.stdout!r}\nstderr: {result.stderr!r}"
    )
