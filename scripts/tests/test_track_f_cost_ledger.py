"""Track F — Cost ledger (with vs without measurement).

F1. Per-session estimated tokens saved when helper ran vs estimated
    tokens spent on broad-scan sessions, using existing benchmark
    coefficients in references/benchmarks/.
F2. Per-source aggregate (claude/codex): avg context size, helper-used
    vs broad-scan, surfaced under a new "Context Impact" review section.
"""
from __future__ import annotations

import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from cost_ledger import (  # noqa: E402
    BENCHMARK_BROAD_TOKENS,
    aggregate_by_source,
    estimate_session_cost,
)


# --------------------------------------------------------------------------- #
# F1 — per-session estimates
# --------------------------------------------------------------------------- #




def test_f1_helper_session_estimates_savings() -> None:
    metrics = {
        "source": "claude",
        "qmd_search": True,
        "token_reduce_search": True,
        "scoped_rg": False,
        "targeted_reads": True,
        "structural_helper": False,
        "subagents": False,
        "broad_scan_violation": False,
        "headroom_command": False,
        "first_discovery_seen": True,
        "first_discovery_compliant": True,
    }
    cost = estimate_session_cost(metrics)
    assert cost["estimated_tokens_saved"] > 0
    assert cost["estimated_tokens_spent_on_broad"] == 0
    assert cost["session_kind"] == "helper"


def test_f1_broad_session_estimates_overspend() -> None:
    metrics = {
        "source": "claude",
        "qmd_search": False,
        "token_reduce_search": False,
        "scoped_rg": False,
        "targeted_reads": False,
        "structural_helper": False,
        "subagents": False,
        "broad_scan_violation": True,
        "headroom_command": False,
        "first_discovery_seen": True,
        "first_discovery_compliant": False,
    }
    cost = estimate_session_cost(metrics)
    assert cost["estimated_tokens_saved"] == 0
    assert cost["estimated_tokens_spent_on_broad"] >= BENCHMARK_BROAD_TOKENS
    assert cost["session_kind"] == "broad"






# --------------------------------------------------------------------------- #
# F2 — per-source aggregate
# --------------------------------------------------------------------------- #


def _fake_metrics(*, source: str, kind: str) -> dict:
    base = {
        "source": source,
        "qmd_search": False,
        "token_reduce_search": False,
        "scoped_rg": False,
        "targeted_reads": False,
        "structural_helper": False,
        "subagents": False,
        "broad_scan_violation": False,
        "headroom_command": False,
        "first_discovery_seen": True,
        "first_discovery_compliant": False,
    }
    if kind == "helper":
        base["token_reduce_search"] = True
        base["targeted_reads"] = True
        base["first_discovery_compliant"] = True
    elif kind == "broad":
        base["broad_scan_violation"] = True
    elif kind == "mixed":
        base["token_reduce_search"] = True
        base["broad_scan_violation"] = True
        base["first_discovery_compliant"] = True
    return base


def test_f2_aggregate_by_source_groups_correctly() -> None:
    items = [
        _fake_metrics(source="claude", kind="helper"),
        _fake_metrics(source="claude", kind="helper"),
        _fake_metrics(source="claude", kind="broad"),
        _fake_metrics(source="codex", kind="helper"),
        _fake_metrics(source="codex", kind="broad"),
        _fake_metrics(source="codex", kind="broad"),
    ]
    agg = aggregate_by_source(items)
    assert set(agg.keys()) == {"claude", "codex"}
    assert agg["claude"]["helper_sessions"] == 2
    assert agg["claude"]["broad_sessions"] == 1
    assert agg["codex"]["helper_sessions"] == 1
    assert agg["codex"]["broad_sessions"] == 2




