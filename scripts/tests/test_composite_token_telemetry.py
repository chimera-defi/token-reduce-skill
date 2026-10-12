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





    def test_invalid_json_returns_none(self) -> None:
        assert maybe_json('not json') is None





# ── _clamp ───────────────────────────────────────────────────────────────────

class TestClamp:

    def test_value_below_lower_returns_lower(self) -> None:
        assert _clamp(-1.0, 0.0, 1.0) == pytest.approx(0.0)

    def test_value_above_upper_returns_upper(self) -> None:
        assert _clamp(2.0, 0.0, 1.0) == pytest.approx(1.0)







# ── _extract_commands ─────────────────────────────────────────────────────────

class TestExtractCommands:


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




    def test_hook_with_non_string_command_is_skipped(self) -> None:
        entries = [{"hooks": [{"command": 123}]}]
        assert _extract_commands(entries) == []

