"""Tests for hook guard scripts: enforce-glob-scope.py and advise-token-reduction.py."""
from __future__ import annotations

import io
import json
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

glob_guard = _load("enforce-glob-scope")
advise_guard = _load("advise-token-reduction")


# ---------------------------------------------------------------------------
# enforce-glob-scope :: is_broad()
# ---------------------------------------------------------------------------

class TestIsBroad:
    def test_unscoped_double_star_prefix(self):
        assert glob_guard.is_broad("**/*.ts") is True

    def test_unscoped_double_star_any(self):
        assert glob_guard.is_broad("**/*") is True

    def test_trailing_double_star_slash(self):
        assert glob_guard.is_broad("src/**") is True

    def test_trailing_double_star_glob(self):
        assert glob_guard.is_broad("src/**/*") is True

    def test_double_wildcard_no_slash(self):
        assert glob_guard.is_broad("*.*.py") is True

    def test_all_wildcard_prefix_segments(self):
        assert glob_guard.is_broad("**/**/*") is True

    def test_scoped_pattern_is_not_broad(self):
        assert glob_guard.is_broad("src/**/*.ts") is False

    def test_single_wildcard_extension_is_not_broad(self):
        assert glob_guard.is_broad("scripts/*.py") is False

    def test_empty_string_is_not_broad(self):
        assert glob_guard.is_broad("") is False

    def test_dotslash_prefix_stripped(self):
        assert glob_guard.is_broad("./**/*.json") is True

    def test_deep_scoped_path_is_not_broad(self):
        assert glob_guard.is_broad("packages/web/src/**/*.tsx") is False


# ---------------------------------------------------------------------------
# enforce-glob-scope :: main() via stdin injection
# ---------------------------------------------------------------------------

class TestGlobGuardMain:
    def _run(self, payload: dict, monkeypatch) -> tuple[int, str]:
        stdin_text = json.dumps(payload)
        monkeypatch.setattr(sys, "stdin", io.StringIO(stdin_text))
        buf = io.StringIO()
        monkeypatch.setattr(sys, "stdout", buf)
        rc = glob_guard.main()
        return rc, buf.getvalue()

    def test_non_glob_tool_passes(self, monkeypatch):
        rc, out = self._run({"tool_name": "Bash", "tool_input": {"command": "ls"}}, monkeypatch)
        assert rc == 0
        assert out == ""

    def test_broad_glob_pattern_blocked(self, monkeypatch):
        rc, out = self._run(
            {"tool_name": "Glob", "tool_input": {"pattern": "**/*.ts"}}, monkeypatch
        )
        assert rc == 2
        data = json.loads(out.strip())
        assert data["decision"] == "block"

    def test_scoped_glob_pattern_passes(self, monkeypatch):
        rc, out = self._run(
            {"tool_name": "Glob", "tool_input": {"pattern": "src/**/*.ts"}}, monkeypatch
        )
        assert rc == 0
        assert out == ""

    def test_invalid_json_returns_zero(self, monkeypatch):
        monkeypatch.setattr(sys, "stdin", io.StringIO("not-json"))
        rc = glob_guard.main()
        assert rc == 0


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
