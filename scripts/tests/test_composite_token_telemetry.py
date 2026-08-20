"""Unit tests for pure-function helpers in composite_token_telemetry.py."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Allow import without installing as a package
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from composite_token_telemetry import _clamp, _extract_commands, maybe_json  # noqa: E402


# ── maybe_json ───────────────────────────────────────────────────────────────

class TestMaybeJson:
    def test_valid_object(self) -> None:
        assert maybe_json('{"a": 1}') == {"a": 1}

    def test_valid_array(self) -> None:
        assert maybe_json('[1, 2, 3]') == [1, 2, 3]

    def test_valid_string(self) -> None:
        assert maybe_json('"hello"') == "hello"

    def test_valid_number(self) -> None:
        assert maybe_json('42') == 42

    def test_valid_null(self) -> None:
        assert maybe_json('null') is None

    def test_invalid_json_returns_none(self) -> None:
        assert maybe_json('not json') is None

    def test_empty_string_returns_none(self) -> None:
        assert maybe_json('') is None

    def test_partial_json_returns_none(self) -> None:
        assert maybe_json('{"a":') is None

    def test_nested_object(self) -> None:
        result = maybe_json('{"x": {"y": [1, 2]}}')
        assert result == {"x": {"y": [1, 2]}}


# ── _clamp ───────────────────────────────────────────────────────────────────

class TestClamp:
    def test_value_within_range_unchanged(self) -> None:
        assert _clamp(0.5, 0.0, 1.0) == pytest.approx(0.5)

    def test_value_below_lower_returns_lower(self) -> None:
        assert _clamp(-1.0, 0.0, 1.0) == pytest.approx(0.0)

    def test_value_above_upper_returns_upper(self) -> None:
        assert _clamp(2.0, 0.0, 1.0) == pytest.approx(1.0)

    def test_value_equal_to_lower_boundary(self) -> None:
        assert _clamp(0.0, 0.0, 1.0) == pytest.approx(0.0)

    def test_value_equal_to_upper_boundary(self) -> None:
        assert _clamp(1.0, 0.0, 1.0) == pytest.approx(1.0)

    def test_large_range(self) -> None:
        assert _clamp(50.0, 0.0, 100.0) == pytest.approx(50.0)

    def test_negative_range(self) -> None:
        assert _clamp(-5.0, -10.0, -1.0) == pytest.approx(-5.0)

    def test_clamp_to_negative_lower(self) -> None:
        assert _clamp(-20.0, -10.0, -1.0) == pytest.approx(-10.0)


# ── _extract_commands ─────────────────────────────────────────────────────────

class TestExtractCommands:
    def test_empty_list_returns_empty(self) -> None:
        assert _extract_commands([]) == []

    def test_single_entry_with_one_hook(self) -> None:
        entries = [{"hooks": [{"command": "remind-token-reduce.py"}]}]
        assert _extract_commands(entries) == ["remind-token-reduce.py"]

    def test_multiple_hooks_in_one_entry(self) -> None:
        entries = [
            {
                "hooks": [
                    {"command": "cmd-a"},
                    {"command": "cmd-b"},
                ]
            }
        ]
        assert _extract_commands(entries) == ["cmd-a", "cmd-b"]

    def test_multiple_entries(self) -> None:
        entries = [
            {"hooks": [{"command": "alpha"}]},
            {"hooks": [{"command": "beta"}]},
        ]
        assert _extract_commands(entries) == ["alpha", "beta"]

    def test_entry_with_no_hooks_key(self) -> None:
        entries = [{"matcher": "Bash"}]
        assert _extract_commands(entries) == []

    def test_hook_without_command_key_is_skipped(self) -> None:
        entries = [{"hooks": [{"other": "value"}]}]
        assert _extract_commands(entries) == []

    def test_hook_with_non_string_command_is_skipped(self) -> None:
        entries = [{"hooks": [{"command": 123}]}]
        assert _extract_commands(entries) == []

    def test_mixed_valid_and_invalid_hooks(self) -> None:
        entries = [
            {
                "hooks": [
                    {"command": "good-cmd"},
                    {"other": "no-cmd"},
                    {"command": "another-good"},
                ]
            }
        ]
        assert _extract_commands(entries) == ["good-cmd", "another-good"]
