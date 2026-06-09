"""Tests for previously zero-coverage modules: token_reduce_config and extract_paths_meta."""
from __future__ import annotations

import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from token_reduce_config import deep_merge, parse_value
from extract_paths_meta import extract_paths


# ---------------------------------------------------------------------------
# deep_merge
# ---------------------------------------------------------------------------

class TestDeepMerge:
    def test_incoming_overrides_base_scalar(self):
        result = deep_merge({"a": 1}, {"a": 2})
        assert result["a"] == 2

    def test_base_key_preserved_when_not_in_incoming(self):
        result = deep_merge({"a": 1, "b": 2}, {"a": 99})
        assert result["b"] == 2

    def test_nested_dicts_merged_recursively(self):
        base = {"db": {"host": "localhost", "port": 5432}}
        incoming = {"db": {"port": 5433}}
        result = deep_merge(base, incoming)
        assert result["db"]["host"] == "localhost"
        assert result["db"]["port"] == 5433

    def test_scalar_replaces_dict_in_incoming(self):
        base = {"cfg": {"key": "val"}}
        incoming = {"cfg": "flat"}
        result = deep_merge(base, incoming)
        assert result["cfg"] == "flat"

    def test_empty_incoming_returns_copy_of_base(self):
        base = {"x": 1}
        result = deep_merge(base, {})
        assert result == base
        assert result is not base  # must be a copy

    def test_empty_base_returns_incoming(self):
        result = deep_merge({}, {"y": 2})
        assert result == {"y": 2}

    def test_deeply_nested_merge(self):
        base = {"a": {"b": {"c": 1, "d": 2}}}
        incoming = {"a": {"b": {"c": 99}}}
        result = deep_merge(base, incoming)
        assert result["a"]["b"]["c"] == 99
        assert result["a"]["b"]["d"] == 2


# ---------------------------------------------------------------------------
# parse_value
# ---------------------------------------------------------------------------

class TestParseValue:
    def test_true_string(self):
        assert parse_value("true") is True
        assert parse_value("True") is True
        assert parse_value("TRUE") is True

    def test_false_string(self):
        assert parse_value("false") is False
        assert parse_value("False") is False

    def test_null_string(self):
        assert parse_value("null") is None
        assert parse_value("none") is None
        assert parse_value("None") is None

    def test_integer(self):
        assert parse_value("42") == 42
        assert isinstance(parse_value("42"), int)

    def test_negative_integer(self):
        assert parse_value("-5") == -5

    def test_float(self):
        result = parse_value("3.14")
        assert abs(result - 3.14) < 1e-9
        assert isinstance(result, float)

    def test_plain_string_passthrough(self):
        assert parse_value("hello") == "hello"
        assert parse_value("some/path") == "some/path"

    def test_whitespace_stripped_before_comparison(self):
        assert parse_value("  true  ") is True
        assert parse_value("  42  ") == 42


# ---------------------------------------------------------------------------
# extract_paths
# ---------------------------------------------------------------------------

class TestExtractPaths:
    def test_plain_file_paths(self):
        raw = "src/foo.ts\nsrc/bar.ts"
        count, paths = extract_paths(raw)
        assert count == 2
        assert paths == ["src/foo.ts", "src/bar.ts"]

    def test_rg_colon_style_strips_to_filename(self):
        raw = "src/index.ts:42:const x = 1"
        count, paths = extract_paths(raw)
        assert count == 1
        assert paths == ["src/index.ts"]

    def test_qmd_url_extracts_path(self):
        # qmd://repo/index/src/utils.ts → split("/", 3)[3] = "index/src/utils.ts"
        raw = "qmd://repo/index/src/utils.ts"
        count, paths = extract_paths(raw)
        assert count == 1
        assert paths == ["index/src/utils.ts"]

    def test_caps_output_at_five_paths(self):
        lines = "\n".join(f"file{i}.ts" for i in range(10))
        count, paths = extract_paths(lines)
        assert count == 10
        assert len(paths) == 5

    def test_empty_string_returns_zero(self):
        count, paths = extract_paths("")
        assert count == 0
        assert paths == []

    def test_blank_lines_ignored(self):
        raw = "a.ts\n\n\nb.ts\n"
        count, paths = extract_paths(raw)
        assert count == 2

    def test_absolute_path_not_split_on_colon(self):
        # Lines starting with "/" are treated as plain paths
        raw = "/home/user/repo/src/main.ts"
        count, paths = extract_paths(raw)
        assert count == 1
        assert paths == ["/home/user/repo/src/main.ts"]
