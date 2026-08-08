from __future__ import annotations

from pathlib import Path
import sys


SCRIPT_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from cost_playbook import (
    build_budget_tripwires,
    build_playbook_findings,
    build_playbook_scorecard,
    render_scorecard_markdown,
)


def _report() -> dict:
    return {
        "session_count": 20,
        "adoption": {
            "helper_sessions_pct_observed_discovery": 72.0,
        },
        "routing": {
            "helper_first_or_helper_any_pct": 65.0,
        },
        "compliance": {
            "discovery_compliance_pct": 78.0,
            "discovery_compliance_pct_observed": 86.0,
        },
        "telemetry": {
            "event_count": 10,
        },
    }


def _config(*, budgets_enabled: bool = True) -> dict:
    return {
        "delegates": {
            "kimi": {"enabled": True},
        },
        "companions": {
            "headroom": {"enabled": True},
            "caliper": {"enabled": True},
        },
        "budgets": {
            "enabled": budgets_enabled,
            "daily_warning_usd": 20,
            "session_warning_usd": 5,
            "repo_warning_usd": 50,
            "actions": ["warn", "recommend_headroom"],
        },
    }


def _caliper_summary() -> dict:
    return {
        "summary": {
            "estimated_cost_usd": 80.0,
            "sessions": 10,
        }
    }


def test_scorecard_marks_token_overhead_pass_and_governance_gaps() -> None:
    scorecard = build_playbook_scorecard(
        _report(),
        config=_config(),
        caliper_summary=_caliper_summary(),
        dependency_health={"dependencies": []},
    )

    assert scorecard["statuses"]["token_overhead"]["status"] == "pass"
    assert scorecard["statuses"]["efficiency_frontier"]["status"] == "missing"
    assert scorecard["statuses"]["tripwires"]["status"] == "partial"
    assert scorecard["summary"]["estimated_cost_usd"] == 80.0
    assert scorecard["summary"]["avg_session_cost_usd"] == 8.0


def test_budget_tripwires_are_warning_only() -> None:
    tripwires = build_budget_tripwires(
        config=_config(),
        caliper_summary=_caliper_summary(),
        report=_report(),
        dependency_health={"dependencies": [{"name": "headroom", "state": "up_to_date"}]},
    )

    areas = {item["area"] for item in tripwires}
    assert "repo_budget" in areas
    assert "session_budget" in areas
    assert "daily_budget" in areas
    assert all("Warning-only" in item["action"] for item in tripwires if item["area"].endswith("_budget"))


def test_disabled_budgets_do_not_emit_spend_tripwires() -> None:
    tripwires = build_budget_tripwires(
        config=_config(budgets_enabled=False),
        caliper_summary=_caliper_summary(),
        report=_report(),
        dependency_health={"dependencies": []},
    )

    assert tripwires == []


def test_playbook_findings_include_missing_levers_and_dependency_gaps() -> None:
    scorecard = build_playbook_scorecard(
        _report(),
        config=_config(),
        caliper_summary=_caliper_summary(),
        dependency_health={
            "dependencies": [
                {"name": "context-mode", "state": "missing"},
                {"name": "gh-axi", "state": "outdated"},
            ]
        },
    )
    findings = build_playbook_findings(scorecard)
    areas = {finding["area"] for finding in findings}

    assert "playbook_efficiency_frontier" in areas
    assert "playbook_request_routing" in areas
    assert "playbook_companion_readiness" in areas


def test_render_scorecard_markdown_includes_tripwires() -> None:
    scorecard = build_playbook_scorecard(
        _report(),
        config=_config(),
        caliper_summary=_caliper_summary(),
        dependency_health={"dependencies": []},
    )
    markdown = render_scorecard_markdown(scorecard)

    assert "# Databricks Cost Playbook Scorecard" in markdown
    assert "Efficiency-frontier model evaluation" in markdown
    assert "Warning-Only Tripwires" in markdown
