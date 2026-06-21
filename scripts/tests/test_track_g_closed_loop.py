"""Track G — Closed-loop tuning.

G1. Behavior-profile escalation: if a session ignores a companion
    recommendation N times, escalate to a stronger nudge.
G2. Mention->use lift: SKILL.md adds concrete trigger cues and
    ready-to-copy examples right at the recommendation point.
"""
from __future__ import annotations

import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = SCRIPT_DIR.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from escalation import (  # noqa: E402
    IGNORE_THRESHOLD,
    EscalationDecision,
    count_ignored_recommendations,
    escalate,
)


# --------------------------------------------------------------------------- #
# G1 — escalation triggers after N ignored recommendations
# --------------------------------------------------------------------------- #


def _rec_event(companion: str, used: bool) -> dict:
    return {
        "event": "helper_invocation",
        "tool": "token_reduce_adaptive",
        "status": "ok",
        "meta": {
            "context": "runtime",
            f"{companion}_recommended": True,
            f"{companion}_used": used,
        },
    }


def test_g1_ignored_count_zero_when_no_recommendations() -> None:
    events: list[dict] = []
    assert count_ignored_recommendations(events, companion="headroom") == 0


def test_g1_ignored_count_tracks_recommendations_without_use() -> None:
    events = [
        _rec_event("headroom", used=False),
        _rec_event("headroom", used=False),
    ]
    assert count_ignored_recommendations(events, companion="headroom") == 2


def test_g1_used_recommendations_do_not_count_as_ignored() -> None:
    events = [
        _rec_event("headroom", used=False),
        _rec_event("headroom", used=True),
        _rec_event("headroom", used=False),
    ]
    assert count_ignored_recommendations(events, companion="headroom") == 2


def test_g1_escalation_below_threshold_returns_baseline() -> None:
    events = [_rec_event("headroom", used=False)]
    decision = escalate(events, companion="headroom")
    assert isinstance(decision, EscalationDecision)
    assert decision.level == "baseline"
    assert decision.ignored_count == 1
    assert decision.threshold == IGNORE_THRESHOLD


def test_g1_escalation_at_threshold_returns_strong_nudge() -> None:
    events = [_rec_event("headroom", used=False) for _ in range(IGNORE_THRESHOLD)]
    decision = escalate(events, companion="headroom")
    assert decision.level == "strong"
    assert decision.ignored_count >= IGNORE_THRESHOLD
    assert decision.auto_compress_suggested is True
    assert "headroom_compress" in decision.message


def test_g1_strong_nudge_mentions_compress_for_headroom() -> None:
    events = [_rec_event("headroom", used=False) for _ in range(IGNORE_THRESHOLD + 1)]
    decision = escalate(events, companion="headroom")
    assert decision.level == "strong"
    assert "headroom_compress" in decision.message.lower() or "compress" in decision.message.lower()


def test_g1_threshold_is_reasonable() -> None:
    # Must be at least 2 — escalating after a single ignore would be hostile.
    assert IGNORE_THRESHOLD >= 2


# --------------------------------------------------------------------------- #
# G2 — SKILL.md gains concrete trigger cues + copy-paste examples
# --------------------------------------------------------------------------- #


def test_g2_skill_md_has_trigger_cues_section() -> None:
    skill = (REPO_ROOT / "SKILL.md").read_text()
    # Concrete cue: a "Trigger cues" or similar heading with copy-paste examples.
    lowered = skill.lower()
    assert "trigger cue" in lowered or "concrete triggers" in lowered


def test_g2_skill_md_headroom_has_copy_pasteable_command() -> None:
    skill = (REPO_ROOT / "SKILL.md").read_text()
    assert "headroom install status" in skill
    assert "headroom_compress" in skill


def test_g2_skill_md_recommendation_examples_mention_compress() -> None:
    skill = (REPO_ROOT / "SKILL.md").read_text()
    # The recommendation point should show the copy-paste action right there,
    # not in a separate "details elsewhere" link.
    lowered = skill.lower()
    assert "20k" in lowered or "large tool" in lowered or "large payload" in lowered
