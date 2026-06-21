"""Track E — subagent + gstack integration.

E1. Router emits subagent_recommended + ready-to-copy Agent snippet when
    helper returns >5 candidates OR query has broad-scope cues.
E2. ``brain_hint_line`` returns a one-line brain-first hint when qmd or
    gbrain CLIs are available.
E3. ``/create-session`` escalation when multi-repo scope cues + skill
    detectable.
E4. Sibling-skill routing maps intent to skill names (/review,
    /investigate, ...).
"""
from __future__ import annotations

import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from token_reduce_adaptive import (  # noqa: E402
    Availability,
    BehaviorProfile,
    RoutingPolicy,
    brain_hint_line,
    decide,
    sibling_skill_for_query,
)


def _availability(**overrides: bool) -> Availability:
    base = {
        "paths": True,
        "snippet": True,
        "structural": False,
        "context_mode": True,
        "headroom": True,
        "code_review_graph": True,
    }
    base.update(overrides)
    return Availability(**base)


def _behavior() -> BehaviorProfile:
    return BehaviorProfile(helper_calls=4, repeated_ratio=0.0, rapid_repeat_ratio=0.0)


def _policy(**overrides: bool) -> RoutingPolicy:
    base = {
        "behavior_days": 3,
        "rapid_repeat_snippet_threshold": 0.35,
        "enable_structural": False,
        "enable_context_mode_recommendations": True,
        "enable_headroom_recommendations": True,
        "enable_code_review_graph_recommendations": True,
    }
    base.update(overrides)
    return RoutingPolicy(**base)  # type: ignore[arg-type]


def _decide(query: str, *, candidate_count: int = 1, gstack_skill_available: bool = False):
    return decide(
        query,
        behavior=_behavior(),
        availability=_availability(),
        policy=_policy(),
        root=Path("."),
        repo_file_count=800,
        candidate_count=candidate_count,
        gstack_skill_available=gstack_skill_available,
    )


# --------------------------------------------------------------------------- #
# E1 — subagent recommendation
# --------------------------------------------------------------------------- #


def test_e1_subagent_recommended_when_candidate_set_large() -> None:
    decision = _decide("look up Component definition", candidate_count=8)
    assert decision.subagent_recommended is True
    assert "Agent(" in decision.subagent_snippet
    assert "Explore" in decision.subagent_snippet


def test_e1_subagent_recommended_when_broad_cue_present() -> None:
    decision = _decide("find this across the workspace", candidate_count=1)
    assert decision.subagent_recommended is True


def test_e1_subagent_not_recommended_when_small_and_narrow() -> None:
    decision = _decide("find Component definition", candidate_count=2)
    assert decision.subagent_recommended is False
    assert decision.subagent_snippet == ""


# --------------------------------------------------------------------------- #
# E2 — brain-first hint
# --------------------------------------------------------------------------- #


def test_e2_brain_hint_when_qmd_present(tmp_path, monkeypatch) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    qmd = bin_dir / "qmd"
    qmd.write_text("#!/bin/sh\nexit 0\n")
    qmd.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{':' if False else ':'}{__import__('os').environ.get('PATH','')}")
    hint = brain_hint_line("how does ranking work")
    assert hint is not None
    assert "brain hits available" in hint
    assert "qmd search" in hint


def test_e2_brain_hint_when_nothing_present(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("PATH", str(tmp_path))
    assert brain_hint_line("how does ranking work") is None


# --------------------------------------------------------------------------- #
# E3 — session-spawn escalation
# --------------------------------------------------------------------------- #


def test_e3_session_spawn_recommended_when_multi_repo_cue_and_skill() -> None:
    decision = _decide(
        "trace this across workspace sibling repos",
        candidate_count=1,
        gstack_skill_available=True,
    )
    assert decision.session_spawn_recommended is True
    assert "/create-session" in " ".join(decision.rationale)


def test_e3_session_spawn_not_recommended_without_skill() -> None:
    decision = _decide(
        "trace this across workspace sibling repos",
        candidate_count=1,
        gstack_skill_available=False,
    )
    assert decision.session_spawn_recommended is False


def test_e3_session_spawn_not_recommended_without_multi_repo_cue() -> None:
    decision = _decide(
        "trace this function",
        candidate_count=1,
        gstack_skill_available=True,
    )
    assert decision.session_spawn_recommended is False


# --------------------------------------------------------------------------- #
# E4 — sibling-skill routing
# --------------------------------------------------------------------------- #


def test_e4_sibling_skill_for_review() -> None:
    assert sibling_skill_for_query("review the PR for me") == "/review"
    assert sibling_skill_for_query("can you review this pull request?") == "/review"


def test_e4_sibling_skill_for_investigate() -> None:
    assert sibling_skill_for_query("fix the bug in submit()") == "/investigate"
    assert sibling_skill_for_query("debug why the test fails") == "/investigate"


def test_e4_sibling_skill_none_for_plain_query() -> None:
    assert sibling_skill_for_query("rank paths for query") is None


def test_e4_decision_surfaces_sibling_skill() -> None:
    decision = _decide("please review the PR for me")
    assert decision.sibling_skill == "/review"
    assert any("/review" in line for line in decision.rationale)
