"""Tests for hook guard scripts: enforce-token-reduce-first.py's Glob-blocking
logic and advise-token-reduction.py.

enforce-glob-scope.py (originally covered here) was removed as dead code:
zero references anywhere in the repo, and its is_broad() logic is strictly
subsumed by enforce-token-reduce-first.py's is_broad_glob()/is_exploratory_glob(),
which is the hook actually wired to the Glob matcher in .claude/settings.json.
That live policy is intentionally stricter than the old script's -- it blocks
*any* pattern containing a wildcard character, including scoped ones like
src/**/*.ts that the old script explicitly allowed -- so these tests assert
the live behavior rather than the retired, more permissive one.
"""
from __future__ import annotations

import io
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

# Dynamic import to handle hyphenated filenames
import importlib.util

def _load(name: str):
    spec = importlib.util.spec_from_file_location(
        name.replace("-", "_"),
        SCRIPT_DIR / f"{name}.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

enforce_guard = _load("enforce-token-reduce-first")
advise_guard = _load("advise-token-reduction")


# ---------------------------------------------------------------------------
# enforce-token-reduce-first :: is_broad_glob() / is_exploratory_glob()
# ---------------------------------------------------------------------------
# The live Glob matcher blocks on `is_broad_glob(pattern) or is_exploratory_glob(pattern)`.
# is_exploratory_glob() is a broad catch-all (any of "*?[" present), so it fires
# on nearly every wildcard pattern -- these cases document that combined policy.

class TestIsBroadGlob:
    def test_unscoped_double_star_prefix(self):
        assert enforce_guard.is_broad_glob("**/*.ts") is True

    def test_unscoped_double_star_any(self):
        assert enforce_guard.is_broad_glob("**/*") is True

    def test_trailing_double_star_slash(self):
        assert enforce_guard.is_broad_glob("src/**") is True

    def test_trailing_double_star_glob(self):
        assert enforce_guard.is_broad_glob("src/**/*") is True

    def test_double_wildcard_no_slash(self):
        assert enforce_guard.is_broad_glob("*.*.py") is True

    def test_all_wildcard_prefix_segments(self):
        assert enforce_guard.is_broad_glob("**/**/*") is True

    def test_scoped_double_star_pattern_is_still_broad(self):
        # Unlike the retired enforce-glob-scope.py (which allowed this),
        # is_broad_glob counts *any* pattern with 2+ wildcards as broad,
        # directory scoping notwithstanding.
        assert enforce_guard.is_broad_glob("src/**/*.ts") is True

    def test_single_wildcard_extension_is_not_broad_alone(self):
        # is_broad_glob alone allows a single trailing wildcard extension --
        # but is_exploratory_glob still catches it (see below).
        assert enforce_guard.is_broad_glob("scripts/*.py") is False
        assert enforce_guard.is_exploratory_glob("scripts/*.py") is True

    def test_empty_string_is_not_broad(self):
        assert enforce_guard.is_broad_glob("") is False

    def test_dotslash_prefix_stripped(self):
        assert enforce_guard.is_broad_glob("./**/*.json") is True

    def test_deep_scoped_path_is_still_broad(self):
        assert enforce_guard.is_broad_glob("packages/web/src/**/*.tsx") is True

    def test_literal_path_with_no_wildcard_is_not_exploratory(self):
        assert enforce_guard.is_broad_glob("scripts/enforce-token-reduce-first.py") is False
        assert enforce_guard.is_exploratory_glob("scripts/enforce-token-reduce-first.py") is False

    def test_empty_string_is_not_exploratory(self):
        assert enforce_guard.is_exploratory_glob("") is False


# ---------------------------------------------------------------------------
# enforce-token-reduce-first :: main() via subprocess, Glob tool calls
# ---------------------------------------------------------------------------
# main() does real filesystem I/O (repo state, telemetry), so this exercises
# it as a subprocess against an isolated tmp git repo -- same pattern as
# test_enforce_integration.py's _run_hook.

HOOK = SCRIPT_DIR / "enforce-token-reduce-first.py"


def _init_git_repo(path: Path) -> None:
    subprocess.run(
        ["git", "-c", "init.defaultBranch=main", "init", "-q", str(path)],
        check=True,
        capture_output=True,
    )


def _run_glob_hook(pattern: str, repo_root: Path, session_id: str = "sess-glob-test") -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["TOKEN_REDUCE_REPO_ROOT"] = str(repo_root)
    env["PYTHONPATH"] = str(SCRIPT_DIR) + os.pathsep + env.get("PYTHONPATH", "")
    payload = json.dumps({"session_id": session_id, "tool_name": "Glob", "tool_input": {"pattern": pattern}})
    return subprocess.run(
        [sys.executable, str(HOOK)],
        input=payload,
        text=True,
        capture_output=True,
        env=env,
        cwd=str(repo_root),
        timeout=30,
    )


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    _init_git_repo(tmp_path)
    return tmp_path


class TestGlobToolBlocking:
    def test_non_glob_tool_passes(self, repo: Path) -> None:
        env = os.environ.copy()
        env["TOKEN_REDUCE_REPO_ROOT"] = str(repo)
        env["PYTHONPATH"] = str(SCRIPT_DIR) + os.pathsep + env.get("PYTHONPATH", "")
        payload = json.dumps({"session_id": "s1", "tool_name": "Bash", "tool_input": {"command": "echo hi"}})
        result = subprocess.run(
            [sys.executable, str(HOOK)],
            input=payload,
            text=True,
            capture_output=True,
            env=env,
            cwd=str(repo),
            timeout=30,
        )
        assert result.returncode == 0
        assert result.stdout.strip() == ""

    def test_broad_glob_pattern_blocked(self, repo: Path) -> None:
        result = _run_glob_hook("**/*.ts", repo)
        assert result.returncode == 2
        decision = json.loads(result.stdout)
        assert decision["decision"] == "block"

    def test_scoped_glob_pattern_is_also_blocked(self, repo: Path) -> None:
        # Documents the live (stricter-than-legacy) policy: even a directory-
        # scoped pattern is blocked until the token-reduce helper has run.
        result = _run_glob_hook("src/**/*.ts", repo)
        assert result.returncode == 2
        decision = json.loads(result.stdout)
        assert decision["decision"] == "block"

    def test_invalid_json_returns_zero(self, repo: Path) -> None:
        env = os.environ.copy()
        env["TOKEN_REDUCE_REPO_ROOT"] = str(repo)
        env["PYTHONPATH"] = str(SCRIPT_DIR) + os.pathsep + env.get("PYTHONPATH", "")
        result = subprocess.run(
            [sys.executable, str(HOOK)],
            input="not-json",
            text=True,
            capture_output=True,
            env=env,
            cwd=str(repo),
            timeout=30,
        )
        assert result.returncode == 0


# ---------------------------------------------------------------------------
# advise-token-reduction :: BROAD_PATTERNS matching
# ---------------------------------------------------------------------------

class TestBroadPatterns:
    def _matches(self, command: str) -> bool:
        import re
        return any(re.search(p, command) for p in advise_guard.BROAD_PATTERNS)

    def test_find_dot_is_broad(self):
        assert self._matches("find . -name '*.py'") is True

    def test_find_slash_is_broad(self):
        assert self._matches("find /home -type f") is True

    def test_ls_recursive_is_broad(self):
        assert self._matches("ls -R") is True

    def test_grep_recursive_long_is_broad(self):
        assert self._matches("grep --recursive pattern .") is True

    def test_grep_capital_R_short_is_broad(self):
        assert self._matches("grep -R foo .") is True

    def test_rg_files_dot_is_broad(self):
        assert self._matches("rg --files .") is True

    def test_rg_files_end_of_string_is_broad(self):
        assert self._matches("rg --files") is True

    def test_tree_dot_is_broad(self):
        assert self._matches("tree .") is True

    def test_tree_bare_is_broad(self):
        assert self._matches("tree") is True

    def test_scoped_rg_not_broad(self):
        assert self._matches("rg -g '*.ts' keyword") is False

    def test_scoped_grep_not_broad(self):
        assert self._matches("grep -n pattern src/foo.py") is False

    def test_du_minus_a_is_broad(self):
        assert self._matches("du -a /home") is True


# ---------------------------------------------------------------------------
# advise-token-reduction :: main() via stdin injection
# ---------------------------------------------------------------------------

class TestAdviseGuardMain:
    def _run(self, payload: dict, monkeypatch) -> tuple[int, str]:
        monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
        buf = io.StringIO()
        monkeypatch.setattr(sys, "stdout", buf)
        rc = advise_guard.main()
        return rc, buf.getvalue()

    def test_non_bash_tool_passes(self, monkeypatch):
        rc, out = self._run({"tool_name": "Glob", "tool_input": {"pattern": "**/*"}}, monkeypatch)
        assert rc == 0
        assert out == ""

    def test_broad_bash_command_blocked(self, monkeypatch):
        rc, out = self._run(
            {"tool_name": "Bash", "tool_input": {"command": "find . -name '*.py'"}}, monkeypatch
        )
        assert rc == 2
        data = json.loads(out.strip())
        assert data["decision"] == "block"
        assert "token-reduce-paths" in data["reason"]

    def test_safe_bash_command_passes(self, monkeypatch):
        rc, out = self._run(
            {"tool_name": "Bash", "tool_input": {"command": "rg -g '*.ts' keyword src/"}},
            monkeypatch,
        )
        assert rc == 0

    def test_invalid_json_returns_zero(self, monkeypatch):
        monkeypatch.setattr(sys, "stdin", io.StringIO("{bad json"))
        rc = advise_guard.main()
        assert rc == 0

    def test_empty_command_passes(self, monkeypatch):
        rc, out = self._run(
            {"tool_name": "Bash", "tool_input": {"command": ""}}, monkeypatch
        )
        assert rc == 0
