from __future__ import annotations

from pathlib import Path
import sys


SCRIPT_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from token_reduce_adaptive import (
    Availability,
    BehaviorProfile,
    RoutingPolicy,
    decide,
    load_behavior_profile,
)


def _availability(**overrides: bool) -> Availability:
    base = {
        "paths": True,
        "snippet": True,
        "structural": True,
        "context_mode": True,
        "code_review_graph": True,
    }
    base.update(overrides)
    return Availability(**base)


def _behavior(*, helper_calls: int = 50, repeated: float = 0.2, rapid: float = 0.1) -> BehaviorProfile:
    return BehaviorProfile(
        helper_calls=helper_calls,
        repeated_ratio=repeated,
        rapid_repeat_ratio=rapid,
    )


def _policy(
    *,
    behavior_days: int = 3,
    snippet_threshold: float = 0.35,
    enable_structural: bool = True,
    enable_context_mode: bool = True,
    enable_code_review_graph: bool = True,
) -> RoutingPolicy:
    return RoutingPolicy(
        behavior_days=behavior_days,
        rapid_repeat_snippet_threshold=snippet_threshold,
        enable_structural=enable_structural,
        enable_context_mode_recommendations=enable_context_mode,
        enable_code_review_graph_recommendations=enable_code_review_graph,
    )


def test_symbol_query_promotes_structural_symbol() -> None:
    decision = decide(
        "prompt_requires_helper",
        behavior=_behavior(),
        availability=_availability(),
        policy=_policy(),
        root=Path("."),
        repo_file_count=800,
    )
    assert decision.tier == "structural_symbol"
    assert decision.command[-2:] == ["find-symbol", "prompt_requires_helper"]


def test_impact_symbol_promotes_structural_impact() -> None:
    decision = decide(
        "impact prompt_requires_helper",
        behavior=_behavior(),
        availability=_availability(),
        policy=_policy(),
        root=Path("."),
        repo_file_count=800,
    )
    assert decision.tier == "structural_impact"
    assert decision.command[-2:] == ["change-impact", "prompt_requires_helper"]


def test_rapid_repeat_promotes_snippet_for_non_symbol() -> None:
    decision = decide(
        "why hook enforcement blocks grep",
        behavior=_behavior(rapid=0.6),
        availability=_availability(structural=False),
        policy=_policy(enable_structural=False),
        root=Path("."),
        repo_file_count=800,
    )
    assert decision.tier == "core_snippet"
    assert decision.command[0].endswith("token-reduce-snippet.sh")


def test_output_heavy_recommends_context_mode() -> None:
    decision = decide(
        "playwright logs and stacktrace",
        behavior=_behavior(),
        availability=_availability(context_mode=True, structural=False),
        policy=_policy(enable_structural=False, enable_context_mode=True),
        root=Path("."),
        repo_file_count=800,
    )
    assert decision.context_mode_recommended is True


def test_structural_unavailable_demotes_to_paths() -> None:
    decision = decide(
        "prompt_requires_helper",
        behavior=_behavior(),
        availability=_availability(structural=False),
        policy=_policy(enable_structural=False),
        root=Path("."),
        repo_file_count=800,
    )
    assert decision.tier == "core_paths"
    assert decision.command[0].endswith("token-reduce-paths.sh")


def test_load_behavior_profile_days_zero_returns_empty_profile() -> None:
    profile = load_behavior_profile(Path("."), days=0)
    assert profile.helper_calls == 0
    assert profile.repeated_ratio == 0.0
    assert profile.rapid_repeat_ratio == 0.0
