"""PR#69-pattern coverage: subprocess.run call sites must not hang or crash
the caller on TimeoutExpired / FileNotFoundError. Mirrors commit 8dfe987's
guard on token-reduce-update-check.py / token-reduce-dependency-health.py,
applied to the two remaining unguarded call sites found while hardening the
hook wedge (token_reduce_state.repo_root and token_reduce_adaptive.run_command).
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from unittest import mock

SCRIPT_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import token_reduce_state
import token_reduce_adaptive


class TestRepoRootGuards:
    def test_timeout_falls_back_to_base_dir(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setenv("TOKEN_REDUCE_REPO_ROOT", str(tmp_path))
        with mock.patch.object(
            token_reduce_state.subprocess,
            "run",
            side_effect=subprocess.TimeoutExpired(cmd="git", timeout=10),
        ):
            result = token_reduce_state.repo_root()
        assert result == tmp_path.resolve()

    def test_missing_git_binary_falls_back_to_base_dir(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setenv("TOKEN_REDUCE_REPO_ROOT", str(tmp_path))
        with mock.patch.object(
            token_reduce_state.subprocess,
            "run",
            side_effect=FileNotFoundError("git not found"),
        ):
            result = token_reduce_state.repo_root()
        assert result == tmp_path.resolve()

    def test_normal_git_repo_still_resolves_toplevel(self, tmp_path: Path, monkeypatch) -> None:
        subprocess.run(["git", "init", "-q", str(tmp_path)], check=True, capture_output=True)
        nested = tmp_path / "a" / "b"
        nested.mkdir(parents=True)
        monkeypatch.setenv("TOKEN_REDUCE_REPO_ROOT", str(nested))
        result = token_reduce_state.repo_root()
        assert result == tmp_path.resolve()


class TestRunCommandGuards:
    def test_timeout_returns_failure_tuple_instead_of_raising(self, tmp_path: Path) -> None:
        with mock.patch.object(
            token_reduce_adaptive.subprocess,
            "run",
            side_effect=subprocess.TimeoutExpired(cmd="rg", timeout=20),
        ):
            exit_code, stdout, stderr, duration_ms = token_reduce_adaptive.run_command(
                ["rg", "--files"], cwd=tmp_path
            )
        assert exit_code == 1
        assert stdout == ""
        assert "timed out" in stderr
        assert duration_ms >= 0

    def test_missing_binary_returns_failure_tuple_instead_of_raising(self, tmp_path: Path) -> None:
        with mock.patch.object(
            token_reduce_adaptive.subprocess,
            "run",
            side_effect=FileNotFoundError("not found"),
        ):
            exit_code, stdout, stderr, duration_ms = token_reduce_adaptive.run_command(
                ["definitely-not-a-real-binary"], cwd=tmp_path
            )
        assert exit_code == 1
        assert stdout == ""
        assert "not found" in stderr

    def test_normal_command_still_returns_output(self, tmp_path: Path) -> None:
        exit_code, stdout, stderr, duration_ms = token_reduce_adaptive.run_command(
            ["echo", "hello"], cwd=tmp_path
        )
        assert exit_code == 0
        assert stdout.strip() == "hello"
