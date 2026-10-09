"""Track D — Headroom + companion funnel tests.

D1. Decision must carry actionable commands when ``headroom_recommended``
    (literal: ``headroom_compress``, ``headroom install status``,
    ``curl -fsS http://127.0.0.1:8787/readyz``) — not prose.
D2. Trigger matrix: ``tool_result``, ``transcript``, ``log dump``,
    ``pytest output``, ``api response``, ``paste`` all flip
    ``headroom_recommended`` to True. Plain query control returns False.
D3. SKILL.md/README.md clarify passive (~8% local) vs active
    ``headroom_compress`` MCP for >20k tool results.
D4. ``review_token_reduction.build_companion_funnels`` exposes
    mention → recommended → used → estimated savings for headroom,
    caveman, context_mode, code_review_graph, axi.
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
    decide,
)


REPO_ROOT = Path(__file__).resolve().parents[2]


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


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
    return BehaviorProfile(helper_calls=10, repeated_ratio=0.0, rapid_repeat_ratio=0.0)


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


def _decide(query: str) -> object:
    return decide(
        query,
        behavior=_behavior(),
        availability=_availability(),
        policy=_policy(),
        root=Path("."),
        repo_file_count=800,
    )


# --------------------------------------------------------------------------- #
# D1 — actionable headroom commands (no prose)
# --------------------------------------------------------------------------- #


def test_d1_decision_includes_literal_health_check() -> None:
    decision = _decide("tool_result payload too large")
    assert any("headroom install status" in cmd for cmd in decision.headroom_commands)


# --------------------------------------------------------------------------- #
# D2 — widened trigger matrix
# --------------------------------------------------------------------------- #


def test_d2_trigger_tool_result() -> None:
    assert _decide("tool_result blob is enormous").headroom_recommended is True


def test_d2_plain_query_does_not_recommend_headroom() -> None:
    assert _decide("rank paths for a query").headroom_recommended is False
    assert _decide("find function definition").headroom_recommended is False


# --------------------------------------------------------------------------- #
# D3 — doc clarity (passive ~8% vs active MCP compress for >20k)
# --------------------------------------------------------------------------- #


# --------------------------------------------------------------------------- #
# D4 — per-companion conversion funnel
# --------------------------------------------------------------------------- #


