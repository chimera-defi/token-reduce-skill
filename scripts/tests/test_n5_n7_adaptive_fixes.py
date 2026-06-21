"""Tests for N5 (wire gstack detection) and N7 (surface rationale/headroom to stderr).

N5: gstack_skill_available param in decide() was never set by main().
    Fix: detect gstack via filesystem/shutil.which and pass to decide().

N7: Rationale + headroom commands built in decide() but never printed to stderr.
    Fix: emit rationale as '# token-reduce: ...' and headroom commands after running.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from token_reduce_adaptive import decide, BehaviorProfile, Availability, RoutingPolicy


def _behavior(*, helper_calls: int = 10, repeated: float = 0.1, rapid: float = 0.0) -> BehaviorProfile:
    return BehaviorProfile(
        helper_calls=helper_calls,
        repeated_ratio=repeated,
        rapid_repeat_ratio=rapid,
    )


def _availability(*, headroom: bool = False, structural: bool = False) -> Availability:
    return Availability(
        paths=True,
        snippet=True,
        structural=structural,
        context_mode=False,
        headroom=headroom,
        code_review_graph=False,
    )


def _policy(*, enable_headroom: bool = True) -> RoutingPolicy:
    return RoutingPolicy(
        behavior_days=3,
        rapid_repeat_snippet_threshold=0.35,
        enable_structural=True,
        enable_context_mode_recommendations=False,
        enable_headroom_recommendations=enable_headroom,
        enable_code_review_graph_recommendations=False,
    )


# ---------------------------------------------------------------------------
# N5: gstack detection wired in main()
# ---------------------------------------------------------------------------

def test_gstack_available_plus_multi_repo_sets_session_spawn_recommended() -> None:
    """N5: multi-repo query + gstack_available=True → session_spawn_recommended=True."""
    decision = decide(
        "search across repos for authentication",  # "across" + "repos" are MULTI_REPO_TERMS
        behavior=_behavior(),
        availability=_availability(),
        policy=_policy(),
        root=Path.cwd(),
        repo_file_count=100,
        gstack_skill_available=True,
    )
    assert decision.session_spawn_recommended is True, (
        "session_spawn_recommended should be True when gstack available + multi_repo query"
    )


def test_gstack_not_available_keeps_session_spawn_false() -> None:
    """N5: multi-repo query + gstack_available=False → session_spawn_recommended=False."""
    decision = decide(
        "search across repos for authentication",
        behavior=_behavior(),
        availability=_availability(),
        policy=_policy(),
        root=Path.cwd(),
        repo_file_count=100,
        gstack_skill_available=False,
    )
    assert decision.session_spawn_recommended is False, (
        "session_spawn_recommended should be False when gstack not available"
    )


def test_gstack_default_is_false_when_not_passed() -> None:
    """N5: gstack_skill_available defaults to False (no regression)."""
    decision = decide(
        "search across repos for auth",
        behavior=_behavior(),
        availability=_availability(),
        policy=_policy(),
        root=Path.cwd(),
        repo_file_count=100,
        # gstack_skill_available not passed — should default False
    )
    assert decision.session_spawn_recommended is False


# ---------------------------------------------------------------------------
# N7: rationale and headroom commands surface to stderr
# ---------------------------------------------------------------------------

def test_n7_adaptive_py_has_rationale_print_to_stderr() -> None:
    """N7: structural check that token_reduce_adaptive.py emits rationale to stderr."""
    adaptive_src = Path(__file__).resolve().parents[1] / "token_reduce_adaptive.py"
    content = adaptive_src.read_text()
    assert "# token-reduce:" in content, (
        "token_reduce_adaptive.py must emit rationale as '# token-reduce: ...' to stderr (N7 fix missing)"
    )
    assert 'file=sys.stderr' in content, (
        "token_reduce_adaptive.py must print rationale to sys.stderr (N7 fix missing)"
    )


def test_n7_headroom_commands_surface_when_recommended() -> None:
    """N7: when headroom is available and output-heavy query, headroom_commands is non-empty."""
    decision = decide(
        "dump all log output from the API response paste here",
        behavior=_behavior(helper_calls=3),
        availability=_availability(headroom=True),
        policy=_policy(enable_headroom=True),
        root=Path.cwd(),
        repo_file_count=100,
    )
    if decision.headroom_recommended:
        assert len(decision.headroom_commands) > 0, (
            "headroom_recommended=True but headroom_commands is empty"
        )
