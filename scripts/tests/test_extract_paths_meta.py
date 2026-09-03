#!/usr/bin/env python3
"""Tests for extract_paths_meta.py — previously zero coverage."""
from __future__ import annotations

import sys
from pathlib import Path

scripts_dir = Path(__file__).parent.parent
sys.path.insert(0, str(scripts_dir))

from extract_paths_meta import extract_paths


class TestExtractPaths:
    def test_empty_input_returns_zero_count_and_empty_paths(self):
        count, paths = extract_paths("")
        assert count == 0
        assert paths == []

    def test_plain_paths_are_returned_as_is(self):
        raw = "/home/user/foo.py\n/home/user/bar.py\n"
        count, paths = extract_paths(raw)
        assert count == 2
        assert "/home/user/foo.py" in paths
        assert "/home/user/bar.py" in paths

    def test_qmd_url_extracts_path_segment(self):
        # split("/", 3)[3] includes the segment after index: "segment/path/to/file.py"
        raw = "qmd://index/segment/path/to/file.py\n"
        count, paths = extract_paths(raw)
        assert count == 1
        assert paths[0] == "segment/path/to/file.py"

    def test_qmd_url_with_three_slash_parts_returns_last_segment(self):
        # "qmd://index/short".split("/", 3) → 4 parts: ['qmd:', '', 'index', 'short']
        # len >= 4 passes, so "short" is returned
        raw = "qmd://index/short\n"
        count, paths = extract_paths(raw)
        assert count == 1
        assert paths[0] == "short"

    def test_rg_style_file_colon_line_extracts_file(self):
        # rg -n output: "file:linenum:content" — but line doesn't start with /
        raw = "src/foo.ts:42:const x = 1\n"
        count, paths = extract_paths(raw)
        assert count == 1
        assert paths[0] == "src/foo.ts"

    def test_absolute_path_with_colon_is_returned_as_is(self):
        # starts with / → treated as plain path, not rg style
        raw = "/abs/path/file.py\n"
        count, paths = extract_paths(raw)
        assert count == 1
        assert paths[0] == "/abs/path/file.py"

    def test_blank_lines_are_ignored(self):
        raw = "\n  \nfoo.py\n\nbar.py\n"
        count, paths = extract_paths(raw)
        assert count == 2

    def test_top_5_paths_are_returned(self):
        raw = "\n".join(f"file{i}.py" for i in range(10))
        count, paths = extract_paths(raw)
        assert count == 10
        assert len(paths) == 5

    def test_fewer_than_5_paths_returns_all(self):
        raw = "a.py\nb.py\nc.py"
        count, paths = extract_paths(raw)
        assert count == 3
        assert len(paths) == 3

    def test_mixed_input_types(self):
        raw = (
            "qmd://idx/seg/alpha/beta.py\n"
            "/abs/plain.py\n"
            "rel/rg-style.ts:10:content\n"
        )
        count, paths = extract_paths(raw)
        assert count == 3
        # qmd splits on "/" maxsplit=3, so parts[3]="seg/alpha/beta.py"
        assert "seg/alpha/beta.py" in paths
        assert "/abs/plain.py" in paths
        assert "rel/rg-style.ts" in paths
