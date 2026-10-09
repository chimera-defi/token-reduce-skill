#!/usr/bin/env python3
"""Tests for token_reduce_state.py pure helper functions."""
from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest import mock

SCRIPT_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from token_reduce_state import (  # noqa: E402
    normalize_session_key,
    session_key,
    broad_attempt_count,
    record_broad_attempt,
    clear_broad_attempts,
    discovery_hint,
)

# ---------------------------------------------------------------------------
# normalize_session_key
# ---------------------------------------------------------------------------


def test_normalize_session_key_returns_default_for_none() -> None:
    assert normalize_session_key(None) == "default"




def test_normalize_session_key_replaces_special_chars() -> None:
    result = normalize_session_key("session/abc 123!")
    assert "/" not in result
    assert " " not in result
    assert "!" not in result






# ---------------------------------------------------------------------------
# session_key
# ---------------------------------------------------------------------------


def test_session_key_extracts_session_id() -> None:
    data = {"session_id": "abc-123"}
    assert session_key(data) == "abc-123"


def test_session_key_falls_back_through_field_priority() -> None:
    data = {"conversationId": "conv-456"}
    result = session_key(data)
    assert result == "conv-456"






# ---------------------------------------------------------------------------
# broad_attempt_count / record_broad_attempt / clear_broad_attempts
# ---------------------------------------------------------------------------


def test_broad_attempt_count_returns_zero_when_unset(tmp_path: Path) -> None:
    assert broad_attempt_count(tmp_path, "test-session") == 0


def test_record_broad_attempt_increments_counter(tmp_path: Path) -> None:
    count1 = record_broad_attempt(tmp_path, "test-session")
    count2 = record_broad_attempt(tmp_path, "test-session")
    assert count1 == 1
    assert count2 == 2
    assert broad_attempt_count(tmp_path, "test-session") == 2


def test_clear_broad_attempts_removes_counter(tmp_path: Path) -> None:
    record_broad_attempt(tmp_path, "test-session")
    clear_broad_attempts(tmp_path, "test-session")
    assert broad_attempt_count(tmp_path, "test-session") == 0


def test_clear_broad_attempts_all_removes_all_sessions(tmp_path: Path) -> None:
    record_broad_attempt(tmp_path, "session-a")
    record_broad_attempt(tmp_path, "session-b")
    clear_broad_attempts(tmp_path)
    assert broad_attempt_count(tmp_path, "session-a") == 0
    assert broad_attempt_count(tmp_path, "session-b") == 0


# ---------------------------------------------------------------------------
# discovery_hint
# ---------------------------------------------------------------------------


def test_discovery_hint_returns_string() -> None:
    with mock.patch.dict(os.environ, {"TOKEN_REDUCE_ADAPTIVE_HINT": "0"}):
        hint = discovery_hint()
    assert isinstance(hint, str)
    assert len(hint) > 0


def test_discovery_hint_with_adaptive_disabled_falls_back() -> None:
    with mock.patch.dict(os.environ, {"TOKEN_REDUCE_ADAPTIVE_HINT": "0"}):
        hint = discovery_hint()
    assert "token-reduce" in hint.lower() or "qmd" in hint.lower()
