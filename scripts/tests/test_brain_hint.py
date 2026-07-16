#!/usr/bin/env python3
"""Tests for brain_hint.py — previously zero coverage."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

scripts_dir = Path(__file__).parent.parent
sys.path.insert(0, str(scripts_dir))

from brain_hint import hint_line, main


class TestHintLineToolAvailability:
    def test_returns_none_when_neither_tool_available(self):
        with patch("brain_hint.shutil.which", return_value=None):
            assert hint_line("some query") is None

    def test_returns_qmd_command_when_only_qmd_available(self):
        def which_qmd_only(name):
            return "/usr/bin/qmd" if name == "qmd" else None
        with patch("brain_hint.shutil.which", side_effect=which_qmd_only):
            result = hint_line("find auth module")
        assert result is not None
        assert "qmd" in result
        assert "gbrain" not in result

    def test_returns_gbrain_command_when_only_gbrain_available(self):
        def which_gbrain_only(name):
            return "/usr/bin/gbrain" if name == "gbrain" else None
        with patch("brain_hint.shutil.which", side_effect=which_gbrain_only):
            result = hint_line("find auth module")
        assert result is not None
        assert "gbrain" in result
        assert "qmd" not in result

    def test_returns_both_when_both_available(self):
        def which_both(name):
            return f"/usr/bin/{name}"
        with patch("brain_hint.shutil.which", side_effect=which_both):
            result = hint_line("find auth module")
        assert result is not None
        assert "qmd" in result
        assert "gbrain" in result


class TestHintLineQueryHandling:
    def _qmd_only(self, name):
        return "/usr/bin/qmd" if name == "qmd" else None

    def test_query_embedded_in_output(self):
        with patch("brain_hint.shutil.which", side_effect=self._qmd_only):
            result = hint_line("token reduce routing")
        assert "token reduce routing" in result

    def test_empty_query_uses_placeholder(self):
        with patch("brain_hint.shutil.which", side_effect=self._qmd_only):
            result = hint_line("")
        assert "<query>" in result

    def test_query_with_double_quotes_escaped(self):
        with patch("brain_hint.shutil.which", side_effect=self._qmd_only):
            result = hint_line('find "exact phrase"')
        assert '\\"' in result

    def test_whitespace_only_query_uses_placeholder(self):
        with patch("brain_hint.shutil.which", side_effect=self._qmd_only):
            result = hint_line("   ")
        assert "<query>" in result


class TestMain:
    def test_main_prints_nothing_when_no_tools(self, capsys):
        with patch("brain_hint.shutil.which", return_value=None):
            rc = main(["some", "query"])
        assert rc == 0
        assert capsys.readouterr().out == ""

    def test_main_prints_hint_when_qmd_available(self, capsys):
        def which_qmd(name):
            return "/usr/bin/qmd" if name == "qmd" else None
        with patch("brain_hint.shutil.which", side_effect=which_qmd):
            rc = main(["my", "topic"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "qmd" in out
        assert "my topic" in out
