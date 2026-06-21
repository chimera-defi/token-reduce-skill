"""Track A5 — telemetry event constant + aggregate_priors tests."""
from __future__ import annotations

import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from rank_paths import (  # noqa: E402
    EVENT_FILE_READ_AFTER_HELPER,
    aggregate_priors,
    click_through_score,
)


def test_event_constant_matches_brief_spec() -> None:
    assert EVENT_FILE_READ_AFTER_HELPER == "file_read_after_helper"


def test_aggregate_priors_counts_per_query_path_pairs() -> None:
    events = [
        {
            "event": "file_read_after_helper",
            "query": "measure script",
            "path": "scripts/measure_token_reduction.py",
        },
        {
            "event": "file_read_after_helper",
            "query": "measure script",
            "path": "scripts/measure_token_reduction.py",
        },
        {
            "event": "file_read_after_helper",
            "query": "measure script",
            "path": "scripts/other.py",
        },
        {
            "event": "helper_invocation",
            "query": "unrelated",
            "meta": {"path": "noise.py"},
        },
    ]
    priors = aggregate_priors(events)
    assert "measure script" in priors
    table = priors["measure script"]
    assert table["scripts/measure_token_reduction.py"] == 2.0
    assert table["scripts/other.py"] == 1.0
    assert "helper_invocation" not in priors
    assert "unrelated" not in priors


def test_aggregate_priors_normalizes_query_whitespace() -> None:
    events = [
        {
            "event": "file_read_after_helper",
            "query": "  Measure   Script  ",
            "path": "scripts/measure_token_reduction.py",
        },
    ]
    priors = aggregate_priors(events)
    assert "measure script" in priors


def test_aggregate_priors_meta_fallback_for_path() -> None:
    events = [
        {
            "event": "file_read_after_helper",
            "query": "rank paths",
            "meta": {"path": "scripts/rank_paths.py"},
        },
    ]
    priors = aggregate_priors(events)
    assert priors["rank paths"]["scripts/rank_paths.py"] == 1.0


def test_aggregate_priors_feeds_click_through_score() -> None:
    events = [
        {
            "event": "file_read_after_helper",
            "query": "rank paths",
            "path": "scripts/rank_paths.py",
        },
        {
            "event": "file_read_after_helper",
            "query": "rank paths",
            "path": "scripts/rank_paths.py",
        },
    ]
    priors = aggregate_priors(events)
    score = click_through_score("scripts/rank_paths.py", "rank paths", priors)
    assert score == 2.0


def test_aggregate_priors_skips_invalid_events() -> None:
    events = [
        "not a dict",
        {"event": "file_read_after_helper"},  # missing query and path
        {"event": "file_read_after_helper", "query": "x"},  # missing path
        {"event": "file_read_after_helper", "path": "y"},  # missing query
        None,
    ]
    priors = aggregate_priors([e for e in events if e is not None])
    assert priors == {}
