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


def test_d1_decision_exposes_headroom_commands_list() -> None:
    decision = _decide("review pytest output for failing trace")
    assert decision.headroom_recommended is True
    assert hasattr(decision, "headroom_commands")
    assert isinstance(decision.headroom_commands, list)


def test_d1_decision_includes_literal_health_check() -> None:
    decision = _decide("tool_result payload too large")
    assert any("headroom install status" in cmd for cmd in decision.headroom_commands)


def test_d1_decision_includes_literal_readyz_curl() -> None:
    decision = _decide("transcript dump grew massive")
    assert any(
        "curl -fsS http://127.0.0.1:8787/readyz" in cmd
        for cmd in decision.headroom_commands
    )


def test_d1_decision_includes_compress_action() -> None:
    decision = _decide("paste of huge api response")
    assert any("headroom_compress" in cmd for cmd in decision.headroom_commands)


def test_d1_empty_commands_when_headroom_not_recommended() -> None:
    decision = decide(
        "rank paths for a query",
        behavior=_behavior(),
        availability=_availability(headroom=False),
        policy=_policy(),
        root=Path("."),
        repo_file_count=800,
    )
    assert decision.headroom_recommended is False
    assert decision.headroom_commands == []


# --------------------------------------------------------------------------- #
# D2 — widened trigger matrix
# --------------------------------------------------------------------------- #


def test_d2_trigger_tool_result() -> None:
    assert _decide("tool_result blob is enormous").headroom_recommended is True


def test_d2_trigger_transcript() -> None:
    assert _decide("transcript history is bloated").headroom_recommended is True


def test_d2_trigger_log_dump() -> None:
    assert _decide("dump the log file here").headroom_recommended is True


def test_d2_trigger_pytest_output() -> None:
    assert _decide("collect pytest output from CI").headroom_recommended is True


def test_d2_trigger_api_response() -> None:
    assert _decide("inspect api response body").headroom_recommended is True


def test_d2_trigger_paste() -> None:
    assert _decide("paste the failing payload").headroom_recommended is True


def test_d2_plain_query_does_not_recommend_headroom() -> None:
    assert _decide("rank paths for a query").headroom_recommended is False
    assert _decide("find function definition").headroom_recommended is False


# --------------------------------------------------------------------------- #
# D3 — doc clarity (passive ~8% vs active MCP compress for >20k)
# --------------------------------------------------------------------------- #


def test_d3_skill_md_mentions_passive_vs_active() -> None:
    text = (REPO_ROOT / "SKILL.md").read_text()
    assert "headroom_compress" in text, "SKILL.md must reference headroom_compress MCP action"
    assert "20" in text, "SKILL.md must call out the >20k threshold"


def test_d3_readme_mentions_passive_vs_active() -> None:
    text = (REPO_ROOT / "README.md").read_text()
    assert "headroom_compress" in text, "README.md must reference headroom_compress MCP action"
    assert "20" in text, "README.md must call out the >20k threshold"


# --------------------------------------------------------------------------- #
# D4 — per-companion conversion funnel
# --------------------------------------------------------------------------- #


def _fake_report() -> dict:
    return {
        "adoption": {
            "caveman_mentions": 12,
            "caveman_command_sessions": 4,
            "caveman_command_pct": 33.3,
            "headroom_mentions": 9,
            "headroom_command_sessions": 3,
            "headroom_command_pct": 33.3,
            "axi_tool_sessions": 5,
            "axi_tool_sessions_pct": 25.0,
            "gh_axi_sessions": 3,
            "chrome_devtools_axi_sessions": 2,
            "session_count": 20,
        },
        "telemetry": {
            "companion_recommendations": {
                "headroom_recommended_events": 7,
                "context_mode_recommended_events": 4,
                "code_review_graph_recommended_events": 2,
            },
        },
    }


def test_d4_build_companion_funnels_returns_all_five() -> None:
    from review_token_reduction import build_companion_funnels

    funnels = build_companion_funnels(_fake_report())
    names = {f["companion"] for f in funnels}
    assert names == {"headroom", "caveman", "context_mode", "code_review_graph", "axi"}


def test_d4_funnel_shape_includes_funnel_stages() -> None:
    from review_token_reduction import build_companion_funnels

    funnels = build_companion_funnels(_fake_report())
    for funnel in funnels:
        for key in ("companion", "mentions", "recommended", "used", "estimated_savings_pct"):
            assert key in funnel, f"{funnel['companion']} missing key {key}"


def test_d4_funnel_headroom_stage_values() -> None:
    from review_token_reduction import build_companion_funnels

    funnels = {f["companion"]: f for f in build_companion_funnels(_fake_report())}
    headroom = funnels["headroom"]
    assert headroom["mentions"] == 9
    assert headroom["recommended"] == 7
    assert headroom["used"] == 3


def test_d4_funnel_caveman_stage_values() -> None:
    from review_token_reduction import build_companion_funnels

    funnels = {f["companion"]: f for f in build_companion_funnels(_fake_report())}
    cave = funnels["caveman"]
    assert cave["mentions"] == 12
    assert cave["used"] == 4


def test_d4_review_markdown_contains_funnel_section() -> None:
    from review_token_reduction import format_companion_funnels_markdown

    md = format_companion_funnels_markdown(_fake_report())
    assert "Companion conversion funnel" in md
    for name in ("headroom", "caveman", "context_mode", "code_review_graph", "axi"):
        assert name in md
