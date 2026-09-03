#!/usr/bin/env python3
"""Tests for escalation.py — previously zero coverage."""
from __future__ import annotations

import sys
from pathlib import Path

scripts_dir = Path(__file__).parent.parent
sys.path.insert(0, str(scripts_dir))

from escalation import (
    IGNORE_THRESHOLD,
    EscalationDecision,
    count_ignored_recommendations,
    escalate,
)


def _make_event(companion: str, *, recommended: bool, used: bool | None = None) -> dict:
    meta: dict = {f"{companion}_recommended": recommended}
    if used is not None:
        meta[f"{companion}_used"] = used
    return {"meta": meta}


class TestCountIgnoredRecommendations:
    def test_empty_events_returns_zero(self):
        assert count_ignored_recommendations([], companion="headroom") == 0

    def test_recommended_and_used_is_not_ignored(self):
        events = [_make_event("headroom", recommended=True, used=True)]
        assert count_ignored_recommendations(events, companion="headroom") == 0

    def test_recommended_but_not_used_counts_as_ignored(self):
        events = [_make_event("headroom", recommended=True, used=False)]
        assert count_ignored_recommendations(events, companion="headroom") == 1

    def test_recommended_with_missing_used_counts_as_ignored(self):
        events = [_make_event("headroom", recommended=True)]
        assert count_ignored_recommendations(events, companion="headroom") == 1

    def test_not_recommended_is_skipped(self):
        events = [_make_event("headroom", recommended=False, used=False)]
        assert count_ignored_recommendations(events, companion="headroom") == 0

    def test_multiple_ignores_are_summed(self):
        events = [
            _make_event("headroom", recommended=True, used=False),
            _make_event("headroom", recommended=True, used=True),
            _make_event("headroom", recommended=True),
        ]
        assert count_ignored_recommendations(events, companion="headroom") == 2

    def test_only_counts_target_companion(self):
        events = [
            _make_event("headroom", recommended=True, used=False),
            _make_event("caveman", recommended=True, used=False),
        ]
        assert count_ignored_recommendations(events, companion="headroom") == 1
        assert count_ignored_recommendations(events, companion="caveman") == 1

    def test_event_with_no_meta_field_is_skipped(self):
        events = [{"type": "tool_call"}]
        assert count_ignored_recommendations(events, companion="headroom") == 0

    def test_event_with_non_dict_meta_is_skipped(self):
        events = [{"meta": "not-a-dict"}]
        assert count_ignored_recommendations(events, companion="headroom") == 0

    def test_event_with_none_meta_is_skipped(self):
        events = [{"meta": None}]
        assert count_ignored_recommendations(events, companion="headroom") == 0


class TestEscalate:
    def test_below_threshold_returns_baseline(self):
        events = [_make_event("headroom", recommended=True, used=False)] * (IGNORE_THRESHOLD - 1)
        result = escalate(events, companion="headroom")
        assert result.level == "baseline"
        assert result.ignored_count == IGNORE_THRESHOLD - 1
        assert result.auto_compress_suggested is False
        assert result.message == ""

    def test_at_threshold_returns_strong_for_headroom(self):
        events = [_make_event("headroom", recommended=True, used=False)] * IGNORE_THRESHOLD
        result = escalate(events, companion="headroom")
        assert result.level == "strong"
        assert result.ignored_count == IGNORE_THRESHOLD
        assert result.threshold == IGNORE_THRESHOLD
        assert result.auto_compress_suggested is True
        assert "headroom_compress" in result.message
        assert str(IGNORE_THRESHOLD) in result.message

    def test_above_threshold_returns_strong_for_headroom(self):
        events = [_make_event("headroom", recommended=True, used=False)] * (IGNORE_THRESHOLD + 2)
        result = escalate(events, companion="headroom")
        assert result.level == "strong"
        assert result.auto_compress_suggested is True

    def test_at_threshold_returns_strong_for_non_headroom(self):
        events = [_make_event("caveman", recommended=True, used=False)] * IGNORE_THRESHOLD
        result = escalate(events, companion="caveman")
        assert result.level == "strong"
        assert result.auto_compress_suggested is False
        assert "caveman" in result.message
        assert "routing settings" in result.message

    def test_returns_escalation_decision_dataclass(self):
        result = escalate([], companion="headroom")
        assert isinstance(result, EscalationDecision)

    def test_empty_events_returns_baseline(self):
        result = escalate([], companion="headroom")
        assert result.level == "baseline"
        assert result.ignored_count == 0
