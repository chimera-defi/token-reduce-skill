"""PR#69-pattern coverage: subprocess.run call sites must not hang or crash
the caller on TimeoutExpired / FileNotFoundError. Mirrors commit 8dfe987's
guard on token-reduce-update-check.py / token-reduce-dependency-health.py,
applied to the two remaining unguarded call sites found while hardening the
hook wedge (token_reduce_state.repo_root and token_reduce_adaptive.run_command).

Also covers:
- token-reduce-structural.telemetry_root: called inside the except branch of
  main(); an unguarded FileNotFoundError there would chain on top of the real
  exception, masking it.
- token_reduce_layers.run_command: unguarded subprocess.run(argv) previously
  let FileNotFoundError surface as exit code 2 (argparse error) instead of
  the conventional 127 for "command not found".
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


class TestAdaptiveRepoRootGuards:
    """token_reduce_adaptive.repo_root() is a drifted duplicate of
    token_reduce_state.repo_root() -- same purpose, but never got the
    timeout+FileNotFoundError guard applied. Found via a repo-wide survey
    for other unguarded subprocess.run call sites reachable from the
    discovery-helper chain (token-reduce-adaptive.sh -> repo_root())."""

    def test_timeout_falls_back_to_base_dir(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setenv("TOKEN_REDUCE_REPO_ROOT", str(tmp_path))
        with mock.patch.object(
            token_reduce_adaptive.subprocess,
            "run",
            side_effect=subprocess.TimeoutExpired(cmd="git", timeout=10),
        ):
            result = token_reduce_adaptive.repo_root()
        assert result == tmp_path.resolve()

    def test_missing_git_binary_falls_back_to_base_dir(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setenv("TOKEN_REDUCE_REPO_ROOT", str(tmp_path))
        with mock.patch.object(
            token_reduce_adaptive.subprocess,
            "run",
            side_effect=FileNotFoundError("git not found"),
        ):
            result = token_reduce_adaptive.repo_root()
        assert result == tmp_path.resolve()

    def test_normal_git_repo_still_resolves_toplevel(self, tmp_path: Path, monkeypatch) -> None:
        subprocess.run(["git", "init", "-q", str(tmp_path)], check=True, capture_output=True)
        nested = tmp_path / "a" / "b"
        nested.mkdir(parents=True)
        monkeypatch.setenv("TOKEN_REDUCE_REPO_ROOT", str(nested))
        result = token_reduce_adaptive.repo_root()
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


import importlib.util as _ilu


def _load_structural():
    spec = _ilu.spec_from_file_location(
        "token_reduce_structural",
        Path(__file__).resolve().parents[1] / "token-reduce-structural.py",
    )
    mod = _ilu.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


class TestTelemetryRootGuards:
    """token-reduce-structural.telemetry_root() mirrors repo_root() semantics
    but lacked the FileNotFoundError / TimeoutExpired guard. The function is
    called inside main()'s except branch; an unhandled exception there chains
    on top of the real exception and masks it."""

    def test_timeout_falls_back_to_project_root(self, tmp_path: Path) -> None:
        mod = _load_structural()
        with mock.patch.object(
            mod.subprocess,
            "run",
            side_effect=subprocess.TimeoutExpired(cmd="git", timeout=10),
        ):
            result = mod.telemetry_root(str(tmp_path))
        assert result == tmp_path.resolve()

    def test_missing_git_falls_back_to_project_root(self, tmp_path: Path) -> None:
        mod = _load_structural()
        with mock.patch.object(
            mod.subprocess,
            "run",
            side_effect=FileNotFoundError("git not found"),
        ):
            result = mod.telemetry_root(str(tmp_path))
        assert result == tmp_path.resolve()

    def test_git_toplevel_is_used_when_available(self, tmp_path: Path) -> None:
        mod = _load_structural()
        fake_root = tmp_path / "repo"
        fake_root.mkdir()
        completed = mock.MagicMock()
        completed.stdout = str(fake_root) + "\n"
        completed.returncode = 0
        with mock.patch.object(mod.subprocess, "run", return_value=completed):
            result = mod.telemetry_root(str(tmp_path / "repo" / "sub"))
        assert result == fake_root.resolve()


import token_reduce_layers as _layers


class TestLayersRunCommandNotFound:
    """token_reduce_layers.run_command() previously propagated FileNotFoundError
    as OSError up to main(), which mapped it to exit code 2 (argparse error)
    instead of the conventional 127 for command-not-found."""

    def test_missing_command_returns_127(self, tmp_path: Path) -> None:
        with mock.patch.object(
            _layers.subprocess,
            "run",
            side_effect=FileNotFoundError("no such file"),
        ):
            result = _layers.run_command(["nonexistent-binary-xyz"])
        assert result == 127

    def test_normal_command_returns_exit_code(self, tmp_path: Path) -> None:
        result = _layers.run_command(["true"])
        assert result == 0
