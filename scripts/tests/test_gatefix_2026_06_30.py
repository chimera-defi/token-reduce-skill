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
import json
import os
import shutil
import subprocess
import sys
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


def test_three_sites_have_trailing_newline_guard() -> None:
    """Static: all three while-read sites must use `|| [[ -n \"$token\" ]]`."""
    source = (SCRIPTS_DIR / "token-reduce-search.sh").read_text()
    # Count how many while-read loops have the guard vs without
    guarded = source.count('while IFS= read -r token || [[ -n "$token" ]]; do')
    unguarded = source.count('while IFS= read -r token; do')
    assert unguarded == 0, (
        f"Found {unguarded} unguarded `while IFS= read -r token; do` sites — "
        "fix must add `|| [[ -n \"$token\" ]]` at all 3 locations."
    )
    assert guarded == 3, (
        f"Expected 3 guarded while-read sites, found {guarded}."
    )


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
    monkeypatch.setattr(bcs, "ensure_qmd_collection", lambda: None)

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


def test_composite_stack_exact_symbol_falls_back_to_rg(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Behavioral: composite_stack exact_symbol step must use rg when token-reduce-structural absent.

    Reads the step commands from the JSON output (StepResult.command is persisted),
    so the check is isolated to composite_stack's own steps.
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
    monkeypatch.setattr(bcs, "ensure_qmd_collection", lambda: None)

    bcs.main()

    result = json.loads((tmp_path / "out.json").read_text())
    composite = next((b for b in result["benchmarks"] if b["name"] == "composite_stack"), None)
    assert composite is not None, "composite_stack missing from output"
    assert composite["available"], "composite_stack must be available"

    step_cmds = [s["command"] for s in composite.get("steps", [])]

    # exact_symbol step — must not invoke token-reduce-structural (it's absent)
    exact_cmds = [c for c in step_cmds if "prompt_requires_helper" in c]
    assert exact_cmds, f"exact_symbol step not found in composite_stack steps: {step_cmds}"
    for cmd in exact_cmds:
        assert "token-reduce-structural" not in cmd, (
            f"exact_symbol still calls token-reduce-structural when absent: {cmd!r}"
        )
        assert "rg" in cmd, (
            f"expected rg fallback for exact_symbol, got: {cmd!r}"
        )

    # output_scan step — must not invoke rtk (it's absent)
    scan_cmds = [c for c in step_cmds if "token reduction" in c.lower()]
    assert scan_cmds, f"output_scan step not found in composite_stack steps: {step_cmds}"
    for cmd in scan_cmds:
        assert not cmd.startswith("rtk "), (
            f"output_scan still calls rtk when absent: {cmd!r}"
        )
        assert "rg" in cmd, (
            f"expected rg fallback for output_scan, got: {cmd!r}"
        )
