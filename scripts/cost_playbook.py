#!/usr/bin/env python3
"""Databricks-style AI coding cost playbook scorecard for token-reduce."""
from __future__ import annotations

import argparse
import importlib.util
import json
import shutil
import sys
from pathlib import Path
from typing import Any

from caliper_summary import CaliperUnavailable, fetch_summary
from measure_token_reduction import measure
from token_reduce_config import load_config


PLAYBOOK_LEVERS: tuple[dict[str, str], ...] = (
    {
        "id": "efficiency_frontier",
        "name": "Efficiency-frontier model evaluation",
        "databricks": "Continuously evaluate cheaper/newer coding models for quality per dollar.",
    },
    {
        "id": "harness_flexibility",
        "name": "Harness and model flexibility",
        "databricks": "Avoid lock-in by keeping a meta-harness or easy harness switching path.",
    },
    {
        "id": "request_routing",
        "name": "Request-level model routing",
        "databricks": "Route individual inference requests to the cheapest capable model.",
    },
    {
        "id": "task_routing",
        "name": "Task/delegate routing",
        "databricks": "Route whole tasks or subtasks to cheaper capable workers.",
    },
    {
        "id": "visibility",
        "name": "Spend and usage visibility",
        "databricks": "Give developers near-real-time spend visibility and reduction tips.",
    },
    {
        "id": "tripwires",
        "name": "Tripwires, budgets, and downshift",
        "databricks": "Use progressive warnings/approvals/downshift before suspension.",
    },
    {
        "id": "token_overhead",
        "name": "Token overhead reduction",
        "databricks": "Reduce context bloat, tool verbosity, cache churn, and chatty harness behavior.",
    },
    {
        "id": "gateway_control_plane",
        "name": "AI Gateway control plane",
        "databricks": "Centralize model access, budgets, config enforcement, and trace logging.",
    },
)


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _status(status: str, evidence: str, gap: str, recommendation: str) -> dict[str, str]:
    return {
        "status": status,
        "evidence": evidence,
        "gap": gap,
        "recommendation": recommendation,
    }


def _caliper_cost(caliper_summary: dict[str, Any] | None) -> float:
    if not caliper_summary:
        return 0.0
    summary = caliper_summary.get("summary")
    if not isinstance(summary, dict):
        return 0.0
    return _float(summary.get("estimated_cost_usd"))


def _caliper_sessions(caliper_summary: dict[str, Any] | None) -> int:
    if not caliper_summary:
        return 0
    summary = caliper_summary.get("summary")
    if not isinstance(summary, dict):
        return 0
    return _int(summary.get("sessions"))


def _has_caliper(caliper_summary: dict[str, Any] | None) -> bool:
    return bool(caliper_summary and caliper_summary.get("summary"))


def _dependency_state(dependency_health: dict[str, Any] | None, name: str) -> str:
    if not isinstance(dependency_health, dict):
        return "unknown"
    for item in dependency_health.get("dependencies", []) or []:
        if isinstance(item, dict) and item.get("name") == name:
            return str(item.get("state", "unknown"))
    return "unknown"


def _tool_available(name: str) -> bool:
    return shutil.which(name) is not None


def build_playbook_scorecard(
    report: dict[str, Any],
    *,
    config: dict[str, Any] | None = None,
    caliper_summary: dict[str, Any] | None = None,
    dependency_health: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a coverage scorecard against the Databricks coding-cost playbook."""
    cfg = config or load_config()
    budgets = cfg.get("budgets", {}) if isinstance(cfg.get("budgets"), dict) else {}
    adoption = report.get("adoption", {}) if isinstance(report.get("adoption"), dict) else {}
    telemetry = report.get("telemetry", {}) if isinstance(report.get("telemetry"), dict) else {}
    compliance = report.get("compliance", {}) if isinstance(report.get("compliance"), dict) else {}
    routing = report.get("routing", {}) if isinstance(report.get("routing"), dict) else {}

    session_count = _int(report.get("session_count"))
    helper_pct = _float(
        adoption.get("helper_sessions_pct_observed_discovery", routing.get("helper_first_or_helper_any_pct", 0.0))
    )
    compliance_pct = _float(
        compliance.get("discovery_compliance_pct_observed", compliance.get("discovery_compliance_pct", 0.0))
    )
    telemetry_events = _int(telemetry.get("event_count"))
    has_caliper = _has_caliper(caliper_summary)
    estimated_cost = _caliper_cost(caliper_summary)
    caliper_sessions = _caliper_sessions(caliper_summary)
    avg_session_cost = estimated_cost / caliper_sessions if estimated_cost > 0 and caliper_sessions > 0 else 0.0

    delegate_enabled = any(
        isinstance(value, dict) and bool(value.get("enabled"))
        for value in (cfg.get("delegates", {}) or {}).values()
    )
    companions = cfg.get("companions", {}) if isinstance(cfg.get("companions"), dict) else {}
    headroom_enabled = bool((companions.get("headroom") or {}).get("enabled")) and _tool_available("headroom")

    rows: dict[str, dict[str, str]] = {}
    rows["efficiency_frontier"] = _status(
        "missing",
        "No end-to-end quality-per-dollar model benchmark is wired into token-reduce.",
        "Current benchmarks measure context/token output, not task success per dollar by model or harness.",
        "Add a cross-harness benchmark suite that runs representative coding tasks and records pass/fail, latency, tokens, and estimated cost.",
    )
    rows["harness_flexibility"] = _status(
        "partial",
        "Token-reduce supports Claude, Codex, MCP, and delegate wrappers.",
        "There is no unified meta-harness UX or central model menu.",
        "Keep the helper workflow host-neutral and add a small harness comparison report before attempting gateway-level control.",
    )
    rows["request_routing"] = _status(
        "missing",
        "Headroom can proxy/compress context, but it does not route model requests.",
        "No request-level cheapest-capable-model router or cache-aware model proxy exists here.",
        "Treat this as out-of-scope until there is an AI Gateway or provider-side routing surface to integrate.",
    )
    rows["task_routing"] = _status(
        "partial" if delegate_enabled else "missing",
        "Delegate router config is enabled." if delegate_enabled else "Delegate router config is not enabled.",
        "Routing is task/delegate guidance, not measured model quality/cost routing.",
        "Measure delegate conversion and add per-delegate cost/quality telemetry before expanding automation.",
    )
    rows["visibility"] = _status(
        "partial" if telemetry_events > 0 or has_caliper else "missing",
        (
            f"Runtime helper telemetry events: {telemetry_events}; "
            f"Caliper available: {str(has_caliper).lower()}."
        ),
        "Visibility is local and fragmented; Caliper is Claude-specific and may be unavailable.",
        "Build a compact dashboard/report that merges helper compliance, Caliper spend, companion health, and workspace audit state.",
    )
    rows["tripwires"] = _status(
        "partial" if budgets.get("enabled") else "missing",
        "Warning-only budget config is enabled." if budgets.get("enabled") else "No budget/tripwire config is enabled.",
        "There are no approval gates, automatic model downshift, or central suspension controls.",
        "Start with warning-only tripwires and concrete recommendations; avoid hard blocking until spend telemetry is reliable.",
    )
    rows["token_overhead"] = _status(
        "pass" if helper_pct >= 60.0 and compliance_pct >= 80.0 else "partial",
        f"Helper usage observed: {helper_pct:.1f}%; discovery compliance observed: {compliance_pct:.1f}%; Headroom available: {str(headroom_enabled).lower()}.",
        "Adoption still limits realized savings when helper usage/compliance are low.",
        "Keep enforcing helper-first discovery and convert output-heavy sessions into Headroom/context-mode usage.",
    )
    rows["gateway_control_plane"] = _status(
        "missing",
        "Local config and hooks exist, but no central gateway owns model access, budgets, and traces.",
        "No organization-wide control plane is provided by this skill.",
        "Document this boundary clearly; integrate with an AI Gateway if one becomes available.",
    )

    tripwires = build_budget_tripwires(
        config=cfg,
        caliper_summary=caliper_summary,
        report=report,
        dependency_health=dependency_health,
    )
    missing_optional = [
        name
        for name in ("context-mode", "code-review-graph", "gh-axi", "chrome-devtools-axi")
        if _dependency_state(dependency_health, name) in {"missing", "outdated"}
    ]
    return {
        "source": "databricks-ai-coding-cost-playbook",
        "source_url": "https://www.databricks.com/blog/managing-ai-coding-costs-scale",
        "statuses": rows,
        "summary": {
            "pass": sum(1 for row in rows.values() if row["status"] == "pass"),
            "partial": sum(1 for row in rows.values() if row["status"] == "partial"),
            "missing": sum(1 for row in rows.values() if row["status"] == "missing"),
            "session_count": session_count,
            "helper_usage_pct": round(helper_pct, 1),
            "discovery_compliance_pct": round(compliance_pct, 1),
            "telemetry_events": telemetry_events,
            "caliper_available": has_caliper,
            "estimated_cost_usd": round(estimated_cost, 6),
            "avg_session_cost_usd": round(avg_session_cost, 6),
            "optional_dependency_gaps": missing_optional,
        },
        "tripwires": tripwires,
    }


def build_budget_tripwires(
    *,
    config: dict[str, Any],
    caliper_summary: dict[str, Any] | None,
    report: dict[str, Any],
    dependency_health: dict[str, Any] | None,
) -> list[dict[str, str]]:
    budgets = config.get("budgets", {}) if isinstance(config.get("budgets"), dict) else {}
    if not budgets.get("enabled", False):
        return []

    estimated_cost = _caliper_cost(caliper_summary)
    sessions = max(1, _caliper_sessions(caliper_summary))
    avg_session_cost = estimated_cost / sessions if estimated_cost > 0 else 0.0
    repo_warning = _float(budgets.get("repo_warning_usd"))
    session_warning = _float(budgets.get("session_warning_usd"))
    daily_warning = _float(budgets.get("daily_warning_usd"))
    actions = budgets.get("actions")
    if not isinstance(actions, list) or not actions:
        actions = ["warn", "recommend_headroom", "recommend_delegate", "recommend_downshift"]
    action_text = ", ".join(str(action) for action in actions)

    tripwires: list[dict[str, str]] = []
    if estimated_cost > 0 and repo_warning > 0 and estimated_cost >= repo_warning:
        tripwires.append(
            {
                "level": "warning",
                "area": "repo_budget",
                "finding": f"Caliper estimated cost ${estimated_cost:.2f} crosses repo warning ${repo_warning:.2f}.",
                "action": f"Warning-only actions: {action_text}. Review expensive sessions before escalating.",
            }
        )
    if avg_session_cost > 0 and session_warning > 0 and avg_session_cost >= session_warning:
        tripwires.append(
            {
                "level": "warning",
                "area": "session_budget",
                "finding": f"Average Caliper session cost ${avg_session_cost:.2f} crosses session warning ${session_warning:.2f}.",
                "action": f"Warning-only actions: {action_text}. Downshift discovery/research work before synthesis.",
            }
        )
    if estimated_cost > 0 and daily_warning > 0 and estimated_cost >= daily_warning:
        tripwires.append(
            {
                "level": "warning",
                "area": "daily_budget",
                "finding": f"Caliper window cost ${estimated_cost:.2f} crosses daily warning ${daily_warning:.2f}.",
                "action": f"Warning-only actions: {action_text}. Split work and prefer cheap helpers/delegates.",
            }
        )

    if _dependency_state(dependency_health, "headroom") in {"missing", "outdated"}:
        tripwires.append(
            {
                "level": "advisory",
                "area": "headroom_readiness",
                "finding": "Budget actions include Headroom-style compression, but Headroom is not healthy in dependency checks.",
                "action": "Run deps-check-conditional and install/update Headroom before relying on compression tripwires.",
            }
        )
    helper_pct = _float(
        (report.get("adoption", {}) or {}).get(
            "helper_sessions_pct_observed_discovery",
            (report.get("routing", {}) or {}).get("helper_first_or_helper_any_pct", 0.0),
        )
    )
    if helper_pct < 60.0:
        tripwires.append(
            {
                "level": "advisory",
                "area": "helper_adoption",
                "finding": f"Helper usage is {helper_pct:.1f}%, so token-overhead controls are not reliably exercised.",
                "action": "Tighten first-move guidance and run workspace-audit before adding stronger spend gates.",
            }
        )
    return tripwires


def build_playbook_findings(scorecard: dict[str, Any]) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    statuses = scorecard.get("statuses", {})
    for lever_id in ("efficiency_frontier", "request_routing", "gateway_control_plane"):
        row = statuses.get(lever_id)
        if isinstance(row, dict) and row.get("status") == "missing":
            findings.append(
                {
                    "priority": "medium",
                    "area": f"playbook_{lever_id}",
                    "finding": f"Databricks playbook lever is missing: {PLAYBOOK_NAMES.get(lever_id, lever_id)}.",
                    "recommendation": str(row.get("recommendation", "")),
                }
            )
    for tripwire in scorecard.get("tripwires", []) or []:
        if not isinstance(tripwire, dict):
            continue
        priority = "medium" if tripwire.get("level") == "warning" else "low"
        findings.append(
            {
                "priority": priority,
                "area": f"budget_{tripwire.get('area', 'tripwire')}",
                "finding": str(tripwire.get("finding", "")),
                "recommendation": str(tripwire.get("action", "")),
            }
        )
    gaps = (scorecard.get("summary", {}) or {}).get("optional_dependency_gaps", [])
    if gaps:
        findings.append(
            {
                "priority": "medium",
                "area": "playbook_companion_readiness",
                "finding": f"Optional cost-control companions are missing or outdated: {', '.join(gaps)}.",
                "recommendation": "Run `token-reduce-manage.sh deps-update-conditional`, then rerun the cost playbook scorecard.",
            }
        )
    return findings


PLAYBOOK_NAMES = {item["id"]: item["name"] for item in PLAYBOOK_LEVERS}


def render_scorecard_markdown(scorecard: dict[str, Any]) -> str:
    summary = scorecard.get("summary", {})
    lines = [
        "# Databricks Cost Playbook Scorecard",
        "",
        f"- Source: {scorecard.get('source_url')}",
        f"- Coverage: pass={summary.get('pass', 0)} partial={summary.get('partial', 0)} missing={summary.get('missing', 0)}",
        f"- Helper usage / compliance: `{summary.get('helper_usage_pct', 0.0)}%` / `{summary.get('discovery_compliance_pct', 0.0)}%`",
        f"- Telemetry events: `{summary.get('telemetry_events', 0)}`",
        f"- Caliper available: `{summary.get('caliper_available', False)}`",
        f"- Estimated Caliper cost: `${_float(summary.get('estimated_cost_usd')):.4f}`",
        "",
        "| Lever | Status | Evidence | Gap | Recommendation |",
        "| --- | --- | --- | --- | --- |",
    ]
    statuses = scorecard.get("statuses", {})
    for lever in PLAYBOOK_LEVERS:
        row = statuses.get(lever["id"], {})
        lines.append(
            "| {name} | `{status}` | {evidence} | {gap} | {recommendation} |".format(
                name=lever["name"],
                status=row.get("status", "missing"),
                evidence=str(row.get("evidence", "")).replace("\n", " "),
                gap=str(row.get("gap", "")).replace("\n", " "),
                recommendation=str(row.get("recommendation", "")).replace("\n", " "),
            )
        )
    lines.extend(["", "## Warning-Only Tripwires", ""])
    tripwires = scorecard.get("tripwires", []) or []
    if not tripwires:
        lines.append("- No budget tripwires fired.")
    else:
        for item in tripwires:
            lines.append(f"- **{item.get('level', 'advisory').upper()} · {item.get('area', 'tripwire')}**: {item.get('finding', '')}")
            lines.append(f"  Action: {item.get('action', '')}")
    gaps = summary.get("optional_dependency_gaps") or []
    if gaps:
        lines.extend(["", "## Optional Dependency Gaps", ""])
        for gap in gaps:
            lines.append(f"- `{gap}`")
    return "\n".join(lines) + "\n"


def build_dependency_health(include_conditional: bool) -> dict[str, Any]:
    module_path = Path(__file__).with_name("token-reduce-dependency-health.py")
    spec = importlib.util.spec_from_file_location("token_reduce_dependency_health", module_path)
    if spec is None or spec.loader is None:
        return {"dependencies": [], "counts": {"unknown": 1}}
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

    dependencies = [
        module.dependency_status(dep)
        for dep in module.selected_dependencies(include_conditional=include_conditional)
    ]
    counts: dict[str, int] = {}
    for item in dependencies:
        state = str(item.get("state", "unknown"))
        counts[state] = counts.get(state, 0) + 1
    return {"dependencies": dependencies, "counts": counts}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scope", default="repo", choices=["repo", "global"])
    parser.add_argument("--repo-root", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--with-caliper", action="store_true")
    parser.add_argument("--caliper-url")
    parser.add_argument("--check-deps", action="store_true", help="Include conditional companion dependency freshness")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--output-json")
    parser.add_argument("--output-md")
    args = parser.parse_args()

    report = measure(args.scope, args.repo_root)
    caliper_summary = None
    caliper_error = None
    if args.with_caliper:
        try:
            caliper_summary = fetch_summary(args.caliper_url)
        except CaliperUnavailable as exc:
            caliper_error = str(exc)
    dep_health = build_dependency_health(include_conditional=True) if args.check_deps else None
    scorecard = build_playbook_scorecard(
        report,
        config=load_config(),
        caliper_summary=caliper_summary,
        dependency_health=dep_health,
    )
    payload = {
        "scorecard": scorecard,
        "caliper_error": caliper_error,
        "dependency_health": dep_health,
    }
    if args.output_json:
        Path(args.output_json).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    markdown = render_scorecard_markdown(scorecard)
    if args.output_md:
        Path(args.output_md).write_text(markdown, encoding="utf-8")
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(markdown, end="")
        if caliper_error:
            print(f"\nCaliper unavailable: {caliper_error}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
