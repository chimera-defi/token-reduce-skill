"""Tests for normalize_session_key() and session_key() in token_reduce_state.py.

These pure-mapping functions have no prior test coverage.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))


def _load_state_module():
    path = SCRIPTS_DIR / "token_reduce_state.py"
    spec = importlib.util.spec_from_file_location("token_reduce_state", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


state = _load_state_module()


class TestNormalizeSessionKey:
    def test_none_returns_default(self):
        assert state.normalize_session_key(None) == "default"

    def test_empty_string_returns_default(self):
        assert state.normalize_session_key("") == "default"

    def test_whitespace_only_returns_default(self):
        # all chars are illegal → stripped to empty → "default"
        assert state.normalize_session_key("   ") == "default"

    def test_valid_alphanum_returned_unchanged(self):
        assert state.normalize_session_key("abc123") == "abc123"

    def test_valid_with_allowed_punctuation(self):
        assert state.normalize_session_key("my-session.id_1") == "my-session.id_1"

    def test_special_chars_replaced_with_dash(self):
        key = state.normalize_session_key("session/with spaces!@#")
        assert "/" not in key
        assert " " not in key
        assert "!" not in key

    def test_consecutive_special_chars_collapsed_to_single_dash(self):
        key = state.normalize_session_key("abc!!!def")
        assert "!!!" not in key
        assert "abc-def" == key

    def test_leading_trailing_dashes_stripped(self):
        key = state.normalize_session_key("!hello!")
        assert not key.startswith("-")
        assert not key.endswith("-")

    def test_uuid_style_string_keeps_hyphens(self):
        raw = "01YSLzVd8AKA6uT9dq6uRJ7z"
        assert state.normalize_session_key(raw) == raw


class TestSessionKey:
    def test_session_id_field_used(self):
        assert state.session_key({"session_id": "abc"}) == state.normalize_session_key("abc")

    def test_sessionId_camel_field_used(self):
        assert state.session_key({"sessionId": "camel"}) == state.normalize_session_key("camel")

    def test_conversation_id_field_used(self):
        assert state.session_key({"conversation_id": "conv"}) == state.normalize_session_key("conv")

    def test_uuid_field_used_as_fallback(self):
        assert state.session_key({"uuid": "uuid-val"}) == state.normalize_session_key("uuid-val")

    def test_empty_dict_returns_default(self):
        assert state.session_key({}) == "default"

    def test_empty_string_value_skipped_falls_through(self):
        assert state.session_key({"session_id": ""}) == "default"

    def test_priority_session_id_over_uuid(self):
        result = state.session_key({"session_id": "primary", "uuid": "secondary"})
        assert result == state.normalize_session_key("primary")

    def test_non_string_value_skipped(self):
        assert state.session_key({"session_id": 42}) == "default"
